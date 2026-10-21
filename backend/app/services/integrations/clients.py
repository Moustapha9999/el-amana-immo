"""Applications clientes du Studio d'intégration API (Phase 2) : fiches, demandes de droits, décisions.

Règles :
- une fiche est une configuration ; elle ne permet à aucune application de s'authentifier ;
- une opération n'est demandable que si le catalogue la documente sans réserve (voir ``admissibilite``) ;
- une demande ne devient « approuvée » que par une décision explicite d'un détenteur de
  ``core.admin.integrations.grants.approve`` ; aucune permission utilisateur ni aucun rôle n'est modifié ;
- rien n'est supprimé : archivage, retrait et révocation conservent l'historique.
"""

from __future__ import annotations

import re
import secrets
import unicodedata
import uuid
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import Departement, User
from app.models.integrations import IntegrationClient, IntegrationClientGrant, IntegrationClientGrantEvent
from app.services.audit_helpers import record_audit
from app.services.integrations import catalogue as cat
from app.services.integrations.exemples import generer
from app.services.permission_service import user_has_permission_codes
from app.services.plateforme_access_service import PlateformeAccessService

P_CLIENTS_VIEW = "core.admin.integrations.clients.view"
P_CLIENTS_MANAGE = "core.admin.integrations.clients.manage"
P_GRANTS_VIEW = "core.admin.integrations.grants.view"
P_GRANTS_MANAGE = "core.admin.integrations.grants.manage"
P_GRANTS_APPROVE = "core.admin.integrations.grants.approve"
P_EXPORT = "core.admin.integrations.export"

AVERTISSEMENT = (
    "Une fiche d'application cliente est une configuration : elle ne permet à aucune application de "
    "s'authentifier ni d'appeler l'API BEA DIGITAL. Une opération « approuvée » n'ouvre aucun accès tant "
    "que l'authentification machine-à-machine n'existe pas (non implémentée)."
)
AVERTISSEMENT_GRANTS = (
    "Les opérations sélectionnées sont des demandes. Seule une décision explicite d'un approbateur les "
    "passe à « approuvée », et cette approbation reste une configuration sans effet sur les accès : "
    "aucun rôle ni aucune permission utilisateur n'est modifié."
)

TRANSITIONS_CLIENT: dict[str, frozenset[str]] = {
    "brouillon": frozenset({"en_preparation"}),
    "en_preparation": frozenset({"brouillon", "active"}),
    "active": frozenset({"suspendue"}),
    "suspendue": frozenset({"active", "en_preparation"}),
    "archivee": frozenset(),
}
# (ancien, nouveau) → permission exigée pour la décision.
TRANSITIONS_GRANT: dict[tuple[str, str], str] = {
    ("demandee", "en_attente"): P_GRANTS_MANAGE,
    ("demandee", "retiree"): P_GRANTS_MANAGE,
    ("en_attente", "retiree"): P_GRANTS_MANAGE,
    ("en_attente", "approuvee"): P_GRANTS_APPROVE,
    ("en_attente", "refusee"): P_GRANTS_APPROVE,
    ("approuvee", "revoquee"): P_GRANTS_APPROVE,
    ("refusee", "demandee"): P_GRANTS_MANAGE,
    ("revoquee", "demandee"): P_GRANTS_MANAGE,
    ("retiree", "demandee"): P_GRANTS_MANAGE,
}
MOTIF_OBLIGATOIRE = frozenset({"refusee", "revoquee"})
GRANTS_OUVERTS = frozenset({"demandee", "en_attente", "approuvee"})
CLIENT_DEMANDES_OUVERTES = frozenset({"brouillon", "en_preparation", "active"})
CLIENT_APPROBATION = frozenset({"en_preparation", "active"})

_AUTH_ADMISSIBLES = frozenset({cat.AUTH_LOGIN1, cat.AUTH_LOGIN2, cat.AUTH_SESSION})
_CHEMIN_SENSIBLE = re.compile(
    r"export|download|t[eé]l[eé]charg|import|upload|purge|reset|restor|backup|sauvegard|password|mot-de-passe"
    r"|token|jeton|secret|mfa|totp|2fa|session|impersonat|bulk|masse",
    re.I,
)
_ALPHABET_CODE = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_TRIS = {"nom", "code", "statut", "environnement", "created_at", "updated_at", "nb_operations"}


def _erreur(message: str, code: str, status: int) -> AppError:
    return AppError(message, status, code=code)


def _maintenant() -> datetime:
    return datetime.now(UTC)


