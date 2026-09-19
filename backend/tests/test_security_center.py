"""Tests sécurité — reset public désactivé, secret box, MDP temporaire, TOTP seal."""

from __future__ import annotations

import os

import pytest
import pyotp
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.secret_box import open_secret, seal
from app.core.temp_password import generate_temporary_password
from app.core.password_policy import validate_password_policy
from app.db.session import engine
from app.main import app
from app.services.totp_service import generate_secret, store_secret, verify_code


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


def test_temp_password_meets_policy():
    pwd = generate_temporary_password()
    validate_password_policy(pwd)


def test_secret_box_roundtrip():
    plain = "JBSWY3DPEHPK3PXP"
    sealed = seal(plain)
    assert sealed is not None
    assert sealed.startswith("enc:v1:")
    assert open_secret(sealed) == plain
    assert open_secret(plain) == plain  # legacy plaintext


def test_totp_verify_with_sealed_secret():
    secret = generate_secret()
    stored = store_secret(secret)
    assert stored.startswith("enc:v1:")
    code = pyotp.TOTP(secret).now()
    assert verify_code(stored, code)


@pytest.mark.asyncio
async def test_public_password_reset_disabled(client: AsyncClient):
    forgot = await client.post("/api/v1/auth/forgot-password", json={"email": "admin@el-amana.mr"})
    assert forgot.status_code == 403
    detail = forgot.json().get("detail")
    if isinstance(detail, dict):
        assert detail.get("code") == "PASSWORD_RESET_DISABLED"

    reset = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": "x.y.z", "new_password": "NewPass@2026xx"},
    )
    assert reset.status_code == 403


@pytest.mark.asyncio
async def test_security_snapshot_hides_secrets(client: AsyncClient):
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "admin@el-amana.mr",
            "password": os.environ.get("BEA_TEST_PASSWORD", "Admin@2026"),
        },
    )
    if login.status_code != 200:
        pytest.skip("Compte admin seed indisponible")
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    resp = await client.get("/api/v1/plateforme/admin/settings/security", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "secret_key" not in data
    assert data.get("public_password_reset_enabled") is False
    assert "https_status" in data
    assert data["https_status"] == "non_verifie"
    check = await client.post("/api/v1/plateforme/admin/settings/security/check", headers=headers)
    assert check.status_code == 200
    body = check.json()
    assert "items" in body
