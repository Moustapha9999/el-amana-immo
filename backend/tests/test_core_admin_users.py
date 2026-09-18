"""CORE ADMIN — administration des utilisateurs (Login 1, core.admin.users)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

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


async def _archive_email(email: str) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.email == email))
        row = result.scalar_one_or_none()
        if row is None:
            return
        row.is_active = False
        row.deleted_at = datetime.now(timezone.utc)
        await session.commit()


@pytest.mark.asyncio
async def test_core_admin_users_platform_only(client: AsyncClient):
    login = await _login_platform(client)
    if login.status_code != 200:
        pytest.skip("Compte admin seed indisponible")
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    listed = await client.get("/api/v1/plateforme/admin/users?page=1&size=5", headers=headers)
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert "items" in body
    assert body["total"] >= 1

    module_login = await client.post(
        "/api/v1/auth/modules/immobilisations/login",
        json={"email": "admin@el-amana.mr", "password": _admin_secret()},
        headers=headers,
    )
    if module_login.status_code != 200:
        pytest.skip("Login module indisponible (catalogue / grants)")
    blocked = await client.get(
        "/api/v1/plateforme/admin/users?page=1&size=5",
        headers={"Authorization": f"Bearer {module_login.json()['access_token']}"},
    )
    assert blocked.status_code == 401


@pytest.mark.asyncio
async def test_core_admin_users_forbidden_without_permission(client: AsyncClient):
    email = f"core-users-deny-{uuid4().hex[:8]}@el-amana.mr"
    password = "TestDeny@2026"
    async with AsyncSessionLocal() as session:
        user = User(
            email=email,
            full_name="Sans CORE users",
            hashed_password=get_password_hash(password),
            is_superuser=False,
        )
        session.add(user)
        await session.commit()
    try:
        denied_login = await _login_platform(client, email=email, password=password)
        assert denied_login.status_code == 200, denied_login.text
        listed = await client.get(
            "/api/v1/plateforme/admin/users",
            headers={"Authorization": f"Bearer {denied_login.json()['access_token']}"},
        )
        assert listed.status_code == 403
    finally:
        await _archive_email(email)


@pytest.mark.asyncio
async def test_core_admin_users_crud_activate_and_reset(client: AsyncClient):
    login = await _login_platform(client)
    if login.status_code != 200:
        pytest.skip("Compte admin seed indisponible")
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    actor_id = me.json()["id"]

    email = f"core-users-{uuid4().hex[:8]}@el-amana.mr"
    password = "Phase2User@2026"
    created_id = None
    try:
        created = await client.post(
            "/api/v1/plateforme/admin/users",
            headers=headers,
            json={
                "email": email,
                "full_name": "Utilisateur CORE Phase 2",
                "password": password,
                "phone": "22000000",
                "role_codes": [],
                "espace_codes": [],
                "module_codes": [],
            },
        )
        assert created.status_code == 201, created.text
        payload = created.json()
        created_id = payload["id"]
        assert payload["is_active"] is True
        assert payload["phone"] == "22000000"
        assert payload["espace_codes"] == []
        assert payload["module_codes"] == []

        listed = await client.get(
            f"/api/v1/plateforme/admin/users?search={email}&statut=tous",
            headers=headers,
        )
        assert listed.status_code == 200
        assert any(row["id"] == created_id for row in listed.json()["items"])
        assert listed.json()["kpis"]["total"] >= 1

        by_phone = await client.get(
            "/api/v1/plateforme/admin/users?search=22000000&statut=tous",
            headers=headers,
        )
        assert any(row["id"] == created_id for row in by_phone.json()["items"])

        fiche = await client.get(f"/api/v1/plateforme/admin/users/{created_id}", headers=headers)
        assert fiche.status_code == 200, fiche.text
        detail = fiche.json()
        assert detail["email"] == email
        assert "sessions" in detail
        assert "activite" in detail
        assert "permission_codes" in detail

        patched = await client.patch(
            f"/api/v1/plateforme/admin/users/{created_id}",
            headers=headers,
            json={"full_name": "Utilisateur CORE modifié", "espace_codes": ["comptabilite"]},
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["full_name"] == "Utilisateur CORE modifié"
        assert "comptabilite" in patched.json()["espace_codes"]

        by_espace = await client.get(
            "/api/v1/plateforme/admin/users?espace_code=comptabilite&statut=tous&search=" + email,
            headers=headers,
        )
        assert any(row["id"] == created_id for row in by_espace.json()["items"])

        self_deny = await client.post(
            f"/api/v1/plateforme/admin/users/{actor_id}/deactivate",
            headers=headers,
        )
        assert self_deny.status_code == 400

        deactivated = await client.post(
            f"/api/v1/plateforme/admin/users/{created_id}/deactivate",
            headers=headers,
        )
        assert deactivated.status_code == 200, deactivated.text
        assert deactivated.json()["is_active"] is False

        inactive = await client.get(
            f"/api/v1/plateforme/admin/users?search={email}&statut=inactif",
            headers=headers,
        )
        assert any(row["id"] == created_id for row in inactive.json()["items"])

        blocked_login = await _login_platform(client, email=email, password=password)
        assert blocked_login.status_code == 401

        immo_users = await client.get("/api/v1/users?page=1&size=100", headers=headers)
        assert immo_users.status_code == 200
        assert all(row["id"] != created_id for row in immo_users.json()["items"])

        activated = await client.post(
            f"/api/v1/plateforme/admin/users/{created_id}/activate",
            headers=headers,
        )
        assert activated.status_code == 200
        assert activated.json()["is_active"] is True

        ok_login = await _login_platform(client, email=email, password=password)
        assert ok_login.status_code == 200, ok_login.text

        new_password = "Phase2Reset@2026"
        reset = await client.post(
            f"/api/v1/plateforme/admin/users/{created_id}/reset-access",
            headers=headers,
            json={"password": new_password},
        )
        assert reset.status_code == 200, reset.text
        old_login = await _login_platform(client, email=email, password=password)
        assert old_login.status_code == 401
        new_login = await _login_platform(client, email=email, password=new_password)
        assert new_login.status_code == 200, new_login.text

        self_delete = await client.delete(
            f"/api/v1/plateforme/admin/users/{actor_id}",
            headers=headers,
        )
        assert self_delete.status_code == 400

        removed = await client.delete(
            f"/api/v1/plateforme/admin/users/{created_id}",
            headers=headers,
        )
        assert removed.status_code == 200, removed.text
        gone = await client.get(
            f"/api/v1/plateforme/admin/users?search={email}&statut=tous",
            headers=headers,
        )
        assert all(row["id"] != created_id for row in gone.json()["items"])
    finally:
        await _archive_email(email)
