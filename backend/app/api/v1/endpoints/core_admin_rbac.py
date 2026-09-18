from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_platform_permission
from app.db.session import get_db
from app.models import User
from app.schemas.common import MessageResponse
from app.schemas.plateforme import (
    CoreAdminMatrixGrantResult,
    CoreAdminMatrixGrantUpdate,
    CoreAdminMatrixRead,
    CoreAdminPermissionFiche,
    CoreAdminPermissionListRead,
    CoreAdminPermissionOptions,
    CoreAdminPermissionUpdate,
    CoreAdminPermissionWrite,
    CoreAdminRoleFiche,
    CoreAdminRoleListRead,
    CoreAdminRoleOptions,
    CoreAdminRoleUpdate,
    CoreAdminRoleWrite,
)
from app.services.audit_helpers import record_audit
from app.services.core_admin_rbac_service import CoreAdminRbacService

router = APIRouter(prefix="/plateforme/admin", tags=["core-admin"])

_ROLES_PERM = require_platform_permission("core.admin.roles")
_PERMS_PERM = require_platform_permission("core.admin.permissions")


def _http_from_value_error(exc: ValueError) -> HTTPException:
    detail = str(exc)
    missing = detail.endswith("introuvable")
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND if missing else status.HTTP_400_BAD_REQUEST,
        detail=detail,
    )


async def _audit(
    db: AsyncSession,
    *,
    actor: User,
    action: str,
    entity: str,
    entity_id: str,
    request: Request,
    after: dict | None = None,
) -> None:
    await record_audit(
        db,
        user=actor,
        action=action,
        entity=entity,
        entity_id=entity_id,
        request=request,
        after=after,
        module_code="core",
    )


@router.get("/roles", response_model=CoreAdminRoleListRead)
async def list_roles(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    kind: Literal["tous", "systeme", "custom"] = Query("tous"),
    _: User = Depends(_ROLES_PERM),
    db: AsyncSession = Depends(get_db),
):
    items, total, kpis = await CoreAdminRbacService(db).list_roles(page, size, search=search, kind=kind)
    return {"items": items, "total": total, "page": page, "size": size, "kpis": kpis}


@router.get("/roles/options", response_model=CoreAdminRoleOptions)
async def role_options(
    _: User = Depends(_ROLES_PERM),
    db: AsyncSession = Depends(get_db),
):
    return await CoreAdminRbacService(db).role_options()