def normaliser_nom(nom: str) -> str:
    decompose = unicodedata.normalize("NFKD", nom)
    sans_accent = "".join(c for c in decompose if not unicodedata.combining(c))
    return " ".join(sans_accent.casefold().split())[:120]


def _nouveau_code() -> str:
    """Identifiant interne lisible de la fiche — public, non secret, distinct de tout identifiant d'authentification."""
    return "INT-" + "".join(secrets.choice(_ALPHABET_CODE) for _ in range(8))


# ------------------------------------------------------------------------------ admissibilité
async def etats_modules(db: AsyncSession, operations: list[cat.Operation]) -> dict[str, str]:
    access = PlateformeAccessService(db)
    etats: dict[str, str] = {}
    for code in sorted({op.module_code for op in operations if op.module_code}):
        module = await access.get_module(code)
        if module is None:
            etats[code] = "introuvable"
        elif not module.is_active:
            etats[code] = "desactive"
        else:
            etats[code] = module.statut or "inconnu"
    return etats


def admissibilite(op: cat.Operation | None, etats: dict[str, str]) -> tuple[bool, str | None]:
    """Une opération n'est demandable que si tout ce qui la concerne est établi par le catalogue."""
    if op is None:
        return False, "Opération absente du catalogue actuel."
    if op.disponibilite != cat.DISPO_DOCUMENTEE:
        detail = op.motifs[0] if op.motifs else "documentation incomplète."
        return False, f"Opération non documentée sans réserve ({op.disponibilite}) : {detail}"
    if op.authentification not in _AUTH_ADMISSIBLES:
        return False, "Authentification de l'opération non déterminée."
    if op.permission_statut != cat.PERM_IDENTIFIEE or not op.permissions:
        return False, "Permission de l'opération non identifiée avec certitude."
    if any(code not in cat.PERMISSIONS_CONNUES for code in op.permissions):
        return False, "Permission de l'opération absente du référentiel."
    if any(code.startswith("core.admin") or code.split(".")[-1] == "admin" for code in op.permissions):
        return False, "Opération d'administration : non ouverte aux applications clientes."
    if op.methode == "DELETE":
        return False, "Suppression : non ouverte aux applications clientes."
    if _CHEMIN_SENSIBLE.search(op.chemin) or _CHEMIN_SENSIBLE.search(op.nom):
        return False, "Opération sensible (export, import, fichier, sécurité, session ou traitement de masse)."
    if op.module_code:
        etat = etats.get(op.module_code, "introuvable")
        if etat != "actif":
            return False, f"Module « {op.module_code} » non actif ({etat})."
    return True, None


# ------------------------------------------------------------------------------ lecture
async def _noms(db: AsyncSession, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str | None]:
    propres = {i for i in ids if i}
    if not propres:
        return {}
    rows = (await db.execute(select(User.id, User.full_name, User.email).where(User.id.in_(propres)))).all()
    return {i: (nom or email) for i, nom, email in rows}


def _personne(noms: dict[uuid.UUID, str | None], uid: uuid.UUID | None) -> dict | None:
    if uid is None:
        return None
    return {"id": uid, "nom": noms.get(uid)}


async def _entites(db: AsyncSession, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, dict]:
    propres = {i for i in ids if i}
    if not propres:
        return {}
    rows = (await db.scalars(select(Departement).where(Departement.id.in_(propres)))).all()
    return {
        e.id: {"id": e.id, "code": e.code, "libelle": e.libelle, "actif": bool(e.is_active and e.deleted_at is None)}
        for e in rows
    }


def _compteurs_sq():
    g = IntegrationClientGrant
    return (
        select(
            g.client_id.label("client_id"),
            func.count().label("n"),
            func.count().filter(g.statut == "approuvee").label("a"),
        )
        .where(g.statut != "retiree")
        .group_by(g.client_id)
        .subquery()
    )


def _resume(c: IntegrationClient, n: int, a: int, noms: dict, entites: dict) -> dict:
    return {
        "id": c.id,
        "code": c.code,
        "nom": c.nom,
        "description": c.description,
        "entite": entites.get(c.org_entite_id) if c.org_entite_id else None,
        "environnement": c.environnement,
        "statut": c.statut,
        "nb_operations": int(n or 0),
        "nb_approuvees": int(a or 0),
        "created_at": c.created_at,
        "updated_at": c.updated_at,
        "cree_par": _personne(noms, c.created_by_id),
        "modifie_par": _personne(noms, c.updated_by_id),
    }


