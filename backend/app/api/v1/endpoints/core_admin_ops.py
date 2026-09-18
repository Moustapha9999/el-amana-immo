"""CORE ADMIN — activité, alertes, notifications, GED, configuration (Login 1)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_platform_permission
from app.db.session import get_db
from app.models import User
from app.schemas.plateforme import (
    CoreAdminActivityListRead,
    CoreAdminAlertListRead,
    CoreAdminGedListRead,
    CoreAdminGeneralSettings,
    CoreAdminMaintenanceSettings,
    CoreAdminNotificationListRead,
    CoreAdminSecuritySettings,
)
from app.services.core_admin_ops_service import CoreAdminOpsService

router = APIRouter(prefix="/plateforme/admin", tags=["core-admin"])

_AUDIT = require_platform_permission("core.admin.audit")
_SECURITY = require_platform_permission("core.admin.security")
_SETTINGS = require_platform_permission("core.admin.settings")


@router.get("/activity", response_model=CoreAdminActivityListRead)
async def list_activity(
    page: int = Query(1, ge=1),
    size: int = Query(30, ge=1, le=100),
    search: str | None = None,
    module_code: str | None = None,
    hours: int = Query(48, ge=1, le=168),
    _: User = Depends(_AUDIT),
    db: AsyncSession = Depends(get_db),
):
    items, total, kpis = await CoreAdminOpsService(db).activity(
        page, size, search=search, module_code=module_code, hours=hours
    )
    return {"items": items, "total": total, "page": page, "size": size, "kpis": kpis}


@router.get("/alerts", response_model=CoreAdminAlertListRead)
async def list_alerts(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    kind: str = Query("echecs", pattern="^(tous|echecs|succes|fenetre)$"),
    _: User = Depends(_SECURITY),
    db: AsyncSession = Depends(get_db),
):
    items, total, kpis, lockout = await CoreAdminOpsService(db).alerts(
        page, size, search=search, kind=kind
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "kpis": kpis,
        **lockout,
    }


@router.get("/notifications", response_model=CoreAdminNotificationListRead)
async def list_admin_notifications(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    statut: str = Query("tous", pattern="^(tous|non_lues|lues)$"),
    module_code: str | None = None,
    _: User = Depends(_SETTINGS),
    db: AsyncSession = Depends(get_db),
):
    items, total, kpis = await CoreAdminOpsService(db).notifications(
        page, size, search=search, statut=statut, module_code=module_code
    )
    return {"items": items, "total": total, "page": page, "size": size, "kpis": kpis}


@router.get("/ged", response_model=CoreAdminGedListRead)
async def list_ged(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    module_code: str | None = None,
    _: User = Depends(_SETTINGS),
    db: AsyncSession = Depends(get_db),
):
    items, total, kpis = await CoreAdminOpsService(db).ged(
        page, size, search=search, module_code=module_code
    )
    return {"items": items, "total": total, "page": page, "size": size, "kpis": kpis}


@router.get("/settings/general", response_model=CoreAdminGeneralSettings)
async def settings_general(
    _: User = Depends(_SETTINGS),
    db: AsyncSession = Depends(get_db),
):
    _ = db
    return CoreAdminOpsService(db).general_settings()


@router.get("/settings/security", response_model=CoreAdminSecuritySettings)
async def settings_security(
    _: User = Depends(_SECURITY),
    db: AsyncSession = Depends(get_db),
):
    return await CoreAdminOpsService(db).security_settings()


@router.get("/settings/maintenance", response_model=CoreAdminMaintenanceSettings)
async def settings_maintenance(
    _: User = Depends(_SETTINGS),
    db: AsyncSession = Depends(get_db),
):
    return await CoreAdminOpsService(db).maintenance_settings()
