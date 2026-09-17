"""Limitation des tentatives de connexion (Login 1 et Login 2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import AuthLoginAttempt


class LoginLockedError(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "LOGIN_LOCKED",
                "message": "Trop de tentatives. Réessayez dans quelques minutes.",
            },
        )


class LoginAttemptService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _window_start(self) -> datetime:
        settings = get_settings()
        return datetime.now(UTC) - timedelta(minutes=settings.login_lockout_window_minutes)

    async def assert_not_locked(
        self,
        *,
        email: str,
        ip_address: str | None,
        login_kind: str,
        module_code: str | None = None,
    ) -> None:
        settings = get_settings()
        filters = [
            func.lower(AuthLoginAttempt.email) == email.strip().lower(),
            AuthLoginAttempt.login_kind == login_kind,
            AuthLoginAttempt.success.is_(False),
            AuthLoginAttempt.created_at >= self._window_start(),
        ]
        if module_code:
            filters.append(AuthLoginAttempt.module_code == module_code)
        result = await self.db.execute(select(func.count()).select_from(AuthLoginAttempt).where(*filters))
        count = int(result.scalar_one())
        if count >= settings.login_lockout_max_failures:
            raise LoginLockedError()

    async def record(
        self,
        *,
        email: str,
        ip_address: str | None,
        login_kind: str,
        success: bool,
        module_code: str | None = None,
    ) -> None:
        self.db.add(
            AuthLoginAttempt(
                email=email.strip().lower()[:255],
                ip_address=ip_address[:64] if ip_address else None,
                login_kind=login_kind,
                module_code=module_code,
                success=success,
            )
        )
        await self.db.flush()
