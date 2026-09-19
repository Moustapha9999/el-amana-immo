"""CORE ADMIN — activité, alertes, notifications, GED, configuration (Login 1)."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
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
    CoreAdminSecurityCheckRead,
    CoreAdminSecurityPolicyUpdate,
    CoreAdminSecuritySettings,
)
from app.services.core_admin_ops_service import CoreAdminOpsService
from app.services.audit_helpers import record_audit

router = APIRouter(prefix="/plateforme/admin", tags=["core-admin"])

_AUDIT = require_platform_permission("core.admin.audit")
_SECURITY = require_platform_permission("core.admin.security")
_SETTINGS = require_platform_permission("core.admin.settings")
CONFIRM_PHRASE = "CONFIRMER"


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
    statut: str = Query("tous", pattern="^(tous|non_lues|lues|archivees)$"),
    module_code: str | None = None,
    espace_code: str | None = None,
    categorie: str | None = None,
    priorite: str | None = None,
    periode: str | None = Query(None, pattern="^(tous|aujourd_hui|7j|30j|mois)?$"),
    user_id: str | None = None,
    _: User = Depends(_SETTINGS),
    db: AsyncSession = Depends(get_db),
):
    items, total, kpis = await CoreAdminOpsService(db).notifications(
        page,
        size,
        search=search,
        statut=statut,
        module_code=module_code,
        espace_code=espace_code,
        categorie=categorie,
        priorite=priorite,
        periode=periode,
        user_id=user_id,
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


@router.post("/settings/security/check", response_model=CoreAdminSecurityCheckRead)
async def settings_security_check(
    _: User = Depends(_SECURITY),
    db: AsyncSession = Depends(get_db),
):
    """Contrôle défensif de configuration — aucune action offensive."""
    return await CoreAdminOpsService(db).security_check()


@router.patch("/settings/security/policy", response_model=CoreAdminSecuritySettings)
async def settings_security_policy_update(
    payload: CoreAdminSecurityPolicyUpdate,
    request: Request,
    user: User = Depends(_SECURITY),
    db: AsyncSession = Depends(get_db),
):
    """Met à jour la politique sécurité (persistée dans platform_ops_flags)."""
    if payload.confirmation_phrase.strip().upper() != CONFIRM_PHRASE:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "CONFIRMATION_REQUIRED",
                "message": f'Tapez « {CONFIRM_PHRASE} » pour appliquer la modification.',
            },
        )
    data = payload.model_dump(exclude_unset=True, exclude={"confirmation_phrase"})
    if not data:
        raise HTTPException(status_code=400, detail="Aucune modification fournie")
    result = await CoreAdminOpsService(db).update_security_policy(data)
    await record_audit(
        db,
        user=user,
        action="security_policy_update",
        entity="platform_ops_flags",
        entity_id="security_policy",
        request=request,
        after={k: data[k] for k in data},
    )
    await db.commit()
    return result


@router.post("/settings/security/unlock")
async def settings_security_unlock(
    payload: dict,
    request: Request,
    user: User = Depends(_SECURITY),
    db: AsyncSession = Depends(get_db),
):
    """Déverrouille un compte (efface les échecs de la fenêtre de lockout)."""
    from app.services.login_attempt_service import LoginAttemptService

    email = str(payload.get("email") or "").strip()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Email invalide")
    cleared = await LoginAttemptService(db).clear_lockout(email=email)
    await record_audit(
        db,
        user=user,
        action="unlock_login",
        entity="user",
        entity_id=email.lower(),
        request=request,
        after={"cleared_failures": cleared},
    )
    await db.commit()
    return {"email": email.lower(), "cleared_failures": cleared, "unlocked": True}


@router.get("/settings/maintenance", response_model=CoreAdminMaintenanceSettings)
async def settings_maintenance(
    _: User = Depends(_SETTINGS),
    db: AsyncSession = Depends(get_db),
):
    return await CoreAdminOpsService(db).maintenance_settings()
