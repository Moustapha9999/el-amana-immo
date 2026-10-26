"""Changement de mot de passe obligatoire après un mot de passe fixé par un administrateur.

Transaction jamais validée (rollback final) : aucune donnée persistée.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db.session import AsyncSessionLocal, engine, get_db
from app.main import app
from app.schemas.auth import UserCreate, UserUpdate
from app.services.auth_service import AuthService
from app.services.auth_session_service import AuthSessionService

ANCIEN = "Ancien#Mdp2026x"
NOUVEAU = "Nouveau#Mdp2026y"


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
            app.dependency_overrides.pop(get_db, None)


@pytest.fixture
async def user(session):
    return await AuthService(session).create_user(
        UserCreate(email=f"mdp-{uuid4().hex[:8]}@el-amana.mr", full_name="Premier login", password=ANCIEN)
    )


async def _client(session, user) -> AsyncClient:
    async def _db():
        yield session

    app.dependency_overrides[get_db] = _db
    tokens = await AuthSessionService(session).issue_platform_tokens(user)
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {tokens.access_token}"},
    )


@pytest.mark.asyncio
async def test_compte_cree_par_admin_doit_changer(session, user):
    assert user.must_change_password is True


@pytest.mark.asyncio
async def test_reset_admin_reimpose_le_changement_et_admin_peut_lever(session, user):
    svc = AuthService(session)
    user.must_change_password = False
    await session.flush()
    user = await svc.update_user(user.id, UserUpdate(password="Reset#Admin2026z"))
    assert user.must_change_password is True
    user = await svc.update_user(user.id, UserUpdate(must_change_password=False))
    assert user.must_change_password is False


@pytest.mark.asyncio
async def test_acces_bloque_tant_que_mot_de_passe_non_change(session, user):
    async with await _client(session, user) as ac:
        bloque = await ac.get("/api/v1/auth/2fa/status")
        assert bloque.status_code == 403, bloque.text
        assert "PASSWORD_CHANGE_REQUIRED" in bloque.text

        me = await ac.get("/api/v1/auth/me")
        assert me.status_code == 200, me.text
        assert me.json()["must_change_password"] is True

        faux = await ac.post(
            "/api/v1/auth/change-password",
            json={"current_password": "Mauvais#2026", "new_password": NOUVEAU},
        )
        assert faux.status_code == 400 and "CURRENT_PASSWORD_INVALID" in faux.text

        identique = await ac.post(
            "/api/v1/auth/change-password", json={"current_password": ANCIEN, "new_password": ANCIEN}
        )
        assert identique.status_code == 400, identique.text

        ok = await ac.post(
            "/api/v1/auth/change-password", json={"current_password": ANCIEN, "new_password": NOUVEAU}
        )
        assert ok.status_code == 200, ok.text

        libre = await ac.get("/api/v1/auth/2fa/status")
        assert libre.status_code == 200, libre.text
    assert user.must_change_password is False
