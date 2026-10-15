"""Référentiel organisationnel central BEA DIGITAL — point unique pour tous les modules.

- Entités (table ``departements``) : arborescence configurable de profondeur libre.
- Postes (``org_postes``) et affectations utilisateurs (``org_affectations``) : notions distinctes
  des comptes et des rôles applicatifs.
- Périmètre organisationnel (``PerimetreOrg``) : appliqué par le backend des modules, jamais déduit
  automatiquement — une affectation vaut PERSONNEL tant qu'un administrateur ne l'élargit pas.

Désactiver une entité ne supprime rien : dossiers, documents et historiques gardent leur lien.
Toute écriture est journalisée dans ``audit_logs`` (module ``core``).
"""

from __future__ import annotations

import difflib
import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

from fastapi import Request
from sqlalchemy import ColumnElement, false, func, or_, select, text, true
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import Agence, AuditLog, OrgAffectation, OrgEntite, OrgPoste, User
from app.models.organisation import PERIMETRES, TYPES_AFFECTATION, TYPES_ENTITE
from app.services.audit_helpers import record_audit
from app.services.permission_service import load_user_permission_codes, user_has_permission_codes

PERMISSION_PERIMETRE_GLOBAL = "org.scope.all"

TYPE_LIBELLES: dict[str, str] = {
    "CONSEIL": "Conseil",
    "COMITE": "Comité",
    "DIRECTION_GENERALE": "Direction générale",
    "DIRECTION": "Direction",
    "DEPARTEMENT": "Département",
    "SERVICE": "Service",
    "SECTION": "Section",
    "CELLULE": "Cellule / unité rattachée",
}
# Rang hiérarchique indicatif : un enfant de rang inférieur ou égal à son parent est signalé
# (pas bloqué — l'organigramme réel a des rattachements atypiques). Comités / cellules : libres.
RANGS: dict[str, int] = {
    "CONSEIL": 0, "DIRECTION_GENERALE": 1, "DIRECTION": 2, "DEPARTEMENT": 3, "SERVICE": 4, "SECTION": 5,
}
PERIMETRE_LIBELLES = {
    "PERSONNEL": "Ses propres dossiers",
    "ENTITE": "Dossiers de l'entité",
    "ENTITE_ET_SOUS_ENTITES": "Dossiers de l'entité et de ses sous-entités",
}
AFFECTATION_LIBELLES = {"PRINCIPALE": "Principale", "SECONDAIRE": "Secondaire", "INTERIM": "Intérim"}

ENTITES_AUDITEES = ("org_entite", "org_poste", "org_affectation", "org_correspondance", "agence")


# ------------------------------------------------------------------------------------ liaisons
@dataclass(frozen=True)
class Liaison:
    """Table métier rattachée au référentiel. ``colonne_texte`` : ancienne saisie libre conservée."""

    code: str
    module: str
    libelle: str
    table: str
    colonne_entite: str
    colonne_texte: str | None = None
    filtre: str = "TRUE"


LIAISONS: tuple[Liaison, ...] = (
    Liaison("immobilisations", "immobilisations", "Immobilisations", "immobilisations", "departement_id",
            filtre="deleted_at IS NULL"),
    Liaison("centres_cout", "immobilisations", "Centres de coût", "centres_cout", "departement_id"),
    Liaison("mg_achat_demandes", "achats-appro", "Demandes d'achat", "mg_achat_demandes", "departement_id"),
    Liaison("mg_bons_commande", "achats-appro", "Bons de commande", "mg_bons_commande", "org_entite_id",
            "departement"),
    Liaison("mg_bc_lignes", "achats-appro", "Lignes de bons de commande", "mg_bc_lignes", "org_entite_id",
            "departement"),
    Liaison("mg_stock_mouvements", "stock-fournitures", "Mouvements de stock", "mg_stock_mouvements",
            "org_entite_id", "departement"),
    Liaison("mg_stock_sorties_service", "stock-fournitures", "Sorties de stock (service destinataire)",
            "mg_stock_mouvements", "service_id"),
    Liaison("mg_demandes_fourniture", "stock-fournitures", "Demandes de fournitures", "mg_demandes_fourniture",
            "org_entite_id", "departement"),
    Liaison("mg_notes_frais", "notes-frais", "Notes de frais", "mg_notes_frais", "org_entite_id", "departement"),
    Liaison("mg_employee_requests", "demandes", "Demandes des employés", "mg_employee_requests", "department_id"),
    Liaison("mg_procurement_batches", "demandes", "Lots d'approvisionnement", "mg_procurement_batches",
            "department_id"),
    Liaison("ged_documents", "ged", "Documents GED", "ged_documents", "department_id"),
    Liaison("reclamation_unites", "reclamations", "Unités Réclamations", "reclamation_unites", "org_entite_id",
            "libelle", "type_unite <> 'AGENCE'"),
    Liaison("formation_entites", "formation", "Entités Formation", "formation_entites", "org_entite_id",
            "libelle", "agence_id IS NULL"),
    Liaison("agences", "core", "Agences rattachées", "agences", "org_entite_id", filtre="deleted_at IS NULL"),
)
LIAISONS_PAR_CODE = {lz.code: lz for lz in LIAISONS}
LIAISONS_TEXTE = tuple(lz for lz in LIAISONS if lz.colonne_texte)


# ------------------------------------------------------------------------------------ erreurs
def _erreur(message: str, code: str, status: int = 400) -> AppError:
    return AppError(message, status, code=code)


def _introuvable(quoi: str) -> AppError:
    return _erreur(f"{quoi} introuvable", "NOT_FOUND", 404)


def _propre(valeur: str | None) -> str:
    return " ".join((valeur or "").split())


async def _cle(db: AsyncSession, texte: str) -> str | None:
    """Même normalisation que la base (fonction SQL ``org_cle``) : une seule règle."""
    return await db.scalar(select(func.org_cle(texte)))


async def _auditer(db: AsyncSession, actor: User | None, request: Request | None, action: str, entity: str,
                   entity_id: uuid.UUID | str | None, *, before: dict | None = None,
                   after: dict | None = None) -> None:
    await record_audit(db, user=actor, action=action, entity=entity,
                       entity_id=str(entity_id) if entity_id else None, request=request,
                       before=before, after=after, module_code="core")


