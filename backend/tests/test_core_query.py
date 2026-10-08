"""CORE QUERY — validateur lecture seule, NL parser, builder, exécution et API."""

from __future__ import annotations

import os
from datetime import datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db.session import engine
from app.main import app
from app.services.core_query.builder import build_sql
from app.services.core_query.executor import ensure_reader_role, execute_admin, execute_select
from app.services.core_query.nl_parser import EXAMPLES, TZ, interpret, normalize, parse_period
from app.services.core_query.schema import get_catalog, is_sensitive_column
from app.services.core_query.validator import QueryRefused, check_admin_sql, tokenize, validate_sql

API = "/api/v1/plateforme/admin/core-query"
NOW = datetime(2026, 10, 8, 10, 30, tzinfo=TZ)
MODULES = {"stock-fournitures": "Stock & Fournitures", "immobilisations": "Immobilisations & Amortissements",
           "demandes-rh": "Demandes", "demandes-credit": "Demandes"}


async def _db_ready() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest.fixture
async def catalog():
    if not await _db_ready():
        pytest.skip("Base PostgreSQL indisponible")
    try:
        yield await get_catalog(engine, refresh=True)
    finally:
        await engine.dispose()


# --------------------------------------------------------------------------- schéma / secrets


def test_sensitive_column_detection():
    for name in ("hashed_password", "totp_secret", "password_hash", "refresh_jti", "jti", "api_token"):
        assert is_sensitive_column(name), name
    for name in ("totp_enabled", "email", "snapshot_hash", "created_at", "security_level"):
        assert not is_sensitive_column(name), name


@pytest.mark.asyncio
async def test_catalog_hides_secrets(catalog):
    users = catalog.table("users")
    assert users is not None and "email" in users.columns
    assert "hashed_password" not in users.columns and "hashed_password" in users.hidden_columns
    assert catalog.table("password_history") is None
    assert any(fk.table == "user_roles" and fk.ref_table == "roles" for fk in catalog.foreign_keys)
    assert users.primary_key == ["id"]


# --------------------------------------------------------------------------- validateur


def test_tokenizer_handles_strings_and_comments():
    toks = tokenize("SELECT 'a;b''c' AS \"x;y\" -- DROP\n/* DELETE */ FROM users")
    values = [t.value for t in toks]
    assert "a;b'c" in values and "x;y" in values
    assert "DROP" not in values and "DELETE" not in values


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sql, code",
    [
        ("DELETE FROM users", "NOT_SELECT"),
        ("UPDATE users SET is_active = false", "NOT_SELECT"),
        ("DROP TABLE users", "NOT_SELECT"),
        ("SELECT 1; DROP TABLE users", "MULTI_STATEMENT"),
        ("WITH x AS (DELETE FROM users RETURNING id) SELECT * FROM x", "FORBIDDEN_KEYWORD"),
        ("SELECT * INTO copie FROM agences", "FORBIDDEN_KEYWORD"),
        ("SELECT id FROM agences FOR UPDATE", "LOCKING"),
        ("SELECT id FROM agences FOR SHARE", "LOCKING"),
        ("SELECT pg_sleep(10)", "FORBIDDEN_FUNCTION"),
        ('SELECT "pg_sleep"(10)', "FORBIDDEN_FUNCTION"),
        ("SELECT pg_catalog.lower('a')", "FORBIDDEN_FUNCTION"),
        ("SELECT set_config('role', 'admin', true)", "FORBIDDEN_FUNCTION"),
        ("SELECT current_setting('server_version')", "FORBIDDEN_FUNCTION"),
        ("SELECT usename FROM pg_user", "UNKNOWN_TABLE"),
        ("SELECT * FROM pg_catalog.pg_authid", "FORBIDDEN_TABLE"),
        ("SELECT * FROM information_schema.tables", "FORBIDDEN_TABLE"),
        ("SELECT hashed_password FROM users", "SENSITIVE_COLUMN"),
        ('SELECT u."totp_secret" FROM users u', "SENSITIVE_COLUMN"),
        ("SELECT * FROM users", "SENSITIVE_COLUMN"),
        ("SELECT u.* FROM users u", "SENSITIVE_COLUMN"),
        ("SELECT u FROM users u", "SENSITIVE_COLUMN"),
        ("SELECT user_id FROM password_history", "FORBIDDEN_TABLE"),
        ("SELECT id FROM password_reset_jtis", "FORBIDDEN_TABLE"),
        ("SELECT u.prenom FROM users u", "UNKNOWN_COLUMN"),
        ("SELECT id FROM table_inexistante", "UNKNOWN_TABLE"),
        ("SELECT $$x$$", "DOLLAR_QUOTE"),
        ("COPY users TO '/tmp/x'", "NOT_SELECT"),
        ("", "EMPTY"),
    ],
)
async def test_validator_refuses(catalog, sql, code):
    with pytest.raises(QueryRefused) as exc:
        validate_sql(sql, catalog)
    assert exc.value.code == code, exc.value.message


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sql",
    [
        "SELECT email, full_name FROM users WHERE is_active = true ORDER BY full_name LIMIT 10",
        "SELECT u.full_name, r.label FROM users u JOIN user_roles ur ON ur.user_id = u.id "
        "JOIN roles r ON r.id = ur.role_id",
        "SELECT a.libelle, count(*), sum(i.valeur_brute) FROM immobilisations i "
        "LEFT JOIN agences a ON a.id = i.agence_id GROUP BY a.libelle HAVING count(*) > 1",
        "WITH s AS (SELECT user_id, count(*) AS n FROM auth_sessions GROUP BY user_id) "
        "SELECT u.email, s.n FROM s JOIN users u ON u.id = s.user_id",
        "SELECT extract(hour FROM created_at) AS h, count(*) FROM audit_logs GROUP BY 1",
        "SELECT DISTINCT action FROM audit_logs WHERE created_at >= now() - interval '7 days';",
        "SELECT * FROM agences",
        "SELECT date_trunc('day', created_at)::date AS jour FROM auth_sessions "
        "WHERE created_at IS DISTINCT FROM NULL",
        "SELECT id FROM agences a WHERE EXISTS (SELECT 1 FROM users u WHERE u.agence_id = a.id)",
        "SELECT 'DELETE FROM users' AS texte FROM agences",
    ],
)
async def test_validator_accepts(catalog, sql):
    v = validate_sql(sql, catalog)
    assert v.tables


