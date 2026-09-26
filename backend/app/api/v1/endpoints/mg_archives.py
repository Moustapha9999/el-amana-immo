"""API Archives MG — memoire documentaire moyens-generaux."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_module_access, require_permission
from app.models.auth import User
from app.schemas.common import PaginatedResponse
from app.schemas.mg_archives import (
    ArchiveDashboardOut,
    ArchiveDocOut,
    ArchiveDocUpdate,
    ArchiveMissingItem,
    ArchiveSoftDeleteIn,
)
from app.services.audit_helpers import record_audit
from app.services.ged_service import GedService
from app.services.mg_archives_service import ESPACE, MgArchivesService

router = APIRouter(prefix="/mg/archives", tags=["mg-archives"])
_module = [Depends(require_module_access("archives-mg"))]


async def _audit(db, user, action, entity_id, request, after=None):
    await record_audit(
        db,
        user=user,
        action=action,
        entity="ged_document",
        entity_id=str(entity_id) if entity_id else None,
        request=request,
        after=after,
        espace_code=ESPACE,
        module_code="archives-mg",
    )


@router.get("/dashboard", response_model=ArchiveDashboardOut, dependencies=_module)
async def dashboard(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.archives.view")),
):
    return await MgArchivesService(db).dashboard()


@router.get(
    "/documents",
    response_model=PaginatedResponse[ArchiveDocOut],
    dependencies=_module,
)
async def list_documents(
    module_code: str | None = None,
    q: str | None = None,
    doc_type: str | None = None,
    entity: str | None = None,
    agence_id: UUID | None = None,
    fournisseur_id: UUID | None = None,
    department_id: UUID | None = None,
    year: int | None = None,
    date_debut: date | None = None,
    date_fin: date | None = None,
    uploaded_by_id: UUID | None = None,
    mine: bool = False,
    recent_days: int | None = None,
    trash: bool = False,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.archives.view")),
):
    items, total = await MgArchivesService(db).list_documents(
        module_code=module_code,
        q=q,
        doc_type=doc_type,
        entity=entity,
        agence_id=agence_id,
        fournisseur_id=fournisseur_id,
        department_id=department_id,
        year=year,
        date_debut=date_debut,
        date_fin=date_fin,
        uploaded_by_id=uploaded_by_id,
        mine_only=mine,
        recent_days=recent_days,
        trash=trash,
        page=page,
        size=size,
        user=user,
    )
    return PaginatedResponse(items=items, total=total, page=page, size=size)


@router.get("/documents/{document_id}", response_model=ArchiveDocOut, dependencies=_module)
async def get_document(
    document_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.archives.view")),
):
    row = await MgArchivesService(db).get_document_out(document_id)
    await _audit(db, user, "archive_view", document_id, request)
    return row


@router.patch("/documents/{document_id}", response_model=ArchiveDocOut, dependencies=_module)
async def update_document(
    document_id: UUID,
    body: ArchiveDocUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.archives.update")),
):
    row = await MgArchivesService(db).update_document(document_id, body, user)
    await _audit(db, user, "archive_update", document_id, request, after=row.model_dump(mode="json"))
    return row


@router.post(
    "/documents",
    response_model=ArchiveDocOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=_module,
)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    module_code: str = Form(...),
    entity: str = Form(...),
    entity_id: str = Form(...),
    title: str | None = Form(None),
    description: str | None = Form(None),
    doc_type: str | None = Form(None),
    reference: str | None = Form(None),
    date_document: date | None = Form(None),
    agence_id: UUID | None = Form(None),
    department_id: UUID | None = Form(None),
    fournisseur_id: UUID | None = Form(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.archives.create", "mg.archives.archive")),
):
    row = await MgArchivesService(db).upload_manual(
        file=file,
        user=user,
        module_code=module_code,
        entity=entity,
        entity_id=entity_id,
        title=title,
        description=description,
        doc_type=doc_type,
        reference=reference,
        date_document=date_document,
        agence_id=agence_id,
        department_id=department_id,
        fournisseur_id=fournisseur_id,
    )
    await _audit(
        db,
        user,
        "archive_manual",
        row.id,
        request,
        after={"module_code": row.module_code, "entity": row.entity, "filename": row.filename},
    )
    return row


@router.get("/documents/{document_id}/download", dependencies=_module)
async def download_document(
    document_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.archives.download", "mg.archives.view")),
):
    svc = MgArchivesService(db)
    row = await svc.get_document(document_id)
    path = GedService(db).absolute_path(row.stored_path)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Fichier introuvable sur disque")
    await _audit(db, user, "archive_download", document_id, request)
    return FileResponse(
        path,
        filename=row.filename,
        media_type=row.mime_type or "application/octet-stream",
    )


@router.post("/documents/{document_id}/desactiver", response_model=ArchiveDocOut, dependencies=_module)
async def soft_delete_document(
    document_id: UUID,
    body: ArchiveSoftDeleteIn | None = None,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.archives.update")),
):
    reason = body.reason if body else None
    row = await MgArchivesService(db).soft_delete(document_id, user, reason)
    await _audit(db, user, "archive_delete", document_id, request, after={"reason": reason})
    return row


@router.delete("/documents/{document_id}", response_model=ArchiveDocOut, dependencies=_module)
async def delete_document(
    document_id: UUID,
    request: Request,
    reason: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.archives.update")),
):
    row = await MgArchivesService(db).soft_delete(document_id, user, reason)
    await _audit(db, user, "archive_delete", document_id, request)
    return row


@router.post("/documents/{document_id}/restore", response_model=ArchiveDocOut, dependencies=_module)
async def restore_document(
    document_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.archives.restore")),
):
    row = await MgArchivesService(db).restore(document_id, user)
    await _audit(db, user, "archive_restore", document_id, request)
    return row


@router.delete("/documents/{document_id}/purge", status_code=status.HTTP_204_NO_CONTENT, dependencies=_module)
async def purge_document(
    document_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.archives.delete")),
):
    await MgArchivesService(db).purge(document_id, user)
    await _audit(db, user, "archive_purge", document_id, request)


@router.get("/missing", response_model=list[ArchiveMissingItem], dependencies=_module)
async def list_missing(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.archives.view")),
):
    return await MgArchivesService(db).list_missing()


@router.get("/dossiers/{source_module}/{source_type}/{source_id}", dependencies=_module)
async def get_dossier(
    source_module: str,
    source_type: str,
    source_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.archives.view")),
):
    return await MgArchivesService(db).dossier(source_module, source_type, source_id)


@router.get("/trash", response_model=PaginatedResponse[ArchiveDocOut], dependencies=_module)
async def trash(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
    q: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.archives.view")),
):
    items, total = await MgArchivesService(db).list_documents(
        trash=True, page=page, size=size, q=q, user=user
    )
    return PaginatedResponse(items=items, total=total, page=page, size=size)
