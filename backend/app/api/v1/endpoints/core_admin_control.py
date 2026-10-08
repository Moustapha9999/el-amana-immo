"""CORE ADMIN — sauvegardes, recovery, supervision, état modules, versions."""

from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.api.deps import require_platform_permission
from app.db.session import get_db
from app.models import User
from app.schemas.plateforme import (
    GlobalMaintenanceUpdate,
    ModuleStatusUpdate,
    ModuleVersionCreate,
    PlatformBackupCreate,
    PlatformRestoreRequest,
)
from app.services.platform_backup_service import PlatformBackupService
from app.services.platform_ops_service import PlatformOpsService

router = APIRouter(prefix="/plateforme/admin", tags=["core-admin-ops"])

_BACKUP_VIEW = require_platform_permission("core.admin.backup.view")
_BACKUP_CREATE = require_platform_permission("core.admin.backup.create")
_BACKUP_DELETE = require_platform_permission("core.admin.backup.delete")
_BACKUP_DOWNLOAD = require_platform_permission("core.admin.backup.download")
_RECOVERY_VIEW = require_platform_permission("core.admin.recovery.view")
_RECOVERY_EXEC = require_platform_permission("core.admin.recovery.execute")
_MONITOR = require_platform_permission("core.admin.monitoring.view")
_MAINT_VIEW = require_platform_permission("core.admin.maintenance.view")
_MAINT_MANAGE = require_platform_permission("core.admin.maintenance.manage")
_STATUS_VIEW = require_platform_permission("core.admin.module_status.view")
_STATUS_MANAGE = require_platform_permission("core.admin.module_status.manage")
_VERSION_VIEW = require_platform_permission("core.admin.versions.view")
_VERSION_MANAGE = require_platform_permission("core.admin.versions.manage")


@router.get("/backups/dashboard")
async def backups_dashboard(
    _: User = Depends(_BACKUP_VIEW),
    db: AsyncSession = Depends(get_db),
):
    return await PlatformBackupService(db).dashboard()


@router.get("/backups/catalogue")
async def backups_catalogue(
    _: User = Depends(_BACKUP_VIEW),
    db: AsyncSession = Depends(get_db),
):
    return await PlatformBackupService(db).catalogue()


@router.get("/backups/preview")
async def backups_preview(
    level: Literal["global", "departement", "module"],
    espace_code: str | None = None,
    module_code: str | None = None,
    user: User = Depends(_BACKUP_VIEW),
    db: AsyncSession = Depends(get_db),
):
    return await PlatformBackupService(db).preview_backup(
        user=user, level=level, espace_code=espace_code, module_code=module_code
    )


@router.get("/backups/history")
async def backups_history(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    kind: Literal["backup", "restore"] | None = None,
    level: Literal["global", "departement", "module"] | None = None,
    status: str | None = Query(None, max_length=20),
    espace_code: str | None = None,
    module_code: str | None = None,
    _: User = Depends(_BACKUP_VIEW),
    db: AsyncSession = Depends(get_db),
):
    return await PlatformBackupService(db).history(
        page=page,
        size=size,
        kind=kind,
        level=level,
        status_filter=status,
        espace_code=espace_code,
        module_code=module_code,
    )


@router.get("/backups")
async def list_backups(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    level: str | None = None,
    module_code: str | None = None,
    espace_code: str | None = None,
    status: str | None = Query(None, max_length=20),
    _: User = Depends(_BACKUP_VIEW),
    db: AsyncSession = Depends(get_db),
):
    items, total = await PlatformBackupService(db).list_backups(
        page=page,
        size=size,
        level=level,
        module_code=module_code,
        espace_code=espace_code,
        status_filter=status,
    )
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/backups/{backup_id}")
async def get_backup(
    backup_id: UUID,
    _: User = Depends(_BACKUP_VIEW),
    db: AsyncSession = Depends(get_db),
):
    svc = PlatformBackupService(db)
    row = await svc.get(backup_id)
    if row is None:
        raise HTTPException(
            status_code=404, detail={"code": "BACKUP_NOT_FOUND", "message": "Sauvegarde introuvable."}
        )
    data = await svc.serialize(row)
    data["manifest"] = row.manifest
    data["restores"] = [await svc.serialize_restore(r) for r in await svc.restores_of(backup_id)]
    return data


