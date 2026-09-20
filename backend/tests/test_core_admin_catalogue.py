"""CORE ADMIN — départements / modules (Login 1, core.admin.departments|modules)."""

from __future__ import annotations

import os
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
    return await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password or _admin_secret()},
    )


async def _headers(client: AsyncClient) -> dict[str, str]:
    login = await _login_platform(client)
    if login.status_code != 200:
        pytest.skip("Compte admin seed indisponible")
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_core_admin_catalogue_platform_only(client: AsyncClient):
    headers = await _headers(client)
    listed = await client.get("/api/v1/plateforme/admin/departments?page=1&size=20", headers=headers)
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["total"] >= 1
    assert any(row["code"] == "comptabilite" for row in body["items"])
    assert "kpis" in body

    modules = await client.get("/api/v1/plateforme/admin/modules?page=1&size=20", headers=headers)
    assert modules.status_code == 200, modules.text
    assert any(row["code"] == "immobilisations" for row in modules.json()["items"])

    module_login = await client.post(
        "/api/v1/auth/modules/immobilisations/login",
        json={"email": "admin@el-amana.mr", "password": _admin_secret()},
        headers=headers,
    )
    if module_login.status_code != 200:
        pytest.skip("Login module indisponible")
    blocked = await client.get(
        "/api/v1/plateforme/admin/departments",
        headers={"Authorization": f"Bearer {module_login.json()['access_token']}"},
    )
    assert blocked.status_code == 401


@pytest.mark.asyncio
async def test_core_admin_catalogue_forbidden_without_permission(client: AsyncClient):
    email = f"core-cat-deny-{uuid4().hex[:8]}@el-amana.mr"
    password = "TestDeny@2026"
    async with AsyncSessionLocal() as session:
        session.add(
            User(
                email=email,
                full_name="Sans CORE catalogue",
                hashed_password=get_password_hash(password),
                is_superuser=False,
            )
        )
        await session.commit()
    try:
        denied = await _login_platform(client, email=email, password=password)
        assert denied.status_code == 200
        token = {"Authorization": f"Bearer {denied.json()['access_token']}"}
        assert (await client.get("/api/v1/plateforme/admin/departments", headers=token)).status_code == 403
        assert (await client.get("/api/v1/plateforme/admin/modules", headers=token)).status_code == 403
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(text("UPDATE users SET is_active=false, deleted_at=now() WHERE email=:e"), {"e": email})
            await session.commit()


@pytest.mark.asyncio
async def test_protected_catalogue_cannot_be_disabled_or_deleted(client: AsyncClient):
    headers = await _headers(client)
    depts = await client.get("/api/v1/plateforme/admin/departments?search=comptabilite", headers=headers)
    compta = next(row for row in depts.json()["items"] if row["code"] == "comptabilite")
    assert compta["locked"] is True
    assert (await client.post(f"/api/v1/plateforme/admin/departments/{compta['id']}/deactivate", headers=headers)).status_code == 400
    assert (await client.delete(f"/api/v1/plateforme/admin/departments/{compta['id']}", headers=headers)).status_code == 400
    patched = await client.patch(
        f"/api/v1/plateforme/admin/departments/{compta['id']}",
        headers=headers,
        json={"route": "/autre"},
    )
    assert patched.status_code == 400

    mods = await client.get("/api/v1/plateforme/admin/modules?search=immobilisations", headers=headers)
    immo = next(row for row in mods.json()["items"] if row["code"] == "immobilisations")
    assert immo["locked"] is True
    assert (await client.post(f"/api/v1/plateforme/admin/modules/{immo['id']}/deactivate", headers=headers)).status_code == 400
    assert (await client.delete(f"/api/v1/plateforme/admin/modules/{immo['id']}", headers=headers)).status_code == 400
    path_lock = await client.patch(
        f"/api/v1/plateforme/admin/modules/{immo['id']}",
        headers=headers,
        json={"entry_path": "/ailleurs"},
    )
    assert path_lock.status_code == 400


@pytest.mark.asyncio
async def test_core_admin_catalogue_crud_and_seed_not_overwritten(client: AsyncClient):
    headers = await _headers(client)
    suffix = uuid4().hex[:8]
    dept_code = f"test-dept-{suffix}"
    mod_code = f"test-mod-{suffix}"
    dept_id = None
    mod_id = None
    try:
        created = await client.post(
            "/api/v1/plateforme/admin/departments",
            headers=headers,
            json={
                "code": dept_code,
                "label": "Département test Phase 3",
                "description": "Créé par test",
                "statut": "bientot",
                "sort_order": 90,
            },
        )
        assert created.status_code == 201, created.text
        dept_id = created.json()["id"]
        assert created.json()["code"] == dept_code
        assert created.json()["route"] == f"/{dept_code}"
        assert created.json()["locked"] is False

        listed = await client.get(
            f"/api/v1/plateforme/admin/departments?search={dept_code}&statut=bientot",
            headers=headers,
        )
        assert any(row["id"] == dept_id for row in listed.json()["items"])

        patched = await client.patch(
            f"/api/v1/plateforme/admin/departments/{dept_id}",
            headers=headers,
            json={"label": "Département test modifié", "description": "Après PATCH"},
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["label"] == "Département test modifié"

        # ensure_catalogue (via dashboard) ne doit pas écraser la saisie.
        dash = await client.get("/api/v1/plateforme/admin/dashboard", headers=headers)
        assert dash.status_code == 200, dash.text
        again = await client.get(f"/api/v1/plateforme/admin/departments/{dept_id}", headers=headers)
        assert again.json()["label"] == "Département test modifié"

        module = await client.post(
            "/api/v1/plateforme/admin/modules",
            headers=headers,
            json={
                "code": mod_code,
                "espace_id": dept_id,
                "label": "Module test Phase 3",
                "statut": "bientot",
                "sort_order": 1,
            },
        )
        assert module.status_code == 201, module.text
        mod_id = module.json()["id"]
        assert module.json()["espace_id"] == dept_id

        refuse_dept = await client.delete(f"/api/v1/plateforme/admin/departments/{dept_id}", headers=headers)
        assert refuse_dept.status_code == 400

        deactivated = await client.post(
            f"/api/v1/plateforme/admin/modules/{mod_id}/deactivate",
            headers=headers,
        )
        assert deactivated.status_code == 200
        assert deactivated.json()["is_active"] is False

        activated = await client.post(
            f"/api/v1/plateforme/admin/modules/{mod_id}/activate",
            headers=headers,
        )
        assert activated.status_code == 200
        assert activated.json()["is_active"] is True

        deleted_mod = await client.delete(f"/api/v1/plateforme/admin/modules/{mod_id}", headers=headers)
        assert deleted_mod.status_code == 200
        mod_id = None

        deleted_dept = await client.delete(f"/api/v1/plateforme/admin/departments/{dept_id}", headers=headers)
        assert deleted_dept.status_code == 200, deleted_dept.text
        dept_id = None
        missing = await client.get(f"/api/v1/plateforme/admin/departments/{created.json()['id']}", headers=headers)
        assert missing.status_code == 404
    finally:
        if mod_id:
            await client.delete(f"/api/v1/plateforme/admin/modules/{mod_id}", headers=headers)
        if dept_id:
            await client.delete(f"/api/v1/plateforme/admin/departments/{dept_id}", headers=headers)
