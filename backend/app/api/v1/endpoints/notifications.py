"""Notifications de l'utilisateur, cloisonnées par espace.

L'espace consulté (module + département, ou plateforme) est déduit de la session authentifiée
par ``get_notification_context`` : aucun paramètre de requête ne permet d'en changer.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_notification_context
from app.db.session import get_db
from app.models import User
from app.schemas.common import MessageResponse, PaginatedResponse
from app.schemas.reporting import NotificationRead
from app.services.notification_service import NotificationScope, NotificationService
from app.api.v1.endpoints.helpers import to_paginated

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=PaginatedResponse[NotificationRead])
async def list_notifications(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    unread_only: bool = False,
    entity: str | None = Query(None, max_length=80),
    event_type: str | None = Query(None, max_length=80),
    ctx: tuple[User, NotificationScope] = Depends(get_notification_context),
    db: AsyncSession = Depends(get_db),
):
    user, scope = ctx
    items, total = await NotificationService(db).list_for_user(
        user.id, page, size, unread_only, entity=entity, event_type=event_type, scope=scope
    )
    return to_paginated(items, total, page, size, NotificationRead.model_validate)


@router.get("/unread-count")
async def unread_count(
    entity: str | None = Query(None, max_length=80),
    ctx: tuple[User, NotificationScope] = Depends(get_notification_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user, scope = ctx
    count = await NotificationService(db).count_unread(user.id, scope=scope, entity=entity)
    return {"count": count, "portee": scope.portee, "module_code": scope.module_code}


@router.patch("/{notification_id}/read", response_model=NotificationRead)
async def mark_notification_read(
    notification_id: UUID,
    ctx: tuple[User, NotificationScope] = Depends(get_notification_context),
    db: AsyncSession = Depends(get_db),
):
    user, scope = ctx
    row = await NotificationService(db).mark_read(notification_id, user.id, scope=scope)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification introuvable")
    return row


@router.post("/read-all", response_model=MessageResponse)
async def mark_all_read(
    entity: str | None = Query(None, max_length=80),
    ctx: tuple[User, NotificationScope] = Depends(get_notification_context),
    db: AsyncSession = Depends(get_db),
):
    user, scope = ctx
    count = await NotificationService(db).mark_all_read(user.id, entity=entity, scope=scope)
    return MessageResponse(message=f"{count} notification(s) lue(s)")