# ------------------------------------------------------------------------------------ arbre
@dataclass
class Arbre:
    """Instantané de toutes les entités (quelques centaines au plus) pour les calculs de chemin."""

    entites: dict[uuid.UUID, OrgEntite]
    enfants: dict[uuid.UUID | None, list[uuid.UUID]]

    def chemin(self, entite_id: uuid.UUID | None) -> list[OrgEntite]:
        out: list[OrgEntite] = []
        vus: set[uuid.UUID] = set()
        courant = self.entites.get(entite_id) if entite_id else None
        while courant is not None and courant.id not in vus:
            out.append(courant)
            vus.add(courant.id)
            courant = self.entites.get(courant.parent_id) if courant.parent_id else None
        return list(reversed(out))

    def descendants(self, entite_id: uuid.UUID, *, inclure: bool = True) -> set[uuid.UUID]:
        out: set[uuid.UUID] = {entite_id} if inclure else set()
        pile = list(self.enfants.get(entite_id, []))
        while pile:
            courant = pile.pop()
            if courant in out:
                continue
            out.add(courant)
            pile.extend(self.enfants.get(courant, []))
        return out

    def libelle_chemin(self, entite_id: uuid.UUID | None) -> str | None:
        chemin = self.chemin(entite_id)
        return " › ".join(e.libelle for e in chemin) if chemin else None


async def charger_arbre(db: AsyncSession) -> Arbre:
    lignes = (await db.scalars(select(OrgEntite).where(OrgEntite.deleted_at.is_(None)))).all()
    enfants: dict[uuid.UUID | None, list[uuid.UUID]] = defaultdict(list)
    for e in sorted(lignes, key=lambda x: (x.ordre, x.libelle)):
        enfants[e.parent_id].append(e.id)
    return Arbre(entites={e.id: e for e in lignes}, enfants=enfants)


def entite_resume(e: OrgEntite, arbre: Arbre | None = None) -> dict:
    return {
        "id": str(e.id), "code": e.code, "libelle": e.libelle, "sigle": e.sigle,
        "type_entite": e.type_entite, "type_libelle": TYPE_LIBELLES.get(e.type_entite, e.type_entite),
        "parent_id": str(e.parent_id) if e.parent_id else None, "actif": bool(e.is_active),
        "a_confirmer": e.a_confirmer,
        "chemin": arbre.libelle_chemin(e.id) if arbre else None,
    }


def entite_dict(e: OrgEntite, arbre: Arbre, compteurs: dict[str, dict[uuid.UUID, int]] | None = None) -> dict:
    c = compteurs or {}
    chemin = arbre.chemin(e.id)
    return {
        **entite_resume(e, arbre),
        "description": e.description, "ordre": e.ordre, "alias": list(e.alias or []),
        "note_confirmation": e.note_confirmation, "source": e.source,
        "profondeur": max(len(chemin) - 1, 0),
        "chemin_ids": [str(x.id) for x in chemin],
        "nb_enfants": len(arbre.enfants.get(e.id, [])),
        "nb_utilisateurs": c.get("utilisateurs", {}).get(e.id, 0),
        "nb_postes": c.get("postes", {}).get(e.id, 0),
        "metadonnees": e.metadonnees or {},
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
    }


async def _compteurs(db: AsyncSession) -> dict[str, dict[uuid.UUID, int]]:
    users = dict((await db.execute(
        select(OrgAffectation.entite_id, func.count(func.distinct(OrgAffectation.user_id)))
        .where(OrgAffectation.actif.is_(True)).group_by(OrgAffectation.entite_id))).all())
    postes = dict((await db.execute(
        select(OrgPoste.entite_id, func.count()).where(OrgPoste.actif.is_(True)).group_by(OrgPoste.entite_id)
    )).all())
    return {"utilisateurs": users, "postes": postes}


# ------------------------------------------------------------------------------- lecture
async def lister_entites(db: AsyncSession, *, types: Iterable[str] | None = None, actives_seulement: bool = False,
                         recherche: str | None = None, racine_id: uuid.UUID | None = None) -> list[dict]:
    arbre = await charger_arbre(db)
    compteurs = await _compteurs(db)
    perimetre = arbre.descendants(racine_id) if racine_id else None
    types_ok = set(types or [])
    motif = (await _cle(db, recherche)) if recherche else None
    out = []
    for e in _ordre_arbre(arbre):
        if actives_seulement and not e.is_active:
            continue
        if types_ok and e.type_entite not in types_ok:
            continue
        if perimetre is not None and e.id not in perimetre:
            continue
        if motif and motif not in (e.cle or "") and motif not in (e.code or "").lower() \
                and not any(motif in a for a in (e.alias or [])):
            continue
        out.append(entite_dict(e, arbre, compteurs))
    return out


def _ordre_arbre(arbre: Arbre) -> list[OrgEntite]:
    """Ordre d'affichage : parcours en profondeur (parent, puis ses enfants triés)."""
    out: list[OrgEntite] = []
    vus: set[uuid.UUID] = set()

    def visiter(parent: uuid.UUID | None) -> None:
        for eid in arbre.enfants.get(parent, []):
            if eid in vus:
                continue
            vus.add(eid)
            out.append(arbre.entites[eid])
            visiter(eid)

    visiter(None)
    # Entités dont le parent est supprimé / inconnu : ajoutées en fin pour rester visibles.
    out.extend(e for e in arbre.entites.values() if e.id not in vus)
    return out


async def usages(db: AsyncSession, entite_ids: Iterable[uuid.UUID]) -> list[dict]:
    """Dossiers et données des modules rattachés aux entités (conservés même si l'entité est désactivée)."""
    ids = [str(i) for i in entite_ids]
    if not ids:
        return []
    out = []
    for lz in LIAISONS:
        n = await db.scalar(text(
            f"SELECT count(*) FROM {lz.table} WHERE {lz.colonne_entite} = ANY(CAST(:ids AS uuid[])) AND {lz.filtre}"
        ), {"ids": ids})
        if n:
            out.append({"liaison": lz.code, "module": lz.module, "libelle": lz.libelle, "nombre": int(n)})
    return out