# --------------------------------------------------------------------------- NL parser


def test_period_parsing():
    q = normalize("utilisateurs connectés hier entre 8h et 17h")
    p = parse_period(q, NOW)
    assert p.label == "Hier" and p.date_label() == "07/10/2026" and p.hours_label() == "08:00 – 17:00"
    assert parse_period(normalize("documents ajoutés ce mois-ci"), NOW).start.day == 1
    assert parse_period(normalize("depuis 30 jours"), NOW).days == 30
    assert parse_period(normalize("le 05/10/2026"), NOW).date_label() == "05/10/2026"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question, intent, table",
    [
        ("Quels utilisateurs se sont connectés hier entre 8h et 17h ?", "connections", "auth_sessions"),
        ("Quels utilisateurs sont actuellement actifs ?", "active_sessions", "auth_sessions"),
        ("Quels utilisateurs ne se sont pas connectés depuis 30 jours ?", "inactive_users", "users"),
        ("Combien d'utilisateurs ?", "generic_count", "users"),
        ("Immobilisations par agence", "generic_group", "immobilisations"),
        ("Valeur totale des immobilisations", "generic_aggregate", "immobilisations"),
        ("Demandes de stock en attente", "stock_demands", "mg_demandes_fourniture"),
        ("Dernières opérations administratives", "admin_operations", "audit_logs"),
        ("Dernières connexions au module Stock & Fournitures", "connections", "auth_sessions"),
        ("Documents ajoutés aux archives ce mois-ci", "archives_documents", "archive_fichiers"),
        ("Modules les plus utilisés aujourd'hui", "modules_usage", "auth_sessions"),
        ("sessions de plus de 8 heures", "long_sessions", "auth_sessions"),
        ("activité des administrateurs aujourd'hui", "admin_activity", "audit_logs"),
    ],
)
async def test_parser_examples(catalog, question, intent, table):
    interp = interpret(question, catalog, now=NOW, modules=MODULES)
    assert interp.ok, interp.clarification
    assert interp.intent == intent
    assert interp.tables[0] == table
    validate_sql(interp.sql, catalog)
    for ref in interp.columns:
        t, c = ref.split(".")
        assert catalog.has(t, c), f"colonne inventée : {ref}"