@router.post("/backups/{backup_id}/verify")
async def verify_backup(
    backup_id: UUID,
    request: Request,
    user: User = Depends(_BACKUP_VIEW),
    db: AsyncSession = Depends(get_db),
):
    return await PlatformBackupService(db).verify(backup_id, user=user, request=request)


@router.get("/backups/{backup_id}/download")
async def download_backup(
    backup_id: UUID,
    request: Request,
    user: User = Depends(_BACKUP_DOWNLOAD),
    db: AsyncSession = Depends(get_db),
):
    path, filename, temporary = await PlatformBackupService(db).prepare_download(
        backup_id, user=user, request=request
    )
    cleanup = BackgroundTask(Path(path).unlink, missing_ok=True) if temporary else None
    return FileResponse(
        path,
        filename=filename,
        media_type="application/x-tar" if filename.endswith(".tar") else "application/octet-stream",
        background=cleanup,
    )


@router.post("/backups")
async def create_backup(
    payload: PlatformBackupCreate,
    request: Request,
    user: User = Depends(_BACKUP_CREATE),
    db: AsyncSession = Depends(get_db),
):
    result = await PlatformBackupService(db).create_backup(
        user=user,
        level=payload.level,
        backup_type=payload.backup_type,
        espace_code=payload.espace_code,
        module_code=payload.module_code,
        label=payload.label,
        request=request,
    )
    await db.commit()
    return result


@router.delete("/backups/{backup_id}")
async def delete_backup(
    backup_id: UUID,
    request: Request,
    user: User = Depends(_BACKUP_DELETE),
    db: AsyncSession = Depends(get_db),
):
    await PlatformBackupService(db).delete_backup(backup_id, user=user, request=request)
    await db.commit()
    return {"ok": True}


class BackupBulkDelete(BaseModel):
    ids: list[UUID] = Field(min_length=1, max_length=200)


@router.post("/backups/bulk-delete")
async def bulk_delete_backups(
    payload: BackupBulkDelete,
    request: Request,
    user: User = Depends(_BACKUP_DELETE),
    db: AsyncSession = Depends(get_db),
):
    svc = PlatformBackupService(db)
    deleted: list[str] = []
    failed: list[dict] = []
    for backup_id in dict.fromkeys(payload.ids):
        try:
            async with db.begin_nested():
                await svc.delete_backup(backup_id, user=user, request=request)
            deleted.append(str(backup_id))
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
            failed.append({"id": str(backup_id), "code": detail.get("code"), "message": detail.get("message")})
    await db.commit()
    return {"deleted": deleted, "failed": failed}


@router.get("/recovery")
async def list_recovery(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _: User = Depends(_RECOVERY_VIEW),
    db: AsyncSession = Depends(get_db),
):
    backups, total = await PlatformBackupService(db).list_backups(page=page, size=size)
    restores, rtotal = await PlatformBackupService(db).list_restores(page=1, size=10)
    return {
        "backups": backups,
        "backups_total": total,
        "restores": restores,
        "restores_total": rtotal,
        "page": page,
        "size": size,
    }


@router.get("/recovery/history")
async def recovery_history(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _: User = Depends(_RECOVERY_VIEW),
    db: AsyncSession = Depends(get_db),
):
    items, total = await PlatformBackupService(db).list_restores(page=page, size=size)
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/recovery/restores/{restore_id}")
async def get_restore(
    restore_id: UUID,
    _: User = Depends(_RECOVERY_VIEW),
    db: AsyncSession = Depends(get_db),
):
    svc = PlatformBackupService(db)
    row = await svc.get_restore(restore_id)
    if row is None:
        raise HTTPException(
            status_code=404, detail={"code": "RESTORE_NOT_FOUND", "message": "Restauration introuvable."}
        )
    return await svc.serialize_restore(row)


@router.get("/recovery/{backup_id}/preview")
async def recovery_preview(
    backup_id: UUID,
    include_security: bool = False,
    _: User = Depends(_RECOVERY_VIEW),
    db: AsyncSession = Depends(get_db),
):
    return await PlatformBackupService(db).preview_restore(backup_id, include_security=include_security)


