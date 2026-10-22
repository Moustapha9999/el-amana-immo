from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.pagination import page_offset
from app.data.notification_routing import (
    PORTEE_CORE_ADMIN,
    PORTEE_MODULE,
    PORTEE_PLATEFORME,
    PORTEES,
    codes_module,
    portee_par_defaut,
    route_autorisee,
)
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


@dataclass(frozen=True)
class NotificationScope:
    """Espace de notifications consulté, déduit de la session authentifiée (jamais de la requête)."""

    portee: str
    module_code: str | None = None
    espace_code: str | None = None

    @classmethod
    def module(cls, module_code: str, espace_code: str | None) -> "NotificationScope":
        return cls(PORTEE_MODULE, module_code.strip().lower(), espace_code)

    @classmethod
    def plateforme(cls) -> "NotificationScope":
        return cls(PORTEE_PLATEFORME)

    @classmethod
    def core_admin(cls) -> "NotificationScope":
        return cls(PORTEE_CORE_ADMIN)

    def filters(self) -> list:
        if self.portee == PORTEE_MODULE:
            if not self.module_code or not self.espace_code:
                return [Notification.id.is_(None)]
            return [
                Notification.portee == PORTEE_MODULE,
                Notification.module_code.in_(codes_module(self.module_code)),
                Notification.espace_code == self.espace_code,
            ]
        if self.portee == PORTEE_PLATEFORME:
            # Anciennes notifications sans module d'origine connu : visibles ici seulement.
            return [
                or_(
                    Notification.portee == PORTEE_PLATEFORME,
                    and_(Notification.portee == PORTEE_MODULE, Notification.module_code.is_(None)),
                )
            ]
        return [Notification.portee == PORTEE_CORE_ADMIN]


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
        portee: str | None = None,
        categorie: str | None = None,
        priorite: str | None = None,
        event_type: str | None = None,
        emetteur_type: str = "systeme",
        emetteur_label: str = "Système",
        destinataire_type: str = "utilisateur",
        destinataire_label: str | None = None,
        actor_user_id: UUID | None = None,
    ) -> Notification:
        portee = portee or portee_par_defaut(module_code)
        if portee not in PORTEES:
            raise ValueError(f"Portée de notification inconnue : {portee}")
        if portee == PORTEE_MODULE and not module_code:
            raise ValueError("Une notification de module exige son module d'origine")
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
            portee=portee,
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

    async def create_multi_espaces(
        self,
        *,
        source_module: str,
        destinations: list[tuple[str, str]],
        **kwargs,
    ) -> list[Notification]:
        """Diffusion explicite : une notification par (espace_code, module_code) autorisé."""
        refusees = [m for _e, m in destinations if not route_autorisee(source_module, m)]
        if refusees:
            raise ValueError(
                f"Diffusion non autorisée depuis {source_module} vers : {', '.join(sorted(set(refusees)))}"
            )
        return [
            await self.create(espace_code=espace, module_code=module, portee=PORTEE_MODULE, **kwargs)
            for espace, module in dict.fromkeys(destinations)
        ]

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
        portee: str | None = None,
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
                    portee=portee,
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

    @staticmethod
    def _base_filters(user_id: UUID, scope: NotificationScope) -> list:
        return [Notification.user_id == user_id, Notification.archived.is_(False), *scope.filters()]

    async def list_for_user(
        self,
        user_id: UUID,
        page: int,
        size: int,
        unread_only: bool = False,
        entity: str | None = None,
        event_type: str | None = None,
        *,
        scope: NotificationScope,
    ) -> tuple[list[Notification], int]:
        filters = self._base_filters(user_id, scope)
        if unread_only:
            filters.append(Notification.lu.is_(False))
        if entity:
            filters.append(Notification.entity == entity)
        if event_type:
            filters.append(Notification.event_type == event_type)
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

    async def count_unread(
        self, user_id: UUID, *, scope: NotificationScope, entity: str | None = None
    ) -> int:
        filters = [*self._base_filters(user_id, scope), Notification.lu.is_(False)]
        if entity:
            filters.append(Notification.entity == entity)
        return int(
            (await self.db.scalar(select(func.count()).select_from(Notification).where(*filters))) or 0
        )

    async def mark_read(
        self, notification_id: UUID, user_id: UUID, *, scope: NotificationScope
    ) -> Notification | None:
        row = await self.db.scalar(
            select(Notification).where(
                Notification.id == notification_id, *self._base_filters(user_id, scope)
            )
        )
        if row is None:
            return None
        row.lu = True
        await self.db.flush()
        return row

    async def mark_all_read(
        self, user_id: UUID, entity: str | None = None, *, scope: NotificationScope
    ) -> int:
        filters = [*self._base_filters(user_id, scope), Notification.lu.is_(False)]
        if entity:
            filters.append(Notification.entity == entity)
        result = await self.db.execute(select(Notification).where(*filters))
        rows = list(result.scalars().all())
        for row in rows:
            row.lu = True
        await self.db.flush()
        return len(rows)
