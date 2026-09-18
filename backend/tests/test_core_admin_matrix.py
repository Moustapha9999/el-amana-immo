"""CORE ADMIN — matrice d’accès rôles × permissions (Phase 5)."""

from __future__ import annotations

import os
from uuid import uuid4

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
async def test_core_admin_matrix_read_and_toggle(client: AsyncClient):
    headers = await _headers(client)
    matrix = await client.get("/api/v1/plateforme/admin/matrix", headers=headers)
    assert matrix.status_code == 200, matrix.text
    body = matrix.json()
    assert body["kpis"]["roles"] >= 1
    assert body["kpis"]["permissions"] >= 1
    assert isinstance(body["grants"], dict)
    assert any(role["code"] == "consultation" for role in body["roles"])
    assert any(perm["code"] == "immobilisations.read" for perm in body["permissions"])

    filtered = await client.get(
        "/api/v1/plateforme/admin/matrix",
        headers=headers,
        params={"module": "immobilisations"},
    )
    assert filtered.status_code == 200
    assert all(row["module"] == "immobilisations" for row in filtered.json()["permissions"])

    suffix = uuid4().hex[:8]
    perm_code = f"matrixmod.{suffix}"
    role_code = f"matrix_role_{suffix}"
    role_id = None
    perm_id = None
    try:
        created_perm = await client.post(
            "/api/v1/plateforme/admin/permissions",
            headers=headers,
            json={"code": perm_code, "label": "Permission matrice"},
        )
        assert created_perm.status_code == 201, created_perm.text
        perm_id = created_perm.json()["id"]

        created_role = await client.post(
            "/api/v1/plateforme/admin/roles",
            headers=headers,
            json={"code": role_code, "label": "Rôle matrice", "permission_codes": []},
        )
        assert created_role.status_code == 201, created_role.text
        role_id = created_role.json()["id"]

        granted = await client.patch(
            "/api/v1/plateforme/admin/matrix",
            headers=headers,
            json={"role_id": role_id, "permission_code": perm_code, "granted": True},
        )
        assert granted.status_code == 200, granted.text
        assert granted.json()["granted"] is True

        again = await client.get("/api/v1/plateforme/admin/matrix", headers=headers, params={"search": perm_code})
        assert perm_code in again.json()["grants"].get(role_id, [])

        revoked = await client.patch(
            "/api/v1/plateforme/admin/matrix",
            headers=headers,
            json={"role_id": role_id, "permission_code": perm_code, "granted": False},
        )
        assert revoked.status_code == 200
        assert revoked.json()["granted"] is False

        admins = await client.get("/api/v1/plateforme/admin/roles?search=administrateur", headers=headers)
        admin = next(row for row in admins.json()["items"] if row["code"] == "administrateur")
        blocked = await client.patch(
            "/api/v1/plateforme/admin/matrix",
            headers=headers,
            json={"role_id": admin["id"], "permission_code": "core.admin.access", "granted": True},
        )
        assert blocked.status_code == 400
    finally:
        if role_id:
            await client.delete(f"/api/v1/plateforme/admin/roles/{role_id}", headers=headers)
        if perm_id:
            await client.delete(f"/api/v1/plateforme/admin/permissions/{perm_id}", headers=headers)
