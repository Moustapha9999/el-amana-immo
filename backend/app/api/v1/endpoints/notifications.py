from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.common import MessageResponse, PaginatedResponse
from app.schemas.reporting import NotificationRead
from app.services.notification_service import NotificationService
from app.api.v1.endpoints.helpers import to_paginated

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=PaginatedResponse[NotificationRead])
async def list_notifications(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    unread_only: bool = False,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await NotificationService(db).list_for_user(user.id, page, size, unread_only)
    return to_paginated(items, total, page, size, NotificationRead.model_validate)


@router.patch("/{notification_id}/read", response_model=NotificationRead)
async def mark_notification_read(
    notification_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await NotificationService(db).mark_read(notification_id, user.id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification introuvable")
    return row


@router.post("/read-all", response_model=MessageResponse)
async def mark_all_read(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    count = await NotificationService(db).mark_all_read(user.id)
    return MessageResponse(message=f"{count} notification(s) lue(s)")