def _echapper_like(texte: str) -> str:
    return texte.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def lister_clients(
    db: AsyncSession,
    *,
    q: str | None,
    statut: str | None,
    environnement: str | None,
    inclure_archivees: bool,
    tri: str,
    ordre: str,
    page: int,
    size: int,
) -> dict:
    c = IntegrationClient
    sq = _compteurs_sq()
    n = func.coalesce(sq.c.n, 0)
    a = func.coalesce(sq.c.a, 0)
    base: Select = select(c, n, a).outerjoin(sq, sq.c.client_id == c.id)
    filtres = []
    if q and q.strip():
        motif = f"%{_echapper_like(q.strip())}%"
        filtres.append(or_(c.nom.ilike(motif, escape="\\"), c.code.ilike(motif, escape="\\"),
                           c.description.ilike(motif, escape="\\")))
    if statut:
        filtres.append(c.statut == statut)
    elif not inclure_archivees:
        filtres.append(c.statut != "archivee")
    if environnement:
        filtres.append(c.environnement == environnement)
    if filtres:
        base = base.where(and_(*filtres))
    total = await db.scalar(select(func.count()).select_from(base.order_by(None).subquery()))
    colonne = n if tri == "nb_operations" else getattr(c, tri if tri in _TRIS else "updated_at")
    colonne = colonne.asc() if ordre == "asc" else colonne.desc()
    rows = (await db.execute(base.order_by(colonne, c.id).offset((page - 1) * size).limit(size))).all()
    noms = await _noms(db, {x.created_by_id for x, *_ in rows} | {x.updated_by_id for x, *_ in rows})
    entites = await _entites(db, {x.org_entite_id for x, *_ in rows})
    return {
        "items": [_resume(x, nn, aa, noms, entites) for x, nn, aa in rows],
        "total": int(total or 0),
        "page": page,
        "size": size,
        "avertissement": AVERTISSEMENT,
    }


async def _client(db: AsyncSession, client_id: uuid.UUID, *, verrou: bool = False) -> IntegrationClient:
    q = select(IntegrationClient).where(IntegrationClient.id == client_id)
    if verrou:
        q = q.with_for_update()
    c = await db.scalar(q)
    if c is None:
        raise _erreur("Application cliente introuvable", "CLIENT_INTROUVABLE", 404)
    return c


async def fiche_client(db: AsyncSession, client_id: uuid.UUID) -> dict:
    c = await _client(db, client_id)
    sq = _compteurs_sq()
    n, a = (await db.execute(
        select(func.coalesce(sq.c.n, 0), func.coalesce(sq.c.a, 0)).select_from(sq).where(sq.c.client_id == c.id)
    )).first() or (0, 0)
    noms = await _noms(db, {c.created_by_id, c.updated_by_id, c.archived_by_id})
    entites = await _entites(db, {c.org_entite_id})
    return {
        **_resume(c, n, a, noms, entites),
        "contact_technique": c.contact_technique,
        "finalite": c.finalite,
        "notes": c.notes,
        "revision": c.revision,
        "archived_at": c.archived_at,
        "archive_par": _personne(noms, c.archived_by_id),
        "motif_archivage": c.motif_archivage,
        "transitions": sorted(TRANSITIONS_CLIENT.get(c.statut, ())),
        "avertissement": AVERTISSEMENT,
    }


# ------------------------------------------------------------------------------ écriture fiche
_CHAMPS_AUDIT = ("code", "nom", "description", "org_entite_id", "contact_technique", "environnement", "finalite",
                 "statut", "notes", "revision")


def _etat(c: IntegrationClient) -> dict:
    return {k: (str(v) if isinstance(v, uuid.UUID) else v) for k in _CHAMPS_AUDIT if (v := getattr(c, k)) is not None}


async def _verifier_entite(db: AsyncSession, entite_id: uuid.UUID) -> None:
    e = await db.get(Departement, entite_id)
    if e is None or e.deleted_at is not None or not e.is_active:
        raise _erreur("Service responsable introuvable ou désactivé dans l'organigramme", "ENTITE_INVALIDE", 422)


async def _verifier_doublon(db: AsyncSession, nom_normalise: str, environnement: str,
                            exclure: uuid.UUID | None = None) -> None:
    q = select(IntegrationClient.id).where(
        IntegrationClient.nom_normalise == nom_normalise,
        IntegrationClient.environnement == environnement,
        IntegrationClient.statut != "archivee",
    )
    if exclure:
        q = q.where(IntegrationClient.id != exclure)
    if await db.scalar(q.limit(1)):
        raise _erreur("Une application de même nom existe déjà dans cet environnement", "CLIENT_DOUBLON", 409)


