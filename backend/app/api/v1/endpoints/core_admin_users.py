from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_platform_permission
from app.api.v1.endpoints.helpers import to_paginated
from app.db.session import get_db
from app.models import User
from app.schemas.auth import RoleRead, UserCreate, UserRead, UserUpdate
from app.schemas.common import MessageResponse
from app.schemas.plateforme import (
    CoreAdminResetAccess,
    CoreAdminUserCreate,
    CoreAdminUserCreateResult,
    CoreAdminUserFiche,
    CoreAdminUserListRead,
    CoreAdminUserUpdate,
)
from app.services.audit_helpers import record_audit
from app.services.core_admin_service import CoreAdminService
from app.core.temp_password import generate_temporary_password

router = APIRouter(prefix="/plateforme/admin", tags=["core-admin"])

_USERS_PERM = require_platform_permission("core.admin.users")
_SECURITY_PERM = require_platform_permission("core.admin.security")


def _http_from_value_error(exc: ValueError) -> HTTPException:
    detail = str(exc)
    code = (
        status.HTTP_404_NOT_FOUND
        if detail == "Utilisateur introuvable"
        else status.HTTP_400_BAD_REQUEST
    )
    return HTTPException(status_code=code, detail=detail)


def _to_create(payload: CoreAdminUserCreate, *, password: str) -> UserCreate:
    return UserCreate(
        email=payload.email,
        full_name=payload.full_name,
        password=password,
        phone=payload.phone,
        is_superuser=payload.is_superuser,
        role_codes=payload.role_codes,
        espace_codes=payload.espace_codes,
        module_codes=payload.module_codes,
    )


def _to_update(payload: CoreAdminUserUpdate) -> UserUpdate:
    return UserUpdate.model_validate(payload.model_dump(exclude_unset=True))


async def _audit_user(
    db: AsyncSession,
    *,
    actor: User,
    action: str,
    user: User,
    request: Request,
    extra: dict | None = None,
) -> None:
    after = {"email": user.email, "is_active": user.is_active, "module_codes": user.module_codes}
    if extra:
        after.update(extra)
    await record_audit(
        db,
        user=actor,
        action=action,
        entity="user",
        entity_id=str(user.id),
        request=request,
        after=after,
        module_code="core",
    )


@router.get("/users", response_model=CoreAdminUserListRead)
async def list_admin_users(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    statut: Literal["tous", "actif", "inactif"] = Query("tous"),
    role_code: str | None = Query(None),
    espace_code: str | None = Query(None),
    module_code: str | None = Query(None),
    profil: Literal["tous", "superuser", "standard"] = Query("tous"),
    totp: Literal["tous", "oui", "non"] = Query("tous"),
    connexion: Literal["tous", "connecte", "jamais"] = Query("tous"),
    _: User = Depends(_USERS_PERM),
    db: AsyncSession = Depends(get_db),
):
    service = CoreAdminService(db)
    try:
        items, total = await service.list_users(
            page,
            size,
            search=search,
            statut=statut,
            role_code=role_code,
            espace_code=espace_code,
            module_code=module_code,
            profil=profil,
            totp=totp,
            connexion=connexion,
        )
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    listed = to_paginated(items, total, page, size, UserRead.model_validate)
    return {
        "items": listed.items,
        "total": listed.total,
        "page": listed.page,
        "size": listed.size,
        "kpis": await service.users_kpis(),
    }


@router.get("/users/roles", response_model=list[RoleRead])
async def list_admin_roles(
    _: User = Depends(_USERS_PERM),
    db: AsyncSession = Depends(get_db),
):
    return await CoreAdminService(db).list_roles()


@router.post("/users", response_model=CoreAdminUserCreateResult, status_code=status.HTTP_201_CREATED)
async def create_admin_user(
    payload: CoreAdminUserCreate,
    request: Request,
    actor: User = Depends(_USERS_PERM),
    db: AsyncSession = Depends(get_db),
):
    service = CoreAdminService(db)
    temporary = (payload.password or "").strip() or generate_temporary_password()
    try:
        user = await service.create_user(_to_create(payload, password=temporary), actor=actor)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    await _audit_user(
        db,
        actor=actor,
        action="create",
        user=user,
        request=request,
        extra={"temporary_password_issued": True},
    )
    return CoreAdminUserCreateResult(
        user=UserRead.model_validate(user),
        temporary_password=temporary,
    )


@router.post("/users/{user_id}/reset-access", response_model=MessageResponse)
async def reset_admin_user_access(
    user_id: UUID,
    payload: CoreAdminResetAccess,
    request: Request,
    actor: User = Depends(_SECURITY_PERM),
    db: AsyncSession = Depends(get_db),
):
    """Reset MDP réservé à core.admin.security (centre Sécurité)."""
    service = CoreAdminService(db)
    try:
        user = await service.reset_access(user_id, payload.password, actor=actor)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    await _audit_user(
        db,
        actor=actor,
        action="reset-access",
        user=user,
        request=request,
        extra={"sessions_revoked": True},
    )
    return MessageResponse(message="Accès réinitialisé")


@router.get("/users/{user_id}", response_model=CoreAdminUserFiche)
async def get_admin_user(
    user_id: UUID,
    _: User = Depends(_USERS_PERM),
    db: AsyncSession = Depends(get_db),
):
    fiche = await CoreAdminService(db).user_fiche(user_id)
    if fiche is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable")
    return fiche


@router.patch("/users/{user_id}", response_model=UserRead)
async def update_admin_user(
    user_id: UUID,
    payload: CoreAdminUserUpdate,
    request: Request,
    actor: User = Depends(_USERS_PERM),
    db: AsyncSession = Depends(get_db),
):
    if payload.password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La gestion des mots de passe se fait via CORE ADMIN → Sécurité",
        )
    service = CoreAdminService(db)
    try:
        user = await service.update_user(user_id, _to_update(payload), actor=actor)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    await _audit_user(db, actor=actor, action="update", user=user, request=request)
    return user


@router.post("/users/{user_id}/deactivate", response_model=UserRead)
async def deactivate_admin_user(
    user_id: UUID,
    request: Request,
    actor: User = Depends(_USERS_PERM),
    db: AsyncSession = Depends(get_db),
):
    service = CoreAdminService(db)
    try:
        user = await service.set_active(user_id, active=False, actor=actor)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    await _audit_user(db, actor=actor, action="deactivate", user=user, request=request)
    return user


@router.post("/users/{user_id}/activate", response_model=UserRead)
async def activate_admin_user(
    user_id: UUID,
    request: Request,
    actor: User = Depends(_USERS_PERM),
    db: AsyncSession = Depends(get_db),
):
    service = CoreAdminService(db)
    try:
        user = await service.set_active(user_id, active=True, actor=actor)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    await _audit_user(db, actor=actor, action="activate", user=user, request=request)
    return user


@router.delete("/users/{user_id}", response_model=MessageResponse)
async def archive_admin_user(
    user_id: UUID,
    request: Request,
    actor: User = Depends(_USERS_PERM),
    db: AsyncSession = Depends(get_db),
):
    service = CoreAdminService(db)
    try:
        user = await service.archive_user(user_id, actor=actor)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    await _audit_user(db, actor=actor, action="delete", user=user, request=request)
    return MessageResponse(message="Utilisateur supprimé")
