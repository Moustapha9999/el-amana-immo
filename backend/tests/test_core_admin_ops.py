"""CORE ADMIN — activité / alertes / notifications / GED / settings."""

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
async def test_core_admin_ops_endpoints(client: AsyncClient):
    headers = await _headers(client)
    for path in (
        "/api/v1/plateforme/admin/activity",
        "/api/v1/plateforme/admin/alerts",
        "/api/v1/plateforme/admin/notifications",
        "/api/v1/plateforme/admin/ged",
        "/api/v1/plateforme/admin/settings/general",
        "/api/v1/plateforme/admin/settings/security",
        "/api/v1/plateforme/admin/settings/maintenance",
    ):
        resp = await client.get(path, headers=headers)
        assert resp.status_code == 200, f"{path}: {resp.text}"

    activity = (await client.get("/api/v1/plateforme/admin/activity", headers=headers)).json()
    assert "kpis" in activity
    assert "items" in activity

    alerts = (await client.get("/api/v1/plateforme/admin/alerts", headers=headers)).json()
    assert "lockout_window_minutes" in alerts

    general = (await client.get("/api/v1/plateforme/admin/settings/general", headers=headers)).json()
    assert "secret_key" not in general
    assert "app_env" in general

    maintenance = (await client.get("/api/v1/plateforme/admin/settings/maintenance", headers=headers)).json()
    assert "skip_migrations" in maintenance
    assert "etat" in maintenance
