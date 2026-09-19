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


@router.post("/settings/security/reset-password")
async def settings_security_reset_password(
    payload: dict,
    request: Request,
    actor: User = Depends(_SECURITY),
    db: AsyncSession = Depends(get_db),
):
    """Reset MDP admin — confirmation CONFIRMER obligatoire."""
    from uuid import UUID

    from app.services.core_admin_security_center_service import CoreAdminSecurityCenterService

    phrase = str(payload.get("confirmation_phrase") or "").strip().upper()
    if phrase != CONFIRM_PHRASE:
        raise HTTPException(status_code=400, detail="Confirmation CONFIRMER requise")
    svc = CoreAdminSecurityCenterService(db)
    user_id_raw = payload.get("user_id")
    password = str(payload.get("password") or "").strip() or None
    try:
        if user_id_raw:
            result = await svc.reset_password(
                UUID(str(user_id_raw)), password=password, actor=actor
            )
        else:
            email = str(payload.get("email") or "").strip().lower()
            if not email or "@" not in email:
                raise HTTPException(status_code=400, detail="Email ou user_id requis")
            from app.services.auth_service import AuthService
            from sqlalchemy import select
            from app.models import User as UserModel

            user = await AuthService(db).find_active_by_email(email)
            if user is None:
                result_u = await db.execute(select(UserModel).where(UserModel.email == email))
                user = result_u.scalar_one_or_none()
            if user is None:
                raise HTTPException(status_code=404, detail="Utilisateur introuvable")
            result = await svc.reset_password(user.id, password=password, actor=actor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await record_audit(
        db,
        user=actor,
        action="password_reset_admin",
        entity="user",
        entity_id=result["id"],
        request=request,
        after={"email": result["email"], "sessions_revoked": True},
        module_code="core",
    )
    await db.commit()
    return result


@router.get("/settings/security/overview")
async def settings_security_overview(
    _: User = Depends(_SECURITY),
    db: AsyncSession = Depends(get_db),
):
    from app.services.core_admin_security_center_service import CoreAdminSecurityCenterService

    return await CoreAdminSecurityCenterService(db).overview()


@router.get("/settings/security/users/search")
async def settings_security_users_search(
    q: str = Query("", min_length=0, max_length=120),
    limit: int = Query(12, ge=1, le=25),
    _: User = Depends(_SECURITY),
    db: AsyncSession = Depends(get_db),
):
    from app.services.core_admin_security_center_service import CoreAdminSecurityCenterService

    items = await CoreAdminSecurityCenterService(db).search_users(q, limit=limit)
    return {"items": items, "total": len(items)}


@router.get("/settings/security/users/{user_id}/dossier")
async def settings_security_user_dossier(
    user_id: str,
    _: User = Depends(_SECURITY),
    db: AsyncSession = Depends(get_db),
):
    from uuid import UUID

    from app.services.core_admin_security_center_service import CoreAdminSecurityCenterService

    try:
        uid = UUID(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="user_id invalide") from exc
    dossier = await CoreAdminSecurityCenterService(db).user_dossier(uid)
    if dossier is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    return dossier


@router.patch("/settings/security/users/{user_id}/login")
async def settings_security_update_login(
    user_id: str,
    payload: dict,
    request: Request,
    actor: User = Depends(_SECURITY),
    db: AsyncSession = Depends(get_db),
):
    from uuid import UUID

    from app.services.core_admin_security_center_service import CoreAdminSecurityCenterService

    phrase = str(payload.get("confirmation_phrase") or "").strip().upper()
    if phrase != CONFIRM_PHRASE:
        raise HTTPException(status_code=400, detail="Confirmation CONFIRMER requise")
    try:
        uid = UUID(user_id)
        result = await CoreAdminSecurityCenterService(db).update_login(
            uid, new_email=str(payload.get("new_login") or payload.get("email") or ""), actor=actor
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await record_audit(
        db,
        user=actor,
        action="login1_changed",
        entity="user",
        entity_id=str(uid),
        request=request,
        before={"login": result["old_login"]},
        after={"login": result["new_login"]},
        module_code="core",
    )
    await db.commit()
    return result


@router.post("/settings/security/users/{user_id}/mfa/disable")
async def settings_security_mfa_disable(
    user_id: str,
    payload: dict,
    request: Request,
    actor: User = Depends(_SECURITY),
    db: AsyncSession = Depends(get_db),
):
    from uuid import UUID

    from app.services.core_admin_security_center_service import CoreAdminSecurityCenterService

    phrase = str(payload.get("confirmation_phrase") or "").strip().upper()
    if phrase != CONFIRM_PHRASE:
        raise HTTPException(status_code=400, detail="Confirmation CONFIRMER requise")
    try:
        uid = UUID(user_id)
        result = await CoreAdminSecurityCenterService(db).mfa_disable(uid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await record_audit(
        db,
        user=actor,
        action="mfa_disabled",
        entity="user",
        entity_id=str(uid),
        request=request,
        after=result,
        module_code="core",
    )
    await db.commit()
    return result


@router.post("/settings/security/users/{user_id}/mfa/reset")
async def settings_security_mfa_reset(
    user_id: str,
    payload: dict,
    request: Request,
    actor: User = Depends(_SECURITY),
    db: AsyncSession = Depends(get_db),
):
    from uuid import UUID

    from app.services.core_admin_security_center_service import CoreAdminSecurityCenterService

    phrase = str(payload.get("confirmation_phrase") or "").strip().upper()
    if phrase != CONFIRM_PHRASE:
        raise HTTPException(status_code=400, detail="Confirmation CONFIRMER requise")
    try:
        uid = UUID(user_id)
        result = await CoreAdminSecurityCenterService(db).mfa_reset(uid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await record_audit(
        db,
        user=actor,
        action="mfa_reset",
        entity="user",
        entity_id=str(uid),
        request=request,
        after=result,
        module_code="core",
    )
    await db.commit()
    return result


@router.get("/settings/security/incidents")
async def list_security_incidents(
    statut: str | None = None,
    niveau: str | None = None,
    _: User = Depends(_SECURITY),
    db: AsyncSession = Depends(get_db),
):
    from app.services.core_admin_security_center_service import CoreAdminSecurityCenterService

    return await CoreAdminSecurityCenterService(db).list_incidents(statut=statut, niveau=niveau)


@router.post("/settings/security/incidents")
async def create_security_incident(
    payload: dict,
    request: Request,
    actor: User = Depends(_SECURITY),
    db: AsyncSession = Depends(get_db),
):
    from app.services.core_admin_security_center_service import CoreAdminSecurityCenterService

    try:
        incident = await CoreAdminSecurityCenterService(db).create_incident(payload, actor=actor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Table security_incidents indisponible — appliquer les migrations sécurité.",
        ) from exc
    await record_audit(
        db,
        user=actor,
        action="security_incident_create",
        entity="security_incident",
        entity_id=str(incident.id),
        request=request,
        after={"titre": incident.titre, "niveau": incident.niveau, "type": incident.type_incident},
        module_code="core",
    )
    await db.commit()
    return CoreAdminSecurityCenterService(db)._incident_dict(incident)


@router.patch("/settings/security/incidents/{incident_id}")
async def update_security_incident(
    incident_id: str,
    payload: dict,
    request: Request,
    actor: User = Depends(_SECURITY),
    db: AsyncSession = Depends(get_db),
):
    from uuid import UUID

    from app.services.core_admin_security_center_service import CoreAdminSecurityCenterService

    try:
        iid = UUID(incident_id)
        incident = await CoreAdminSecurityCenterService(db).update_incident(iid, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await record_audit(
        db,
        user=actor,
        action="security_incident_update",
        entity="security_incident",
        entity_id=str(iid),
        request=request,
        after={k: payload.get(k) for k in payload},
        module_code="core",
    )
    await db.commit()
    return CoreAdminSecurityCenterService(db)._incident_dict(incident)


@router.get("/settings/security/incidents/{incident_id}")
async def get_security_incident(
    incident_id: str,
    _: User = Depends(_SECURITY),
    db: AsyncSession = Depends(get_db),
):
    from uuid import UUID

    from app.services.core_admin_security_center_service import CoreAdminSecurityCenterService

    try:
        iid = UUID(incident_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="incident_id invalide") from exc
    svc = CoreAdminSecurityCenterService(db)
    incident = await svc.get_incident(iid)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident introuvable")
    return svc._incident_dict(incident)


@router.delete("/settings/security/incidents/{incident_id}")
async def delete_security_incident(
    incident_id: str,
    request: Request,
    actor: User = Depends(_SECURITY),
    db: AsyncSession = Depends(get_db),
):
    from uuid import UUID

    from app.services.core_admin_security_center_service import CoreAdminSecurityCenterService

    try:
        iid = UUID(incident_id)
        meta = await CoreAdminSecurityCenterService(db).delete_incident(iid)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await record_audit(
        db,
        user=actor,
        action="security_incident_delete",
        entity="security_incident",
        entity_id=str(iid),
        request=request,
        before={"titre": meta.get("titre"), "statut": meta.get("statut")},
        module_code="core",
    )
    await db.commit()
    return {"ok": True, "id": str(iid)}


@router.get("/settings/maintenance", response_model=CoreAdminMaintenanceSettings)
async def settings_maintenance(
    _: User = Depends(_SETTINGS),
    db: AsyncSession = Depends(get_db),
):
    return await CoreAdminOpsService(db).maintenance_settings()
