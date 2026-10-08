"""CORE ADMIN — Sauvegardes & Recovery : périmètres, moteur, API (sans restauration réelle)."""

from __future__ import annotations

import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.data.module_backup_scopes import (
    GLOBAL_RESTORE_JOURNAL_TABLES,
    MODULE_BACKUP_SCOPES,
    SECURITY_PLANE_TABLES,
    SHARED_CORE_TABLES,
    ged_codes_for,
    resolve_tables,
)
from app.db.session import engine
from app.main import app
from app.services.platform_backup_engine import fk_check_sql, friendly_restore_error, safe_ident
from app.services.platform_backup_service import confirmation_phrase

API = "/api/v1/plateforme/admin"


# --------------------------------------------------------------------------- périmètres


def test_exclusive_tables_never_shared_core():
    shared = set(SHARED_CORE_TABLES)
    for code, scope in MODULE_BACKUP_SCOPES.items():
        overlap = shared & set(scope["exclusive_tables"])
        assert not overlap, f"{code} revendique des tables CORE : {sorted(overlap)}"


def test_exclusive_tables_owned_by_single_module():
    owners: dict[str, str] = {}
    for code, scope in MODULE_BACKUP_SCOPES.items():
        for table in scope["exclusive_tables"]:
            assert table not in owners, f"{table} revendiquée par {owners[table]} et {code}"
            owners[table] = code


def test_global_restore_preserves_journal_and_security():
    for table in ("audit_logs", "platform_backups", "platform_restores", "notifications", "auth_sessions"):
        assert table in GLOBAL_RESTORE_JOURNAL_TABLES
    for table in ("users", "roles", "permissions", "user_roles", "plateforme_modules"):
        assert table in SECURITY_PLANE_TABLES


def test_resolve_tables_uses_prefixes_and_skips_missing():
    existing = {"formation_sessions", "formation_participants", "formation_nouvelle_table", "users"}
    tables = resolve_tables("formation", existing)
    assert "formation_sessions" in tables
    assert "formation_nouvelle_table" in tables
    assert "users" not in tables
    assert all(t in existing for t in tables)
    assert resolve_tables("module-inconnu", existing) == []


def test_ged_codes():
    assert ged_codes_for("formation") == ["formation"]
    assert set(ged_codes_for("immobilisations")) == {"immos", "immobilisations"}
    assert ged_codes_for("archives-mg") == []
    assert ged_codes_for("module-inconnu") == []


# --------------------------------------------------------------------------- moteur


def test_safe_ident_rejects_injection():
    assert safe_ident("formation_sessions") == "formation_sessions"
    for bad in ("x; DROP TABLE users", "a b", "", 'x"y', "../etc"):
        with pytest.raises(ValueError):
            safe_ident(bad)


def test_fk_check_sql_shape():
    sql = fk_check_sql(["formation_sessions", "formation_participants"])
    assert "'public.formation_sessions'::regclass" in sql
    assert "BEA_FK_VIOLATION" in sql
    assert "pg_catalog.unnest" not in sql
    with pytest.raises(ValueError):
        fk_check_sql(["x; DROP TABLE users"])


def test_friendly_restore_error_classification():
    fk = friendly_restore_error("ERROR:  BEA_FK_VIOLATION: public.a -> public.b : 1 ligne(s)\nCONTEXT: ...")
    assert "intégrité référentielle" in fk and "public.a -> public.b" in fk
    assert "GRANT SET ON PARAMETER" in friendly_restore_error(
        'ERROR:  permission denied to set parameter "session_replication_role"'
    )
    assert "verrouillées" in friendly_restore_error("ERROR:  canceling statement due to lock timeout")
    assert "Schéma incompatible" in friendly_restore_error('ERROR:  column "x" of relation "y" does not exist')
    generic = friendly_restore_error("ERROR:  function foo() does not exist")
    assert "Schéma incompatible" not in generic
    assert "aucune donnée modifiée" in generic