@pytest.mark.asyncio
async def test_parser_specific_sql(catalog):
    hier = interpret("utilisateurs connectés hier entre 8h et 17h", catalog, now=NOW, modules=MODULES)
    assert "'2026-10-07 08:00:00+00:00'::timestamptz" in hier.sql
    assert "'2026-10-07 17:00:00+00:00'::timestamptz" in hier.sql
    assert "s.kind = 'platform'" in hier.sql
    stock = interpret("dernières connexions au module Stock & Fournitures", catalog, now=NOW, modules=MODULES)
    assert "s.module_code = 'stock-fournitures'" in stock.sql and "LIMIT 50" in stock.sql
    pending = interpret("demandes de stock en attente", catalog, now=NOW, modules=MODULES)
    assert "'SOUMIS'" in pending.sql and "'SERVIE'" not in pending.sql
    group = interpret("immobilisations par agence", catalog, now=NOW, modules=MODULES)
    assert "agences" in group.tables and "sum(t.valeur_brute)" in group.sql


@pytest.mark.asyncio
async def test_parser_asks_clarification(catalog):
    assert not interpret("bonjour", catalog, now=NOW).ok
    vague = interpret("blabla quelque chose", catalog, now=NOW)
    assert not vague.ok and vague.clarification and vague.suggestions
    ambiguous = interpret("connexions au module demandes", catalog, now=NOW, modules=MODULES)
    assert not ambiguous.ok and "Plusieurs modules" in ambiguous.clarification
    bad_group = interpret("immobilisations par couleur", catalog, now=NOW)
    assert not bad_group.ok and "Regroupements possibles" in bad_group.clarification


def test_examples_list():
    assert len(EXAMPLES) == 11


# --------------------------------------------------------------------------- builder


@pytest.mark.asyncio
async def test_builder_joins_from_foreign_keys(catalog):
    fk_ur = next(fk for fk in catalog.foreign_keys if fk.table == "user_roles" and fk.ref_table == "users")
    fk_r = next(fk for fk in catalog.foreign_keys if fk.table == "user_roles" and fk.ref_table == "roles")
    built = build_sql(
        {
            "table": "users",
            "joins": [
                {"relation": fk_ur.name, "from": "t0", "direction": "in"},
                {"relation": fk_r.name, "from": "t1", "direction": "out"},
            ],
            "columns": [{"alias": "t0", "column": "email"}, {"alias": "t2", "column": "label"}],
            "filters": [
                {"alias": "t0", "column": "email", "operator": "contains", "value": "50%_x"},
                {"alias": "t0", "column": "created_at", "operator": "between", "value": "2026-01-01",
                 "value2": "2026-12-31"},
                {"alias": "t0", "column": "phone", "operator": "is_empty"},
            ],
            "limit": 100,
        },
        catalog,
    )
    sql = built["sql"]
    assert "LEFT JOIN user_roles t1 ON t1.user_id = t0.id" in sql
    assert "LEFT JOIN roles t2 ON t2.id = t1.role_id" in sql
    assert "ILIKE '%50\\%\\_x%'" in sql
    assert "< '2027-01-01 00:00:00+00:00'::timestamptz" in sql
    validate_sql(sql, catalog)


@pytest.mark.asyncio
async def test_builder_rejects_invalid(catalog):
    for spec in (
        {"table": "password_history", "columns": [{"column": "user_id"}]},
        {"table": "users", "columns": [{"column": "hashed_password"}]},
        {"table": "users", "columns": [{"column": "email"}], "joins": [{"relation": "fk_inventee"}]},
        {"table": "users", "columns": [{"column": "email", "aggregate": "sum"}]},
        {"table": "users", "columns": [{"column": "email"}],
         "filters": [{"column": "is_active", "operator": "eq", "value": "peut-être"}]},
    ):
        with pytest.raises(QueryRefused):
            build_sql(spec, catalog)


# --------------------------------------------------------------------------- exécution


@pytest.mark.asyncio
async def test_executor_read_only_and_role(catalog):
    role = await ensure_reader_role(engine, catalog)
    res = await execute_select(engine, "SELECT code, libelle FROM agences ORDER BY code", limit=2,
                               use_reader_role=role)
    assert res.columns[0]["name"] == "code" and len(res.rows) <= 2
    if role:
        with pytest.raises(Exception) as exc:
            await execute_select(engine, "SELECT hashed_password FROM users", use_reader_role=True)
        assert getattr(exc.value, "code", "") == "PERMISSION"