@router.post("/roles", response_model=CoreAdminRoleFiche, status_code=status.HTTP_201_CREATED)
async def create_role(
    payload: CoreAdminRoleWrite,
    request: Request,
    actor: User = Depends(_ROLES_PERM),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await CoreAdminRbacService(db).create_role(payload)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    await _audit(
        db,
        actor=actor,
        action="create",
        entity="role",
        entity_id=row["id"],
        request=request,
        after={"code": row["code"], "permissions": row.get("permission_codes", [])},
    )
    return row


@router.get("/roles/{role_id}", response_model=CoreAdminRoleFiche)
async def get_role(
    role_id: UUID,
    _: User = Depends(_ROLES_PERM),
    db: AsyncSession = Depends(get_db),
):
    fiche = await CoreAdminRbacService(db).role_fiche(role_id)
    if fiche is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rôle introuvable")
    return fiche


@router.patch("/roles/{role_id}", response_model=CoreAdminRoleFiche)
async def update_role(
    role_id: UUID,
    payload: CoreAdminRoleUpdate,
    request: Request,
    actor: User = Depends(_ROLES_PERM),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await CoreAdminRbacService(db).update_role(role_id, payload)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    await _audit(
        db,
        actor=actor,
        action="update",
        entity="role",
        entity_id=row["id"],
        request=request,
        after={"code": row["code"], "permissions": row.get("permission_codes", [])},
    )
    return row


@router.delete("/roles/{role_id}", response_model=MessageResponse)
async def delete_role(
    role_id: UUID,
    request: Request,
    actor: User = Depends(_ROLES_PERM),
    db: AsyncSession = Depends(get_db),
):
    try:
        await CoreAdminRbacService(db).delete_role(role_id)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    await _audit(db, actor=actor, action="delete", entity="role", entity_id=str(role_id), request=request)
    return MessageResponse(message="Rôle supprimé")


@router.get("/permissions", response_model=CoreAdminPermissionListRead)
async def list_permissions(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    kind: Literal["tous", "systeme", "custom"] = Query("tous"),
    module: str | None = None,
    _: User = Depends(_PERMS_PERM),
    db: AsyncSession = Depends(get_db),
):
    items, total, kpis = await CoreAdminRbacService(db).list_permissions(
        page, size, search=search, kind=kind, module=module
    )
    return {"items": items, "total": total, "page": page, "size": size, "kpis": kpis}


@router.get("/permissions/options", response_model=CoreAdminPermissionOptions)
async def permission_options(
    _: User = Depends(_PERMS_PERM),
    db: AsyncSession = Depends(get_db),
):
    return {"modules": await CoreAdminRbacService(db).permission_modules()}


@router.post("/permissions", response_model=CoreAdminPermissionFiche, status_code=status.HTTP_201_CREATED)
async def create_permission(
    payload: CoreAdminPermissionWrite,
    request: Request,
    actor: User = Depends(_PERMS_PERM),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await CoreAdminRbacService(db).create_permission(payload)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    await _audit(
        db,
        actor=actor,
        action="create",
        entity="permission",
        entity_id=row["id"],
        request=request,
        after={"code": row["code"], "module": row["module"]},
    )
    return row


@router.get("/permissions/{permission_id}", response_model=CoreAdminPermissionFiche)
async def get_permission(
    permission_id: UUID,
    _: User = Depends(_PERMS_PERM),
    db: AsyncSession = Depends(get_db),
):
    fiche = await CoreAdminRbacService(db).permission_fiche(permission_id)
    if fiche is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Permission introuvable")
    return fiche


@router.patch("/permissions/{permission_id}", response_model=CoreAdminPermissionFiche)
async def update_permission(
    permission_id: UUID,
    payload: CoreAdminPermissionUpdate,
    request: Request,
    actor: User = Depends(_PERMS_PERM),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await CoreAdminRbacService(db).update_permission(permission_id, payload)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    await _audit(
        db,
        actor=actor,
        action="update",
        entity="permission",
        entity_id=row["id"],
        request=request,
        after={"code": row["code"], "module": row["module"]},
    )
    return row


@router.delete("/permissions/{permission_id}", response_model=MessageResponse)
async def delete_permission(
    permission_id: UUID,
    request: Request,
    actor: User = Depends(_PERMS_PERM),
    db: AsyncSession = Depends(get_db),
):
    try:
        await CoreAdminRbacService(db).delete_permission(permission_id)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    await _audit(
        db, actor=actor, action="delete", entity="permission", entity_id=str(permission_id), request=request
    )
    return MessageResponse(message="Permission supprimée")


@router.get("/matrix", response_model=CoreAdminMatrixRead)
async def get_access_matrix(
    module: str | None = None,
    search: str | None = None,
    _: User = Depends(_ROLES_PERM),
    db: AsyncSession = Depends(get_db),
):
    return await CoreAdminRbacService(db).get_matrix(module=module, search=search)


@router.patch("/matrix", response_model=CoreAdminMatrixGrantResult)
async def patch_access_matrix(
    payload: CoreAdminMatrixGrantUpdate,
    request: Request,
    actor: User = Depends(_ROLES_PERM),
    db: AsyncSession = Depends(get_db),
):
    try:
        role_id = UUID(payload.role_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Identifiant de rôle invalide") from exc
    try:
        row = await CoreAdminRbacService(db).set_matrix_grant(role_id, payload.permission_code, payload.granted)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    await _audit(
        db,
        actor=actor,
        action="update",
        entity="role_permission",
        entity_id=row["role_id"],
        request=request,
        after=row,
    )
    return row