@router.post("/recovery/{backup_id}")
async def execute_recovery(
    backup_id: UUID,
    payload: PlatformRestoreRequest,
    request: Request,
    user: User = Depends(_RECOVERY_EXEC),
    db: AsyncSession = Depends(get_db),
):
    result = await PlatformBackupService(db).restore(
        backup_id,
        user=user,
        acknowledge_dependencies=payload.acknowledge_dependencies,
        confirmation=payload.confirmation,
        reason=payload.reason,
        include_security=payload.include_security,
        request=request,
    )
    await db.commit()
    return result


@router.get("/supervision")
async def supervision(
    _: User = Depends(_MONITOR),
    db: AsyncSession = Depends(get_db),
):
    return await PlatformOpsService(db).supervision()


@router.get("/module-states")
async def module_states(
    _: User = Depends(_STATUS_VIEW),
    db: AsyncSession = Depends(get_db),
):
    return {"items": await PlatformOpsService(db).list_module_states()}


@router.patch("/module-states/{module_id}")
async def update_module_state(
    module_id: UUID,
    payload: ModuleStatusUpdate,
    request: Request,
    user: User = Depends(_STATUS_MANAGE),
    db: AsyncSession = Depends(get_db),
):
    result = await PlatformOpsService(db).update_module_status(
        module_id,
        user=user,
        statut=payload.statut,
        status_message=payload.status_message,
        maintenance_starts_at=payload.maintenance_starts_at,
        maintenance_ends_at=payload.maintenance_ends_at,
        admins_bypass_maintenance=payload.admins_bypass_maintenance,
        notify=payload.notify,
        request=request,
    )
    await db.commit()
    return result


@router.get("/maintenance/control")
async def maintenance_control_get(
    _: User = Depends(_MAINT_VIEW),
    db: AsyncSession = Depends(get_db),
):
    ops = PlatformOpsService(db)
    return {
        "global": await ops.get_global_maintenance(),
        "modules": await ops.list_module_states(),
    }


@router.put("/maintenance/control/global")
async def maintenance_control_global(
    payload: GlobalMaintenanceUpdate,
    request: Request,
    user: User = Depends(_MAINT_MANAGE),
    db: AsyncSession = Depends(get_db),
):
    result = await PlatformOpsService(db).set_global_maintenance(
        user=user,
        enabled=payload.enabled,
        title=payload.title,
        message=payload.message,
        ends_at=payload.ends_at,
        admins_bypass=payload.admins_bypass,
        request=request,
    )
    await db.commit()
    return result


@router.get("/versions/{module_id}")
async def list_versions(
    module_id: UUID,
    _: User = Depends(_VERSION_VIEW),
    db: AsyncSession = Depends(get_db),
):
    return {"items": await PlatformOpsService(db).list_versions(module_id)}


@router.post("/versions/{module_id}")
async def create_version(
    module_id: UUID,
    payload: ModuleVersionCreate,
    request: Request,
    user: User = Depends(_VERSION_MANAGE),
    db: AsyncSession = Depends(get_db),
):
    ops = PlatformOpsService(db)
    backup_info = None
    if payload.create_backup:
        from app.models.plateforme import PlateformeModule
        from sqlalchemy.orm import selectinload

        module = await db.get(
            PlateformeModule, module_id, options=[selectinload(PlateformeModule.espace)]
        )
        if module is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Module introuvable")
        if payload.activate_maintenance:
            await ops.update_module_status(
                module_id,
                user=user,
                statut="mise_a_jour",
                status_message="Mise à jour de version en cours.",
                notify=True,
                request=request,
            )
        try:
            backup_info = await PlatformBackupService(db).create_backup(
                user=user,
                level="module",
                backup_type="avant_mise_a_jour",
                module_code=module.code,
                espace_code=module.espace.code if module.espace else None,
                request=request,
                label=f"Avant version {payload.version}",
            )
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            if detail.get("code") != "BACKUP_SCOPE_EMPTY":
                raise
            backup_info = {"skipped": True, "message": detail.get("message")}
    result = await ops.add_version(
        module_id,
        user=user,
        version=payload.version,
        notes=payload.notes,
        set_current=payload.set_current,
        request=request,
    )
    if payload.activate_maintenance:
        await ops.update_module_status(
            module_id,
            user=user,
            statut="actif",
            status_message="",
            notify=True,
            request=request,
        )
    await db.commit()
    return {**result, "backup": backup_info}