# --------------------------------------------------------------------------- mode administrateur


@pytest.mark.parametrize(
    ("sql", "write"),
    [
        ("SELECT hashed_password FROM users", False),
        ("SELECT * FROM users", False),
        ("UPDATE agences SET libelle = libelle WHERE false", True),
        ("DELETE FROM agences WHERE false", True),
        ("CREATE TABLE t (id int); DROP TABLE t", True),
        ("DO $$ BEGIN PERFORM 1; END $$", True),
        ("SELECT 'DELETE FROM users' AS texte", False),
        ("-- UPDATE users\nSELECT 1", False),
    ],
)
def test_admin_check_allows_everything_on_data(sql, write):
    assert check_admin_sql(sql).is_write is write


@pytest.mark.parametrize(
    ("sql", "code"),
    [
        ("", "EMPTY"),
        ("COPY users TO '/tmp/u.csv'", "SERVER_ACCESS"),
        ("COPY (SELECT 1) TO PROGRAM 'id'", "SERVER_ACCESS"),
        ("ALTER SYSTEM SET work_mem = '1GB'", "SERVER_ACCESS"),
        ("DROP DATABASE bea_digital", "SERVER_ACCESS"),
        ("SELECT pg_read_file('/etc/passwd')", "SERVER_ACCESS"),
        ("BEGIN; UPDATE agences SET code = code; COMMIT", "TRANSACTION"),
        ("UPDATE agences SET code = code; ROLLBACK", "TRANSACTION"),
    ],
)
def test_admin_check_blocks_server_access(sql, code):
    with pytest.raises(QueryRefused) as exc:
        check_admin_sql(sql)
    assert exc.value.code == code


@pytest.mark.asyncio
async def test_execute_admin_commit_and_dry_run(catalog):
    script = (
        "CREATE TEMP TABLE cq_admin_probe (id int) ON COMMIT DROP; "
        "INSERT INTO cq_admin_probe VALUES (1), (2), (3); "
        "UPDATE cq_admin_probe SET id = id + 10"
    )
    sim = await execute_admin(engine, script, dry_run=True)
    assert sim.command_tag == "UPDATE 3" and sim.affected_rows == 3 and not sim.committed

    done = await execute_admin(engine, script)
    assert done.committed and done.affected_rows == 3

    rows = await execute_admin(engine, "SELECT hashed_password IS NOT NULL AS h FROM users LIMIT 3", limit=2)
    assert rows.columns[0]["name"] == "h" and len(rows.rows) <= 2

    with pytest.raises(Exception) as exc:
        await execute_admin(engine, "UPDATE agences SET id = NULL WHERE false; SELECT 1/0")
    assert getattr(exc.value, "code", "") == "SQL_ERROR"


# --------------------------------------------------------------------------- API


@pytest.fixture
async def client():
    if not await _db_ready():
        pytest.skip("Base PostgreSQL indisponible")
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
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
async def test_endpoints_require_auth(client: AsyncClient):
    for path in ("/schema", "/dashboard", "/history", "/favorites"):
        assert (await client.get(f"{API}{path}")).status_code == 401, path
    assert (await client.post(f"{API}/execute", json={"mode": "sql", "sql": "SELECT 1"})).status_code == 401


@pytest.mark.asyncio
async def test_api_analyze_execute_history(client: AsyncClient):
    headers = await _headers(client)
    schema = (await client.get(f"{API}/schema", headers=headers)).json()
    assert any(t["name"] == "users" for t in schema["tables"])
    users = next(t for t in schema["tables"] if t["name"] == "users")
    assert all(c["name"] != "hashed_password" for c in users["columns"])

    analysis = (await client.post(f"{API}/analyze", json={"question": "combien d'utilisateurs"}, headers=headers)).json()
    assert analysis["ok"] and analysis["validation"]["ok"]

    run = await client.post(
        f"{API}/execute",
        json={"mode": "assistant", "question": "combien d'utilisateurs", "expected_sql": analysis["sql"]},
        headers=headers,
    )
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["total"] == 1 and body["rows"][0][0] >= 1
    assert all(s["status"] == "ok" for s in body["steps"])

    stale = await client.post(
        f"{API}/execute",
        json={"mode": "assistant", "question": "combien d'utilisateurs", "expected_sql": "SELECT 1"},
        headers=headers,
    )
    assert stale.status_code == 400 and stale.json()["detail"]["reason"] == "STALE"

    refused = await client.post(f"{API}/execute", json={"mode": "sql", "sql": "DELETE FROM users"}, headers=headers)
    assert refused.status_code == 400
    assert refused.json()["code"] == "QUERY_REFUSED" and refused.json()["request_id"]

    hist = (await client.get(f"{API}/history", params={"size": 5}, headers=headers)).json()
    statuses = {item["status"] for item in hist["items"]}
    assert {"success", "refused"} <= statuses

    dash = (await client.get(f"{API}/dashboard", headers=headers)).json()
    assert dash["today"]["total"] >= 2 and dash["today"]["refused"] >= 1

    exp = await client.post(
        f"{API}/export", json={"mode": "sql", "sql": "SELECT code, libelle FROM agences", "format": "csv"},
        headers=headers,
    )
    assert exp.status_code == 200 and "code;libelle" in exp.content.decode("utf-8-sig")


