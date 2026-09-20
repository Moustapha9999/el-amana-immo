from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_platform_user
from app.api.v1.endpoints.helpers import to_paginated
from app.core.temp_password import generate_temporary_password
from app.db.session import get_db
from app.models import User
from app.schemas.auth import RoleRead, UserCreate, UserRead, UserUpdate
from app.schemas.common import MessageResponse, PaginatedResponse
from app.services.audit_helpers import record_audit
from app.services.auth_service import AuthService

router = APIRouter(prefix="/users", tags=["users"])


async def _require_platform_admin(
    user: User = Depends(get_platform_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Users métier : session plateforme + permission plateforme.users.admin."""
    from app.services.permission_service import load_user_permission_codes, user_has_permission_codes

    have = await load_user_permission_codes(db, user)
    if user_has_permission_codes(have, "plateforme.users.admin"):
        return user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission refusée")


@router.get("", response_model=PaginatedResponse[UserRead])
async def list_users(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    _: User = Depends(_require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    items, total = await AuthService(db).list_users(page, size, search=search)
    return to_paginated(items, total, page, size, UserRead.model_validate)


@router.get("/roles", response_model=list[RoleRead])
async def list_roles(
    _: User = Depends(_require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    return await AuthService(db).list_roles()


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    request: Request,
    actor: User = Depends(_require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    """Création sans MDP libre : mot de passe temporaire serveur."""
    data = payload.model_dump()
    data["password"] = generate_temporary_password()
    service = AuthService(db)
    try:
        user = await service.create_user(UserCreate.model_validate(data))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await record_audit(
        db,
        user=actor,
        action="create",
        entity="user",
        entity_id=str(user.id),
        request=request,
        after={
            "email": user.email,
            "module_codes": user.module_codes,
            "temporary_password_issued": True,
        },
    )
    return user


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: UUID,
    _: User = Depends(_require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    user = await service.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable")
    return user


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: UUID,
    payload: UserUpdate,
    request: Request,
    actor: User = Depends(_require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    if payload.password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La gestion des mots de passe se fait via CORE ADMIN → Sécurité",
        )
    service = AuthService(db)
    try:
        user = await service.update_user(user_id, payload)
    except ValueError as exc:
        detail = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND
            if detail == "Utilisateur introuvable"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=detail) from exc
    await record_audit(
        db,
        user=actor,
        action="update",
        entity="user",
        entity_id=str(user.id),
        request=request,
        after={"email": user.email, "module_codes": user.module_codes},
    )
    return user


@router.delete("/{user_id}", response_model=MessageResponse)
async def delete_user(
    user_id: UUID,
    request: Request,
    current: User = Depends(_require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    try:
        await service.soft_delete_user(user_id, actor_id=current.id)
    except ValueError as exc:
        detail = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND
            if detail == "Utilisateur introuvable"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=detail) from exc
    await record_audit(
        db,
        user=current,
        action="delete",
        entity="user",
        entity_id=str(user_id),
        request=request,
    )
    return MessageResponse(message="Utilisateur supprimé")
