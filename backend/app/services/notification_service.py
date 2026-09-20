from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.pagination import page_offset
from app.data.notification_taxonomy import (
    categorie_from_type,
    coerce_type_notification,
    infer_priorite,
)
from app.models import Notification, User
from app.models.enums import TypeNotification


def _event_code_for(notif_id: UUID, when: datetime | None = None) -> str:
    year = (when or datetime.now(timezone.utc)).year
    return f"EVT-{year}-{str(notif_id).replace('-', '')[:8].upper()}"


class NotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        *,
        user_id: UUID,
        type_notification: TypeNotification | str,
        titre: str,
        message: str,
        entity: str | None = None,
        entity_id: str | None = None,
        espace_code: str | None = None,
        module_code: str | None = None,
        categorie: str | None = None,
        priorite: str | None = None,
        event_type: str | None = None,
        emetteur_type: str = "systeme",
        emetteur_label: str = "Système",
        destinataire_type: str = "utilisateur",
        destinataire_label: str | None = None,
        actor_user_id: UUID | None = None,
    ) -> Notification:
        raw_type = (
            type_notification.value
            if hasattr(type_notification, "value")
            else str(type_notification)
        )
        enum_type = coerce_type_notification(type_notification)
        row = Notification(
            user_id=user_id,
            type_notification=enum_type,
            titre=titre,
            message=message,
            entity=entity,
            entity_id=entity_id,
            espace_code=espace_code,
            module_code=module_code,
            lu=False,
            categorie=categorie or categorie_from_type(raw_type, module_code=module_code),
            priorite=infer_priorite(titre, message, explicit=priorite),
            event_type=event_type or raw_type,
            emetteur_type=emetteur_type,
            emetteur_label=emetteur_label,
            destinataire_type=destinataire_type,
            destinataire_label=destinataire_label,
            actor_user_id=actor_user_id,
            archived=False,
        )
        self.db.add(row)
        await self.db.flush()
        if not row.event_code:
            row.event_code = _event_code_for(row.id, row.created_at)
            await self.db.flush()
        if not row.destinataire_label:
            user = await self.db.get(User, user_id)
            if user:
                row.destinataire_label = user.full_name or user.email
                await self.db.flush()
        return row

    async def notify_staff(
        self,
        *,
        role_codes: set[str],
        type_notification: TypeNotification | str,
        titre: str,
        message: str,
        entity: str | None = None,
        entity_id: str | None = None,
        espace_code: str | None = None,
        module_code: str | None = None,
        categorie: str | None = None,
        priorite: str | None = None,
        event_type: str | None = None,
        emetteur_type: str = "systeme",
        emetteur_label: str = "Système",
        destinataire_type: str = "role",
        destinataire_label: str | None = None,
        actor_user_id: UUID | None = None,
    ) -> int:
        result = await self.db.execute(
            select(User).options(selectinload(User.roles)).where(User.is_active.is_(True), User.deleted_at.is_(None))
        )
        count = 0
        dest_label = destinataire_label or (
            "Administrateurs" if destinataire_type == "administrateurs" else "Rôles concernés"
        )
        for user in result.scalars().all():
            if user.is_superuser or any(r.code in role_codes for r in user.roles):
                await self.create(
                    user_id=user.id,
                    type_notification=type_notification,
                    titre=titre,
                    message=message,
                    entity=entity,
                    entity_id=entity_id,
                    espace_code=espace_code,
                    module_code=module_code,
                    categorie=categorie,
                    priorite=priorite,
                    event_type=event_type,
                    emetteur_type=emetteur_type,
                    emetteur_label=emetteur_label,
                    destinataire_type=destinataire_type,
                    destinataire_label=dest_label,
                    actor_user_id=actor_user_id,
                )
                count += 1
        return count

    async def list_for_user(self, user_id: UUID, page: int, size: int, unread_only: bool = False) -> tuple[list[Notification], int]:
        filters = [Notification.user_id == user_id, Notification.archived.is_(False)]
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
        result = await self.db.execute(
            select(Notification).where(
                Notification.user_id == user_id,
                Notification.lu.is_(False),
                Notification.archived.is_(False),
            )
        )
        rows = list(result.scalars().all())
        for row in rows:
            row.lu = True
        await self.db.flush()
        return len(rows)
