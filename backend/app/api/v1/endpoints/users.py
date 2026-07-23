from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.api.v1.endpoints.helpers import to_paginated
from app.db.session import get_db
from app.models import User
from app.schemas.common import PaginatedResponse
from app.schemas.auth import UserCreate, UserRead
from app.services.auth_service import AuthService

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=PaginatedResponse[UserRead])
async def list_users(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _: User = Depends(require_roles("administrateur")),
    db: AsyncSession = Depends(get_db),
):
    items, total = await AuthService(db).list_users(page, size)
    return to_paginated(items, total, page, size, UserRead.model_validate)


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    _: User = Depends(require_roles("administrateur")),
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    try:
        return await service.create_user(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: UUID,
    _: User = Depends(require_roles("administrateur")),
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    user = await service.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable")
    return user
