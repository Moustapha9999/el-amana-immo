"""CORE ADMIN — rôles / permissions (Login 1, core.admin.roles|permissions)."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.security import get_password_hash
from app.data.plateforme_catalogue import ROLE_PERMISSIONS
from app.db.session import AsyncSessionLocal, engine
from app.main import app
from app.models import User
from app.services.core_admin_rbac_service import normalize_permission_code, normalize_role_code


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


def test_normalize_rbac_codes():
    assert normalize_role_code("Credit_Lecteur") == "credit_lecteur"
    assert normalize_role_code("Credit.Admin") == "credit.admin"
    try:
        normalize_role_code("Crédit")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    assert normalize_permission_code("Credit.Read") == "credit.read"
    try:
        normalize_permission_code("*")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_validate_new_role_code_requires_module_prefix():
    from app.services.core_admin_rbac_service import validate_new_role_code

    assert validate_new_role_code("credit.admin") == "credit.admin"
    try:
        validate_new_role_code("lecteur_credit")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "préfixés" in str(exc)
    try:
        validate_new_role_code("immobilisations.admin")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "Immobilisations" in str(exc)


@pytest.mark.asyncio
async def test_core_admin_rbac_platform_only(client: AsyncClient):
    headers = await _headers(client)
    listed = await client.get("/api/v1/plateforme/admin/roles?page=1&size=50", headers=headers)
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["total"] >= 1
    admin = next(row for row in body["items"] if row["code"] == "administrateur")
    assert admin["locked"] is True
    assert "kpis" in body

    perms = await client.get("/api/v1/plateforme/admin/permissions?page=1&size=50", headers=headers)
    assert perms.status_code == 200, perms.text
    assert any(row["code"] == "immobilisations.read" for row in perms.json()["items"])
    assert any(row["code"] == "core.admin.roles" for row in perms.json()["items"])

    module_login = await client.post(
        "/api/v1/auth/modules/immobilisations/login",
        json={"email": "admin@el-amana.mr", "password": _admin_secret()},
        headers=headers,
    )
    if module_login.status_code != 200:
        pytest.skip("Login module indisponible")
    blocked = await client.get(
        "/api/v1/plateforme/admin/roles",
        headers={"Authorization": f"Bearer {module_login.json()['access_token']}"},
    )
    assert blocked.status_code == 401


@pytest.mark.asyncio
async def test_core_admin_rbac_forbidden_without_permission(client: AsyncClient):
    email = f"core-rbac-deny-{uuid4().hex[:8]}@el-amana.mr"
    password = "TestDeny@2026"
    async with AsyncSessionLocal() as session:
        session.add(
            User(
                email=email,
                full_name="Sans CORE rôles",
                hashed_password=get_password_hash(password),
                is_superuser=False,
            )
        )
        await session.commit()
    try:
        denied = await _login_platform(client, email=email, password=password)
        assert denied.status_code == 200
        token = {"Authorization": f"Bearer {denied.json()['access_token']}"}
        assert (await client.get("/api/v1/plateforme/admin/roles", headers=token)).status_code == 403
        assert (await client.get("/api/v1/plateforme/admin/permissions", headers=token)).status_code == 403
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("UPDATE users SET is_active=false, deleted_at=now() WHERE email=:e"),
                {"e": email},
            )
            await session.commit()


@pytest.mark.asyncio
async def test_system_roles_and_permissions_are_protected(client: AsyncClient):
    headers = await _headers(client)
    roles = await client.get("/api/v1/plateforme/admin/roles?search=administrateur", headers=headers)
    admin = next(row for row in roles.json()["items"] if row["code"] == "administrateur")
    assert (await client.delete(f"/api/v1/plateforme/admin/roles/{admin['id']}", headers=headers)).status_code == 400

    core_grant = await client.patch(
        f"/api/v1/plateforme/admin/roles/{admin['id']}",
        headers=headers,
        json={"permission_codes": ["immobilisations.read", "core.admin.access"]},
    )
    assert core_grant.status_code == 400

    perms = await client.get("/api/v1/plateforme/admin/permissions?search=immobilisations.read", headers=headers)
    read = next(row for row in perms.json()["items"] if row["code"] == "immobilisations.read")
    assert read["locked"] is True
    assert (await client.delete(f"/api/v1/plateforme/admin/permissions/{read['id']}", headers=headers)).status_code == 400
    module_lock = await client.patch(
        f"/api/v1/plateforme/admin/permissions/{read['id']}",
        headers=headers,
        json={"module": "autre"},
    )
    assert module_lock.status_code == 400


@pytest.mark.asyncio
async def test_core_admin_rbac_crud_and_seed_not_overwritten(client: AsyncClient):
    headers = await _headers(client)
    suffix = uuid4().hex[:8]
    role_code = f"test_role_{suffix[:8]}"
    perm_code = f"testmod.{suffix[:8]}"
    role_id = None
    perm_id = None
    consultation = None
    original_consultation = None
    original_admin_label = None
    admin_id = None
    try:
        created_perm = await client.post(
            "/api/v1/plateforme/admin/permissions",
            headers=headers,
            json={"code": perm_code, "label": "Permission test Phase 4"},
        )
        assert created_perm.status_code == 201, created_perm.text
        perm_id = created_perm.json()["id"]
        assert created_perm.json()["module"] == "testmod"
        assert created_perm.json()["locked"] is False

        created_role = await client.post(
            "/api/v1/plateforme/admin/roles",
            headers=headers,
            json={
                "code": role_code,
                "label": "Rôle test Phase 4",
                "description": "Créé par test",
                "permission_codes": [perm_code],
            },
        )
        assert created_role.status_code == 201, created_role.text
        role_id = created_role.json()["id"]
        assert created_role.json()["locked"] is False
        assert created_role.json()["permission_codes"] == [perm_code]

        patched_role = await client.patch(
            f"/api/v1/plateforme/admin/roles/{role_id}",
            headers=headers,
            json={"label": "Rôle test modifié"},
        )
        assert patched_role.status_code == 200, patched_role.text
        assert patched_role.json()["label"] == "Rôle test modifié"
        assert patched_role.json()["permission_codes"] == [perm_code]

        dash = await client.get("/api/v1/plateforme/admin/dashboard", headers=headers)
        assert dash.status_code == 200, dash.text
        again = await client.get(f"/api/v1/plateforme/admin/roles/{role_id}", headers=headers)
        assert again.json()["label"] == "Rôle test modifié"
        assert again.json()["permission_codes"] == [perm_code]

        refuse_perm = await client.delete(f"/api/v1/plateforme/admin/permissions/{perm_id}", headers=headers)
        assert refuse_perm.status_code == 400

        deleted_role = await client.delete(f"/api/v1/plateforme/admin/roles/{role_id}", headers=headers)
        assert deleted_role.status_code == 200
        role_id = None
        deleted_perm = await client.delete(f"/api/v1/plateforme/admin/permissions/{perm_id}", headers=headers)
        assert deleted_perm.status_code == 200
        perm_id = None

        roles = await client.get("/api/v1/plateforme/admin/roles?search=consultation&kind=systeme", headers=headers)
        consultation = next(row for row in roles.json()["items"] if row["code"] == "consultation")
        fiche = await client.get(f"/api/v1/plateforme/admin/roles/{consultation['id']}", headers=headers)
        original_consultation = fiche.json()["permission_codes"]
        stripped = await client.patch(
            f"/api/v1/plateforme/admin/roles/{consultation['id']}",
            headers=headers,
            json={"permission_codes": []},
        )
        assert stripped.status_code == 200, stripped.text
        await client.get("/api/v1/plateforme/admin/dashboard", headers=headers)
        still = await client.get(f"/api/v1/plateforme/admin/roles/{consultation['id']}", headers=headers)
        assert still.json()["permission_codes"] == []

        admins = await client.get("/api/v1/plateforme/admin/roles?search=administrateur", headers=headers)
        admin_row = next(row for row in admins.json()["items"] if row["code"] == "administrateur")
        admin_id = admin_row["id"]
        original_admin_label = admin_row["label"]
        renamed = await client.patch(
            f"/api/v1/plateforme/admin/roles/{admin_id}",
            headers=headers,
            json={"label": "Administration test"},
        )
        assert renamed.status_code == 200
        await client.get("/api/v1/plateforme/admin/dashboard", headers=headers)
        restored_check = await client.get(f"/api/v1/plateforme/admin/roles/{admin_id}", headers=headers)
        assert restored_check.json()["label"] == "Administration test"
    finally:
        if consultation is not None and original_consultation is not None:
            await client.patch(
                f"/api/v1/plateforme/admin/roles/{consultation['id']}",
                headers=headers,
                json={"permission_codes": original_consultation or list(ROLE_PERMISSIONS["consultation"])},
            )
        if admin_id and original_admin_label:
            await client.patch(
                f"/api/v1/plateforme/admin/roles/{admin_id}",
                headers=headers,
                json={"label": original_admin_label},
            )
        if role_id:
            await client.delete(f"/api/v1/plateforme/admin/roles/{role_id}", headers=headers)
        if perm_id:
            await client.delete(f"/api/v1/plateforme/admin/permissions/{perm_id}", headers=headers)
