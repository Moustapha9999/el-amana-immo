"""Audit & notifications — moteur de demandes inter-départements."""

from __future__ import annotations

from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.demandes_engine import ESPACE_LABELS, PROCESSOR_ROLES
from app.models.auth import User
from app.models.enums import TypeNotification
from app.services.audit_helpers import record_audit
from app.services.notification_service import NotificationService

ESPACE_MG = "moyens-generaux"
MODULE_MG = "demandes-mg"


async def audit_request(
    db: AsyncSession,
    user: User | None,
    action: str,
    entity: str,
    entity_id,
    request: Request | None = None,
    before: dict | None = None,
    after: dict | None = None,
    *,
    espace_code: str = ESPACE_MG,
    module_code: str = MODULE_MG,
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
        espace_code=espace_code,
        module_code=module_code,
    )


async def notify_requester(
    db: AsyncSession,
    user_id: UUID,
    titre: str,
    message: str,
    *,
    entity_id=None,
    actor: User | None = None,
    source_espace: str | None = None,
    source_module: str | None = None,
) -> None:
    await NotificationService(db).create(
        user_id=user_id,
        type_notification=TypeNotification.SYSTEME,
        titre=titre,
        message=message,
        entity="mg_employee_request",
        entity_id=str(entity_id) if entity_id is not None else None,
        espace_code=source_espace or ESPACE_MG,
        module_code=source_module or MODULE_MG,
        event_type="mg.request.workflow",
        emetteur_type="utilisateur" if actor else "systeme",
        emetteur_label=(actor.full_name if actor and actor.full_name else "Système"),
        actor_user_id=actor.id if actor else None,
    )


async def notify_target_roles(
    db: AsyncSession,
    titre: str,
    message: str,
    *,
    target_espace: str = ESPACE_MG,
    entity_id=None,
    actor: User | None = None,
) -> int:
    roles = PROCESSOR_ROLES.get(target_espace) or PROCESSOR_ROLES[ESPACE_MG]
    return await NotificationService(db).notify_staff(
        role_codes=roles,
        type_notification=TypeNotification.SYSTEME,
        titre=titre,
        message=message,
        entity="mg_employee_request",
        entity_id=str(entity_id) if entity_id is not None else None,
        espace_code=target_espace,
        module_code=MODULE_MG if target_espace == ESPACE_MG else f"demandes-{target_espace}",
        event_type="mg.request.inbox",
        emetteur_type="utilisateur" if actor else "systeme",
        emetteur_label=(actor.full_name if actor and actor.full_name else "Système"),
        actor_user_id=actor.id if actor else None,
    )


# Compat tests existants
async def notify_mg_roles(
    db: AsyncSession,
    titre: str,
    message: str,
    *,
    entity_id=None,
    actor: User | None = None,
) -> int:
    return await notify_target_roles(
        db, titre, message, target_espace=ESPACE_MG, entity_id=entity_id, actor=actor
    )


def target_label(code: str | None) -> str:
    return ESPACE_LABELS.get(code or "", code or "service destinataire")
