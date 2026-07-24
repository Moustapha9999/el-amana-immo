from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.api.v1.endpoints.helpers import to_paginated
from app.db.session import get_db
from app.models import AuditLog, User
from app.schemas.common import PaginatedResponse
from app.schemas.reporting import AuditLogRead, DashboardCharts, DashboardKpi
from app.services.audit_query import list_audit_for_export
from app.services.audit_service import AuditService
from app.services.immobilisation_service import DashboardService
from app.services.reporting_export import (
    audit_logs_to_excel,
    ecritures_to_excel,
    ecritures_to_pdf,
    format_period_label,
    immobilisations_to_excel,
)
from app.services.reporting_service import list_ecritures_for_export, list_immobilisations_for_export

router = APIRouter(tags=["reporting"])


def _audit_to_read(row: AuditLog) -> AuditLogRead:
    return AuditLogRead(
        id=row.id,
        user_id=row.user_id,
        user_email=row.user.email if row.user else None,
        action=row.action,
        entity=row.entity,
        entity_id=row.entity_id,
        ip_address=row.ip_address,
        created_at=row.created_at,
    )


@router.get("/dashboard/kpi", response_model=DashboardKpi)
async def dashboard_kpi(
    statut: str | None = None,
    famille: str | None = None,
    mois: int | None = Query(None, ge=1, le=12),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await DashboardService(db).kpi(statut=statut, famille=famille, mois=mois)
    return DashboardKpi(**data)


@router.get("/dashboard/charts", response_model=DashboardCharts)
async def dashboard_charts(
    statut: str | None = None,
    famille: str | None = None,
    mois: int | None = Query(None, ge=1, le=12),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await DashboardService(db).charts(statut=statut, famille=famille, mois=mois)
    return DashboardCharts(**data)


@router.get("/audit", response_model=PaginatedResponse[AuditLogRead])
async def list_audit(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    entity: str | None = None,
    action: str | None = None,
    search: str | None = None,
    date_debut: date | None = None,
    date_fin: date | None = None,
    _: User = Depends(require_roles("administrateur", "auditeur")),
    db: AsyncSession = Depends(get_db),
):
    items, total = await AuditService(db).list(
        page,
        size,
        entity=entity,
        action=action,
        search=search,
        date_debut=date_debut,
        date_fin=date_fin,
    )
    return to_paginated(items, total, page, size, _audit_to_read)


@router.get("/reporting/audit/export")
async def export_audit(
    entity: str | None = None,
    action: str | None = None,
    search: str | None = None,
    date_debut: date | None = None,
    date_fin: date | None = None,
    _: User = Depends(require_roles("administrateur", "auditeur")),
    db: AsyncSession = Depends(get_db),
):
    rows = await list_audit_for_export(
        db,
        entity=entity,
        action=action,
        search=search,
        date_debut=date_debut,
        date_fin=date_fin,
    )
    content = audit_logs_to_excel(rows, subtitle=format_period_label(date_debut, date_fin))
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="audit-el-amana.xlsx"'},
    )


@router.get("/reporting/ecritures/export")
async def export_ecritures(
    format: str = Query("xlsx", pattern="^(xlsx|pdf)$"),
    date_debut: date | None = None,
    date_fin: date | None = None,
    _: User = Depends(require_roles("administrateur", "comptable", "auditeur")),
    db: AsyncSession = Depends(get_db),
):
    rows = await list_ecritures_for_export(db, date_debut=date_debut, date_fin=date_fin)
    subtitle = format_period_label(date_debut, date_fin)
    if format == "pdf":
        content = ecritures_to_pdf(rows, subtitle=subtitle)
        media = "application/pdf"
        filename = "ecritures-el-amana.pdf"
    else:
        content = ecritures_to_excel(rows, subtitle=subtitle)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = "ecritures-el-amana.xlsx"
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/reporting/immobilisations/export")
async def export_immobilisations(
    _: User = Depends(require_roles("administrateur", "comptable", "auditeur")),
    db: AsyncSession = Depends(get_db),
):
    rows = await list_immobilisations_for_export(db)
    content = immobilisations_to_excel(rows, subtitle="Parc actif (hors biens supprimés)")
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="immobilisations-el-amana.xlsx"'},
    )


@router.get("/reporting/immobilisations/import-template")
async def download_import_template(_: User = Depends(require_roles("administrateur", "comptable"))):
    from app.services.immobilisation_import import immobilisations_import_template_bytes

    return Response(
        content=immobilisations_import_template_bytes(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="modele-import-immobilisations.xlsx"'},
    )