async def fiche_entite(db: AsyncSession, entite_id: uuid.UUID) -> dict:
    arbre = await charger_arbre(db)
    e = arbre.entites.get(entite_id)
    if e is None:
        raise _introuvable("Entité")
    compteurs = await _compteurs(db)
    enfants = [entite_dict(arbre.entites[i], arbre, compteurs) for i in arbre.enfants.get(e.id, [])]
    postes = await lister_postes(db, e.id)
    affectations = await _affectations_entite(db, e.id, arbre)
    agences = (await db.execute(
        select(Agence.id, Agence.code, Agence.libelle).where(Agence.org_entite_id == e.id,
                                                             Agence.deleted_at.is_(None))
        .order_by(Agence.code))).all()
    return {
        "entite": entite_dict(e, arbre, compteurs),
        "chemin": [entite_resume(x) for x in arbre.chemin(e.id)],
        "enfants": enfants,
        "postes": postes,
        "affectations": affectations,
        "agences": [{"id": str(i), "code": c, "libelle": lib} for i, c, lib in agences],
        "usages": await usages(db, [e.id]),
        "usages_sous_arbre": await usages(db, arbre.descendants(e.id)),
    }


async def _affectations_entite(db: AsyncSession, entite_id: uuid.UUID, arbre: Arbre) -> list[dict]:
    rows = (await db.execute(
        select(OrgAffectation, User.full_name, User.email, User.is_active)
        .join(User, User.id == OrgAffectation.user_id)
        .where(OrgAffectation.entite_id == entite_id, OrgAffectation.actif.is_(True))
        .order_by(OrgAffectation.type_affectation, User.full_name))).all()
    postes = await _postes_par_id(db, [a.poste_id for a, *_ in rows if a.poste_id])
    return [affectation_dict(a, arbre, nom=n, email=m, compte_actif=ok, postes=postes) for a, n, m, ok in rows]


# ------------------------------------------------------------------------------- écriture entités
async def _entite(db: AsyncSession, entite_id: uuid.UUID) -> OrgEntite:
    e = await db.get(OrgEntite, entite_id)
    if e is None or e.deleted_at is not None:
        raise _introuvable("Entité")
    return e


def _verifier_type(type_entite: str) -> str:
    if type_entite not in TYPES_ENTITE:
        raise _erreur(f"Type d'entité inconnu : {type_entite}", "TYPE_INVALIDE", 422)
    return type_entite


async def _verifier_parent(db: AsyncSession, parent_id: uuid.UUID, entite_id: uuid.UUID | None = None) -> OrgEntite:
    parent = await _entite(db, parent_id)
    if not parent.is_active:
        raise _erreur(f"L'entité parente « {parent.libelle} » est désactivée", "PARENT_INACTIF")
    if entite_id is not None:
        arbre = await charger_arbre(db)
        if parent_id in arbre.descendants(entite_id):
            raise _erreur("Rattachement circulaire : une entité ne peut pas dépendre d'elle-même ni de l'une "
                          "de ses sous-entités", "HIERARCHIE_CIRCULAIRE", 422)
    return parent


async def _verifier_doublon(db: AsyncSession, parent_id: uuid.UUID | None, libelle: str,
                            exclure: uuid.UUID | None = None) -> None:
    cle = await _cle(db, libelle)
    if not cle:
        raise _erreur("Libellé obligatoire", "LIBELLE_OBLIGATOIRE", 422)
    q = select(OrgEntite).where(OrgEntite.deleted_at.is_(None), OrgEntite.cle == cle,
                                OrgEntite.parent_id.is_(None) if parent_id is None
                                else OrgEntite.parent_id == parent_id)
    if exclure:
        q = q.where(OrgEntite.id != exclure)
    existant = await db.scalar(q)
    if existant:
        etat = "" if existant.is_active else " (désactivée — réactivez-la)"
        raise _erreur(f"« {existant.libelle} » existe déjà à ce niveau{etat}", "ENTITE_EXISTANTE", 409)


async def _verifier_code(db: AsyncSession, code: str, exclure: uuid.UUID | None = None) -> None:
    q = select(OrgEntite.id).where(func.upper(OrgEntite.code) == code.upper())
    if exclure:
        q = q.where(OrgEntite.id != exclure)
    if await db.scalar(q):
        raise _erreur(f"Le code {code} est déjà utilisé", "CODE_EXISTANT", 409)


async def _code_auto(db: AsyncSession, parent: OrgEntite | None, type_entite: str) -> str:
    base = (parent.code if parent else type_entite[:4]).upper()[:14]
    n = 1
    while True:
        code = f"{base}-{n:02d}"[:20]
        if not await db.scalar(select(OrgEntite.id).where(func.upper(OrgEntite.code) == code)):
            return code
        n += 1


def _code_propre(code: str | None) -> str | None:
    c = "".join((code or "").split()).upper()
    return c or None


async def _alias(db: AsyncSession, valeurs: Iterable[str] | None) -> list[str]:
    out: set[str] = set()
    for v in valeurs or []:
        c = await _cle(db, v)
        if c:
            out.add(c)
    return sorted(out)


async def _flush(db: AsyncSession) -> None:
    try:
        await db.flush()
    except IntegrityError as exc:
        message = str(exc.orig)
        if "ck_departements_sans_cycle" in message or "circulaire" in message:
            raise _erreur("Rattachement circulaire interdit dans l'organigramme", "HIERARCHIE_CIRCULAIRE",
                          422) from exc
        if "uq_departements_parent_cle" in message:
            raise _erreur("Une entité de même libellé existe déjà à ce niveau", "ENTITE_EXISTANTE", 409) from exc
        if "uq_org_affectations_principale" in message:
            raise _erreur("Cet utilisateur a déjà une affectation principale active", "AFFECTATION_EXISTANTE",
                          409) from exc
        raise


