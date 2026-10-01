"""Vues Archives — départementale et Archive Générale (même table ged_documents)."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_module_access, require_permission
from app.core.exceptions import AppError, raise_http_from_app
from app.db.session import get_db
from app.models import User
from app.schemas.documents import DocumentDashboardOut, DocumentListOut, document_out
from app.services.audit_helpers import record_audit
from app.services.document_query_service import DocumentQueryService
from app.services.document_reporting_service import DocumentReportingService

router = APIRouter(prefix="/doc-archives", tags=["archives-vues"])


@router.get(
    "/general/dashboard",
    response_model=DocumentDashboardOut,
    dependencies=[Depends(require_module_access("archives-generales"))],
)
async def archives_generales_dashboard(
    request: Request,
    espace_code: str | None = Query(None),
    user: User = Depends(require_permission("archives.general.view")),
    db: AsyncSession = Depends(get_db),
):
    try:
        stats = await DocumentQueryService(db).dashboard_stats(
            user, espace_code=espace_code, general=True
        )
        await record_audit(
            db,
            user=user,
            action="archives_general_dashboard",
            entity="ged_document",
            entity_id=None,
            after={"total": stats.get("total")},
            request=request,
            module_code="archives-generales",
        )
        return DocumentDashboardOut(
            total=stats["total"],
            ce_mois=stats["ce_mois"],
            cette_annee=stats["cette_annee"],
            ocr_done=stats["ocr_done"],
            ocr_pending=stats["ocr_pending"],
            ocr_processing=stats["ocr_processing"],
            ocr_failed=stats["ocr_failed"],
            ocr_en_cours=stats.get("ocr_en_cours", stats["ocr_pending"] + stats["ocr_processing"]),
            corbeille=stats["corbeille"],
            manquants=stats.get("manquants", 0),
            a_verifier=stats.get("a_verifier", stats["ocr_failed"]),
            dossiers_actifs=stats.get("dossiers_actifs", 0),
            departements_actifs=stats.get("departements_actifs", 0),
            par_mois=stats["par_mois"],
            par_espace=stats["par_espace"],
            par_module=stats["par_module"],
            par_type=stats["par_type"],
            par_agence=stats.get("par_agence", []),
            activite=stats["activite"],
            activite_recente=stats.get("activite_recente", []),
            recents=[document_out(r) for r in stats["recents"]],
            ocr=stats.get(
                "ocr",
                {
                    "pending": stats["ocr_pending"],
                    "processing": stats["ocr_processing"],
                    "done": stats["ocr_done"],
                    "failed": stats["ocr_failed"],
                    "en_cours": stats.get("ocr_en_cours", 0),
                },
            ),
        )
    except AppError as exc:
        raise_http_from_app(exc)


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
    entity: str | None = Query(None),
    entity_id: str | None = Query(None),
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
            entity=entity,
            entity_id=entity_id,
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


@router.get(
    "/general/rapports/export",
    dependencies=[Depends(require_module_access("archives-generales"))],
)
async def archives_generales_export(
    request: Request,
    format: str = Query("csv"),
    report_key: str = Query("documents"),
    espace_code: str | None = Query(None),
    module_code: str | None = Query(None),
    doc_type: str | None = Query(None),
    ocr_status: str | None = Query(None),
    date_debut: date | None = Query(None),
    date_fin: date | None = Query(None),
    q: str | None = Query(None),
    entity: str | None = Query(None),
    entity_id: str | None = Query(None),
    agence_id: UUID | None = Query(None),
    user: User = Depends(
        require_permission("ged.export", "archives.general.view", "mg.archives.export")
    ),
    db: AsyncSession = Depends(get_db),
):
    try:
        content, media, filename = await DocumentReportingService(db).export(
            user=user,
            fmt=format,
            espace_code=espace_code,
            module_code=module_code,
            doc_type=doc_type,
            ocr_status=ocr_status,
            date_debut=date_debut,
            date_fin=date_fin,
            q=q,
            entity=entity,
            entity_id=entity_id,
            agence_id=agence_id,
            general=True,
            report_key=report_key,
        )
        await record_audit(
            db,
            user=user,
            action="archives_general_export",
            entity="ged_document",
            entity_id=None,
            after={"format": format},
            request=request,
            module_code="archives-generales",
        )
        return Response(
            content=content,
            media_type=media,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except AppError as exc:
        raise_http_from_app(exc)


@router.get(
    "/general/dossiers",
    dependencies=[Depends(require_module_access("archives-generales"))],
)
async def archives_generales_dossiers(
    user: User = Depends(require_permission("archives.general.view")),
    db: AsyncSession = Depends(get_db),
):
    """Regroupement des documents existants (pas une nouvelle table)."""
    try:
        return await DocumentQueryService(db).list_dossiers(user)
    except AppError as exc:
        raise_http_from_app(exc)


@router.get(
    "/general/doublons",
    dependencies=[Depends(require_module_access("archives-generales"))],
)
async def archives_generales_doublons(
    user: User = Depends(require_permission("archives.general.view")),
    db: AsyncSession = Depends(get_db),
):
    try:
        groups = await DocumentQueryService(db).list_duplicates(user)
        return [
            {
                "filename": g["filename"],
                "size_bytes": g["size_bytes"],
                "criterion": g["criterion"],
                "documents": [document_out(d) for d in g["documents"]],
            }
            for g in groups
        ]
    except AppError as exc:
        raise_http_from_app(exc)


@router.get(
    "/general/a-verifier",
    dependencies=[Depends(require_module_access("archives-generales"))],
)
async def archives_generales_a_verifier(
    user: User = Depends(require_permission("archives.general.view")),
    db: AsyncSession = Depends(get_db),
):
    try:
        items = await DocumentQueryService(db).list_a_verifier(user)
        return [
            {"motifs": item["motifs"], "document": document_out(item["document"])}
            for item in items
        ]
    except AppError as exc:
        raise_http_from_app(exc)


@router.get(
    "/general/manquants",
    dependencies=[Depends(require_module_access("archives-generales"))],
)
async def archives_generales_manquants(
    user: User = Depends(require_permission("archives.general.view")),
    db: AsyncSession = Depends(get_db),
):
    try:
        from app.services.mg_archives_service import MgArchivesService

        items = await MgArchivesService(db).list_missing(limit=200)
        return [item.model_dump(mode="json") for item in items]
    except AppError as exc:
        raise_http_from_app(exc)


@router.get(
    "/general/filtres",
    dependencies=[Depends(require_module_access("archives-generales"))],
)
async def archives_generales_filtres(
    user: User = Depends(require_permission("archives.general.view")),
    db: AsyncSession = Depends(get_db),
):
    """Catalogue départements / modules autorisés + types documentaires présents."""
    try:
        return await DocumentQueryService(db).filter_catalogue(user)
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
