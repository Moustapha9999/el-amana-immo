"""Document Service — ingestion, recherche, OCR retry, téléchargement."""

from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.exceptions import AppError, raise_http_from_app
from app.db.session import get_db
from app.models import User
from app.schemas.documents import DocumentListOut, DocumentOut, document_out
from app.services.audit_helpers import record_audit
from app.services.document_ingest_service import DocumentIngestService
from app.services.document_query_service import DocumentQueryService
from app.services.ged_service import GedService

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    espace_code: str = Form(...),
    module_code: str = Form(...),
    entity: str = Form("manuel"),
    entity_id: str | None = Form(None),
    doc_type: str | None = Form(None),
    title: str | None = Form(None),
    description: str | None = Form(None),
    reference: str | None = Form(None),
    date_document: date | None = Form(None),
    agence_id: UUID | None = Form(None),
    department_id: UUID | None = Form(None),
    fournisseur_id: UUID | None = Form(None),
    security_level: str = Form("internal"),
    user: User = Depends(require_permission("ged.write")),
    db: AsyncSession = Depends(get_db),
):
    """Flux 1 — upload manuel + OCR asynchrone."""
    try:
        eid = (entity_id or "").strip() or str(uuid4())
        query = DocumentQueryService(db)
        allowed = await query.user_espace_codes(user)
        espace = espace_code.strip().lower()
        if not user.is_superuser and espace not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Espace non autorisé")

        row = await DocumentIngestService(db).ingest_document(
            file=file,
            espace_code=espace,
            module_code=module_code,
            entity=entity,
            entity_id=eid,
            uploaded_by_id=user.id,
            title=title,
            description=description,
            doc_type=doc_type,
            reference=reference,
            date_document=date_document,
            agence_id=agence_id,
            department_id=department_id,
            fournisseur_id=fournisseur_id,
            security_level=security_level,
        )
        await record_audit(
            db,
            user=user,
            action="document_ingest",
            entity="ged_document",
            entity_id=str(row.id),
            after={
                "espace_code": row.espace_code,
                "module_code": row.module_code,
                "filename": row.filename,
                "ocr_status": row.ocr_status,
            },
            request=request,
            espace_code=row.espace_code,
            module_code="documents",
        )
        return document_out(row)
    except AppError as exc:
        raise_http_from_app(exc)


@router.post(
    "/from-operation",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
)
async def archive_from_operation(
    request: Request,
    file: UploadFile = File(...),
    espace_code: str = Form(...),
    module_code: str = Form(...),
    source_type: str = Form(..., description="entity métier (= entity)"),
    source_id: str = Form(..., description="id opération (= entity_id)"),
    doc_type: str | None = Form(None),
    title: str | None = Form(None),
    description: str | None = Form(None),
    reference: str | None = Form(None),
    date_document: date | None = Form(None),
    agence_id: UUID | None = Form(None),
    department_id: UUID | None = Form(None),
    fournisseur_id: UUID | None = Form(None),
    security_level: str = Form("internal"),
    user: User = Depends(require_permission("ged.write")),
    db: AsyncSession = Depends(get_db),
):
    """Flux 2 — archivage depuis une opération métier."""
    try:
        query = DocumentQueryService(db)
        allowed = await query.user_espace_codes(user)
        espace = espace_code.strip().lower()
        if not user.is_superuser and espace not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Espace non autorisé")

        row = await DocumentIngestService(db).ingest_document(
            file=file,
            espace_code=espace,
            module_code=module_code,
            entity=source_type.strip(),
            entity_id=source_id.strip(),
            uploaded_by_id=user.id,
            title=title,
            description=description,
            doc_type=doc_type,
            reference=reference,
            date_document=date_document,
            agence_id=agence_id,
            department_id=department_id,
            fournisseur_id=fournisseur_id,
            security_level=security_level,
        )
        await record_audit(
            db,
            user=user,
            action="document_archive_operation",
            entity="ged_document",
            entity_id=str(row.id),
            after={
                "source_type": row.entity,
                "source_id": row.entity_id,
                "module_code": row.module_code,
                "ocr_status": row.ocr_status,
            },
            request=request,
            espace_code=row.espace_code,
            module_code=row.module_code,
        )
        return document_out(row)
    except AppError as exc:
        raise_http_from_app(exc)


