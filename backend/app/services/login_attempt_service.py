"""Limitation des tentatives de connexion (Login 1 et Login 2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

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
        from app.services.security_policy_service import get_cached_security_policy

        pol = get_cached_security_policy()
        minutes = int(pol.get("login_lockout_window_minutes") or 15)
        return datetime.now(UTC) - timedelta(minutes=minutes)

    async def assert_not_locked(
        self,
        *,
        email: str,
        ip_address: str | None,
        login_kind: str,
        module_code: str | None = None,
    ) -> None:
        from app.services.security_policy_service import get_cached_security_policy

        pol = get_cached_security_policy()
        max_failures = int(pol.get("login_lockout_max_failures") or 5)
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
        if count >= max_failures:
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

    async def clear_lockout(self, *, email: str) -> int:
        """Efface les échecs récents pour lever le lockout (fenêtre courante)."""
        from sqlalchemy import delete

        normalized = email.strip().lower()
        result = await self.db.execute(
            delete(AuthLoginAttempt).where(
                func.lower(AuthLoginAttempt.email) == normalized,
                AuthLoginAttempt.success.is_(False),
                AuthLoginAttempt.created_at >= self._window_start(),
            )
        )
        await self.db.flush()
        return int(result.rowcount or 0)
