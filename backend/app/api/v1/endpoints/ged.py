"""API GED métier — upload / liste / téléchargement (Login 1 ou Login 2).

Les pièces immo (`pieces_jointes`) et archives Excel restent hors de cette API.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.exceptions import AppError, raise_http_from_app
from app.db.session import get_db
from app.models import User
from app.schemas.common import MessageResponse
from app.services.audit_helpers import record_audit
from app.services.ged_service import GedService

router = APIRouter(prefix="/ged", tags=["ged"])


class GedDocumentRead(BaseModel):
    id: UUID
    espace_code: str
    module_code: str
    entity: str
    entity_id: str
    filename: str
    mime_type: str | None = None
    size_bytes: int = 0
    created_at: object | None = None

    model_config = {"from_attributes": True}


class GedDocumentListRead(BaseModel):
    items: list[GedDocumentRead] = Field(default_factory=list)


def _to_read(row) -> GedDocumentRead:
    return GedDocumentRead.model_validate(row)


@router.post(
    "/documents",
    response_model=GedDocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    espace_code: str = Form(...),
    module_code: str = Form(...),
    entity: str = Form(...),
    entity_id: str = Form(...),
    user: User = Depends(require_permission("ged.write")),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await GedService(db).upload(
            file=file,
            espace_code=espace_code.strip().lower(),
            module_code=module_code.strip().lower(),
            entity=entity.strip(),
            entity_id=entity_id.strip(),
            uploaded_by_id=user.id,
        )
        await record_audit(
            db,
            user=user,
            action="ged_upload",
            entity="ged_document",
            entity_id=str(row.id),
            after={
                "module_code": row.module_code,
                "entity": row.entity,
                "filename": row.filename,
                "size_bytes": row.size_bytes,
            },
            request=request,
        )
        return _to_read(row)
    except AppError as exc:
        raise_http_from_app(exc)


@router.get("/documents", response_model=GedDocumentListRead)
async def list_documents(
    module_code: str = Query(...),
    entity: str = Query(...),
    entity_id: str = Query(...),
    _: User = Depends(require_permission("ged.read")),
    db: AsyncSession = Depends(get_db),
):
    rows = await GedService(db).list_for_entity(
        module_code=module_code.strip().lower(),
        entity=entity.strip(),
        entity_id=entity_id.strip(),
    )
    return GedDocumentListRead(items=[_to_read(r) for r in rows])


@router.get("/documents/{document_id}/download")
async def download_document(
    document_id: UUID,
    _: User = Depends(require_permission("ged.read")),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await GedService(db).get(document_id)
        path = GedService(db).absolute_path(row.stored_path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Fichier introuvable sur le serveur")
        return FileResponse(
            path,
            filename=row.filename,
            media_type=row.mime_type or "application/octet-stream",
        )
    except AppError as exc:
        raise_http_from_app(exc)


@router.delete("/documents/{document_id}", response_model=MessageResponse)
async def delete_document(
    document_id: UUID,
    request: Request,
    user: User = Depends(require_permission("ged.write")),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await GedService(db).soft_delete(document_id)
        await record_audit(
            db,
            user=user,
            action="ged_delete",
            entity="ged_document",
            entity_id=str(row.id),
            after={"filename": row.filename, "module_code": row.module_code},
            request=request,
        )
        return MessageResponse(message="Document GED supprimé")
    except AppError as exc:
        raise_http_from_app(exc)
