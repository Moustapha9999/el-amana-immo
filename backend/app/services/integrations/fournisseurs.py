"""Fournisseurs d'API externes du Studio d'intégration API (Phase 4) : fiches, import OpenAPI, opérations.

Règles :
- aucun appel réseau : ni téléchargement, ni test de connectivité, ni résolution de référence distante ;
  les URL sont des métadonnées ;
- la validation d'un fournisseur atteste seulement que sa configuration a été examinée ;
- une version importée n'est jamais modifiée ; un nouvel import crée une version suivante après
  confirmation explicite de l'analyse (même fichier, même version courante, conflits acceptés) ;
- rien n'est supprimé : archivage et versions conservent l'historique ; l'historique des fiches est
  ``audit_logs`` (entité ``integration_fournisseur``).
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime

from fastapi import Request
from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import AuditLog, Departement, User
from app.models.integrations import IntegrationFournisseur, IntegrationFournisseurOperation, IntegrationFournisseurSpec
from app.services.audit_helpers import record_audit
from app.services.integrations import openapi_import as oa
from app.services.integrations.clients import _echapper_like, _entites, _noms, _personne, normaliser_nom
from app.services.integrations.exemples_externes import generer
from app.services.permission_service import user_has_permission_codes

P_VIEW = "core.admin.integrations.fournisseurs.view"
P_MANAGE = "core.admin.integrations.fournisseurs.manage"
P_VALIDATE = "core.admin.integrations.fournisseurs.validate"

AUCUN_APPEL = "Configuration enregistrée — aucun appel externe effectué."
AVERTISSEMENT = (
    "Les fournisseurs sont des configurations : aucune URL n'est contactée, aucune spécification n'est "
    "téléchargée, aucune opération n'est exécutée. « Validé » signifie seulement que la configuration a été "
    "examinée, pas que le fournisseur est fiable ni que ses API fonctionnent."
)
AVERTISSEMENT_IMPORT = (
    "Analyse locale du fichier fourni : aucune référence distante chargée, aucun serveur contacté. "
    "Rien n'est enregistré avant confirmation."
)

MODIFIABLES = frozenset({"brouillon", "a_valider"})
# (ancien, nouveau) → permission exigée.
TRANSITIONS: dict[tuple[str, str], str] = {
    ("brouillon", "a_valider"): P_MANAGE,
    ("a_valider", "brouillon"): P_MANAGE,
    ("a_valider", "valide"): P_VALIDATE,
    ("valide", "a_valider"): P_MANAGE,
    ("valide", "suspendu"): P_VALIDATE,
    ("suspendu", "a_valider"): P_MANAGE,
}
MOTIF_OBLIGATOIRE = frozenset({"suspendu"})
_ALPHABET_CODE = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_MECANISMES_MANUELS: dict[str, dict] = {
    "api_key_header": {"type": "apiKey", "emplacement": "header"},
    "api_key_query": {"type": "apiKey", "emplacement": "query"},
    "http_basic": {"type": "http", "schema_http": "basic"},
    "http_bearer": {"type": "http", "schema_http": "bearer"},
    "oauth2_client_credentials": {"type": "oauth2", "flux": [{"flux": "clientCredentials", "scopes": []}]},
    "oauth2_autre": {"type": "oauth2", "flux": []},
    "mtls": {"type": "mutualTLS"},
    "autre": {"type": "autre"},
    "non_precise": {"type": "non_precise"},
}
LIBELLES_ACTIONS = {
    "integration_fournisseur_create": "Création de la fiche",
    "integration_fournisseur_update": "Modification de la fiche",
    "integration_fournisseur_statut": "Changement de statut",
    "integration_fournisseur_archive": "Archivage",
    "integration_fournisseur_spec_analyse": "Analyse d'une spécification (sans enregistrement)",
    "integration_fournisseur_spec_import": "Import d'une version de spécification",
    "integration_fournisseur_operation_create": "Opération manuelle créée",
    "integration_fournisseur_operation_update": "Opération manuelle modifiée",
    "integration_fournisseur_operation_archive": "Opération manuelle archivée",
    "integration_fournisseur_operation_delete": "Opération manuelle supprimée",
}


def _erreur(message: str, code: str, status: int) -> AppError:
    return AppError(message, status, code=code)


def _maintenant() -> datetime:
    return datetime.now(UTC)


def _nouveau_code() -> str:
    return "EXT-" + "".join(secrets.choice(_ALPHABET_CODE) for _ in range(8))


def _cle(methode: str, chemin: str) -> str:
    return f"{methode} {chemin}"


async def _audit(db: AsyncSession, actor: User, action: str, f: IntegrationFournisseur, request: Request | None,
                 before: dict | None = None, after: dict | None = None) -> None:
    await record_audit(db, user=actor, action=action, entity="integration_fournisseur", entity_id=str(f.id),
                       request=request, before=before, after=after, module_code="core")


# ------------------------------------------------------------------------------ lecture fiches


def _spec_courante_sq():
    s = IntegrationFournisseurSpec
    return (
        select(s.id).where(s.fournisseur_id == IntegrationFournisseur.id)
        .order_by(s.numero.desc()).limit(1).correlate(IntegrationFournisseur).scalar_subquery()
    )


def _filtre_courantes(spec_courante):
    o = IntegrationFournisseurOperation
    manuelles = and_(o.origine == "manuelle", o.statut == "active")
    if spec_courante is None:
        return manuelles
    return or_(manuelles, and_(o.origine == "openapi", o.spec_id == spec_courante))


def _colonnes_compteurs():
    s, o = IntegrationFournisseurSpec, IntegrationFournisseurOperation
    version = (
        select(func.max(s.numero)).where(s.fournisseur_id == IntegrationFournisseur.id)
        .correlate(IntegrationFournisseur).scalar_subquery()
    )
    nb = (
        select(func.count()).select_from(o)
        .where(o.fournisseur_id == IntegrationFournisseur.id, _filtre_courantes(_spec_courante_sq()))
        .correlate(IntegrationFournisseur).scalar_subquery()
    )
    return version, nb


def _resume(f: IntegrationFournisseur, version: int | None, nb: int, noms: dict, entites: dict) -> dict:
    return {
        "id": f.id,
        "code": f.code,
        "nom": f.nom,
        "description": f.description,
        "entite": entites.get(f.org_entite_id) if f.org_entite_id else None,
        "environnement": f.environnement,
        "statut": f.statut,
        "url_base": f.url_base,
        "version_courante": version,
        "nb_operations": int(nb or 0),
        "created_at": f.created_at,
        "updated_at": f.updated_at,
        "cree_par": _personne(noms, f.created_by_id),
        "modifie_par": _personne(noms, f.updated_by_id),
    }


async def lister_fournisseurs(db: AsyncSession, *, q: str | None, statut: str | None, environnement: str | None,
                              inclure_archives: bool, tri: str, ordre: str, page: int, size: int) -> dict:
    f = IntegrationFournisseur
    version, nb = _colonnes_compteurs()
    base: Select = select(f, version, nb)
    filtres = []
    if q and q.strip():
        motif = f"%{_echapper_like(q.strip())}%"
        filtres.append(or_(f.nom.ilike(motif, escape="\\"), f.code.ilike(motif, escape="\\"),
                           f.description.ilike(motif, escape="\\"), f.url_base.ilike(motif, escape="\\")))
    if statut:
        filtres.append(f.statut == statut)
    elif not inclure_archives:
        filtres.append(f.statut != "archive")
    if environnement:
        filtres.append(f.environnement == environnement)
    if filtres:
        base = base.where(and_(*filtres))
    total = await db.scalar(select(func.count()).select_from(base.order_by(None).subquery()))
    colonne = {"nom": f.nom, "code": f.code, "statut": f.statut, "environnement": f.environnement,
               "created_at": f.created_at}.get(tri, f.updated_at)
    colonne = colonne.asc() if ordre == "asc" else colonne.desc()
    rows = (await db.execute(base.order_by(colonne, f.id).offset((page - 1) * size).limit(size))).all()
    noms = await _noms(db, {x.created_by_id for x, *_ in rows} | {x.updated_by_id for x, *_ in rows})
    entites = await _entites(db, {x.org_entite_id for x, *_ in rows})
    return {
        "items": [_resume(x, v, n, noms, entites) for x, v, n in rows],
        "total": int(total or 0),
        "page": page,
        "size": size,
        "avertissement": AVERTISSEMENT,
    }


async def _fournisseur(db: AsyncSession, fid: uuid.UUID, *, verrou: bool = False) -> IntegrationFournisseur:
    q = select(IntegrationFournisseur).where(IntegrationFournisseur.id == fid)
    if verrou:
        q = q.with_for_update()
    f = await db.scalar(q)
    if f is None:
        raise _erreur("Fournisseur introuvable", "FOURNISSEUR_INTROUVABLE", 404)
    return f


async def _spec_courante(db: AsyncSession, fid: uuid.UUID) -> IntegrationFournisseurSpec | None:
    s = IntegrationFournisseurSpec
    return await db.scalar(select(s).where(s.fournisseur_id == fid).order_by(s.numero.desc()).limit(1))


async def _nb_courantes(db: AsyncSession, fid: uuid.UUID, spec_id: uuid.UUID | None) -> int:
    o = IntegrationFournisseurOperation
    return int(await db.scalar(
        select(func.count()).where(o.fournisseur_id == fid, _filtre_courantes(spec_id))
    ) or 0)


def _transitions(statut: str) -> list[str]:
    return sorted(nouveau for (ancien, nouveau) in TRANSITIONS if ancien == statut)


async def fiche_fournisseur(db: AsyncSession, fid: uuid.UUID) -> dict:
    f = await _fournisseur(db, fid)
    courante = await _spec_courante(db, f.id)
    nb = await _nb_courantes(db, f.id, courante.id if courante else None)
    noms = await _noms(db, {f.created_by_id, f.updated_by_id, f.archived_by_id, f.valide_par_id})
    entites = await _entites(db, {f.org_entite_id})
    return {
        **_resume(f, courante.numero if courante else None, nb, noms, entites),
        "responsable_interne": f.responsable_interne,
        "contact_technique": f.contact_technique,
        "documentation": f.documentation,
        "notes": f.notes,
        "motif_statut": f.motif_statut,
        "revision": f.revision,
        "valide_par": _personne(noms, f.valide_par_id),
        "valide_le": f.valide_le,
        "archived_at": f.archived_at,
        "archive_par": _personne(noms, f.archived_by_id),
        "motif_archivage": f.motif_archivage,
        "modifiable": f.statut in MODIFIABLES,
        "transitions": [] if f.statut == "archive" else _transitions(f.statut),
        "avertissement": AVERTISSEMENT,
    }


# ------------------------------------------------------------------------------ écriture fiches

_CHAMPS_AUDIT = ("code", "nom", "description", "org_entite_id", "responsable_interne", "contact_technique",
                 "environnement", "url_base", "documentation", "statut", "notes", "revision")


def _etat(f: IntegrationFournisseur) -> dict:
    return {k: (str(v) if isinstance(v, uuid.UUID) else v) for k in _CHAMPS_AUDIT if (v := getattr(f, k)) is not None}


def _verifier_url(url: str | None, environnement: str) -> None:
    if url and environnement == "TEST" and not url.startswith("https://"):
        raise _erreur("En TEST, l'URL de base déclarée doit être en https", "URL_HTTPS_REQUISE", 422)


async def _verifier_entite(db: AsyncSession, entite_id: uuid.UUID) -> None:
    e = await db.get(Departement, entite_id)
    if e is None or e.deleted_at is not None or not e.is_active:
        raise _erreur("Service responsable introuvable ou désactivé dans l'organigramme", "ENTITE_INVALIDE", 422)


async def _verifier_doublon(db: AsyncSession, nom_normalise: str, environnement: str,
                            exclure: uuid.UUID | None = None) -> None:
    f = IntegrationFournisseur
    q = select(f.id).where(f.nom_normalise == nom_normalise, f.environnement == environnement, f.statut != "archive")
    if exclure:
        q = q.where(f.id != exclure)
    if await db.scalar(q.limit(1)):
        raise _erreur("Un fournisseur de même nom existe déjà dans cet environnement", "FOURNISSEUR_DOUBLON", 409)


async def _flush(db: AsyncSession, message: str, code: str) -> None:
    try:
        await db.flush()
    except IntegrityError as exc:
        raise _erreur(message, code, 409) from exc


def _exiger_modifiable(f: IntegrationFournisseur) -> None:
    if f.statut == "archive":
        raise _erreur("Fournisseur archivé : modification impossible", "FOURNISSEUR_ARCHIVE", 409)
    if f.statut not in MODIFIABLES:
        raise _erreur(
            "Fournisseur validé ou suspendu : le repasser « à valider » avant toute modification",
            "FOURNISSEUR_VERROUILLE",
            409,
        )


def _exiger_revision(f: IntegrationFournisseur, revision: int) -> None:
    if revision != f.revision:
        raise _erreur("La fiche a été modifiée entre-temps : recharger avant d'enregistrer", "CONFLIT_REVISION", 409)


def _toucher(f: IntegrationFournisseur, actor: User) -> None:
    f.revision += 1
    f.updated_by_id = actor.id
    f.updated_at = _maintenant()


async def creer_fournisseur(db: AsyncSession, actor: User, data: dict, request: Request | None) -> dict:
    nom_normalise = normaliser_nom(data["nom"])
    _verifier_url(data.get("url_base"), data["environnement"])
    await _verifier_doublon(db, nom_normalise, data["environnement"])
    if data.get("org_entite_id"):
        await _verifier_entite(db, data["org_entite_id"])
    code = None
    for _ in range(5):
        candidat = _nouveau_code()
        if not await db.scalar(select(IntegrationFournisseur.id).where(IntegrationFournisseur.code == candidat)):
            code = candidat
            break
    if code is None:
        raise _erreur("Identifiant interne indisponible, réessayer", "CODE_INDISPONIBLE", 503)
    f = IntegrationFournisseur(
        code=code, nom=data["nom"], nom_normalise=nom_normalise, statut="brouillon", revision=1,
        created_by_id=actor.id, updated_by_id=actor.id,
        **{k: data.get(k) for k in ("description", "org_entite_id", "responsable_interne", "contact_technique",
                                    "environnement", "url_base", "documentation", "notes")},
    )
    db.add(f)
    await _flush(db, "Un fournisseur de même nom existe déjà dans cet environnement", "FOURNISSEUR_DOUBLON")
    await _audit(db, actor, "integration_fournisseur_create", f, request, after=_etat(f))
    await db.flush()
    await db.refresh(f)
    return await fiche_fournisseur(db, f.id)


async def modifier_fournisseur(db: AsyncSession, actor: User, fid: uuid.UUID, data: dict, fournis: set[str],
                               request: Request | None) -> dict:
    f = await _fournisseur(db, fid, verrou=True)
    _exiger_modifiable(f)
    _exiger_revision(f, data["revision"])
    avant = _etat(f)
    for obligatoire in ("nom", "environnement"):
        if obligatoire in fournis and not data.get(obligatoire):
            raise _erreur(f"Champ obligatoire : {obligatoire}", "CHAMP_OBLIGATOIRE", 422)
    nom = data["nom"] if "nom" in fournis else f.nom
    environnement = data["environnement"] if "environnement" in fournis else f.environnement
    url = data.get("url_base") if "url_base" in fournis else f.url_base
    entite_id = data.get("org_entite_id") if "org_entite_id" in fournis else f.org_entite_id
    _verifier_url(url, environnement)
    if environnement != f.environnement:
        o, s = IntegrationFournisseurOperation, IntegrationFournisseurSpec
        nb_ops = await db.scalar(select(func.count()).select_from(o).where(o.fournisseur_id == f.id))
        nb_specs = await db.scalar(select(func.count()).select_from(s).where(s.fournisseur_id == f.id))
        if nb_ops or nb_specs:
            raise _erreur("Environnement verrouillé : des opérations ou spécifications existent déjà",
                          "ENVIRONNEMENT_VERROUILLE", 409)
    if entite_id and entite_id != f.org_entite_id:
        await _verifier_entite(db, entite_id)
    if normaliser_nom(nom) != f.nom_normalise or environnement != f.environnement:
        await _verifier_doublon(db, normaliser_nom(nom), environnement, exclure=f.id)

    f.nom, f.nom_normalise, f.environnement, f.url_base, f.org_entite_id = (
        nom, normaliser_nom(nom), environnement, url, entite_id)
    for champ in ("description", "responsable_interne", "contact_technique", "documentation", "notes"):
        if champ in fournis:
            setattr(f, champ, data.get(champ))
    apres = _etat(f)
    changes = sorted(k for k in set(avant) | set(apres) if avant.get(k) != apres.get(k))
    if changes:
        _toucher(f, actor)
        await _flush(db, "Un fournisseur de même nom existe déjà dans cet environnement", "FOURNISSEUR_DOUBLON")
        await _audit(db, actor, "integration_fournisseur_update", f, request,
                     before={k: avant.get(k) for k in changes}, after={k: apres.get(k) for k in changes})
        await db.flush()
    return await fiche_fournisseur(db, f.id)


async def changer_statut(db: AsyncSession, actor: User, have: set[str], fid: uuid.UUID, revision: int, statut: str,
                         motif: str | None, request: Request | None) -> dict:
    f = await _fournisseur(db, fid, verrou=True)
    if f.statut == "archive":
        raise _erreur("Fournisseur archivé", "FOURNISSEUR_ARCHIVE", 409)
    permission = TRANSITIONS.get((f.statut, statut))
    if permission is None:
        raise _erreur(f"Transition interdite : {f.statut} → {statut}", "TRANSITION_INTERDITE", 409)
    if not user_has_permission_codes(have, permission):
        raise _erreur("Permission insuffisante pour cette transition", "PERMISSION_INSUFFISANTE", 403)
    _exiger_revision(f, revision)
    if statut in MOTIF_OBLIGATOIRE and not motif:
        raise _erreur("Motif obligatoire", "MOTIF_OBLIGATOIRE", 422)
    if statut == "valide":
        courante = await _spec_courante(db, f.id)
        manquants = [lib for lib, ok in (
            ("URL de base déclarée", f.url_base),
            ("service responsable", f.org_entite_id),
            ("au moins une opération", await _nb_courantes(db, f.id, courante.id if courante else None)),
        ) if not ok]
        if manquants:
            raise _erreur("Validation impossible : " + ", ".join(manquants) + ".", "VALIDATION_INCOMPLETE", 422)
        f.valide_par_id, f.valide_le = actor.id, _maintenant()
    ancien = f.statut
    f.statut = statut
    f.motif_statut = motif
    _toucher(f, actor)
    await db.flush()
    await _audit(db, actor, "integration_fournisseur_statut", f, request,
                 before={"statut": ancien}, after={"statut": statut, "motif": motif})
    await db.flush()
    return await fiche_fournisseur(db, f.id)


async def archiver_fournisseur(db: AsyncSession, actor: User, fid: uuid.UUID, revision: int, motif: str,
                               request: Request | None) -> dict:
    f = await _fournisseur(db, fid, verrou=True)
    if f.statut == "archive":
        raise _erreur("Fournisseur déjà archivé", "FOURNISSEUR_ARCHIVE", 409)
    _exiger_revision(f, revision)
    ancien = f.statut
    f.statut, f.motif_archivage = "archive", motif
    f.archived_at, f.archived_by_id = _maintenant(), actor.id
    _toucher(f, actor)
    await db.flush()
    await _audit(db, actor, "integration_fournisseur_archive", f, request,
                 before={"statut": ancien}, after={"statut": "archive", "motif": motif})
    await db.flush()
    return await fiche_fournisseur(db, f.id)


async def historique(db: AsyncSession, fid: uuid.UUID, *, page: int, size: int) -> dict:
    await _fournisseur(db, fid)
    a = AuditLog
    filtre = and_(a.entity == "integration_fournisseur", a.entity_id == str(fid))
    total = await db.scalar(select(func.count()).select_from(a).where(filtre))
    rows = (await db.scalars(
        select(a).where(filtre).order_by(a.created_at.desc(), a.id).offset((page - 1) * size).limit(size)
    )).all()
    noms = await _noms(db, {r.user_id for r in rows})
    return {
        "items": [
            {
                "id": r.id,
                "action": r.action,
                "libelle": LIBELLES_ACTIONS.get(r.action, r.action),
                "acteur": _personne(noms, r.user_id),
                "details": {"avant": r.before_data or {}, "apres": r.after_data or {}},
                "request_id": r.request_id,
                "created_at": r.created_at,
            }
            for r in rows
        ],
        "total": int(total or 0),
        "page": page,
        "size": size,
    }


# ------------------------------------------------------------------------------ import OpenAPI


async def _cles_courantes(db: AsyncSession, fid: uuid.UUID, spec_id: uuid.UUID | None) -> tuple[dict, set]:
    o = IntegrationFournisseurOperation
    importees: dict[str, str] = {}
    if spec_id:
        for m, c, e in (await db.execute(select(o.methode, o.chemin, o.empreinte).where(o.spec_id == spec_id))).all():
            importees[_cle(m, c)] = e
    manuelles = {
        _cle(m, c) for m, c in (await db.execute(
            select(o.methode, o.chemin).where(o.fournisseur_id == fid, o.origine == "manuelle", o.statut == "active")
        )).all()
    }
    return importees, manuelles


def _messages(liste: list[oa.Message]) -> list[dict]:
    return [m.dict() for m in liste]


async def _comparer(db: AsyncSession, f: IntegrationFournisseur, analyse: oa.Analyse) -> dict:
    courante = await _spec_courante(db, f.id)
    importees, manuelles = await _cles_courantes(db, f.id, courante.id if courante else None)
    nouvelles = {_cle(op["methode"], op["chemin"]): op["empreinte"] for op in analyse.operations}
    deja = await db.scalar(select(IntegrationFournisseurSpec.numero).where(
        IntegrationFournisseurSpec.fournisseur_id == f.id, IntegrationFournisseurSpec.empreinte == analyse.empreinte))
    diff = None
    if courante is not None:
        diff = {
            "ajoutees": sorted(set(nouvelles) - set(importees)),
            "supprimees": sorted(set(importees) - set(nouvelles)),
            "modifiees": sorted(k for k in set(nouvelles) & set(importees) if nouvelles[k] != importees[k]),
            "inchangees": sum(1 for k in set(nouvelles) & set(importees) if nouvelles[k] == importees[k]),
        }
    return {
        "version_courante": courante.numero if courante else None,
        "deja_importee": deja,
        "diff": diff,
        "conflits": sorted(set(nouvelles) & manuelles),
    }


def _apercu(analyse: oa.Analyse) -> dict:
    return {
        "valide": analyse.valide,
        "nom_fichier": analyse.nom_fichier,
        "taille": analyse.taille,
        "empreinte": analyse.empreinte,
        "format": analyse.format,
        "openapi_version": analyse.openapi_version,
        "titre": analyse.titre,
        "version_api": analyse.version_api,
        "serveurs": analyse.serveurs,
        "securite": analyse.securite,
        "nb_operations": len(analyse.operations),
        "operations": [
            {"cle": _cle(op["methode"], op["chemin"]), "methode": op["methode"], "chemin": op["chemin"],
             "operation_id": op["operation_id"], "nom": op["nom"], "deprecie": op["deprecie"]}
            for op in analyse.operations[:500]
        ],
        "erreurs": _messages(analyse.erreurs),
        "avertissements": _messages(analyse.avertissements),
        "avertissement": AVERTISSEMENT_IMPORT,
    }


async def analyser_spec(db: AsyncSession, actor: User, fid: uuid.UUID, contenu: bytes, nom_fichier: str | None,
                        request: Request | None) -> dict:
    f = await _fournisseur(db, fid)
    if f.statut == "archive":
        raise _erreur("Fournisseur archivé", "FOURNISSEUR_ARCHIVE", 409)
    analyse = oa.analyser(contenu, nom_fichier)
    resultat = _apercu(analyse)
    if analyse.valide:
        resultat.update(await _comparer(db, f, analyse))
    await _audit(db, actor, "integration_fournisseur_spec_analyse", f, request, after={
        "nom_fichier": analyse.nom_fichier, "empreinte": analyse.empreinte, "taille": analyse.taille,
        "valide": analyse.valide, "nb_erreurs": len(analyse.erreurs), "nb_operations": len(analyse.operations),
    })
    await db.flush()
    return resultat


async def importer_spec(db: AsyncSession, actor: User, fid: uuid.UUID, contenu: bytes, nom_fichier: str | None,
                        empreinte_attendue: str, version_attendue: int | None, accepter_conflits: bool,
                        request: Request | None) -> dict:
    f = await _fournisseur(db, fid, verrou=True)
    _exiger_modifiable(f)
    analyse = oa.analyser(contenu, nom_fichier)
    if analyse.empreinte != empreinte_attendue:
        raise _erreur("Le fichier diffère de celui analysé : relancer l'analyse", "ANALYSE_PERIMEE", 409)
    if not analyse.valide:
        premier = analyse.erreurs[0].message if analyse.erreurs else "Spécification invalide."
        raise _erreur(f"Spécification invalide : {premier}", "SPEC_INVALIDE", 422)
    comparaison = await _comparer(db, f, analyse)
    if comparaison["deja_importee"]:
        raise _erreur(f"Fichier déjà importé (version {comparaison['deja_importee']})", "SPEC_DEJA_IMPORTEE", 409)
    if comparaison["version_courante"] != version_attendue:
        raise _erreur("Une autre version a été importée entre-temps : relancer l'analyse", "CONFLIT_VERSION", 409)
    if comparaison["conflits"] and not accepter_conflits:
        raise _erreur("Des opérations manuelles portent la même méthode et le même chemin : confirmer les conflits",
                      "CONFLITS_NON_ACCEPTES", 409)
    numero = (comparaison["version_courante"] or 0) + 1
    spec = IntegrationFournisseurSpec(
        fournisseur_id=f.id, numero=numero, format=analyse.format, nom_fichier=analyse.nom_fichier,
        taille=analyse.taille, empreinte=analyse.empreinte, openapi_version=analyse.openapi_version,
        titre=analyse.titre, version_api=analyse.version_api, document=analyse.document, resume=analyse.resume(),
        avertissements=_messages(analyse.avertissements), importe_par_id=actor.id,
    )
    db.add(spec)
    await _flush(db, "Version déjà importée", "SPEC_DEJA_IMPORTEE")
    for op in analyse.operations:
        db.add(IntegrationFournisseurOperation(
            fournisseur_id=f.id, spec_id=spec.id, origine="openapi", statut="active", created_by_id=actor.id,
            updated_by_id=actor.id,
            **{k: op[k] for k in ("methode", "chemin", "operation_id", "nom", "description", "tags", "deprecie",
                                  "parametres", "entetes", "corps", "reponses", "authentification", "empreinte")},
        ))
    _toucher(f, actor)
    await _flush(db, "Opération en double dans la spécification", "OPERATION_DOUBLON")
    diff = comparaison["diff"] or {}
    await _audit(db, actor, "integration_fournisseur_spec_import", f, request, after={
        "numero": numero, "nom_fichier": analyse.nom_fichier, "empreinte": analyse.empreinte,
        "nb_operations": len(analyse.operations), "ajoutees": len(diff.get("ajoutees", [])),
        "supprimees": len(diff.get("supprimees", [])), "modifiees": len(diff.get("modifiees", [])),
        "conflits_acceptes": len(comparaison["conflits"]),
    })
    await db.flush()
    return await spec_detail(db, f.id, spec.id)


def _spec_resume(s: IntegrationFournisseurSpec, courante_id: uuid.UUID | None, noms: dict) -> dict:
    return {
        "id": s.id, "numero": s.numero, "courante": s.id == courante_id, "format": s.format,
        "nom_fichier": s.nom_fichier, "taille": s.taille, "empreinte": s.empreinte,
        "openapi_version": s.openapi_version, "titre": s.titre, "version_api": s.version_api,
        "nb_operations": int((s.resume or {}).get("nb_operations") or 0),
        "nb_avertissements": len(s.avertissements or []),
        "importe_par": _personne(noms, s.importe_par_id), "created_at": s.created_at,
    }


async def lister_specs(db: AsyncSession, fid: uuid.UUID) -> dict:
    await _fournisseur(db, fid)
    s = IntegrationFournisseurSpec
    rows = (await db.scalars(select(s).where(s.fournisseur_id == fid).order_by(s.numero.desc()))).all()
    noms = await _noms(db, {r.importe_par_id for r in rows})
    courante = rows[0].id if rows else None
    return {"items": [_spec_resume(r, courante, noms) for r in rows], "avertissement": AVERTISSEMENT}


async def spec_detail(db: AsyncSession, fid: uuid.UUID, spec_id: uuid.UUID) -> dict:
    await _fournisseur(db, fid)
    s = IntegrationFournisseurSpec
    spec = await db.scalar(select(s).where(s.id == spec_id, s.fournisseur_id == fid))
    if spec is None:
        raise _erreur("Version introuvable", "SPEC_INTROUVABLE", 404)
    courante = await _spec_courante(db, fid)
    noms = await _noms(db, {spec.importe_par_id})
    resume = spec.resume or {}
    return {
        **_spec_resume(spec, courante.id if courante else None, noms),
        "serveurs": resume.get("serveurs") or [],
        "securite": resume.get("securite") or [],
        "description": resume.get("description"),
        "avertissements": spec.avertissements or [],
        "avertissement": AUCUN_APPEL,
    }


# ------------------------------------------------------------------------------ opérations


def _op_resume(o: IntegrationFournisseurOperation, numeros: dict, conflits: set[str]) -> dict:
    return {
        "id": o.id, "origine": o.origine, "statut": o.statut, "methode": o.methode, "chemin": o.chemin,
        "operation_id": o.operation_id, "nom": o.nom, "tags": o.tags or [], "deprecie": o.deprecie,
        "spec_numero": numeros.get(o.spec_id), "conflit": _cle(o.methode, o.chemin) in conflits,
        "updated_at": o.updated_at,
    }


async def _conflits(db: AsyncSession, fid: uuid.UUID, spec_id: uuid.UUID | None) -> set[str]:
    importees, manuelles = await _cles_courantes(db, fid, spec_id)
    return set(importees) & manuelles


async def lister_operations(db: AsyncSession, fid: uuid.UUID, *, q: str | None, methode: str | None,
                            origine: str | None, page: int, size: int) -> dict:
    await _fournisseur(db, fid)
    courante = await _spec_courante(db, fid)
    o = IntegrationFournisseurOperation
    filtres = [o.fournisseur_id == fid, _filtre_courantes(courante.id if courante else None)]
    if q and q.strip():
        motif = f"%{_echapper_like(q.strip())}%"
        filtres.append(or_(o.chemin.ilike(motif, escape="\\"), o.nom.ilike(motif, escape="\\"),
                           o.operation_id.ilike(motif, escape="\\")))
    if methode:
        filtres.append(o.methode == methode)
    if origine:
        filtres.append(o.origine == origine)
    total = await db.scalar(select(func.count()).select_from(o).where(*filtres))
    rows = (await db.scalars(select(o).where(*filtres).order_by(o.chemin, o.methode, o.origine)
                             .offset((page - 1) * size).limit(size))).all()
    numeros = {courante.id: courante.numero} if courante else {}
    conflits = await _conflits(db, fid, courante.id if courante else None)
    return {
        "items": [_op_resume(r, numeros, conflits) for r in rows],
        "total": int(total or 0), "page": page, "size": size,
        "version_courante": courante.numero if courante else None,
        "avertissement": AVERTISSEMENT,
    }


async def _operation(db: AsyncSession, fid: uuid.UUID, op_id: uuid.UUID, *, verrou: bool = False):
    o = IntegrationFournisseurOperation
    q = select(o).where(o.id == op_id, o.fournisseur_id == fid)
    if verrou:
        q = q.with_for_update()
    op = await db.scalar(q)
    if op is None:
        raise _erreur("Opération introuvable", "OPERATION_INTROUVABLE", 404)
    return op


async def operation_detail(db: AsyncSession, fid: uuid.UUID, op_id: uuid.UUID) -> dict:
    f = await _fournisseur(db, fid)
    op = await _operation(db, fid, op_id)
    courante = await _spec_courante(db, fid)
    spec = await db.get(IntegrationFournisseurSpec, op.spec_id) if op.spec_id else None
    mecanismes = ((spec.resume or {}).get("securite") if spec else (op.configuration or {}).get("securite")) or []
    numeros = {spec.id: spec.numero} if spec else {}
    conflits = await _conflits(db, fid, courante.id if courante else None)
    noms = await _noms(db, {op.created_by_id, op.updated_by_id})
    donnees = {"methode": op.methode, "chemin": op.chemin, "parametres": op.parametres, "corps": op.corps,
               "authentification": op.authentification}
    exemples = generer(donnees, mecanismes, op.origine, f.url_base)
    if op.origine == "openapi":
        courante_txt = "version courante" if courante and spec and courante.id == spec.id else "version antérieure"
        source = f"Spécification importée v{spec.numero} ({courante_txt}) — déclarée par le fournisseur, non vérifiée."
    else:
        source = "Configuration manuelle — non validée par le fournisseur, non vérifiée."
    configuration = dict(op.configuration or {})
    return {
        **_op_resume(op, numeros, conflits),
        "description": op.description, "parametres": op.parametres or [], "entetes": op.entetes or [],
        "corps": op.corps, "reponses": op.reponses or [], "authentification": op.authentification or [],
        "mecanismes": mecanismes, "configuration": configuration or None, "notes": op.notes,
        "revision": op.revision, "source": source, **exemples,
        "cree_par": _personne(noms, op.created_by_id), "modifie_par": _personne(noms, op.updated_by_id),
        "created_at": op.created_at,
    }


def _normaliser_manuelle(data: dict) -> dict:
    mecanisme = data["mecanisme_auth"]
    securite = []
    if mecanisme != "aucun":
        schema = {"nom": "manuel", "description": None, **_MECANISMES_MANUELS[mecanisme]}
        if mecanisme.startswith("api_key"):
            schema["nom_parametre"] = data.get("nom_cle_api")
        securite.append(schema)
    deux_cents = next((c for c in data["codes_reponse"] if 200 <= c < 300), None)
    reponse_resume = oa.resumer_schema(data.get("reponse_schema"))
    normalise = {
        "methode": data["methode"],
        "chemin": data["chemin"],
        "operation_id": None,
        "nom": data["nom"],
        "description": data.get("description"),
        "tags": [],
        "deprecie": False,
        "parametres": [
            {"nom": p["nom"], "emplacement": p["emplacement"], "requis": p["requis"] or p["emplacement"] == "path",
             "description": p.get("description"), "schema": {"type": p["type"]}, "deprecie": False}
            for p in data.get("parametres") or []
        ],
        "entetes": [{"nom": e["nom"], "requis": e["requis"], "description": e.get("description")}
                    for e in data.get("entetes") or []],
        "corps": {"requis": True, "description": None, "contenus": [
            {"type_contenu": "application/json", "schema": oa.resumer_schema(data["corps_schema"])}]}
        if data.get("corps_schema") is not None else None,
        "reponses": [
            {"code": str(c), "description": None,
             "contenus": [{"type_contenu": "application/json", "schema": reponse_resume}]
             if c == deux_cents and reponse_resume else []}
            for c in data["codes_reponse"]
        ],
        "authentification": [{"mecanismes": ["manuel"]}] if securite else [],
        "notes": data.get("notes"),
    }
    normalise["empreinte"] = oa.empreinte_operation(normalise)
    normalise["configuration"] = {**{k: v for k, v in data.items() if k != "revision"}, "securite": securite}
    return normalise


async def _verifier_cle_manuelle(db: AsyncSession, fid: uuid.UUID, methode: str, chemin: str,
                                 exclure: uuid.UUID | None = None) -> None:
    o = IntegrationFournisseurOperation
    q = select(o.id).where(o.fournisseur_id == fid, o.origine == "manuelle", o.statut == "active",
                           o.methode == methode, o.chemin == chemin)
    if exclure:
        q = q.where(o.id != exclure)
    if await db.scalar(q.limit(1)):
        raise _erreur("Une opération manuelle identique (méthode et chemin) existe déjà", "OPERATION_DOUBLON", 409)
    courante = await _spec_courante(db, fid)
    if courante and await db.scalar(select(o.id).where(o.spec_id == courante.id, o.methode == methode,
                                                       o.chemin == chemin).limit(1)):
        raise _erreur("Opération déjà décrite par la spécification importée", "OPERATION_DEJA_IMPORTEE", 409)


async def creer_operation(db: AsyncSession, actor: User, fid: uuid.UUID, data: dict, request: Request | None) -> dict:
    f = await _fournisseur(db, fid, verrou=True)
    _exiger_modifiable(f)
    await _verifier_cle_manuelle(db, f.id, data["methode"], data["chemin"])
    n = _normaliser_manuelle(data)
    op = IntegrationFournisseurOperation(fournisseur_id=f.id, spec_id=None, origine="manuelle", statut="active",
                                         revision=1, created_by_id=actor.id, updated_by_id=actor.id, **n)
    db.add(op)
    _toucher(f, actor)
    await _flush(db, "Une opération manuelle identique existe déjà", "OPERATION_DOUBLON")
    await _audit(db, actor, "integration_fournisseur_operation_create", f, request,
                 after={"operation": str(op.id), "methode": op.methode, "chemin": op.chemin})
    await db.flush()
    return await operation_detail(db, f.id, op.id)


async def modifier_operation(db: AsyncSession, actor: User, fid: uuid.UUID, op_id: uuid.UUID, data: dict,
                             request: Request | None) -> dict:
    f = await _fournisseur(db, fid, verrou=True)
    _exiger_modifiable(f)
    op = await _operation(db, fid, op_id, verrou=True)
    if op.origine != "manuelle":
        raise _erreur("Opération issue d'une spécification importée : non modifiable", "OPERATION_IMPORTEE", 409)
    if op.statut != "active":
        raise _erreur("Opération archivée", "OPERATION_ARCHIVEE", 409)
    if data["revision"] != op.revision:
        raise _erreur("L'opération a été modifiée entre-temps : recharger", "CONFLIT_REVISION", 409)
    if (data["methode"], data["chemin"]) != (op.methode, op.chemin):
        await _verifier_cle_manuelle(db, f.id, data["methode"], data["chemin"], exclure=op.id)
    n = _normaliser_manuelle(data)
    avant = {"methode": op.methode, "chemin": op.chemin, "empreinte": op.empreinte}
    if n["empreinte"] == op.empreinte and n["configuration"] == op.configuration:
        return await operation_detail(db, f.id, op.id)
    for cle, valeur in n.items():
        setattr(op, cle, valeur)
    op.revision += 1
    op.updated_by_id = actor.id
    op.updated_at = _maintenant()
    _toucher(f, actor)
    await _flush(db, "Une opération manuelle identique existe déjà", "OPERATION_DOUBLON")
    await _audit(db, actor, "integration_fournisseur_operation_update", f, request, before=avant,
                 after={"operation": str(op.id), "methode": op.methode, "chemin": op.chemin, "empreinte": op.empreinte})
    await db.flush()
    return await operation_detail(db, f.id, op.id)


async def archiver_operation(db: AsyncSession, actor: User, fid: uuid.UUID, op_id: uuid.UUID, revision: int,
                             request: Request | None) -> dict:
    f = await _fournisseur(db, fid, verrou=True)
    _exiger_modifiable(f)
    op = await _operation(db, fid, op_id, verrou=True)
    if op.origine != "manuelle":
        raise _erreur("Opération issue d'une spécification importée : non archivable", "OPERATION_IMPORTEE", 409)
    if op.statut != "active":
        raise _erreur("Opération déjà archivée", "OPERATION_ARCHIVEE", 409)
    if revision != op.revision:
        raise _erreur("L'opération a été modifiée entre-temps : recharger", "CONFLIT_REVISION", 409)
    op.statut = "archivee"
    op.revision += 1
    op.updated_by_id = actor.id
    op.updated_at = _maintenant()
    _toucher(f, actor)
    await db.flush()
    await _audit(db, actor, "integration_fournisseur_operation_archive", f, request,
                 after={"operation": str(op.id), "methode": op.methode, "chemin": op.chemin})
    await db.flush()
    return await operation_detail(db, f.id, op.id)
