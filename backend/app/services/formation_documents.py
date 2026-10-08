"""Feuilles de présence signées : pièces GED CORE rattachées à une formation.

Stockage ``ged_documents`` (module ``formation``, entité ``formation_session``) : visibles dans
la GED de l'espace Audit, Contrôle & Conformité et indexées par l'OCR. Dépôt et retrait passent
par l'API Formation (``formation.attendance.manage``) et sont tracés dans l'historique de la
formation. Formation clôturée = pièces figées (réouverture motivée pour corriger).
"""

from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import func, select

from app.core.exceptions import AppError
from app.models import FormationSession, GedDocument, User
from app.services.document_ingest_service import enqueue_ocr
from app.services.formation_service import ESPACE_CODE, MODULE_CODE, FormationService, maintenant, propre
from app.services.ged_service import GedService

GED_ENTITE = "formation_session"
DOC_TYPE = "FEUILLE_PRESENCE_SIGNEE"


def peut_deposer(svc: FormationService, s: FormationSession) -> bool:
    return (s.statut in ("PLANIFIEE", "REALISEE", "CLOTUREE") and s.date_session <= date.today()
            and svc.ctx.peut("formation.attendance.manage"))


def peut_retirer(svc: FormationService, s: FormationSession) -> bool:
    if svc.ctx.peut("formation.admin"):
        return True
    return s.statut in ("PLANIFIEE", "REALISEE") and svc.ctx.peut("formation.attendance.manage")


def _q_documents(session_ids: list[str]):
    return select(GedDocument).where(
        GedDocument.module_code == MODULE_CODE, GedDocument.entity == GED_ENTITE,
        GedDocument.entity_id.in_(session_ids), GedDocument.deleted_at.is_(None))


async def compter(svc: FormationService, session_ids: list[uuid.UUID]) -> dict[str, int]:
    if not session_ids:
        return {}
    ids = [str(i) for i in session_ids]
    rows = await svc.db.execute(
        select(GedDocument.entity_id, func.count(GedDocument.id)).where(
            GedDocument.module_code == MODULE_CODE, GedDocument.entity == GED_ENTITE,
            GedDocument.entity_id.in_(ids), GedDocument.deleted_at.is_(None))
        .group_by(GedDocument.entity_id))
    return {eid: n for eid, n in rows.all()}


def sessions_avec_feuille():
    """Sous-requête des formations ayant au moins une feuille signée (filtre liste)."""
    return select(GedDocument.entity_id).where(
        GedDocument.module_code == MODULE_CODE, GedDocument.entity == GED_ENTITE,
        GedDocument.deleted_at.is_(None))


def _doc_dict(d: GedDocument, noms: dict[uuid.UUID, str]) -> dict:
    return {
        "id": str(d.id), "filename": d.filename, "mime_type": d.mime_type, "size_bytes": d.size_bytes,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "uploaded_by": noms.get(d.uploaded_by_id) if d.uploaded_by_id else None,
        "ocr_status": d.ocr_status,
    }


async def lister(svc: FormationService, sid: uuid.UUID) -> dict:
    s = await svc._session(sid)
    docs = list((await svc.db.scalars(_q_documents([str(s.id)]).order_by(GedDocument.created_at))).all())
    ids = {d.uploaded_by_id for d in docs if d.uploaded_by_id}
    noms: dict[uuid.UUID, str] = {}
    if ids:
        for u in (await svc.db.scalars(select(User).where(User.id.in_(ids)))).all():
            noms[u.id] = u.full_name or u.email
    return {
        "items": [_doc_dict(d, noms) for d in docs],
        "actions": {"deposer": peut_deposer(svc, s), "retirer": peut_retirer(svc, s)},
    }


async def _document(svc: FormationService, s: FormationSession, document_id: uuid.UUID) -> GedDocument:
    doc = await svc.db.get(GedDocument, document_id)
    if (doc is None or doc.deleted_at is not None or doc.module_code != MODULE_CODE
            or doc.entity != GED_ENTITE or doc.entity_id != str(s.id)):
        raise AppError("Document introuvable", 404, code="NOT_FOUND")
    return doc


async def deposer(svc: FormationService, sid: uuid.UUID, fichier: UploadFile) -> dict:
    svc.ctx.exiger("formation.attendance.manage")
    s = await svc._session(sid, verrou=True)
    if not peut_deposer(svc, s):
        raise AppError("Dépôt impossible : la formation doit avoir eu lieu et ne pas être annulée ni archivée.",
                       409, code="DEPOT_INTERDIT")
    doc = await GedService(svc.db).upload(file=fichier, espace_code=ESPACE_CODE, module_code=MODULE_CODE,
                                          entity=GED_ENTITE, entity_id=str(s.id), uploaded_by_id=svc.ctx.user.id)
    doc.doc_type = DOC_TYPE
    doc.title = f"Feuille de présence signée — {s.reference}"
    doc.description = propre(s.intitule) or None
    doc.reference = s.reference
    doc.date_document = s.date_session
    doc.archived_at = maintenant()
    doc.security_level = "internal"
    doc.ocr_status = "pending"
    await svc.db.flush()
    await svc.audit("formation.document.upload", GED_ENTITE, s.id,
                    after={"fichier": doc.filename, "document_id": str(doc.id), "taille": doc.size_bytes})
    await svc.db.commit()
    enqueue_ocr(doc.id)
    return await lister(svc, sid)


async def retirer(svc: FormationService, sid: uuid.UUID, document_id: uuid.UUID, motif: str | None) -> dict:
    if not svc.ctx.peut("formation.admin"):
        svc.ctx.exiger("formation.attendance.manage")
    motif = propre(motif)
    if not motif:
        raise AppError("Motif obligatoire", 422, code="MOTIF_OBLIGATOIRE")
    s = await svc._session(sid, verrou=True)
    if not peut_retirer(svc, s):
        raise AppError("Formation clôturée : rouvrez-la pour retirer une feuille signée.", 409, code="RETRAIT_INTERDIT")
    doc = await _document(svc, s, document_id)
    doc.deleted_at = maintenant()
    doc.is_active = False
    doc.deleted_by_id = svc.ctx.user.id
    doc.delete_reason = motif[:500]
    await svc.db.flush()
    await svc.audit("formation.document.delete", GED_ENTITE, s.id,
                    before={"fichier": doc.filename, "document_id": str(doc.id)}, after={"motif": motif})
    return await lister(svc, sid)


async def retirer_tous(svc: FormationService, sid: uuid.UUID, motif: str) -> None:
    """Suppression physique d'une formation : ses pièces passent à la corbeille GED."""
    for doc in (await svc.db.scalars(_q_documents([str(sid)]))).all():
        doc.deleted_at = maintenant()
        doc.is_active = False
        doc.deleted_by_id = svc.ctx.user.id
        doc.delete_reason = f"Formation supprimée : {motif}"[:500]


async def fichier(svc: FormationService, sid: uuid.UUID, document_id: uuid.UUID) -> tuple[GedDocument, Path]:
    s = await svc._session(sid)
    doc = await _document(svc, s, document_id)
    chemin = GedService(svc.db).absolute_path(doc.stored_path)
    if not chemin.exists():
        raise AppError("Fichier introuvable sur le serveur", 404, code="NOT_FOUND")
    await svc.audit("formation.document.download", GED_ENTITE, s.id,
                    after={"fichier": doc.filename, "document_id": str(doc.id)})
    return doc, chemin
