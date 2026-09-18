"""CORE ADMIN — audit (Phase 7)."""

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
async def test_core_admin_audit_list(client: AsyncClient):
    headers = await _headers(client)
    listed = await client.get("/api/v1/plateforme/admin/audit", headers=headers, params={"page": 1, "size": 20})
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert "kpis" in body
    assert body["kpis"]["total"] >= 1
    assert isinstance(body["items"], list)
    assert "modules" in body
    assert "entities" in body

    today = await client.get(
        "/api/v1/plateforme/admin/audit",
        headers=headers,
        params={"kind": "aujourd_hui", "page": 1, "size": 20},
    )
    assert today.status_code == 200, today.text

    mutations = await client.get(
        "/api/v1/plateforme/admin/audit",
        headers=headers,
        params={"kind": "mutations", "page": 1, "size": 20},
    )
    assert mutations.status_code == 200
    for row in mutations.json()["items"]:
        assert row["action"] in {
            "create",
            "update",
            "delete",
            "revoke",
            "revoke_all",
            "activate",
            "deactivate",
        }


@pytest.mark.asyncio
async def test_core_admin_audit_platform_only(client: AsyncClient):
    headers = await _headers(client)
    module_login = await client.post(
        "/api/v1/auth/modules/immobilisations/login",
        json={"email": "admin@el-amana.mr", "password": _admin_secret()},
        headers=headers,
    )
    if module_login.status_code != 200:
        pytest.skip("Login module indisponible")
    blocked = await client.get(
        "/api/v1/plateforme/admin/audit",
        headers={"Authorization": f"Bearer {module_login.json()['access_token']}"},
    )
    assert blocked.status_code == 401
