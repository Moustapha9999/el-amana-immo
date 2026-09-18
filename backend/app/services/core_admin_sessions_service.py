"""CORE ADMIN — sessions auth (Login 1)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import User
from app.models.auth import SESSION_KIND_MODULE, SESSION_KIND_PLATFORM, AuthSession
from app.services.auth_session_service import AuthSessionService


def _iso(value) -> str | None:
    return value.isoformat() if value else None


class CoreAdminSessionsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _count(self, stmt) -> int:
        result = await self.db.execute(stmt)
        return int(result.scalar() or 0)

    def _status_clause(self, status: str, now: datetime):
        if status == "actives":
            return AuthSession.revoked_at.is_(None), AuthSession.expires_at > now
        if status == "expirees":
            return AuthSession.revoked_at.is_(None), AuthSession.expires_at <= now
        if status == "revoquees":
            return (AuthSession.revoked_at.is_not(None),)
        return ()

    async def kpis(self) -> dict:
        now = datetime.now(timezone.utc)
        total = await self._count(select(func.count()).select_from(AuthSession))
        actives = await self._count(
            select(func.count())
            .select_from(AuthSession)
            .where(AuthSession.revoked_at.is_(None), AuthSession.expires_at > now)
        )
        platform = await self._count(
            select(func.count())
            .select_from(AuthSession)
            .where(
                AuthSession.kind == SESSION_KIND_PLATFORM,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
            )
        )
        module = await self._count(
            select(func.count())
            .select_from(AuthSession)
            .where(
                AuthSession.kind == SESSION_KIND_MODULE,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
            )
        )
        expirees = await self._count(
            select(func.count())
            .select_from(AuthSession)
            .where(AuthSession.revoked_at.is_(None), AuthSession.expires_at <= now)
        )
        revoquees = await self._count(
            select(func.count()).select_from(AuthSession).where(AuthSession.revoked_at.is_not(None))
        )
        return {
            "total": total,
            "actives": actives,
            "platform": platform,
            "module": module,
            "expirees": expirees,
            "revoquees": revoquees,
        }

    def serialize(self, row: AuthSession, *, now: datetime, current_session_id: UUID | None) -> dict:
        user = row.user
        return {
            "id": str(row.id),
            "user_id": str(row.user_id),
            "user_email": user.email if user else "",
            "user_full_name": user.full_name if user else "",
            "kind": row.kind or SESSION_KIND_PLATFORM,
            "module_code": row.module_code,
            "ip_address": row.ip_address,
            "user_agent": row.user_agent,
            "created_at": _iso(row.created_at),
            "expires_at": _iso(row.expires_at),
            "revoked_at": _iso(row.revoked_at),
            "active": row.revoked_at is None and row.expires_at > now,
            "is_current": current_session_id is not None and row.id == current_session_id,
        }

    async def list_sessions(
        self,
        page: int,
        size: int,
        *,
        search: str | None = None,
        kind: str = "tous",
        status: str = "actives",
        current_session_id: UUID | None = None,
    ) -> tuple[list[dict], int, dict]:
        now = datetime.now(timezone.utc)
        stmt = select(AuthSession).options(selectinload(AuthSession.user)).join(User, User.id == AuthSession.user_id)
        if search and search.strip():
            term = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    User.email.ilike(term),
                    User.full_name.ilike(term),
                    AuthSession.ip_address.ilike(term),
                    AuthSession.module_code.ilike(term),
                    AuthSession.user_agent.ilike(term),
                )
            )
        if kind == "platform":
            stmt = stmt.where(AuthSession.kind == SESSION_KIND_PLATFORM)
        elif kind == "module":
            stmt = stmt.where(AuthSession.kind == SESSION_KIND_MODULE)
        for clause in self._status_clause(status, now):
            stmt = stmt.where(clause)

        total = await self._count(select(func.count()).select_from(stmt.order_by(None).subquery()))
        result = await self.db.execute(
            stmt.order_by(AuthSession.created_at.desc()).offset((page - 1) * size).limit(size)
        )
        rows = list(result.scalars().unique().all())
        items = [self.serialize(row, now=now, current_session_id=current_session_id) for row in rows]
        return items, total, await self.kpis()

    async def revoke(self, session_id: UUID, *, actor_session_id: UUID | None) -> dict:
        result = await self.db.execute(
            select(AuthSession).options(selectinload(AuthSession.user)).where(AuthSession.id == session_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise ValueError("Session introuvable")
        if row.revoked_at is not None:
            raise ValueError("Session déjà révoquée")
        if actor_session_id is not None and row.id == actor_session_id:
            raise ValueError("Impossible de révoquer votre session courante")
        await AuthSessionService(self.db).revoke_session(session_id)
        await self.db.refresh(row)
        now = datetime.now(timezone.utc)
        return self.serialize(row, now=now, current_session_id=actor_session_id)