async def _flush(db: AsyncSession) -> None:
    try:
        await db.flush()
    except IntegrityError as exc:
        raise _erreur("Une application de même nom ou identifiant existe déjà", "CLIENT_DOUBLON", 409) from exc


async def creer_client(db: AsyncSession, actor: User, data: dict, request: Request | None) -> dict:
    nom = data["nom"]
    nom_normalise = normaliser_nom(nom)
    await _verifier_doublon(db, nom_normalise, data["environnement"])
    if data.get("org_entite_id"):
        await _verifier_entite(db, data["org_entite_id"])
    code = None
    for _ in range(5):
        candidat = _nouveau_code()
        if not await db.scalar(select(IntegrationClient.id).where(IntegrationClient.code == candidat)):
            code = candidat
            break
    if code is None:
        raise _erreur("Identifiant interne indisponible, réessayer", "CODE_INDISPONIBLE", 503)
    c = IntegrationClient(
        code=code,
        nom=nom,
        nom_normalise=nom_normalise,
        description=data.get("description"),
        org_entite_id=data.get("org_entite_id"),
        contact_technique=data.get("contact_technique"),
        environnement=data["environnement"],
        finalite=data.get("finalite"),
        statut=data.get("statut") or "brouillon",
        notes=data.get("notes"),
        revision=1,
        created_by_id=actor.id,
        updated_by_id=actor.id,
    )
    db.add(c)
    await _flush(db)
    await record_audit(db, user=actor, action="integration_client_create", entity="integration_client",
                       entity_id=str(c.id), request=request, after=_etat(c), module_code="core")
    await db.flush()
    await db.refresh(c)
    return await fiche_client(db, c.id)


async def modifier_client(db: AsyncSession, actor: User, client_id: uuid.UUID, data: dict, fournis: set[str],
                          request: Request | None) -> dict:
    c = await _client(db, client_id, verrou=True)
    if c.statut == "archivee":
        raise _erreur("Application archivée : modification impossible", "CLIENT_ARCHIVE", 409)
    if data["revision"] != c.revision:
        raise _erreur("La fiche a été modifiée entre-temps : recharger avant d'enregistrer", "CONFLIT_REVISION", 409)
    avant = _etat(c)

    # Tout est vérifié avant de toucher l'objet : une requête de contrôle déclencherait l'autoflush.
    if "nom" in fournis and not data.get("nom"):
        raise _erreur("Le nom est obligatoire", "NOM_OBLIGATOIRE", 422)
    if "environnement" in fournis and not data.get("environnement"):
        raise _erreur("L'environnement est obligatoire", "ENVIRONNEMENT_OBLIGATOIRE", 422)
    nom = data["nom"] if "nom" in fournis else c.nom
    environnement = data["environnement"] if "environnement" in fournis else c.environnement
    entite_id = data.get("org_entite_id") if "org_entite_id" in fournis else c.org_entite_id
    statut = data["statut"] if "statut" in fournis and data.get("statut") else c.statut
    finalite = data.get("finalite") if "finalite" in fournis else c.finalite

    if environnement != c.environnement:
        engages = await db.scalar(select(func.count()).where(
            IntegrationClientGrant.client_id == c.id,
            IntegrationClientGrant.statut.in_(("en_attente", "approuvee", "refusee", "revoquee")),
        ))
        if engages:
            raise _erreur(
                "Environnement verrouillé : des opérations ont déjà été soumises ou décidées pour cette application",
                "ENVIRONNEMENT_VERROUILLE",
                409,
            )
    if entite_id and entite_id != c.org_entite_id:
        await _verifier_entite(db, entite_id)
    if statut != c.statut and statut not in TRANSITIONS_CLIENT.get(c.statut, frozenset()):
        raise _erreur(f"Transition interdite : {c.statut} → {statut}", "TRANSITION_INTERDITE", 409)
    if statut == "active":
        manquants = [lib for lib, v in (("finalité", finalite), ("service responsable", entite_id)) if not v]
        if manquants:
            raise _erreur("Activation impossible : renseigner " + " et ".join(manquants) + ".",
                          "ACTIVATION_INCOMPLETE", 422)
    if normaliser_nom(nom) != c.nom_normalise or environnement != c.environnement:
        await _verifier_doublon(db, normaliser_nom(nom), environnement, exclure=c.id)

    c.nom = nom
    c.nom_normalise = normaliser_nom(nom)
    c.environnement = environnement
    c.org_entite_id = entite_id
    c.statut = statut
    for champ in ("description", "contact_technique", "finalite", "notes"):
        if champ in fournis:
            setattr(c, champ, data.get(champ))

    apres = _etat(c)
    changes = {k for k in set(avant) | set(apres) if avant.get(k) != apres.get(k)}
    if changes:
        c.revision += 1
        c.updated_by_id = actor.id
        c.updated_at = _maintenant()
        await _flush(db)
        await record_audit(
            db, user=actor, action="integration_client_update", entity="integration_client", entity_id=str(c.id),
            request=request, before={k: avant.get(k) for k in sorted(changes)},
            after={k: apres.get(k) for k in sorted(changes)}, module_code="core",
        )
        await db.flush()
        await db.refresh(c)
    return await fiche_client(db, c.id)


