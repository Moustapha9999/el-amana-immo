"""Référentiel clients — contexte d'appel, audit, constantes."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.services.audit_service import AuditService
from app.services.permission_service import user_has_permission_codes

MODULE_CODE = "clientele"
ESPACE_CODE = "audit-controle-conformite"


def maintenant() -> datetime:
    return datetime.now(UTC)


def conflit(message: str, code: str, **extra: Any) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, detail={"code": code, "message": message, **extra})


@dataclass
class Ctx:
    user: User
    permissions: set[str] = field(default_factory=set)
    ip_address: str | None = None
    session_id: uuid.UUID | None = None

    def peut(self, *codes: str) -> bool:
        return bool(self.user.is_superuser) or user_has_permission_codes(self.permissions, *codes)

    def exiger(self, *codes: str) -> None:
        if not self.peut(*codes):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail={"code": "PERMISSION_DENIED", "message": "Permission refusée", "required": list(codes)},
            )


class ClienteleService:
    def __init__(self, db: AsyncSession, ctx: Ctx):
        self.db = db
        self.ctx = ctx

    async def audit(self, action: str, entity: str, entity_id: Any, *, before: dict | None = None,
                    after: dict | None = None) -> None:
        await AuditService(self.db).log(
            user=self.ctx.user, action=action, entity=entity,
            entity_id=str(entity_id) if entity_id else None, before=before, after=after,
            ip_address=self.ctx.ip_address, espace_code=ESPACE_CODE, module_code=MODULE_CODE,
            session_id=self.ctx.session_id,
        )