def test_confirmation_phrases():
    assert confirmation_phrase("global", None, None) == "RESTAURER GLOBAL"
    assert confirmation_phrase("departement", "moyens-generaux", None) == "RESTAURER MOYENS-GENERAUX"
    assert confirmation_phrase("module", "audit", "formation") == "RESTAURER FORMATION"


# --------------------------------------------------------------------------- API


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
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        # Une boucle asyncio par test : ne pas réutiliser les connexions du pool d'une autre boucle.
        await engine.dispose()


async def _headers(client: AsyncClient) -> dict[str, str]:
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@el-amana.mr", "password": os.environ.get("BEA_TEST_PASSWORD", "Admin@2026")},
    )
    if login.status_code != 200:
        pytest.skip("Compte admin seed indisponible")
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_backup_endpoints_require_auth(client: AsyncClient):
    for path in ("/backups/catalogue", "/backups/dashboard", "/backups/history"):
        resp = await client.get(f"{API}{path}")
        assert resp.status_code == 401, path


@pytest.mark.asyncio
async def test_catalogue_preview_history(client: AsyncClient):
    headers = await _headers(client)

    cat = (await client.get(f"{API}/backups/catalogue", headers=headers)).json()
    assert cat["departements_count"] == len(cat["departements"]) > 0
    module = next(
        (m for d in cat["departements"] for m in d["modules"] if m["backupable"]),
        None,
    )
    assert module is not None
    espace = next(d["code"] for d in cat["departements"] if module in d["modules"])

    preview = await client.get(
        f"{API}/backups/preview",
        params={"level": "module", "espace_code": espace, "module_code": module["code"]},
        headers=headers,
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["type"] == "MODULE" and body["modules_count"] == 1
    assert body["tables_count"] == module["tables_count"]
    assert body["administrateur"]["email"] == "admin@el-amana.mr"

    other = next(d["code"] for d in cat["departements"] if d["code"] != espace)
    mismatch = await client.get(
        f"{API}/backups/preview",
        params={"level": "module", "espace_code": other, "module_code": module["code"]},
        headers=headers,
    )
    assert mismatch.status_code == 400

    glob = (await client.get(f"{API}/backups/preview", params={"level": "global"}, headers=headers)).json()
    assert glob["type"] == "GLOBAL" and glob["departements_count"] == cat["departements_count"]

    hist = await client.get(f"{API}/backups/history", params={"size": 5}, headers=headers)
    assert hist.status_code == 200
    assert {"items", "total"} <= set(hist.json())

    dash = (await client.get(f"{API}/backups/dashboard", headers=headers)).json()
    for key in ("success", "failed", "restores_total", "total_size_bytes", "dernieres_sauvegardes"):
        assert key in dash


@pytest.mark.asyncio
async def test_recovery_refuses_without_strong_confirmation(client: AsyncClient):
    headers = await _headers(client)
    missing = await client.post(
        f"{API}/recovery/{uuid.uuid4()}",
        json={"acknowledge_dependencies": True, "confirmation": "RESTAURER GLOBAL", "reason": "Test automatisé"},
        headers=headers,
    )
    assert missing.status_code == 404

    listing = (await client.get(f"{API}/backups", params={"status": "success", "size": 1}, headers=headers)).json()
    if not listing["items"]:
        pytest.skip("Aucune sauvegarde réussie disponible")
    backup_id = listing["items"][0]["id"]

    for payload in (
        {"acknowledge_dependencies": True},
        {"acknowledge_dependencies": True, "confirmation": "RESTAURER", "reason": "Test automatisé"},
        {"acknowledge_dependencies": True, "confirmation": listing["items"][0]["confirmation_phrase"], "reason": "court"},
    ):
        resp = await client.post(f"{API}/recovery/{backup_id}", json=payload, headers=headers)
        assert resp.status_code == 400, resp.text
