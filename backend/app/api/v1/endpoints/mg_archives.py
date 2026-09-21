"""API Archives MG — vue GED espace moyens-generaux."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_module_access, require_permission
from app.models.auth import User
from app.schemas.mg_ops import ArchiveDocOut
from app.services.mg_ops_service import MgOpsService

router = APIRouter(prefix="/mg/archives", tags=["mg-archives"])
_module = [Depends(require_module_access("archives-mg"))]


@router.get("/documents", response_model=list[ArchiveDocOut], dependencies=_module)
async def list_documents(
    module_code: str | None = None,
    q: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.archives.view")),
):
    rows = await MgOpsService(db).list_archives(module_code=module_code, q=q, limit=limit)
    return [
        ArchiveDocOut(
            id=d.id,
            filename=d.filename,
            original_name=d.filename,
            module_code=d.module_code,
            espace_code=d.espace_code,
            entity=d.entity,
            entity_id=d.entity_id,
            created_at=d.created_at,
            mime_type=d.mime_type,
            size_bytes=d.size_bytes,
        )
        for d in rows
    ]
