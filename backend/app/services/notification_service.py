from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.pagination import page_offset
from app.models import Notification, User
from app.models.enums import TypeNotification


class NotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        *,
        user_id: UUID,
        type_notification: TypeNotification,
        titre: str,
        message: str,
        entity: str | None = None,
        entity_id: str | None = None,
    ) -> Notification:
        row = Notification(
            user_id=user_id,
            type_notification=type_notification,
            titre=titre,
            message=message,
            entity=entity,
            entity_id=entity_id,
            lu=False,
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def notify_staff(
        self,
        *,
        role_codes: set[str],
        type_notification: TypeNotification,
        titre: str,
        message: str,
        entity: str | None = None,
        entity_id: str | None = None,
    ) -> int:
        result = await self.db.execute(
            select(User).options(selectinload(User.roles)).where(User.is_active.is_(True), User.deleted_at.is_(None))
        )
        count = 0
        for user in result.scalars().all():
            if user.is_superuser or any(r.code in role_codes for r in user.roles):
                await self.create(
                    user_id=user.id,
                    type_notification=type_notification,
                    titre=titre,
                    message=message,
                    entity=entity,
                    entity_id=entity_id,
                )
                count += 1
        return count

    async def list_for_user(self, user_id: UUID, page: int, size: int, unread_only: bool = False) -> tuple[list[Notification], int]:
        filters = [Notification.user_id == user_id]
        if unread_only:
            filters.append(Notification.lu.is_(False))
        count = await self.db.execute(select(func.count()).select_from(Notification).where(*filters))
        total = int(count.scalar_one())
        result = await self.db.execute(
            select(Notification)
            .where(*filters)
            .order_by(Notification.created_at.desc())
            .offset(page_offset(page, size))
            .limit(size)
        )
        return list(result.scalars().all()), total

    async def mark_read(self, notification_id: UUID, user_id: UUID) -> Notification | None:
        row = await self.db.get(Notification, notification_id)
        if row is None or row.user_id != user_id:
            return None
        row.lu = True
        await self.db.flush()
        return row

    async def mark_all_read(self, user_id: UUID) -> int:
        result = await self.db.execute(select(Notification).where(Notification.user_id == user_id, Notification.lu.is_(False)))
        rows = list(result.scalars().all())
        for row in rows:
            row.lu = True
        await self.db.flush()
        return len(rows)