async def archiver_client(db: AsyncSession, actor: User, client_id: uuid.UUID, revision: int, motif: str,
                          request: Request | None) -> dict:
    c = await _client(db, client_id, verrou=True)
    if c.statut == "archivee":
        raise _erreur("Application déjà archivée", "CLIENT_ARCHIVE", 409)
    if revision != c.revision:
        raise _erreur("La fiche a été modifiée entre-temps : recharger avant d'archiver", "CONFLIT_REVISION", 409)
    avant = _etat(c)
    grants = (await db.scalars(
        select(IntegrationClientGrant)
        .where(IntegrationClientGrant.client_id == c.id, IntegrationClientGrant.statut.in_(GRANTS_OUVERTS))
        .with_for_update()
    )).all()
    maintenant = _maintenant()
    for g in grants:
        nouveau = "revoquee" if g.statut == "approuvee" else "retiree"
        motif_grant = f"Archivage de l'application : {motif}"
        _evenement(db, g, g.statut, nouveau, motif_grant, actor)
        g.statut = nouveau
        g.motif = motif_grant
        if nouveau == "revoquee":
            g.decide_par_id = actor.id
            g.decide_le = maintenant
        g.updated_at = maintenant
    c.statut = "archivee"
    c.archived_at = maintenant
    c.archived_by_id = actor.id
    c.motif_archivage = motif
    c.revision += 1
    c.updated_by_id = actor.id
    c.updated_at = maintenant
    await _flush(db)
    await record_audit(
        db, user=actor, action="integration_client_archive", entity="integration_client", entity_id=str(c.id),
        request=request, before=avant, after={**_etat(c), "motif": motif, "grants_clos": len(grants)},
        module_code="core",
    )
    await db.flush()
    await db.refresh(c)
    return await fiche_client(db, c.id)


# ------------------------------------------------------------------------------ demandes de droits
def _evenement(db: AsyncSession, g: IntegrationClientGrant, ancien: str | None, nouveau: str, motif: str | None,
               actor: User) -> None:
    db.add(IntegrationClientGrantEvent(
        grant_id=g.id, client_id=g.client_id, operation_id=g.operation_id, ancien_statut=ancien,
        nouveau_statut=nouveau, motif=motif, acteur_id=actor.id,
    ))


def _instantane(g: IntegrationClientGrant, op: cat.Operation) -> None:
    g.methode = op.methode
    g.chemin = op.chemin
    g.permissions = list(op.permissions)
    g.exigence_permissions = cat.exigence_texte(op.exigences)


def _grant_dict(g: IntegrationClientGrant, op: cat.Operation | None, etats: dict, noms: dict) -> dict:
    ok, motif = admissibilite(op, etats)
    return {
        "id": g.id,
        "operation_id": g.operation_id,
        "methode": g.methode,
        "chemin": g.chemin,
        "module": op.module if op else None,
        "permissions": list(g.permissions or []),
        "exigence_permissions": g.exigence_permissions,
        "statut": g.statut,
        "justification": g.justification,
        "motif": g.motif,
        "demande_par": _personne(noms, g.demande_par_id),
        "decide_par": _personne(noms, g.decide_par_id),
        "decide_le": g.decide_le,
        "created_at": g.created_at,
        "updated_at": g.updated_at,
        "catalogue_present": op is not None,
        "admissible": ok,
        "motif_inadmissible": motif,
    }


async def lister_grants(db: AsyncSession, app: FastAPI, client_id: uuid.UUID, statut: str | None = None) -> dict:
    await _client(db, client_id)
    q = select(IntegrationClientGrant).where(IntegrationClientGrant.client_id == client_id)
    tous = (await db.scalars(q.order_by(IntegrationClientGrant.created_at, IntegrationClientGrant.operation_id))).all()
    grants = [g for g in tous if not statut or g.statut == statut]
    _ops, index = cat.operations_de(app)
    ops = {g.operation_id: index.get(g.operation_id) for g in grants}
    etats = await etats_modules(db, [o for o in ops.values() if o])
    noms = await _noms(db, {g.demande_par_id for g in grants} | {g.decide_par_id for g in grants})
    compteurs: dict[str, int] = {}
    for g in tous:
        compteurs[g.statut] = compteurs.get(g.statut, 0) + 1
    return {
        "items": [_grant_dict(g, ops[g.operation_id], etats, noms) for g in grants],
        "compteurs": compteurs,
        "avertissement": AVERTISSEMENT_GRANTS,
    }


