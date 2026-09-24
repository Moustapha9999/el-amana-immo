"""Audit & notifications — Notes de frais (Moyens Généraux)."""

from __future__ import annotations

from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import User
from app.models.enums import TypeNotification
from app.services.audit_helpers import record_audit
from app.services.notification_service import NotificationService

ESPACE = "moyens-generaux"
MODULE = "notes-frais"


async def audit_notes(
    db: AsyncSession,
    user: User | None,
    action: str,
    entity: str,
    entity_id,
    request: Request | None = None,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    await record_audit(
        db,
        user=user,
        action=action,
        entity=entity,
        entity_id=str(entity_id) if entity_id is not None else None,
        request=request,
        before=before,
        after=after,
        espace_code=ESPACE,
        module_code=MODULE,
    )


async def notify_notes_user(
    db: AsyncSession,
    user_id: UUID,
    titre: str,
    message: str,
    *,
    entity: str | None = None,
    entity_id=None,
    event_type: str = "notes.workflow",
    actor: User | None = None,
) -> None:
    await NotificationService(db).create(
        user_id=user_id,
        type_notification=TypeNotification.SYSTEME,
        titre=titre,
        message=message,
        entity=entity,
        entity_id=str(entity_id) if entity_id is not None else None,
        espace_code=ESPACE,
        module_code=MODULE,
        event_type=event_type,
        emetteur_type="utilisateur" if actor else "systeme",
        emetteur_label=(actor.full_name if actor and actor.full_name else "Système"),
        actor_user_id=actor.id if actor else None,
    )


async def notify_notes_roles(
    db: AsyncSession,
    role_codes: set[str],
    titre: str,
    message: str,
    *,
    entity: str | None = None,
    entity_id=None,
    event_type: str = "notes.workflow",
    actor: User | None = None,
) -> int:
    return await NotificationService(db).notify_staff(
        role_codes=role_codes,
        type_notification=TypeNotification.SYSTEME,
        titre=titre,
        message=message,
        entity=entity,
        entity_id=str(entity_id) if entity_id is not None else None,
        espace_code=ESPACE,
        module_code=MODULE,
        event_type=event_type,
        emetteur_type="utilisateur" if actor else "systeme",
        emetteur_label=(actor.full_name if actor and actor.full_name else "Système"),
        actor_user_id=actor.id if actor else None,
    )
