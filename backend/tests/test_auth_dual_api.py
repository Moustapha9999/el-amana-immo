"""Tests d'intégration auth à deux niveaux — skip si la base n'est pas joignable."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.security import get_password_hash
from app.db.session import AsyncSessionLocal, engine
from app.main import app
from app.models import User


async def _db_ready() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest.fixture
async def client():
    if not await _db_ready():
        pytest.skip("Base PostgreSQL indisponible")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _admin_secret() -> str:
    return os.environ.get("BEA_TEST_PASSWORD", "Admin@2026")


async def _login_platform(client: AsyncClient, email="admin@el-amana.mr", password: str | None = None):
    res = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password or _admin_secret()},
    )
    return res


@pytest.mark.asyncio
async def test_immobilisations_requires_module_session(client: AsyncClient):
    bare = await client.get("/api/v1/immobilisations")
    assert bare.status_code == 401

    login = await _login_platform(client)
    if login.status_code != 200:
        pytest.skip("Compte admin seed indisponible")
    tokens = login.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    blocked = await client.get("/api/v1/immobilisations", headers=headers)
    assert blocked.status_code == 401
    detail = blocked.json().get("detail")
    if isinstance(detail, dict):
        assert detail.get("code") == "MODULE_AUTH_REQUIRED"

    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200


@pytest.mark.asyncio
async def test_module_login_bad_password_keeps_platform(client: AsyncClient):
    login = await _login_platform(client)
    if login.status_code != 200:
        pytest.skip("Compte admin seed indisponible")
    platform = login.json()
    p_headers = {"Authorization": f"Bearer {platform['access_token']}"}

    bad = await client.post(
        "/api/v1/auth/modules/immobilisations/login",
        json={"email": "admin@el-amana.mr", "password": "WrongPass1"},
        headers=p_headers,
    )
    assert bad.status_code == 401
    still_me = await client.get("/api/v1/auth/me", headers=p_headers)
    assert still_me.status_code == 200


@pytest.mark.asyncio
async def test_module_login_logout_keeps_platform(client: AsyncClient):
    login = await _login_platform(client)
    if login.status_code != 200:
        pytest.skip("Compte admin seed indisponible")
    platform = login.json()
    p_headers = {"Authorization": f"Bearer {platform['access_token']}"}

    module_login = await client.post(
        "/api/v1/auth/modules/immobilisations/login",
        json={"email": "admin@el-amana.mr", "password": _admin_secret()},
        headers=p_headers,
    )
    assert module_login.status_code == 200, module_login.text
    module = module_login.json()
    m_headers = {"Authorization": f"Bearer {module['access_token']}"}

    ok = await client.get("/api/v1/immobilisations?page=1&size=1", headers=m_headers)
    assert ok.status_code == 200

    logout_mod = await client.post(
        "/api/v1/auth/modules/logout",
        json={"refresh_token": module["refresh_token"]},
        headers=m_headers,
    )
    assert logout_mod.status_code == 200

    denied = await client.get("/api/v1/immobilisations?page=1&size=1", headers=m_headers)
    assert denied.status_code == 401

    still_me = await client.get("/api/v1/auth/me", headers=p_headers)
    assert still_me.status_code == 200

    logout_plat = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": platform["refresh_token"]},
        headers=p_headers,
    )
    assert logout_plat.status_code == 200
    dead = await client.get("/api/v1/auth/me", headers=p_headers)
    assert dead.status_code == 401


@pytest.mark.asyncio
async def test_module_token_rejected_on_other_code(client: AsyncClient):
    login = await _login_platform(client)
    if login.status_code != 200:
        pytest.skip("Compte admin seed indisponible")
    platform = login.json()
    p_headers = {"Authorization": f"Bearer {platform['access_token']}"}
    module_login = await client.post(
        "/api/v1/auth/modules/immobilisations/login",
        json={"email": "admin@el-amana.mr", "password": _admin_secret()},
        headers=p_headers,
    )
    if module_login.status_code != 200:
        pytest.skip("Login module indisponible (catalogue / grants)")
    # Le routeur métier n'expose aujourd'hui que immobilisations : un jeton
    # immo reste kind=module/immobilisations. Vérifie le 401 sur refresh
    # « autre kind » via l'endpoint plateforme refresh.
    bad = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": module_login.json()["refresh_token"]},
    )
    assert bad.status_code == 401


@pytest.mark.asyncio
async def test_core_users_and_manifest_accept_platform_session(client: AsyncClient):
    login = await _login_platform(client)
    if login.status_code != 200:
        pytest.skip("Compte admin seed indisponible")
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    manifest = await client.get("/api/v1/plateforme/core", headers=headers)
    assert manifest.status_code == 200, manifest.text
    body = manifest.json()
    assert body["ged"]["table"] == "ged_documents"
    assert body["ged"]["statut"] == "reserve"
    codes = {row["code"] for row in body["permissions"]}
    assert "plateforme.users.admin" in codes
    assert "immobilisations.read" in codes
    assert "core.admin.access" in codes
    espaces = {row["id"] for row in body["espaces"]}
    assert "comptabilite" in espaces

    users = await client.get("/api/v1/users?page=1&size=5", headers=headers)
    assert users.status_code == 200, users.text


@pytest.mark.asyncio
async def test_core_admin_dashboard_platform_only(client: AsyncClient):
    login = await _login_platform(client)
    if login.status_code != 200:
        pytest.skip("Compte admin seed indisponible")
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    dash = await client.get("/api/v1/plateforme/admin/dashboard", headers=headers)
    assert dash.status_code == 200, dash.text
    body = dash.json()
    assert body["kpis"]["utilisateurs"] >= 1
    assert body["kpis"]["departements"] >= 1
    assert "etat" in body
    assert body["etat"]["api"]["ok"] is True
    assert isinstance(body["activite"], list)

    module_login = await client.post(
        "/api/v1/auth/modules/immobilisations/login",
        json={"email": "admin@el-amana.mr", "password": _admin_secret()},
        headers=headers,
    )
    if module_login.status_code != 200:
        pytest.skip("Login module indisponible (catalogue / grants)")
    blocked = await client.get(
        "/api/v1/plateforme/admin/dashboard",
        headers={"Authorization": f"Bearer {module_login.json()['access_token']}"},
    )
    assert blocked.status_code == 401


@pytest.mark.asyncio
async def test_core_admin_dashboard_forbidden_without_permission(client: AsyncClient):
    email = f"core-admin-deny-{uuid4().hex[:8]}@el-amana.mr"
    password = "TestDeny@2026"
    user_id = None
    async with AsyncSessionLocal() as session:
        user = User(
            email=email,
            full_name="Test sans CORE ADMIN",
            hashed_password=get_password_hash(password),
            is_superuser=False,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        user_id = user.id
    try:
        denied_login = await _login_platform(client, email=email, password=password)
        assert denied_login.status_code == 200, denied_login.text
        dash = await client.get(
            "/api/v1/plateforme/admin/dashboard",
            headers={"Authorization": f"Bearer {denied_login.json()['access_token']}"},
        )
        assert dash.status_code == 403
        detail = dash.json().get("detail")
        if isinstance(detail, dict):
            assert detail.get("code") == "PERMISSION_DENIED"
    finally:
        if user_id is not None:
            async with AsyncSessionLocal() as session:
                row = await session.get(User, user_id)
                if row is not None:
                    row.is_active = False
                    row.deleted_at = datetime.now(timezone.utc)
                    await session.commit()