async def demander_operations(db: AsyncSession, app: FastAPI, actor: User, client_id: uuid.UUID,
                              operation_ids: list[str], justification: str | None, request: Request | None) -> dict:
    c = await _client(db, client_id, verrou=True)
    if c.statut not in CLIENT_DEMANDES_OUVERTES:
        raise _erreur(f"Application {c.statut} : aucune nouvelle demande possible", "CLIENT_NON_MODIFIABLE", 409)
    _ops, index = cat.operations_de(app)
    ops = {op_id: index.get(op_id) for op_id in operation_ids}
    inconnues = [op_id for op_id, op in ops.items() if op is None]
    if inconnues:
        raise _erreur(
            f"{len(inconnues)} opération(s) absente(s) du catalogue : aucune demande enregistrée.",
            "OPERATION_INCONNUE",
            422,
        )
    etats = await etats_modules(db, list(ops.values()))
    refus = [(op_id, motif) for op_id, op in ops.items() for ok, motif in [admissibilite(op, etats)] if not ok]
    if refus:
        detail = "; ".join(f"{op_id} : {motif}" for op_id, motif in refus[:5])
        raise _erreur(f"Opération(s) non admissible(s), aucune demande enregistrée — {detail}",
                      "OPERATION_INADMISSIBLE", 422)
    existants = {
        g.operation_id: g
        for g in (await db.scalars(
            select(IntegrationClientGrant)
            .where(IntegrationClientGrant.client_id == c.id, IntegrationClientGrant.operation_id.in_(operation_ids))
            .with_for_update()
        )).all()
    }
    deja = [op_id for op_id, g in existants.items() if g.statut in GRANTS_OUVERTS]
    if deja:
        raise _erreur(f"Opération(s) déjà demandée(s) : {', '.join(deja[:5])}", "DEJA_DEMANDEE", 409)

    maintenant = _maintenant()
    crees: list[str] = []
    for op_id, op in ops.items():
        g = existants.get(op_id)
        ancien = None
        if g is None:
            g = IntegrationClientGrant(id=uuid.uuid4(), client_id=c.id, operation_id=op_id, statut="demandee")
            db.add(g)
        else:
            ancien = g.statut
            g.statut = "demandee"
            g.decide_par_id = None
            g.decide_le = None
            g.motif = None
            g.updated_at = maintenant
        _instantane(g, op)
        g.justification = justification
        g.demande_par_id = actor.id
        await db.flush()
        _evenement(db, g, ancien, "demandee", justification, actor)
        crees.append(op_id)
    await db.flush()
    await record_audit(
        db, user=actor, action="integration_grant_request", entity="integration_client", entity_id=str(c.id),
        request=request, after={"operations": crees, "environnement": c.environnement}, module_code="core",
    )
    return await lister_grants(db, app, c.id)