@pytest.mark.asyncio
async def test_api_admin_mode(client: AsyncClient):
    headers = await _headers(client)
    schema = (await client.get(f"{API}/schema", headers=headers)).json()
    assert schema["permissions"]["admin"] is True

    script = (
        "CREATE TEMP TABLE cq_api_probe (id int) ON COMMIT DROP; "
        "INSERT INTO cq_api_probe VALUES (1), (2)"
    )
    no_reason = await client.post(f"{API}/execute", json={"mode": "sql", "sql": script, "admin": True}, headers=headers)
    assert no_reason.status_code == 400 and no_reason.json()["detail"]["reason"] == "REASON_REQUIRED"

    sim = await client.post(
        f"{API}/execute", json={"mode": "sql", "sql": script, "admin": True, "dry_run": True}, headers=headers
    )
    assert sim.status_code == 200, sim.text
    assert sim.json()["dry_run"] and not sim.json()["committed"] and sim.json()["command_tag"] == "INSERT 0 2"

    done = await client.post(
        f"{API}/execute",
        json={"mode": "sql", "sql": script, "admin": True, "reason": "Test automatique CORE QUERY"},
        headers=headers,
    )
    assert done.status_code == 200, done.text
    assert done.json()["committed"] and done.json()["affected_rows"] == 2

    read = await client.post(
        f"{API}/execute", json={"mode": "sql", "sql": "SELECT * FROM users LIMIT 1", "admin": True}, headers=headers
    )
    assert read.status_code == 200 and any(c["name"] == "hashed_password" for c in read.json()["columns"])

    blocked = await client.post(
        f"{API}/execute", json={"mode": "sql", "sql": "SELECT pg_read_file('/etc/passwd')", "admin": True},
        headers=headers,
    )
    assert blocked.status_code == 400 and blocked.json()["detail"]["reason"] == "SERVER_ACCESS"

    hist = (await client.get(f"{API}/history", params={"size": 10}, headers=headers)).json()
    admin_items = [i for i in hist["items"] if i["admin_mode"]]
    assert any(i["reason"] == "Test automatique CORE QUERY" and not i["dry_run"] for i in admin_items)


@pytest.mark.asyncio
async def test_api_favorites_crud(client: AsyncClient):
    headers = await _headers(client)
    favs = (await client.get(f"{API}/favorites", headers=headers)).json()
    system = [f for f in favs if f["is_system"]]
    assert len(system) >= 6
    run = await client.post(f"{API}/execute", json={"favorite_id": system[0]["id"]}, headers=headers)
    assert run.status_code == 200, run.text
    assert (await client.delete(f"{API}/favorites/{system[0]['id']}", headers=headers)).status_code == 403

    created = await client.post(
        f"{API}/favorites",
        json={"name": "Test agences", "source": "sql", "sql": "SELECT code FROM agences"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    fav_id = created.json()["id"]
    bad = await client.post(
        f"{API}/favorites", json={"name": "Mauvais", "source": "sql", "sql": "DROP TABLE agences"}, headers=headers
    )
    assert bad.status_code == 400
    renamed = await client.patch(f"{API}/favorites/{fav_id}", json={"name": "Test agences 2"}, headers=headers)
    assert renamed.json()["name"] == "Test agences 2"
    assert (await client.delete(f"{API}/favorites/{fav_id}", headers=headers)).status_code == 204