async def creer_entite(db: AsyncSession, actor: User, data: dict, request: Request | None = None) -> dict:
    libelle = _propre(data.get("libelle"))
    type_entite = _verifier_type(data.get("type_entite") or "")
    parent = await _verifier_parent(db, data["parent_id"]) if data.get("parent_id") else None
    await _verifier_doublon(db, parent.id if parent else None, libelle)
    code = _code_propre(data.get("code"))
    if code:
        await _verifier_code(db, code)
    else:
        code = await _code_auto(db, parent, type_entite)
    ordre = data.get("ordre")
    if ordre is None:
        ordre = (await db.scalar(select(func.coalesce(func.max(OrgEntite.ordre), 0)).where(
            OrgEntite.parent_id.is_(None) if parent is None else OrgEntite.parent_id == parent.id)) or 0) + 1
    e = OrgEntite(
        code=code, libelle=libelle, type_entite=type_entite, parent_id=parent.id if parent else None,
        sigle=_propre(data.get("sigle")) or None, description=(data.get("description") or "").strip() or None,
        ordre=ordre, alias=await _alias(db, data.get("alias")), a_confirmer=bool(data.get("a_confirmer")),
        note_confirmation=(data.get("note_confirmation") or "").strip() or None, source="MANUEL",
        metadonnees={}, is_active=True, created_by_id=actor.id, updated_by_id=actor.id,
    )
    db.add(e)
    await _flush(db)
    await db.refresh(e)
    arbre = await charger_arbre(db)
    apres = entite_dict(e, arbre)
    await _auditer(db, actor, request, "org.entite.create", "org_entite", e.id, after=apres)
    return apres


async def modifier_entite(db: AsyncSession, actor: User, entite_id: uuid.UUID, data: dict,
                          request: Request | None = None) -> dict:
    """Renommer ou déplacer une entité ne réécrit aucune donnée rattachée : elles suivent son identifiant."""
    e = await _entite(db, entite_id)
    arbre = await charger_arbre(db)
    avant = entite_dict(e, arbre)
    parent_id = e.parent_id
    if data.get("detacher_parent"):
        parent_id = None
    elif data.get("parent_id"):
        await _verifier_parent(db, data["parent_id"], e.id)
        parent_id = data["parent_id"]
    libelle = _propre(data["libelle"]) if data.get("libelle") is not None else e.libelle
    if libelle != e.libelle or parent_id != e.parent_id:
        await _verifier_doublon(db, parent_id, libelle, exclure=e.id)
    if data.get("code") is not None:
        code = _code_propre(data["code"])
        if not code:
            raise _erreur("Code obligatoire", "CODE_OBLIGATOIRE", 422)
        if code != e.code:
            await _verifier_code(db, code, exclure=e.id)
            e.code = code
    if data.get("type_entite"):
        e.type_entite = _verifier_type(data["type_entite"])
    e.libelle, e.parent_id = libelle, parent_id
    for champ in ("sigle", "description", "note_confirmation"):
        if data.get(champ) is not None:
            setattr(e, champ, (data[champ] or "").strip() or None)
    if data.get("ordre") is not None:
        e.ordre = data["ordre"]
    if data.get("alias") is not None:
        e.alias = await _alias(db, data["alias"])
    if data.get("a_confirmer") is not None:
        e.a_confirmer = bool(data["a_confirmer"])
        if not e.a_confirmer and data.get("note_confirmation") is None:
            e.note_confirmation = None
    e.updated_by_id = actor.id
    await _flush(db)
    await db.refresh(e)
    arbre = await charger_arbre(db)
    apres = entite_dict(e, arbre)
    action = "org.entite.move" if avant["parent_id"] != apres["parent_id"] else "org.entite.update"
    await _auditer(db, actor, request, action, "org_entite", e.id, before=avant, after=apres)
    return apres


async def changer_statut_entite(db: AsyncSession, actor: User, entite_id: uuid.UUID, actif: bool,
                                motif: str | None = None, request: Request | None = None) -> dict:
    e = await _entite(db, entite_id)
    if e.is_active == actif:
        raise _erreur("L'entité est déjà " + ("active" if actif else "désactivée"), "STATUT_INCHANGE", 409)
    arbre = await charger_arbre(db)
    if actif:
        parent = arbre.entites.get(e.parent_id) if e.parent_id else None
        if parent is not None and not parent.is_active:
            raise _erreur(f"Réactivez d'abord l'entité parente « {parent.libelle} »", "PARENT_INACTIF", 409)
    else:
        actifs = [arbre.entites[i].libelle for i in arbre.enfants.get(e.id, []) if arbre.entites[i].is_active]
        if actifs:
            raise _erreur(f"Désactivez d'abord les sous-entités actives : {', '.join(actifs[:5])}"
                          + ("…" if len(actifs) > 5 else ""), "SOUS_ENTITES_ACTIVES", 409)
    avant = entite_dict(e, arbre)
    e.is_active = actif
    e.updated_by_id = actor.id
    await _flush(db)
    await db.refresh(e)
    apres = entite_dict(e, await charger_arbre(db))
    conserves = await usages(db, [e.id])
    await _auditer(db, actor, request, "org.entite.activate" if actif else "org.entite.deactivate", "org_entite",
                   e.id, before=avant, after={**apres, "motif": (motif or "").strip() or None,
                                              "donnees_conservees": conserves})
    return {**apres, "donnees_conservees": conserves}


# ------------------------------------------------------------------------------------ postes
async def _postes_par_id(db: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, OrgPoste]:
    if not ids:
        return {}
    return {p.id: p for p in (await db.scalars(select(OrgPoste).where(OrgPoste.id.in_(ids)))).all()}


def poste_dict(p: OrgPoste, titulaire: tuple[str | None, str | None] | None = None) -> dict:
    nom, email = titulaire or (None, None)
    return {
        "id": str(p.id), "entite_id": str(p.entite_id), "intitule": p.intitule,
        "est_responsable": p.est_responsable, "effectif_prevu": p.effectif_prevu,
        "titulaire_user_id": str(p.titulaire_user_id) if p.titulaire_user_id else None,
        "titulaire_nom": nom or email, "actif": p.actif, "a_confirmer": p.a_confirmer,
        "note_confirmation": p.note_confirmation, "ordre": p.ordre, "source": p.source,
    }


async def lister_postes(db: AsyncSession, entite_id: uuid.UUID) -> list[dict]:
    rows = (await db.execute(
        select(OrgPoste, User.full_name, User.email).outerjoin(User, User.id == OrgPoste.titulaire_user_id)
        .where(OrgPoste.entite_id == entite_id)
        .order_by(OrgPoste.actif.desc(), OrgPoste.est_responsable.desc(), OrgPoste.ordre, OrgPoste.intitule)
    )).all()
    return [poste_dict(p, (n, m)) for p, n, m in rows]


