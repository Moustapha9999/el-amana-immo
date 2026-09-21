"""API Notes de frais MG."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_module_access, require_permission
from app.models.auth import Agence, User
from app.schemas.mg_ops import NoteCreate, NoteOut, NoteUpdate, TransitionIn
from app.services.mg_ops_service import MgOpsService
from app.services.mg_pdf_service import pdf_note_frais

router = APIRouter(prefix="/mg/notes-frais", tags=["mg-notes-frais"])
_module = [Depends(require_module_access("notes-frais"))]


@router.get("/agences", dependencies=_module)
async def list_agences(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.notes.view")),
):
    rows = (
        await db.execute(
            select(Agence)
            .where(Agence.is_active.is_(True), Agence.deleted_at.is_(None))
            .order_by(Agence.libelle)
        )
    ).scalars().all()
    return [{"id": str(a.id), "code": a.code, "libelle": a.libelle} for a in rows]


@router.get("/notes", response_model=list[NoteOut], dependencies=_module)
async def list_notes(
    statut: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.notes.view")),
):
    return await MgOpsService(db).list_notes(statut=statut)


@router.post("/notes", response_model=NoteOut, dependencies=_module)
async def create_note(
    body: NoteCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.notes.create")),
):
    return await MgOpsService(db).create_note(body, user)


@router.get("/notes/{note_id}", response_model=NoteOut, dependencies=_module)
async def get_note(
    note_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.notes.view")),
):
    return await MgOpsService(db).get_note(note_id)


@router.patch("/notes/{note_id}", response_model=NoteOut, dependencies=_module)
async def update_note(
    note_id: UUID,
    body: NoteUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.notes.create")),
):
    return await MgOpsService(db).update_note(note_id, body)


@router.post("/notes/{note_id}/transition", response_model=NoteOut, dependencies=_module)
async def transition_note(
    note_id: UUID,
    body: TransitionIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.notes.approve")),
):
    return await MgOpsService(db).transition_note(note_id, body.action, user)


@router.get("/notes/{note_id}/pdf", dependencies=_module)
async def note_pdf(
    note_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.notes.export")),
):
    note = await MgOpsService(db).get_note(note_id)
    data = pdf_note_frais(note)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{note.reference}.pdf"'},
    )