async def decider(db: AsyncSession, app: FastAPI, actor: User, have: set[str], client_id: uuid.UUID,
                  grant_id: uuid.UUID, nouveau: str, motif: str | None, request: Request | None) -> dict:
    c = await _client(db, client_id, verrou=True)
    g = await db.scalar(
        select(IntegrationClientGrant)
        .where(IntegrationClientGrant.id == grant_id, IntegrationClientGrant.client_id == c.id)
        .with_for_update()
    )
    if g is None:
        raise _erreur("Demande introuvable pour cette application", "GRANT_INTROUVABLE", 404)
    if c.statut == "archivee":
        raise _erreur("Application archivée : aucune décision possible", "CLIENT_ARCHIVE", 409)
    ancien = g.statut
    permission = TRANSITIONS_GRANT.get((ancien, nouveau))
    if permission is None:
        raise _erreur(f"Transition interdite : {ancien} → {nouveau}", "TRANSITION_INTERDITE", 409)
    if not user_has_permission_codes(have, permission):
        raise _erreur("Permission refusée pour cette décision", "PERMISSION_DENIED", 403)
    if nouveau in MOTIF_OBLIGATOIRE and not motif:
        raise _erreur("Motif obligatoire pour un refus ou une révocation", "MOTIF_OBLIGATOIRE", 422)

    _ops, index = cat.operations_de(app)
    op = index.get(g.operation_id)
    if nouveau in ("approuvee", "demandee", "en_attente"):
        if nouveau == "approuvee" and c.statut not in CLIENT_APPROBATION:
            raise _erreur(f"Application {c.statut} : approbation impossible", "CLIENT_NON_APPROUVABLE", 409)
        if nouveau != "approuvee" and c.statut not in CLIENT_DEMANDES_OUVERTES:
            raise _erreur(f"Application {c.statut} : aucune demande possible", "CLIENT_NON_MODIFIABLE", 409)
        ok, motif_refus = admissibilite(op, await etats_modules(db, [op] if op else []))
        if not ok:
            raise _erreur(f"Opération non admissible : {motif_refus}", "OPERATION_INADMISSIBLE", 422)
        _instantane(g, op)

    maintenant = _maintenant()
    g.statut = nouveau
    g.updated_at = maintenant
    if nouveau in ("approuvee", "refusee", "revoquee"):
        g.decide_par_id = actor.id
        g.decide_le = maintenant
        g.motif = motif
    elif nouveau == "demandee":
        g.decide_par_id = None
        g.decide_le = None
        g.motif = None
        g.demande_par_id = actor.id
    elif nouveau == "retiree":
        g.motif = motif
    _evenement(db, g, ancien, nouveau, motif, actor)
    await db.flush()
    await record_audit(
        db, user=actor, action=f"integration_grant_{nouveau}", entity="integration_client_grant",
        entity_id=str(g.id), request=request,
        before={"statut": ancien},
        after={"statut": nouveau, "client_id": str(c.id), "operation_id": g.operation_id, "motif": motif},
        module_code="core",
    )
    noms = await _noms(db, {g.demande_par_id, g.decide_par_id})
    return _grant_dict(g, op, await etats_modules(db, [op] if op else []), noms)


async def historique(db: AsyncSession, client_id: uuid.UUID, *, page: int, size: int) -> dict:
    await _client(db, client_id)
    e = IntegrationClientGrantEvent
    total = await db.scalar(select(func.count()).where(e.client_id == client_id))
    rows = (await db.scalars(
        select(e).where(e.client_id == client_id).order_by(e.created_at.desc(), e.id)
        .offset((page - 1) * size).limit(size)
    )).all()
    noms = await _noms(db, {x.acteur_id for x in rows})
    return {
        "items": [
            {
                "id": x.id, "grant_id": x.grant_id, "operation_id": x.operation_id, "ancien_statut": x.ancien_statut,
                "nouveau_statut": x.nouveau_statut, "motif": x.motif, "acteur": _personne(noms, x.acteur_id),
                "created_at": x.created_at,
            }
            for x in rows
        ],
        "total": int(total or 0),
        "page": page,
        "size": size,
    }


async def operations_admissibles(db: AsyncSession, app: FastAPI, client_id: uuid.UUID, *, q: str | None,
                                 module: str | None, methode: str | None, admissibles_seulement: bool,
                                 page: int, size: int) -> dict:
    await _client(db, client_id)
    operations, _index = cat.operations_de(app)
    candidats = cat.filtrer(operations, module=module, methode=methode, recherche=q)
    if admissibles_seulement:
        candidats = [op for op in candidats if op.disponibilite == cat.DISPO_DOCUMENTEE]
    etats = await etats_modules(db, candidats)
    evalues = [(op, *admissibilite(op, etats)) for op in candidats]
    if admissibles_seulement:
        evalues = [x for x in evalues if x[1]]
    statuts = dict((await db.execute(
        select(IntegrationClientGrant.operation_id, IntegrationClientGrant.statut)
        .where(IntegrationClientGrant.client_id == client_id)
    )).all())
    debut = (page - 1) * size
    return {
        "items": [
            {
                "operation_id": op.operation_id, "nom": op.nom, "methode": op.methode, "chemin": op.chemin,
                "module": op.module, "module_code": op.module_code, "resume": cat.detail_expose(op)["resume"],
                "permissions": op.permissions, "exigence_permissions": cat.exigence_texte(op.exigences),
                "authentification": op.authentification, "admissible": ok, "motif_inadmissible": motif,
                "deja_demandee": statuts.get(op.operation_id),
            }
            for op, ok, motif in evalues[debut: debut + size]
        ],
        "total": len(evalues),
        "page": page,
        "size": size,
        "avertissement": cat.AVERTISSEMENT,
    }


