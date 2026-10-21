"""Destinations TEST approuvées (Phase 5) : hôtes depuis lesquels un test peut être construit."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime

from fastapi import Request
from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import AuditLog, User
from app.models.integrations import IntegrationDestination, IntegrationFournisseur
from app.services.audit_helpers import record_audit
from app.services.integrations.clients import _echapper_like, _noms, _personne, normaliser_nom
from app.services.integrations.ssrf import RefusSsrf, normaliser_hote, normaliser_port
from app.services.permission_service import user_has_permission_codes

P_VIEW = "core.admin.integrations.destinations.view"
P_MANAGE = "core.admin.integrations.destinations.manage"
P_APPROVE = "core.admin.integrations.destinations.approve"
METHODES_TEST = ("GET", "HEAD")
TRANSITIONS = {
    ("brouillon", "a_valider"): P_MANAGE,
    ("a_valider", "brouillon"): P_MANAGE,
    ("a_valider", "active"): P_APPROVE,
    ("active", "a_valider"): P_MANAGE,
    ("active", "suspendue"): P_APPROVE,
    ("suspendue", "a_valider"): P_MANAGE,
}
MOTIF_OBLIGATOIRE = frozenset({"suspendue"})
MODIFIABLES = frozenset({"brouillon", "a_valider"})
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
LIBELLES = {
    "integration_destination_create": "Création de la destination",
    "integration_destination_update": "Modification de la destination",
    "integration_destination_statut": "Changement de statut",
    "integration_destination_archive": "Archivage de la destination",
}


def _erreur(message: str, code: str, status: int) -> AppError:
    return AppError(message, status, code=code)


def _maintenant() -> datetime:
    return datetime.now(UTC)


def _code() -> str:
    return "DST-" + "".join(secrets.choice(_ALPHABET) for _ in range(8))


def _valider_hotes(hotes: list[str]) -> list[str]:
    if not hotes:
        raise _erreur("Au moins un nom d'hôte est requis", "HOTE_REQUIS", 422)
    if len(hotes) > 10:
        raise _erreur("10 hôtes maximum", "HOTES_MAX", 422)
    propres: list[str] = []
    for h in hotes:
        try:
            n = normaliser_hote(h)
        except RefusSsrf as exc:
            raise _erreur(exc.message, exc.code, 422) from exc
        if n not in propres:
            propres.append(n)
    return propres


def _valider_ports(ports: list[int]) -> list[int]:
    if not ports:
        ports = [443]
    propres: list[int] = []
    for p in ports:
        try:
            n = normaliser_port(p, list(range(1, 65536)))
        except RefusSsrf as exc:
            raise _erreur(exc.message, exc.code, 422) from exc
        if n not in (443,):
            raise _erreur("Seul le port 443 (HTTPS) est autorisé dans cette phase", "PORT_INTERDIT", 422)
        if n not in propres:
            propres.append(n)
    return propres


def _valider_methodes(methodes: list[str]) -> list[str]:
    if not methodes:
        methodes = list(METHODES_TEST)
    propres = []
    for m in methodes:
        u = (m or "").upper()
        if u not in METHODES_TEST:
            raise _erreur("Seules les méthodes GET et HEAD sont autorisées", "METHODE_INTERDITE", 422)
        if u not in propres:
            propres.append(u)
    return propres


async def _fournisseur(db: AsyncSession, fid: uuid.UUID) -> IntegrationFournisseur:
    f = await db.get(IntegrationFournisseur, fid)
    if f is None:
        raise _erreur("Fournisseur introuvable", "FOURNISSEUR_INTROUVABLE", 404)
    return f


async def _destination(db: AsyncSession, did: uuid.UUID, *, verrou=False) -> IntegrationDestination:
    q = select(IntegrationDestination).where(IntegrationDestination.id == did)
    if verrou:
        q = q.with_for_update()
    d = (await db.scalars(q)).first()
    if d is None:
        raise _erreur("Destination introuvable", "DESTINATION_INTROUVABLE", 404)
    return d


def _etat(d: IntegrationDestination) -> dict:
    return {
        "nom": d.nom, "statut": d.statut, "hotes": list(d.hotes or []), "ports": list(d.ports or []),
        "methodes": list(d.methodes or []), "operations": list(d.operations or []),
        "environnement": d.environnement, "revision": d.revision,
    }


async def _audit(db, actor, action, d, request, before=None, after=None):
    await record_audit(db, user=actor, action=action, entity="integration_destination", entity_id=str(d.id),
                       request=request, before=before, after=after, module_code="core")


def _transitions(d: IntegrationDestination) -> list[str]:
    return [cible for (src, cible), _p in TRANSITIONS.items() if src == d.statut]


async def fiche_destination(db: AsyncSession, did: uuid.UUID) -> dict:
    d = await _destination(db, did)
    f = await _fournisseur(db, d.fournisseur_id)
    noms = await _noms(db, {d.created_by_id, d.updated_by_id, d.valide_par_id, d.archived_by_id})
    return {
        "id": d.id, "code": d.code, "nom": d.nom, "fournisseur_id": d.fournisseur_id,
        "fournisseur_nom": f.nom, "fournisseur_statut": f.statut,
        "environnement": d.environnement, "protocole": d.protocole,
        "hotes": list(d.hotes or []), "ports": list(d.ports or []),
        "methodes": list(d.methodes or []), "operations": list(d.operations or []),
        "statut": d.statut, "motif_statut": d.motif_statut, "notes": d.notes,
        "revision": d.revision, "modifiable": d.statut in MODIFIABLES,
        "transitions": _transitions(d),
        "valide_par": _personne(noms, d.valide_par_id), "valide_le": d.valide_le,
        "created_at": d.created_at, "updated_at": d.updated_at,
        "cree_par": _personne(noms, d.created_by_id), "modifie_par": _personne(noms, d.updated_by_id),
        "archived_at": d.archived_at, "archive_par": _personne(noms, d.archived_by_id),
        "motif_archivage": d.motif_archivage,
        "avertissement": "Une destination active autorise uniquement des tests GET/HEAD HTTPS vers ces hôtes, en TEST.",
    }


async def lister_destinations(
    db: AsyncSession, *, q=None, statut=None, fournisseur_id=None, inclure_archivees=False,
    tri="updated_at", ordre="desc", page=1, size=25,
) -> dict:
    t = IntegrationDestination
    filtre = []
    if not inclure_archivees and statut != "archivee":
        filtre.append(t.statut != "archivee")
    if statut:
        filtre.append(t.statut == statut)
    if fournisseur_id:
        filtre.append(t.fournisseur_id == fournisseur_id)
    if q and q.strip():
        like = f"%{_echapper_like(q.strip())}%"
        filtre.append(t.nom.ilike(like) | t.code.ilike(like))
    where = and_(*filtre) if filtre else True
    total = await db.scalar(select(func.count()).select_from(t).where(where))
    colonne = {"nom": t.nom, "code": t.code, "statut": t.statut, "valide_le": t.valide_le}.get(tri, t.updated_at)
    colonne = colonne.asc().nulls_last() if ordre == "asc" else colonne.desc().nulls_last()
    rows = (await db.scalars(
        select(t).where(where).order_by(colonne, t.id).offset((page - 1) * size).limit(size)
    )).all()
    fids = {d.fournisseur_id for d in rows}
    noms_f = dict((await db.execute(
        select(IntegrationFournisseur.id, IntegrationFournisseur.nom).where(IntegrationFournisseur.id.in_(fids))
    )).all()) if fids else {}
    items = []
    for d in rows:
        items.append({
            "id": d.id, "code": d.code, "nom": d.nom, "fournisseur_id": d.fournisseur_id,
            "fournisseur_nom": noms_f.get(d.fournisseur_id), "ports": list(d.ports or []),
            "nb_operations": len(d.operations or []),
            "environnement": d.environnement, "statut": d.statut,
            "hotes": list(d.hotes or []), "methodes": list(d.methodes or []),
            "updated_at": d.updated_at, "valide_le": d.valide_le,
        })
    return {"items": items, "total": int(total or 0), "page": page, "size": size}


async def creer_destination(db: AsyncSession, actor: User, data: dict, request: Request | None) -> dict:
    f = await _fournisseur(db, data["fournisseur_id"])
    d = IntegrationDestination(
        code=_code(), nom=data["nom"], nom_normalise=normaliser_nom(data["nom"]),
        fournisseur_id=f.id, environnement="TEST", protocole="https",
        hotes=_valider_hotes(data.get("hotes") or []),
        ports=_valider_ports(data.get("ports") or [443]),
        methodes=_valider_methodes(data.get("methodes") or list(METHODES_TEST)),
        operations=[str(x) for x in (data.get("operations") or [])],
        notes=data.get("notes"), created_by_id=actor.id, updated_by_id=actor.id,
    )
    db.add(d)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise _erreur("Une destination de même nom existe déjà pour ce fournisseur", "DESTINATION_DOUBLON", 409) from exc
    await _audit(db, actor, "integration_destination_create", d, request, after=_etat(d))
    await db.refresh(d)
    return await fiche_destination(db, d.id)


async def modifier_destination(db: AsyncSession, actor: User, did: uuid.UUID, data: dict, fournis: set[str],
                               request: Request | None) -> dict:
    d = await _destination(db, did, verrou=True)
    if d.statut not in MODIFIABLES:
        raise _erreur("Destination verrouillée", "DESTINATION_VERROUILLEE", 409)
    if data.get("revision") != d.revision:
        raise _erreur("La destination a été modifiée entre-temps", "CONFLIT_REVISION", 409)
    avant = _etat(d)
    if "nom" in fournis and data.get("nom"):
        d.nom, d.nom_normalise = data["nom"], normaliser_nom(data["nom"])
    if "hotes" in fournis:
        d.hotes = _valider_hotes(data.get("hotes") or [])
    if "ports" in fournis:
        d.ports = _valider_ports(data.get("ports") or [443])
    if "methodes" in fournis:
        d.methodes = _valider_methodes(data.get("methodes") or list(METHODES_TEST))
    if "operations" in fournis:
        d.operations = [str(x) for x in (data.get("operations") or [])]
    if "notes" in fournis:
        d.notes = data.get("notes")
    d.updated_by_id = actor.id
    d.revision += 1
    try:
        await db.flush()
    except IntegrityError as exc:
        raise _erreur("Une destination de même nom existe déjà pour ce fournisseur", "DESTINATION_DOUBLON", 409) from exc
    await _audit(db, actor, "integration_destination_update", d, request, before=avant, after=_etat(d))
    return await fiche_destination(db, d.id)


async def changer_statut(db: AsyncSession, actor: User, have: set[str], did: uuid.UUID, revision: int,
                         statut: str, motif: str | None, request: Request | None) -> dict:
    d = await _destination(db, did, verrou=True)
    if revision != d.revision:
        raise _erreur("La destination a été modifiée entre-temps", "CONFLIT_REVISION", 409)
    perm = TRANSITIONS.get((d.statut, statut))
    if perm is None:
        raise _erreur("Transition interdite", "TRANSITION_INTERDITE", 409)
    if not user_has_permission_codes(have, perm):
        raise _erreur("Permission insuffisante pour cette transition", "PERMISSION_INSUFFISANTE", 403)
    if statut in MOTIF_OBLIGATOIRE and not (motif and len(motif.strip()) >= 3):
        raise _erreur("Motif obligatoire", "MOTIF_OBLIGATOIRE", 422)
    if statut == "active":
        f = await _fournisseur(db, d.fournisseur_id)
        if f.statut != "valide":
            raise _erreur("Le fournisseur doit être validé avant d'approuver une destination", "FOURNISSEUR_NON_VALIDE", 422)
        if not d.hotes:
            raise _erreur("Au moins un hôte approuvé est requis", "HOTE_REQUIS", 422)
        d.valide_par_id, d.valide_le = actor.id, _maintenant()
    avant = _etat(d)
    d.statut, d.motif_statut = statut, motif
    d.updated_by_id = actor.id
    d.revision += 1
    await db.flush()
    await _audit(db, actor, "integration_destination_statut", d, request, before=avant, after=_etat(d))
    if statut == "suspendue":
        from app.services.integrations.supervision import ouvrir_alerte
        await ouvrir_alerte(
            db, "destination_suspendue", f"{d.id}", d.fournisseur_id, d.id, None,
            f"Destination « {d.nom} » suspendue.", {"motif": motif},
        )
    return await fiche_destination(db, d.id)


async def archiver_destination(db: AsyncSession, actor: User, did: uuid.UUID, revision: int, motif: str,
                               request: Request | None) -> dict:
    d = await _destination(db, did, verrou=True)
    if revision != d.revision:
        raise _erreur("La destination a été modifiée entre-temps", "CONFLIT_REVISION", 409)
    if d.statut == "archivee":
        return await fiche_destination(db, d.id)
    avant = _etat(d)
    d.statut = "archivee"
    d.archived_at, d.archived_by_id, d.motif_archivage = _maintenant(), actor.id, motif
    d.updated_by_id = actor.id
    d.revision += 1
    await db.flush()
    await _audit(db, actor, "integration_destination_archive", d, request, before=avant, after=_etat(d))
    return await fiche_destination(db, d.id)


async def historique(db: AsyncSession, did: uuid.UUID, *, page=1, size=50) -> dict:
    await _destination(db, did)
    a = AuditLog
    filtre = and_(a.entity == "integration_destination", a.entity_id == str(did))
    total = await db.scalar(select(func.count()).select_from(a).where(filtre))
    rows = (await db.scalars(
        select(a).where(filtre).order_by(a.created_at.desc()).offset((page - 1) * size).limit(size)
    )).all()
    noms = await _noms(db, {r.user_id for r in rows})
    return {
        "items": [
            {
                "id": r.id, "action": r.action, "libelle": LIBELLES.get(r.action, r.action),
                "acteur": _personne(noms, r.user_id),
                "details": {"avant": r.before_data or {}, "apres": r.after_data or {}},
                "created_at": r.created_at,
            }
            for r in rows
        ],
        "total": int(total or 0), "page": page, "size": size,
    }
