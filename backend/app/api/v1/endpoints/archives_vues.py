"""Vues Archives — départementale et Archive Générale (même table ged_documents)."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_module_access, require_permission
from app.core.exceptions import AppError, raise_http_from_app
from app.db.session import get_db
from app.models import User
from app.schemas.documents import DocumentListOut, document_out
from app.services.audit_helpers import record_audit
from app.services.document_query_service import DocumentQueryService

router = APIRouter(prefix="/doc-archives", tags=["archives-vues"])


@router.get(
    "/general",
    response_model=DocumentListOut,
    dependencies=[Depends(require_module_access("archives-generales"))],
)
async def archives_generales(
    request: Request,
    espace_code: str | None = Query(None, description="Filtrer un espace"),
    espaces: str | None = Query(None, description="Liste CSV d'espaces"),
    module_code: str | None = Query(None),
    doc_type: str | None = Query(None),
    agence_id: UUID | None = Query(None),
    fournisseur_id: UUID | None = Query(None),
    ocr_status: str | None = Query(None),
    date_debut: date | None = Query(None),
    date_fin: date | None = Query(None),
    q: str | None = Query(None),
    search_ocr: bool = Query(False),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    user: User = Depends(require_permission("archives.general.view")),
    db: AsyncSession = Depends(get_db),
):
    """Archive Générale — multi-département, filtré par permissions serveur."""
    try:
        espace_list = None
        if espaces:
            espace_list = [c.strip() for c in espaces.split(",") if c.strip()]
        rows, total, meta = await DocumentQueryService(db).search(
            user=user,
            espace_code=espace_code,
            espace_codes=espace_list,
            module_code=module_code,
            doc_type=doc_type,
            agence_id=agence_id,
            fournisseur_id=fournisseur_id,
            ocr_status=ocr_status,
            date_debut=date_debut,
            date_fin=date_fin,
            q=q,
            search_ocr=search_ocr,
            page=page,
            size=size,
            general=True,
        )
        await record_audit(
            db,
            user=user,
            action="archives_general_list",
            entity="ged_document",
            entity_id=None,
            after={"total": total, "q": q, "search_ocr": search_ocr},
            request=request,
            module_code="archives-generales",
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


@router.get("/{espace_code}", response_model=DocumentListOut)
async def archives_departement(
    espace_code: str,
    request: Request,
    module_code: str | None = Query(None),
    doc_type: str | None = Query(None),
    agence_id: UUID | None = Query(None),
    fournisseur_id: UUID | None = Query(None),
    ocr_status: str | None = Query(None),
    date_debut: date | None = Query(None),
    date_fin: date | None = Query(None),
    q: str | None = Query(None),
    search_ocr: bool = Query(False),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    user: User = Depends(require_permission("ged.read")),
    db: AsyncSession = Depends(get_db),
):
    """Vue Archives d'un département (espace_code)."""
    try:
        rows, total, meta = await DocumentQueryService(db).search(
            user=user,
            espace_code=espace_code,
            module_code=module_code,
            doc_type=doc_type,
            agence_id=agence_id,
            fournisseur_id=fournisseur_id,
            ocr_status=ocr_status,
            date_debut=date_debut,
            date_fin=date_fin,
            q=q,
            search_ocr=search_ocr,
            page=page,
            size=size,
            general=False,
        )
        await record_audit(
            db,
            user=user,
            action="archives_espace_list",
            entity="ged_document",
            entity_id=None,
            after={"espace_code": espace_code, "total": total},
            request=request,
            espace_code=espace_code.strip().lower(),
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
