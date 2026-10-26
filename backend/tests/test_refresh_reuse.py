"""Rejeu d'un refresh token déjà consommé : session (et sessions module filles) révoquée.

Tests service sur base PostgreSQL (transaction annulée) ; test endpoint sans base.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.v1.endpoints import auth as auth_endpoint
from app.db.session import AsyncSessionLocal, engine, get_db
from app.main import app
from app.models import AuthSession, User
from app.services.auth_session_service import (
    REFRESH_REUSE_GRACE_SECONDS,
    AuthSessionService,
    RefreshTokenReuseError,
)


@pytest.fixture
async def session():
    await engine.dispose()
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("Base PostgreSQL indisponible")
    async with AsyncSessionLocal() as s:
        try:
            yield s
        finally:
            await s.rollback()


@pytest.fixture
async def user(session):
    u = User(
        email=f"rejeu-{uuid4().hex[:8]}@el-amana.mr",
        full_name="Rejeu",
        hashed_password="x",
        is_superuser=False,
        is_active=True,
        totp_enabled=False,
    )
    session.add(u)
    await session.flush()
    await session.refresh(u, ["roles"])
    return u


async def _vieillir(session, sid, secondes: int) -> None:
    """Simule une rotation survenue il y a `secondes`."""
    row = await session.get(AuthSession, sid)
    row.expires_at = row.expires_at - timedelta(seconds=secondes)
    await session.flush()


def _sid(svc: AuthSessionService, token: str):
    from uuid import UUID

    return UUID(svc._decode_unverified(token)["sid"])


@pytest.mark.asyncio
async def test_rotation_normale_puis_rejeu_dans_la_marge_sans_revocation(session, user):
    svc = AuthSessionService(session)
    initial = await svc.issue_platform_tokens(user)
    suivant = await svc.rotate_refresh(initial.refresh_token, user)
    assert suivant.refresh_token != initial.refresh_token

    with pytest.raises(ValueError) as exc:
        await svc.rotate_refresh(initial.refresh_token, user)
    assert not isinstance(exc.value, RefreshTokenReuseError)

    sid = _sid(svc, initial.refresh_token)
    assert await svc.get_active_session(sid) is not None
    assert (await svc.rotate_refresh(suivant.refresh_token, user)).refresh_token


@pytest.mark.asyncio
async def test_rejeu_hors_marge_revoque_session_et_sessions_module(session, user):
    svc = AuthSessionService(session)
    initial = await svc.issue_platform_tokens(user)
    sid = _sid(svc, initial.refresh_token)
    module = await svc.issue_module_tokens(user, module_code="immobilisations", parent_session_id=sid)
    suivant = await svc.rotate_refresh(initial.refresh_token, user)
    await _vieillir(session, sid, REFRESH_REUSE_GRACE_SECONDS + 30)

    with pytest.raises(RefreshTokenReuseError):
        await svc.rotate_refresh(initial.refresh_token, user)

    assert await svc.get_active_session(sid) is None
    assert await svc.get_active_session(_sid(svc, module.refresh_token)) is None
    with pytest.raises(ValueError):
        await svc.rotate_refresh(suivant.refresh_token, user)


@pytest.mark.asyncio
async def test_endpoint_valide_la_revocation_avant_401(monkeypatch):
    db = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    user = SimpleNamespace(id=uuid4())

    async def _db():
        yield db

    monkeypatch.setattr(auth_endpoint, "decode_token", lambda _t: {"type": "refresh", "sub": str(user.id), "sid": "s"})
    monkeypatch.setattr(auth_endpoint.AuthService, "get_by_id", AsyncMock(return_value=user))
    monkeypatch.setattr(
        auth_endpoint.AuthSessionService,
        "rotate_refresh",
        AsyncMock(side_effect=RefreshTokenReuseError("rejeu")),
    )
    audit = AsyncMock()
    monkeypatch.setattr(auth_endpoint, "record_audit", audit)
    app.dependency_overrides[get_db] = _db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.post("/api/v1/auth/refresh", json={"refresh_token": "x"})
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert res.status_code == 401, res.text
    assert "SESSION_REVOKED" in res.text
    assert audit.await_args.kwargs["action"] == "refresh_token_reuse"
    db.commit.assert_awaited()