# ------------------------------------------------------------------------------ documentation
AVERTISSEMENTS_DOC = (
    "Aucune authentification machine-à-machine n'est disponible : cette application ne peut pas appeler "
    "l'API BEA DIGITAL. Aucun identifiant client, aucune clé et aucun secret n'existent pour elle.",
    "Les exemples montrent un appel effectué avec une session utilisateur (Login 1 / Login 2) par une personne "
    "habilitée. Ils ne doivent pas être intégrés tels quels dans une application.",
    "« Approuvée » signifie que l'opération a été validée pour la configuration future de l'application : "
    "ce n'est pas une autorisation effective.",
    "Une permission identifiée est nécessaire, pas forcément suffisante : les services peuvent restreindre "
    "par périmètre, propriétaire ou état métier.",
    "Environnements DEV / TEST : n'utiliser que des données fictives, jamais de donnée bancaire réelle.",
)


def _markdown(c: IntegrationClient, operations: list[dict], en_attente: int, genere_le: datetime) -> str:
    lignes = [
        f"# {c.nom} — documentation d'intégration (configuration)",
        "",
        f"- Identifiant interne de la fiche : `{c.code}` (pas un identifiant d'authentification)",
        f"- Environnement : {c.environnement}",
        f"- Statut de la fiche : {c.statut}",
        f"- Générée le : {genere_le.strftime('%d/%m/%Y %H:%M')} UTC",
        f"- Opérations approuvées : {len(operations)} — demandes en cours : {en_attente}",
        "",
        "## Avertissements",
        "",
        *[f"- {a}" for a in AVERTISSEMENTS_DOC],
        "",
        "## Opérations approuvées",
        "",
    ]
    if not operations:
        lignes += ["Aucune opération approuvée.", ""]
    for op in operations:
        lignes += [
            f"### `{op['methode']} {op['chemin']}`",
            "",
            f"- Opération : `{op['operation_id']}`" + (f" — {op['resume']}" if op["resume"] else ""),
            f"- Permission(s) : {op['exigence_permissions'] or ', '.join(op['permissions']) or 'non déterminée'}",
            f"- Statut de validation : {op['statut']}",
            "",
        ]
        if op["prerequis"]:
            lignes += ["Prérequis :", "", *[f"- {p}" for p in op["prerequis"]], ""]
        for ex in op["exemples"]:
            langage = {"curl": "bash", "python": "python", "typescript": "typescript"}.get(ex["langage"], "")
            lignes += [f"**{ex['libelle']}**", "", f"```{langage}", ex["code"], "```", ""]
        if op["exemples_motif"]:
            lignes += [f"_Exemples non générés : {op['exemples_motif']}_", ""]
    return "\n".join(lignes)


async def documentation(db: AsyncSession, app: FastAPI, actor: User, client_id: uuid.UUID,
                        request: Request | None) -> dict:
    c = await _client(db, client_id)
    grants = (await db.scalars(
        select(IntegrationClientGrant).where(IntegrationClientGrant.client_id == c.id)
        .order_by(IntegrationClientGrant.chemin, IntegrationClientGrant.methode)
    )).all()
    _ops, index = cat.operations_de(app)
    operations = []
    for g in grants:
        if g.statut != "approuvee":
            continue
        op = index.get(g.operation_id)
        ex = generer(op) if op else None
        motif = None
        if op is None:
            motif = "Opération absente du catalogue actuel."
        elif not ex["disponible"]:
            motif = ex["motif"]
        operations.append({
            "operation_id": g.operation_id,
            "methode": g.methode,
            "chemin": g.chemin,
            "module": op.module if op else None,
            "resume": cat.detail_expose(op)["resume"] if op else None,
            "permissions": list(g.permissions or []),
            "exigence_permissions": g.exigence_permissions,
            "statut": g.statut,
            "decide_le": g.decide_le,
            "prerequis": ex["prerequis"] if ex and ex["disponible"] else [],
            "exemples": ex["exemples"] if ex and ex["disponible"] else [],
            "exemples_motif": motif,
        })
    en_attente = sum(1 for g in grants if g.statut in ("demandee", "en_attente"))
    genere_le = _maintenant()
    await record_audit(
        db, user=actor, action="integration_client_documentation", entity="integration_client",
        entity_id=str(c.id), request=request, after={"operations": len(operations)}, module_code="core",
    )
    return {
        "client_code": c.code,
        "nom": c.nom,
        "environnement": c.environnement,
        "statut": c.statut,
        "genere_le": genere_le,
        "operations": operations,
        "en_attente": en_attente,
        "avertissements": list(AVERTISSEMENTS_DOC),
        "markdown": _markdown(c, operations, en_attente, genere_le),
    }