@router.get("/search", response_model=DocumentListOut)
async def search_documents(
    request: Request,
    espace_code: str | None = Query(None),
    module_code: str | None = Query(None),
    doc_type: str | None = Query(None),
    agence_id: UUID | None = Query(None),
    fournisseur_id: UUID | None = Query(None),
    department_id: UUID | None = Query(None),
    ocr_status: str | None = Query(None),
    security_level: str | None = Query(None),
    date_debut: date | None = Query(None),
    date_fin: date | None = Query(None),
    q: str | None = Query(None),
    search_ocr: bool = Query(False),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    user: User = Depends(require_permission("ged.read")),
    db: AsyncSession = Depends(get_db),
):
    try:
        rows, total, meta = await DocumentQueryService(db).search(
            user=user,
            espace_code=espace_code,
            module_code=module_code,
            doc_type=doc_type,
            agence_id=agence_id,
            fournisseur_id=fournisseur_id,
            department_id=department_id,
            ocr_status=ocr_status,
            security_level=security_level,
            date_debut=date_debut,
            date_fin=date_fin,
            q=q,
            search_ocr=search_ocr,
            page=page,
            size=size,
            general=espace_code is None,
        )
        await record_audit(
            db,
            user=user,
            action="document_search",
            entity="ged_document",
            entity_id=None,
            after={"q": q, "search_ocr": search_ocr, "total": total},
            request=request,
            module_code="documents",
        )
        return DocumentListOut(
            items=[document_out(r) for r in rows],
            total=total,
            page=page,
            size=size,
            ocr_pending_hint=bool(meta.get("ocr_pending_hint")),
        )
    except AppError as exc:
        raise_http_from_app(exc)


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: UUID,
    request: Request,
    user: User = Depends(require_permission("ged.read")),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await DocumentQueryService(db).get_accessible(document_id, user)
        await record_audit(
            db,
            user=user,
            action="document_view",
            entity="ged_document",
            entity_id=str(row.id),
            request=request,
            espace_code=row.espace_code,
            module_code="documents",
        )
        return document_out(row, include_ocr_text=True)
    except AppError as exc:
        raise_http_from_app(exc)


@router.post("/{document_id}/retry-ocr", response_model=DocumentOut)
async def retry_ocr(
    document_id: UUID,
    request: Request,
    user: User = Depends(require_permission("ged.write")),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await DocumentQueryService(db).get_accessible(document_id, user)
        row = await DocumentIngestService(db).retry_ocr(row.id)
        await record_audit(
            db,
            user=user,
            action="ocr_retry",
            entity="ged_document",
            entity_id=str(row.id),
            after={"ocr_status": row.ocr_status},
            request=request,
            espace_code=row.espace_code,
            module_code="documents",
        )
        return document_out(row)
    except AppError as exc:
        raise_http_from_app(exc)


@router.get("/{document_id}/download")
async def download_document(
    document_id: UUID,
    request: Request,
    user: User = Depends(require_permission("ged.read")),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await DocumentQueryService(db).get_accessible(document_id, user)
        path = GedService(db).absolute_path(row.stored_path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Fichier introuvable sur le serveur")
        await record_audit(
            db,
            user=user,
            action="document_download",
            entity="ged_document",
            entity_id=str(row.id),
            after={"filename": row.filename},
            request=request,
            espace_code=row.espace_code,
            module_code="documents",
        )
        return FileResponse(
            path,
            filename=row.filename,
            media_type=row.mime_type or "application/octet-stream",
        )
    except AppError as exc:
        raise_http_from_app(exc)
