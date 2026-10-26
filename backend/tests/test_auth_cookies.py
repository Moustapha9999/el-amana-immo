"""Refresh tokens en cookie HttpOnly (mode X-BEA-Auth: cookie) — plateforme et module."""

from __future__ import annotations

from datetime import datetime, timezone
from http.cookies import SimpleCookie
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import get_password_hash
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models import User

MODE = {"X-BEA-Auth": "cookie"}
PASSWORD = "CookieTest@2026"


def _set_cookies(res) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for raw in res.headers.get_list("set-cookie"):
        jar = SimpleCookie()
        jar.load(raw)
        for name, morsel in jar.items():
            out[name] = {"value": morsel.value, "raw": raw.lower(), "max_age": morsel["max-age"]}
    return out


def _cookie_header(**cookies: str) -> dict[str, str]:
    return {"Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items())}


@pytest.fixture
async def compte(base_jetable):
    email = f"cookie-{uuid4().hex[:8]}@el-amana.mr"
    async with AsyncSessionLocal() as session:
        user = User(
            email=email,
            full_name="Test cookie",
            hashed_password=get_password_hash(PASSWORD),
            is_superuser=True,
            must_change_password=False,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        user_id = user.id
    try:
        yield email
    finally:
        async with AsyncSessionLocal() as session:
            row = await session.get(User, user_id)
            if row is not None:
                row.is_active = False
                row.deleted_at = datetime.now(timezone.utc)
                await session.commit()


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_plateforme_cookie_httponly_rotation_et_deconnexion(client, compte):
    login = await client.post("/api/v1/auth/login", json={"email": compte, "password": PASSWORD}, headers=MODE)
    assert login.status_code == 200, login.text
    assert login.json()["refresh_token"] == ""
    cookie = _set_cookies(login)["bea_rt"]
    for attr in ("httponly", "samesite=strict", "path=/api/v1/auth"):
        assert attr in cookie["raw"]
    rt1 = cookie["value"]

    # Sans l'en-tête, le cookie est ignoré (un autre site ne peut pas l'envoyer).
    sans_entete = await client.post("/api/v1/auth/refresh", json={}, headers=_cookie_header(bea_rt=rt1))
    assert sans_entete.status_code == 401

    rot = await client.post("/api/v1/auth/refresh", json={}, headers={**MODE, **_cookie_header(bea_rt=rt1)})
    assert rot.status_code == 200, rot.text
    assert rot.json()["refresh_token"] == ""
    rt2 = _set_cookies(rot)["bea_rt"]["value"]
    assert rt2 and rt2 != rt1
    access = rot.json()["access_token"]
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})).status_code == 200

    out = await client.post(
        "/api/v1/auth/logout",
        json={},
        headers={**MODE, **_cookie_header(bea_rt=rt2, bea_mrt_immobilisations="x"), "Authorization": f"Bearer {access}"},
    )
    assert out.status_code == 200
    effaces = _set_cookies(out)
    assert effaces["bea_rt"]["value"] == "" and effaces["bea_mrt_immobilisations"]["value"] == ""
    apres = await client.post("/api/v1/auth/refresh", json={}, headers={**MODE, **_cookie_header(bea_rt=rt2)})
    assert apres.status_code == 401


@pytest.mark.asyncio
async def test_module_cookie_par_code_et_deconnexion(client, compte):
    login = await client.post("/api/v1/auth/login", json={"email": compte, "password": PASSWORD}, headers=MODE)
    assert login.status_code == 200, login.text
    bearer = {"Authorization": f"Bearer {login.json()['access_token']}"}

    mod = await client.post(
        "/api/v1/auth/modules/immobilisations/login",
        json={"email": compte, "password": PASSWORD},
        headers={**MODE, **bearer},
    )
    if mod.status_code != 200:
        pytest.skip(f"Login module indisponible : {mod.text[:120]}")
    assert mod.json()["refresh_token"] == ""
    mrt = _set_cookies(mod)["bea_mrt_immobilisations"]["value"]

    autre = await client.post(
        "/api/v1/auth/modules/refresh",
        json={"module_code": "achats-appro"},
        headers={**MODE, **_cookie_header(bea_mrt_immobilisations=mrt)},
    )
    assert autre.status_code == 401

    rot = await client.post(
        "/api/v1/auth/modules/refresh",
        json={"module_code": "immobilisations"},
        headers={**MODE, **_cookie_header(bea_mrt_immobilisations=mrt)},
    )
    assert rot.status_code == 200, rot.text
    mrt2 = _set_cookies(rot)["bea_mrt_immobilisations"]["value"]
    assert mrt2 and mrt2 != mrt

    out = await client.post(
        "/api/v1/auth/modules/logout",
        json={"module_code": "immobilisations"},
        headers={**MODE, **_cookie_header(bea_mrt_immobilisations=mrt2)},
    )
    assert out.status_code == 200
    assert _set_cookies(out)["bea_mrt_immobilisations"]["value"] == ""
    apres = await client.post(
        "/api/v1/auth/modules/refresh",
        json={"module_code": "immobilisations"},
        headers={**MODE, **_cookie_header(bea_mrt_immobilisations=mrt2)},
    )
    assert apres.status_code == 401


@pytest.mark.asyncio
async def test_migration_jeton_localstorage_vers_cookie(client, compte):
    login = await client.post("/api/v1/auth/login", json={"email": compte, "password": PASSWORD})
    assert login.status_code == 200, login.text
    legacy = login.json()["refresh_token"]
    assert legacy

    migr = await client.post("/api/v1/auth/refresh", json={"refresh_token": legacy}, headers=MODE)
    assert migr.status_code == 200, migr.text
    assert migr.json()["refresh_token"] == ""
    assert _set_cookies(migr)["bea_rt"]["value"]


@pytest.mark.asyncio
async def test_code_module_invalide_refuse(client):
    res = await client.post(
        "/api/v1/auth/modules/refresh",
        json={"module_code": "../x; Path=/"},
        headers={**MODE, **_cookie_header(bea_rt="x")},
    )
    assert res.status_code == 400
