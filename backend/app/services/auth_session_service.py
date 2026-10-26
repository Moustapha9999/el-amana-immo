"""Sessions JWT révocables — Login 1 (plateforme) et Login 2 (module) indépendants."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    new_jti,
)
from app.models import AuthSession, User
from app.models.auth import SESSION_KIND_MODULE, SESSION_KIND_PLATFORM
from app.schemas.auth import TokenPair
from app.services.security_policy_service import get_cached_security_policy

# Deux onglets peuvent présenter le même refresh token à quelques secondes d'écart :
# ce n'est pas un vol, la session n'est pas révoquée.
REFRESH_REUSE_GRACE_SECONDS = 20


class RefreshTokenReuseError(ValueError):
    """Refresh token déjà consommé présenté de nouveau : session révoquée (vol probable).

    L'appelant doit valider la transaction avant de répondre, sinon la révocation est annulée."""


class AuthSessionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _role_claims(self, user: User) -> dict:
        return {"roles": [r.code for r in user.roles], "is_superuser": user.is_superuser}

    def _ttl(self) -> tuple[int, int, int]:
        settings = get_settings()
        policy = get_cached_security_policy()
        access_min = int(
            policy.get("access_token_expire_minutes") or settings.access_token_expire_minutes
        )
        refresh_days = int(
            policy.get("refresh_token_expire_days") or settings.refresh_token_expire_days
        )
        module_min = int(
            policy.get("module_refresh_token_expire_minutes")
            or settings.module_refresh_token_expire_minutes
        )
        return max(1, access_min), max(1, refresh_days), max(5, module_min)

    def refresh_max_age_seconds(self, kind: str) -> int:
        _access_min, refresh_days, module_min = self._ttl()
        return module_min * 60 if kind == SESSION_KIND_MODULE else refresh_days * 86400

    def _pair_for(self, user: User, session: AuthSession, refresh_jti: str) -> TokenPair:
        _access_min, refresh_days, module_min = self._ttl()
        extra = {
            **self._role_claims(user),
            "kind": session.kind,
        }
        refresh_extra = {"kind": session.kind}
        expire_delta = timedelta(days=refresh_days)
        if session.kind == SESSION_KIND_MODULE:
            extra["module"] = session.module_code
            extra["parent_sid"] = str(session.parent_session_id) if session.parent_session_id else None
            refresh_extra["module"] = session.module_code
            expire_delta = timedelta(minutes=module_min)
        return TokenPair(
            access_token=create_access_token(user.id, sid=session.id, extra_claims=extra),
            refresh_token=create_refresh_token(
                user.id,
                sid=session.id,
                refresh_jti=refresh_jti,
                extra_claims=refresh_extra,
                expire_delta=expire_delta,
            ),
        )

    async def issue_tokens(
        self,
        user: User,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TokenPair:
        return await self.issue_platform_tokens(user, ip_address=ip_address, user_agent=user_agent)

    async def issue_platform_tokens(
        self,
        user: User,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TokenPair:
        refresh_jti = new_jti()
        _access_min, refresh_days, _module_min = self._ttl()
        expires_at = datetime.now(UTC) + timedelta(days=refresh_days)
        session = AuthSession(
            user_id=user.id,
            refresh_jti=refresh_jti,
            expires_at=expires_at,
            ip_address=ip_address[:64] if ip_address else None,
            user_agent=user_agent[:255] if user_agent else None,
            kind=SESSION_KIND_PLATFORM,
            module_code=None,
            parent_session_id=None,
        )
        self.db.add(session)
        await self.db.flush()
        return self._pair_for(user, session, refresh_jti)

    async def issue_module_tokens(
        self,
        user: User,
        *,
        module_code: str,
        parent_session_id: UUID,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TokenPair:
        await self.revoke_module_sessions(user.id, module_code)
        refresh_jti = new_jti()
        _access_min, _refresh_days, module_min = self._ttl()
        expires_at = datetime.now(UTC) + timedelta(minutes=module_min)
        session = AuthSession(
            user_id=user.id,
            refresh_jti=refresh_jti,
            expires_at=expires_at,
            ip_address=ip_address[:64] if ip_address else None,
            user_agent=user_agent[:255] if user_agent else None,
            kind=SESSION_KIND_MODULE,
            module_code=module_code,
            parent_session_id=parent_session_id,
        )
        self.db.add(session)
        await self.db.flush()
        return self._pair_for(user, session, refresh_jti)

    @staticmethod
    def _expires_utc(session: AuthSession) -> datetime:
        expires = session.expires_at
        return expires.replace(tzinfo=UTC) if expires.tzinfo is None else expires

    def _is_inactive(self, session: AuthSession) -> bool:
        return session.revoked_at is not None or self._expires_utc(session) < datetime.now(UTC)

    def _rotated_seconds_ago(self, session: AuthSession) -> float:
        """Chaque émission/rotation fixe expires_at = maintenant + TTL : on en déduit son heure."""
        _access_min, refresh_days, module_min = self._ttl()
        ttl = (
            timedelta(minutes=module_min)
            if session.kind == SESSION_KIND_MODULE
            else timedelta(days=refresh_days)
        )
        return (datetime.now(UTC) - (self._expires_utc(session) - ttl)).total_seconds()

    async def get_active_session(self, sid: UUID) -> AuthSession | None:
        result = await self.db.execute(select(AuthSession).where(AuthSession.id == sid))
        session = result.scalar_one_or_none()
        if session is None or self._is_inactive(session):
            return None
        return session

    async def rotate_refresh(
        self,
        refresh_token: str,
        user: User,
        *,
        expected_kind: str = SESSION_KIND_PLATFORM,
    ) -> TokenPair:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise ValueError("Refresh token invalide")
        if payload.get("kind", SESSION_KIND_PLATFORM) != expected_kind:
            raise ValueError("Refresh token invalide")
        sid_raw = payload.get("sid")
        jti = payload.get("jti")
        if not sid_raw or not jti:
            raise ValueError("Refresh token invalide")

        session = await self.db.scalar(
            select(AuthSession).where(AuthSession.id == UUID(str(sid_raw))).with_for_update()
        )
        if session is None or self._is_inactive(session):
            raise ValueError("Session invalide ou révoquée")
        if session.user_id != user.id:
            raise ValueError("Session invalide")
        if session.refresh_jti != jti:
            if self._rotated_seconds_ago(session) > REFRESH_REUSE_GRACE_SECONDS:
                await self.revoke_session(session.id)
                raise RefreshTokenReuseError("Réutilisation d'un jeton détectée : session révoquée")
            raise ValueError("Session invalide ou révoquée")
        if (session.kind or SESSION_KIND_PLATFORM) != expected_kind:
            raise ValueError("Session invalide")

        if expected_kind == SESSION_KIND_MODULE:
            if session.parent_session_id is None:
                raise ValueError("Session invalide")
            parent = await self.get_active_session(session.parent_session_id)
            if parent is None or parent.kind != SESSION_KIND_PLATFORM:
                raise ValueError("Session plateforme expirée ou révoquée")

        new_refresh_jti = new_jti()
        _access_min, refresh_days, module_min = self._ttl()
        session.refresh_jti = new_refresh_jti
        if session.kind == SESSION_KIND_MODULE:
            session.expires_at = datetime.now(UTC) + timedelta(minutes=module_min)
        else:
            session.expires_at = datetime.now(UTC) + timedelta(days=refresh_days)
        await self.db.flush()
        return self._pair_for(user, session, new_refresh_jti)

    def _decode_unverified(self, token: str) -> dict | None:
        try:
            return decode_token(token)
        except ValueError:
            from jose import jwt

            settings = get_settings()
            try:
                return jwt.decode(
                    token,
                    settings.secret_key,
                    algorithms=[settings.jwt_algorithm],
                    options={"verify_exp": False},
                )
            except Exception:
                return None

    async def revoke_by_token(self, token: str) -> None:
        payload = self._decode_unverified(token)
        if not payload:
            return
        sid_raw = payload.get("sid")
        if not sid_raw:
            return
        await self.revoke_session(UUID(str(sid_raw)))

    async def revoke_session(self, sid: UUID) -> None:
        now = datetime.now(UTC)
        await self.db.execute(
            update(AuthSession)
            .where(AuthSession.id == sid, AuthSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await self.db.execute(
            update(AuthSession)
            .where(AuthSession.parent_session_id == sid, AuthSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await self.db.flush()

    async def revoke_module_sessions(self, user_id: UUID, module_code: str) -> None:
        now = datetime.now(UTC)
        await self.db.execute(
            update(AuthSession)
            .where(
                AuthSession.user_id == user_id,
                AuthSession.kind == SESSION_KIND_MODULE,
                AuthSession.module_code == module_code,
                AuthSession.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        await self.db.flush()

    async def revoke_all_for_user(self, user_id: UUID) -> None:
        now = datetime.now(UTC)
        await self.db.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await self.db.flush()
