"""Notifications in-app du module Réclamations (jamais d'e-mail automatique)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Reclamation, ReclamationUniteMembre, User
from app.services.notification_service import NotificationService
from app.services.reclamations import constantes as C
from app.services.reclamations.acces import ReclamationsScope


async def notifier(db: AsyncSession, s: ReclamationsScope, r: Reclamation, *,
                   destinataires: set[uuid.UUID], titre: str, message: str,
                   priorite: str = "normale") -> None:
    ids = {i for i in destinataires if i and i != s.user_id}
    if not ids:
        return
    svc = NotificationService(db)
    for uid in ids:
        await svc.create(
            user_id=uid, type_notification="systeme", titre=titre, message=message,
            entity=C.GED_ENTITE, entity_id=str(r.id), espace_code=C.ESPACE_CODE,
            module_code=C.MODULE_CODE, priorite=priorite, event_type="reclamations",
            emetteur_type="module", emetteur_label="Réclamations", actor_user_id=s.user_id,
        )


async def membres_unite(db: AsyncSession, unite_id: uuid.UUID | None) -> set[uuid.UUID]:
    if not unite_id:
        return set()
    return set((await db.scalars(select(ReclamationUniteMembre.user_id).where(
        ReclamationUniteMembre.unite_id == unite_id, ReclamationUniteMembre.actif.is_(True),
    ))).all())


async def membres_profils(db: AsyncSession, *codes: str) -> set[uuid.UUID]:
    from app.models.associations import user_roles_table
    from app.models.auth import Role
    return set((await db.scalars(
        select(User.id).join(user_roles_table, user_roles_table.c.user_id == User.id)
        .join(Role, Role.id == user_roles_table.c.role_id)
        .where(Role.code.in_(codes), User.deleted_at.is_(None))
    )).all())


async def destinataires_sr(db: AsyncSession, ctx) -> set[uuid.UUID]:
    sr = ctx.service_central()
    ids = await membres_unite(db, sr.id) if sr else set()
    ids |= await membres_profils(db, "reclamations.responsable_sr", "reclamations.agent_sr", "reclamations.admin")
    return ids