async def _utilisateur_actif(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await db.get(User, user_id)
    if user is None or user.deleted_at is not None or not user.is_active:
        raise _erreur("Utilisateur introuvable ou inactif", "UTILISATEUR_INCONNU", 422)
    return user


async def creer_poste(db: AsyncSession, actor: User, entite_id: uuid.UUID, data: dict,
                      request: Request | None = None) -> dict:
    e = await _entite(db, entite_id)
    if not e.is_active:
        raise _erreur("Entité désactivée", "ENTITE_INACTIVE", 409)
    intitule = _propre(data.get("intitule"))
    cle = await _cle(db, intitule)
    if not cle:
        raise _erreur("Intitulé obligatoire", "INTITULE_OBLIGATOIRE", 422)
    if await db.scalar(select(OrgPoste.id).where(OrgPoste.entite_id == e.id, OrgPoste.cle == cle,
                                                 OrgPoste.actif.is_(True))):
        raise _erreur(f"Le poste « {intitule} » existe déjà dans cette entité", "POSTE_EXISTANT", 409)
    if data.get("titulaire_user_id"):
        await _utilisateur_actif(db, data["titulaire_user_id"])
    ordre = (await db.scalar(select(func.coalesce(func.max(OrgPoste.ordre), 0)).where(
        OrgPoste.entite_id == e.id)) or 0) + 1
    p = OrgPoste(entite_id=e.id, intitule=intitule, est_responsable=bool(data.get("est_responsable")),
                 effectif_prevu=data.get("effectif_prevu"), titulaire_user_id=data.get("titulaire_user_id"),
                 actif=True, a_confirmer=bool(data.get("a_confirmer")),
                 note_confirmation=(data.get("note_confirmation") or "").strip() or None, ordre=ordre,
                 source="MANUEL", created_by_id=actor.id, updated_by_id=actor.id)
    db.add(p)
    await _flush(db)
    apres = poste_dict(p)
    await _auditer(db, actor, request, "org.poste.create", "org_poste", p.id,
                   after={**apres, "entite": e.libelle})
    return apres


async def modifier_poste(db: AsyncSession, actor: User, poste_id: uuid.UUID, data: dict,
                         request: Request | None = None) -> dict:
    p = await db.get(OrgPoste, poste_id)
    if p is None:
        raise _introuvable("Poste")
    avant = poste_dict(p)
    if data.get("intitule") is not None:
        intitule = _propre(data["intitule"])
        if not await _cle(db, intitule):
            raise _erreur("Intitulé obligatoire", "INTITULE_OBLIGATOIRE", 422)
        p.intitule = intitule
    if data.get("retirer_titulaire"):
        p.titulaire_user_id = None
    elif data.get("titulaire_user_id"):
        await _utilisateur_actif(db, data["titulaire_user_id"])
        p.titulaire_user_id = data["titulaire_user_id"]
    for champ in ("est_responsable", "actif", "a_confirmer"):
        if data.get(champ) is not None:
            setattr(p, champ, bool(data[champ]))
    if "effectif_prevu" in data and data["effectif_prevu"] is not None:
        p.effectif_prevu = data["effectif_prevu"] or None
    if data.get("note_confirmation") is not None:
        p.note_confirmation = data["note_confirmation"].strip() or None
    if data.get("ordre") is not None:
        p.ordre = data["ordre"]
    p.updated_by_id = actor.id
    await _flush(db)
    apres = poste_dict(p)
    await _auditer(db, actor, request, "org.poste.update", "org_poste", p.id, before=avant, after=apres)
    return apres


# ------------------------------------------------------------------------------- affectations
def affectation_dict(a: OrgAffectation, arbre: Arbre, *, nom: str | None = None, email: str | None = None,
                     compte_actif: bool | None = None, postes: dict[uuid.UUID, OrgPoste] | None = None) -> dict:
    e = arbre.entites.get(a.entite_id)
    poste = (postes or {}).get(a.poste_id) if a.poste_id else None
    return {
        "id": str(a.id), "user_id": str(a.user_id), "utilisateur": nom or email, "email": email,
        "compte_actif": compte_actif,
        "entite_id": str(a.entite_id), "entite": e.libelle if e else None,
        "entite_type": TYPE_LIBELLES.get(e.type_entite) if e else None,
        "entite_active": bool(e.is_active) if e else False,
        "chemin": arbre.libelle_chemin(a.entite_id),
        "poste_id": str(a.poste_id) if a.poste_id else None, "poste": poste.intitule if poste else None,
        "type_affectation": a.type_affectation,
        "type_libelle": AFFECTATION_LIBELLES.get(a.type_affectation, a.type_affectation),
        "perimetre": a.perimetre, "perimetre_libelle": PERIMETRE_LIBELLES.get(a.perimetre, a.perimetre),
        "date_debut": a.date_debut.isoformat() if a.date_debut else None,
        "date_fin": a.date_fin.isoformat() if a.date_fin else None,
        "actif": a.actif, "commentaire": a.commentaire,
    }


async def lister_affectations_utilisateur(db: AsyncSession, user_id: uuid.UUID, *,
                                          inclure_closes: bool = True) -> list[dict]:
    q = select(OrgAffectation).where(OrgAffectation.user_id == user_id)
    if not inclure_closes:
        q = q.where(OrgAffectation.actif.is_(True))
    lignes = (await db.scalars(q.order_by(OrgAffectation.actif.desc(), OrgAffectation.date_debut.desc()))).all()
    arbre = await charger_arbre(db)
    postes = await _postes_par_id(db, [a.poste_id for a in lignes if a.poste_id])
    return [affectation_dict(a, arbre, postes=postes) for a in lignes]


async def creer_affectation(db: AsyncSession, actor: User, data: dict, request: Request | None = None) -> dict:
    """Une nouvelle affectation principale clôt la précédente (historique conservé, jamais réécrit)."""
    user = await _utilisateur_actif(db, data["user_id"])
    e = await _entite(db, data["entite_id"])
    if not e.is_active:
        raise _erreur(f"L'entité « {e.libelle} » est désactivée", "ENTITE_INACTIVE", 409)
    type_affectation = data.get("type_affectation") or "PRINCIPALE"
    perimetre = data.get("perimetre") or "PERSONNEL"
    if type_affectation not in TYPES_AFFECTATION or perimetre not in PERIMETRES:
        raise _erreur("Type d'affectation ou périmètre invalide", "AFFECTATION_INVALIDE", 422)
    if data.get("poste_id"):
        poste = await db.get(OrgPoste, data["poste_id"])
        if poste is None or poste.entite_id != e.id:
            raise _erreur("Le poste choisi n'appartient pas à cette entité", "POSTE_INVALIDE", 422)
    date_debut = data.get("date_debut") or date.today()
    doublon = await db.scalar(select(OrgAffectation.id).where(
        OrgAffectation.user_id == user.id, OrgAffectation.entite_id == e.id, OrgAffectation.actif.is_(True),
        OrgAffectation.type_affectation == type_affectation))
    if doublon:
        raise _erreur(f"{user.full_name} a déjà cette affectation active", "AFFECTATION_EXISTANTE", 409)
    precedente = None
    if type_affectation == "PRINCIPALE":
        precedente = await db.scalar(select(OrgAffectation).where(
            OrgAffectation.user_id == user.id, OrgAffectation.actif.is_(True),
            OrgAffectation.type_affectation == "PRINCIPALE"))
        if precedente is not None:
            precedente.actif = False
            precedente.date_fin = max(date_debut, precedente.date_debut)
            precedente.updated_by_id = actor.id
            await _flush(db)
    a = OrgAffectation(user_id=user.id, entite_id=e.id, poste_id=data.get("poste_id"),
                       type_affectation=type_affectation, perimetre=perimetre, date_debut=date_debut,
                       actif=True, commentaire=(data.get("commentaire") or "").strip() or None,
                       created_by_id=actor.id, updated_by_id=actor.id)
    db.add(a)
    await _flush(db)
    arbre = await charger_arbre(db)
    apres = affectation_dict(a, arbre, nom=user.full_name, email=user.email)
    await _auditer(db, actor, request, "org.affectation.create", "org_affectation", a.id, after={
        **apres, "remplace": str(precedente.id) if precedente else None})
    return apres


async def modifier_affectation(db: AsyncSession, actor: User, affectation_id: uuid.UUID, data: dict,
                               request: Request | None = None) -> dict:
    a = await db.get(OrgAffectation, affectation_id)
    if a is None:
        raise _introuvable("Affectation")
    if not a.actif:
        raise _erreur("Affectation close : créez une nouvelle affectation", "AFFECTATION_CLOSE", 409)
    arbre = await charger_arbre(db)
    avant = affectation_dict(a, arbre)
    if data.get("perimetre"):
        if data["perimetre"] not in PERIMETRES:
            raise _erreur("Périmètre invalide", "AFFECTATION_INVALIDE", 422)
        a.perimetre = data["perimetre"]
    if data.get("retirer_poste"):
        a.poste_id = None
    elif data.get("poste_id"):
        poste = await db.get(OrgPoste, data["poste_id"])
        if poste is None or poste.entite_id != a.entite_id:
            raise _erreur("Le poste choisi n'appartient pas à cette entité", "POSTE_INVALIDE", 422)
        a.poste_id = poste.id
    if data.get("commentaire") is not None:
        a.commentaire = data["commentaire"].strip() or None
    a.updated_by_id = actor.id
    await _flush(db)
    postes = await _postes_par_id(db, [a.poste_id] if a.poste_id else [])
    apres = affectation_dict(a, arbre, postes=postes)
    await _auditer(db, actor, request, "org.affectation.update", "org_affectation", a.id, before=avant, after=apres)
    return apres


async def cloturer_affectation(db: AsyncSession, actor: User, affectation_id: uuid.UUID,
                               date_fin: date | None = None, request: Request | None = None) -> dict:
    a = await db.get(OrgAffectation, affectation_id)
    if a is None:
        raise _introuvable("Affectation")
    if not a.actif:
        raise _erreur("Affectation déjà close", "AFFECTATION_CLOSE", 409)
    fin = date_fin or date.today()
    if fin < a.date_debut:
        raise _erreur("La date de fin précède le début de l'affectation", "PERIODE_INVALIDE", 422)
    arbre = await charger_arbre(db)
    avant = affectation_dict(a, arbre)
    a.actif, a.date_fin, a.updated_by_id = False, fin, actor.id
    await _flush(db)
    apres = affectation_dict(a, arbre)
    await _auditer(db, actor, request, "org.affectation.close", "org_affectation", a.id, before=avant, after=apres)
    return apres


# ------------------------------------------------------------------------------- périmètre
@dataclass(frozen=True)
class PerimetreOrg:
    """Périmètre organisationnel d'un utilisateur, à combiner avec les permissions du module.

    ``global_`` : toutes entités (superuser ou ``org.scope.all``). Sinon ``entites`` = entités
    couvertes par ses affectations élargies (ENTITE / ENTITE_ET_SOUS_ENTITES). Un utilisateur sans
    affectation élargie ne voit que ses propres dossiers (``condition`` avec ``colonne_proprietaire``).
    """

    user_id: uuid.UUID
    global_: bool = False
    entites: frozenset[uuid.UUID] = field(default_factory=frozenset)
    entite_principale_id: uuid.UUID | None = None

    @property
    def niveau(self) -> str:
        return "GLOBAL" if self.global_ else ("ENTITES" if self.entites else "PERSONNEL")

    def couvre_entite(self, entite_id: uuid.UUID | None) -> bool:
        return self.global_ or (entite_id is not None and entite_id in self.entites)

    def condition(self, colonne_entite, colonne_proprietaire=None) -> ColumnElement[bool]:
        """Filtre SQL standard : dossiers de l'utilisateur OU de son périmètre organisationnel."""
        if self.global_:
            return true()
        conditions: list[ColumnElement[bool]] = []
        if colonne_proprietaire is not None:
            conditions.append(colonne_proprietaire == self.user_id)
        if self.entites:
            conditions.append(colonne_entite.in_(list(self.entites)))
        return or_(*conditions) if conditions else false()

    def to_dict(self) -> dict:
        return {"niveau": self.niveau, "global": self.global_, "entites": sorted(str(e) for e in self.entites),
                "entite_principale_id": str(self.entite_principale_id) if self.entite_principale_id else None}


async def charger_perimetre(db: AsyncSession, user: User, *, permissions: set[str] | None = None) -> PerimetreOrg:
    have = permissions if permissions is not None else await load_user_permission_codes(db, user)
    principale = await db.scalar(select(OrgAffectation.entite_id).where(
        OrgAffectation.user_id == user.id, OrgAffectation.actif.is_(True),
        OrgAffectation.type_affectation == "PRINCIPALE"))
    if user.is_superuser or user_has_permission_codes(have, PERMISSION_PERIMETRE_GLOBAL):
        return PerimetreOrg(user_id=user.id, global_=True, entite_principale_id=principale)
    lignes = (await db.execute(select(OrgAffectation.entite_id, OrgAffectation.perimetre).where(
        OrgAffectation.user_id == user.id, OrgAffectation.actif.is_(True),
        OrgAffectation.perimetre != "PERSONNEL"))).all()
    if not lignes:
        return PerimetreOrg(user_id=user.id, entite_principale_id=principale)
    arbre = await charger_arbre(db)
    entites: set[uuid.UUID] = set()
    for entite_id, perimetre in lignes:
        if perimetre == "ENTITE_ET_SOUS_ENTITES":
            entites |= arbre.descendants(entite_id)
        else:
            entites.add(entite_id)
    return PerimetreOrg(user_id=user.id, entites=frozenset(entites), entite_principale_id=principale)


async def sous_arbre(db: AsyncSession, entite_id: uuid.UUID) -> set[uuid.UUID]:
    """Entité + descendantes : base des filtres « par direction / département / service »."""
    return (await charger_arbre(db)).descendants(entite_id)


# ------------------------------------------------------------------------------- contrôles
async def controles(db: AsyncSession) -> dict:
    arbre = await charger_arbre(db)
    entites = list(arbre.entites.values())
    actives = [e for e in entites if e.is_active]

    def res(e: OrgEntite, detail: str | None = None) -> dict:
        return {**entite_resume(e, arbre), "detail": detail}

    a_confirmer = [res(e, e.note_confirmation) for e in _ordre_arbre(arbre) if e.a_confirmer]
    postes_a_confirmer = (await db.execute(
        select(OrgPoste, OrgEntite.libelle).join(OrgEntite, OrgEntite.id == OrgPoste.entite_id)
        .where(OrgPoste.a_confirmer.is_(True), OrgPoste.actif.is_(True)))).all()

    par_cle: dict[str, list[OrgEntite]] = defaultdict(list)
    for e in actives:
        par_cle[e.cle].append(e)
    doublons = [
        {"libelle": groupe[0].libelle, "entites": [res(e) for e in groupe]}
        for cle, groupe in sorted(par_cle.items()) if cle and len(groupe) > 1
    ]
    racines_autorisees = {"CONSEIL"}
    non_rattachees = [res(e, "Aucune entité parente") for e in actives
                      if e.parent_id is None and e.type_entite not in racines_autorisees]

    incoherences = []
    for e in actives:
        parent = arbre.entites.get(e.parent_id) if e.parent_id else None
        if parent is None:
            continue
        if not parent.is_active:
            incoherences.append(res(e, f"Active sous une entité désactivée ({parent.libelle})"))
        rang_e, rang_p = RANGS.get(e.type_entite), RANGS.get(parent.type_entite)
        if rang_e is not None and rang_p is not None and rang_e <= rang_p:
            incoherences.append(res(e, f"{TYPE_LIBELLES[e.type_entite]} rattaché(e) à un niveau égal ou "
                                       f"inférieur ({TYPE_LIBELLES[parent.type_entite]} « {parent.libelle} »)"))

    inactives_occupees = (await db.execute(
        select(OrgEntite, func.count(func.distinct(OrgAffectation.user_id)))
        .join(OrgAffectation, OrgAffectation.entite_id == OrgEntite.id)
        .where(OrgEntite.is_active.is_(False), OrgAffectation.actif.is_(True)).group_by(OrgEntite.id))).all()
    for e, n in inactives_occupees:
        incoherences.append(res(e, f"Entité désactivée avec {n} utilisateur(s) encore affecté(s)"))

    sans_affectation_q = select(User.id, User.full_name, User.email).where(
        User.deleted_at.is_(None), User.is_active.is_(True),
        ~select(OrgAffectation.id).where(OrgAffectation.user_id == User.id, OrgAffectation.actif.is_(True),
                                         OrgAffectation.type_affectation == "PRINCIPALE").exists())
    nb_sans = await db.scalar(select(func.count()).select_from(sans_affectation_q.subquery())) or 0
    sans = (await db.execute(sans_affectation_q.order_by(User.full_name).limit(50))).all()

    agences = (await db.execute(select(Agence.id, Agence.code, Agence.libelle).where(
        Agence.deleted_at.is_(None), Agence.org_entite_id.is_(None)).order_by(Agence.code))).all()

    vacants = (await db.execute(
        select(OrgPoste, OrgEntite.libelle).join(OrgEntite, OrgEntite.id == OrgPoste.entite_id)
        .where(OrgPoste.actif.is_(True), OrgPoste.est_responsable.is_(True), OrgPoste.titulaire_user_id.is_(None),
               OrgEntite.is_active.is_(True)).order_by(OrgEntite.libelle))).all()

    correspondances = await resume_correspondances(db)
    return {
        "resume": {
            "entites": len(entites), "actives": len(actives), "a_confirmer": len(a_confirmer),
            "postes_a_confirmer": len(postes_a_confirmer), "doublons": len(doublons),
            "non_rattachees": len(non_rattachees), "incoherences": len(incoherences),
            "utilisateurs_sans_affectation": nb_sans, "agences_non_rattachees": len(agences),
            "responsables_vacants": len(vacants),
            "correspondances_en_attente": sum(c["valeurs"] for c in correspondances),
        },
        "a_confirmer": a_confirmer,
        "postes_a_confirmer": [{**poste_dict(p), "entite": lib} for p, lib in postes_a_confirmer],
        "doublons": doublons,
        "non_rattachees": non_rattachees,
        "incoherences": incoherences,
        "utilisateurs_sans_affectation": [{"id": str(i), "nom": n or m, "email": m} for i, n, m in sans],
        "agences_non_rattachees": [{"id": str(i), "code": c, "libelle": lib} for i, c, lib in agences],
        "responsables_vacants": [{**poste_dict(p), "entite": lib} for p, lib in vacants],
        "correspondances": correspondances,
    }


# --------------------------------------------------------------------------- correspondances
async def resume_correspondances(db: AsyncSession) -> list[dict]:
    out = []
    for lz in LIAISONS_TEXTE:
        row = (await db.execute(text(
            f"SELECT count(DISTINCT org_cle({lz.colonne_texte})), count(*) FROM {lz.table} "
            f"WHERE {lz.colonne_entite} IS NULL AND org_cle({lz.colonne_texte}) IS NOT NULL AND {lz.filtre}"
        ))).one()
        lies = await db.scalar(text(
            f"SELECT count(*) FROM {lz.table} WHERE {lz.colonne_entite} IS NOT NULL AND {lz.filtre}"))
        out.append({"liaison": lz.code, "module": lz.module, "libelle": lz.libelle,
                    "valeurs": int(row[0] or 0), "lignes": int(row[1] or 0), "lignes_rattachees": int(lies or 0)})
    return out


async def lister_correspondances(db: AsyncSession, liaison: str, *, limite: int = 300) -> dict:
    lz = LIAISONS_PAR_CODE.get(liaison)
    if lz is None or not lz.colonne_texte:
        raise _introuvable("Liaison")
    rows = (await db.execute(text(
        f"SELECT org_cle({lz.colonne_texte}) AS cle, count(*) AS n, "
        f"(array_agg(DISTINCT {lz.colonne_texte}))[1:5] AS exemples "
        f"FROM {lz.table} WHERE {lz.colonne_entite} IS NULL AND org_cle({lz.colonne_texte}) IS NOT NULL "
        f"AND {lz.filtre} GROUP BY 1 ORDER BY n DESC, cle LIMIT :lim"), {"lim": limite})).all()
    arbre = await charger_arbre(db)
    candidats = {e.cle: e for e in arbre.entites.values() if e.is_active and e.cle}
    for e in arbre.entites.values():
        for a in e.alias or []:
            candidats.setdefault(a, e)
    valeurs = []
    for cle, n, exemples in rows:
        proches = difflib.get_close_matches(cle, list(candidats), n=3, cutoff=0.72)
        valeurs.append({
            "cle": cle, "lignes": int(n), "exemples": list(exemples or []),
            # Suggestions seulement : rien n'est appliqué sans validation explicite d'un administrateur.
            "suggestions": [entite_resume(candidats[p], arbre) for p in proches],
        })
    return {"liaison": lz.code, "libelle": lz.libelle, "module": lz.module, "valeurs": valeurs}


async def appliquer_correspondance(db: AsyncSession, actor: User, liaison: str, cle_valeur: str,
                                   entite_id: uuid.UUID, *, memoriser_alias: bool = True,
                                   request: Request | None = None) -> dict:
    """Rattache toutes les lignes non rattachées portant ce libellé. Les lignes déjà rattachées
    et l'ancienne valeur texte ne sont jamais modifiées."""
    lz = LIAISONS_PAR_CODE.get(liaison)
    if lz is None or not lz.colonne_texte:
        raise _introuvable("Liaison")
    e = await _entite(db, entite_id)
    if not e.is_active:
        raise _erreur(f"L'entité « {e.libelle} » est désactivée", "ENTITE_INACTIVE", 409)
    cle = await _cle(db, cle_valeur)
    if not cle:
        raise _erreur("Valeur vide", "VALEUR_INVALIDE", 422)
    result = await db.execute(text(
        f"UPDATE {lz.table} SET {lz.colonne_entite} = :e WHERE {lz.colonne_entite} IS NULL "
        f"AND org_cle({lz.colonne_texte}) = :cle AND {lz.filtre}"), {"e": e.id, "cle": cle})
    alias_ajoute = False
    if memoriser_alias and cle != e.cle and cle not in (e.alias or []):
        e.alias = sorted({*(e.alias or []), cle})
        e.updated_by_id = actor.id
        alias_ajoute = True
    await _flush(db)
    resultat = {"liaison": lz.code, "valeur": cle, "entite_id": str(e.id), "entite": e.libelle,
                "lignes_rattachees": result.rowcount or 0, "alias_ajoute": alias_ajoute}
    await _auditer(db, actor, request, "org.correspondance.apply", "org_correspondance", e.id, after=resultat)
    return resultat


# --------------------------------------------------------------------------------- agences
async def rattacher_agence(db: AsyncSession, actor: User, agence_id: uuid.UUID, entite_id: uuid.UUID | None,
                           request: Request | None = None) -> dict:
    agence = await db.get(Agence, agence_id)
    if agence is None or agence.deleted_at is not None:
        raise _introuvable("Agence")
    avant = {"org_entite_id": str(agence.org_entite_id) if agence.org_entite_id else None}
    if entite_id is not None:
        e = await _entite(db, entite_id)
        if not e.is_active:
            raise _erreur(f"L'entité « {e.libelle} » est désactivée", "ENTITE_INACTIVE", 409)
    agence.org_entite_id = entite_id
    await _flush(db)
    apres = {"agence": f"{agence.code} — {agence.libelle}",
             "org_entite_id": str(entite_id) if entite_id else None}
    await _auditer(db, actor, request, "org.agence.attach", "agence", agence.id, before=avant, after=apres)
    return apres


async def lister_agences(db: AsyncSession) -> list[dict]:
    arbre = await charger_arbre(db)
    rows = (await db.scalars(select(Agence).where(Agence.deleted_at.is_(None)).order_by(Agence.code))).all()
    return [{"id": str(a.id), "code": a.code, "libelle": a.libelle, "ville": a.ville, "actif": a.is_active,
             "org_entite_id": str(a.org_entite_id) if a.org_entite_id else None,
             "rattachement": arbre.libelle_chemin(a.org_entite_id)} for a in rows]


# -------------------------------------------------------------------------------- historique
async def historique(db: AsyncSession, *, page: int = 1, size: int = 50, entite_id: uuid.UUID | None = None) -> dict:
    q = select(AuditLog, User.full_name).outerjoin(User, User.id == AuditLog.user_id).where(
        AuditLog.entity.in_(ENTITES_AUDITEES), AuditLog.action.like("org.%"))
    if entite_id:
        q = q.where(AuditLog.entity_id == str(entite_id))
    total = await db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = (await db.execute(q.order_by(AuditLog.created_at.desc()).offset((page - 1) * size).limit(size))).all()
    return {
        "total": total, "page": page, "size": size,
        "items": [{
            "id": str(log.id), "action": log.action, "entity": log.entity, "entity_id": log.entity_id,
            "utilisateur": nom, "avant": log.before_data, "apres": log.after_data,
            "request_id": log.request_id,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        } for log, nom in rows],
    }
