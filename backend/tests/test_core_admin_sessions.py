"""CORE ADMIN — sessions (Phase 6)."""

from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db.session import engine
from app.main import app


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


async def _headers(client: AsyncClient) -> dict[str, str]:
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@el-amana.mr", "password": _admin_secret()},
    )
    if login.status_code != 200:
        pytest.skip("Compte admin seed indisponible")
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_core_admin_sessions_list_and_revoke_guard(client: AsyncClient):
    headers = await _headers(client)
    listed = await client.get(
        "/api/v1/plateforme/admin/sessions",
        headers=headers,
        params={"status": "actives", "page": 1, "size": 50},
    )
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["kpis"]["actives"] >= 1
    assert body["current_session_id"]
    current = next(row for row in body["items"] if row["is_current"])
    assert current["kind"] == "platform"
    assert current["active"] is True

    blocked = await client.post(
        f"/api/v1/plateforme/admin/sessions/{current['id']}/revoke",
        headers=headers,
    )
    assert blocked.status_code == 400

    # Seconde session admin (autre login) pour tester la révocation
    other = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@el-amana.mr", "password": _admin_secret()},
    )
    assert other.status_code == 200
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    other_list = await client.get(
        "/api/v1/plateforme/admin/sessions",
        headers=other_headers,
        params={"status": "actives", "size": 50},
    )
    other_current = next(row for row in other_list.json()["items"] if row["is_current"])
    assert other_current["id"] != current["id"]

    revoked = await client.post(
        f"/api/v1/plateforme/admin/sessions/{other_current['id']}/revoke",
        headers=headers,
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["active"] is False
    assert revoked.json()["revoked_at"]

    dead = await client.get("/api/v1/plateforme/admin/sessions", headers=other_headers)
    assert dead.status_code == 401


@pytest.mark.asyncio
async def test_core_admin_sessions_platform_only(client: AsyncClient):
    headers = await _headers(client)
    module_login = await client.post(
        "/api/v1/auth/modules/immobilisations/login",
        json={"email": "admin@el-amana.mr", "password": _admin_secret()},
        headers=headers,
    )
    if module_login.status_code != 200:
        pytest.skip("Login module indisponible")
    blocked = await client.get(
        "/api/v1/plateforme/admin/sessions",
        headers={"Authorization": f"Bearer {module_login.json()['access_token']}"},
    )
    assert blocked.status_code == 401
