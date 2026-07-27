"""Sessions JWT révocables — multi-utilisateurs / multi-onglets indépendants."""

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
from app.schemas.auth import TokenPair


class AuthSessionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def issue_tokens(
        self,
        user: User,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TokenPair:
        settings = get_settings()
        refresh_jti = new_jti()
        expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
        session = AuthSession(
            user_id=user.id,
            refresh_jti=refresh_jti,
            expires_at=expires_at,
            ip_address=ip_address[:64] if ip_address else None,
            user_agent=user_agent[:255] if user_agent else None,
        )
        self.db.add(session)
        await self.db.flush()

        role_codes = [r.code for r in user.roles]
        claims = {"roles": role_codes, "is_superuser": user.is_superuser}
        return TokenPair(
            access_token=create_access_token(user.id, sid=session.id, extra_claims=claims),
            refresh_token=create_refresh_token(user.id, sid=session.id, refresh_jti=refresh_jti),
        )

    async def get_active_session(self, sid: UUID) -> AuthSession | None:
        result = await self.db.execute(select(AuthSession).where(AuthSession.id == sid))
        session = result.scalar_one_or_none()
        if session is None or session.revoked_at is not None:
            return None
        expires = session.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if expires < datetime.now(UTC):
            return None
        return session

    async def rotate_refresh(self, refresh_token: str, user: User) -> TokenPair:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise ValueError("Refresh token invalide")
        sid_raw = payload.get("sid")
        jti = payload.get("jti")
        if not sid_raw or not jti:
            raise ValueError("Refresh token invalide")

        session = await self.get_active_session(UUID(str(sid_raw)))
        if session is None or session.refresh_jti != jti:
            raise ValueError("Session invalide ou révoquée")
        if session.user_id != user.id:
            raise ValueError("Session invalide")

        new_refresh_jti = new_jti()
        settings = get_settings()
        session.refresh_jti = new_refresh_jti
        session.expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
        await self.db.flush()

        role_codes = [r.code for r in user.roles]
        claims = {"roles": role_codes, "is_superuser": user.is_superuser}
        return TokenPair(
            access_token=create_access_token(user.id, sid=session.id, extra_claims=claims),
            refresh_token=create_refresh_token(
                user.id, sid=session.id, refresh_jti=new_refresh_jti
            ),
        )

    async def revoke_by_token(self, token: str) -> None:
        try:
            payload = decode_token(token)
        except ValueError:
            # Token expiré : tenter de lire sans vérif d'exp pour révoquer la session
            from jose import jwt
            from app.core.config import get_settings

            settings = get_settings()
            try:
                payload = jwt.decode(
                    token,
                    settings.secret_key,
                    algorithms=[settings.jwt_algorithm],
                    options={"verify_exp": False},
                )
            except Exception:
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
        await self.db.flush()

    async def revoke_all_for_user(self, user_id: UUID) -> None:
        now = datetime.now(UTC)
        await self.db.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await self.db.flush()
