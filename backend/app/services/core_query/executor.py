"""Exécution CORE QUERY : transaction READ ONLY, timeout, rôle restreint, rollback.

Le mode administrateur (``execute_admin``) exécute le SQL tel quel dans une
transaction validée (COMMIT) ou annulée (simulation).

Le rôle ``bea_core_query_reader`` (NOLOGIN) ne reçoit que ``SELECT`` sur les
colonnes non secrètes du catalogue public. Il est créé / resynchronisé quand
l'empreinte du schéma change. Si le compte applicatif ne peut pas le gérer
(compte non propriétaire en TEST/PROD), l'exécution reste en transaction READ
ONLY derrière le validateur et ``reader_role_available()`` renvoie False.
"""

from __future__ import annotations

import base64
import logging
import re
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine

from app.services.core_query.schema import Catalog
from app.services.core_query.validator import is_multi_statement

logger = logging.getLogger(__name__)

READER_ROLE = "bea_core_query_reader"
DEFAULT_LIMIT = 500
MAX_LIMIT = 5000
EXPORT_LIMIT = 20_000
STATEMENT_TIMEOUT_MS = 15_000
ADMIN_TIMEOUT_MS = 120_000
_ROW_KEYWORDS = {"SELECT", "WITH", "TABLE", "VALUES", "SHOW", "EXPLAIN"}

_role_state: dict[str, Any] = {"fingerprint": None, "available": False, "error": None}


class QueryExecutionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class ExecResult:
    columns: list[dict[str, str]]
    rows: list[list[Any]]
    total: int
    truncated: bool
    duration_ms: int
    command_tag: str | None = None
    affected_rows: int | None = None
    committed: bool = False


def reader_role_available() -> bool:
    return bool(_role_state["available"])


def reader_role_status() -> dict[str, Any]:
    return {"role": READER_ROLE, "available": bool(_role_state["available"]), "error": _role_state["error"]}


def _qi(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


async def ensure_reader_role(engine: AsyncEngine, catalog: Catalog) -> bool:
    if _role_state["fingerprint"] == catalog.fingerprint:
        return bool(_role_state["available"])
    statements = [
        f"""
        DO $cq$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{READER_ROLE}') THEN
            CREATE ROLE {READER_ROLE} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
          END IF;
        END $cq$
        """,
        f"GRANT {READER_ROLE} TO CURRENT_USER",
        f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {READER_ROLE}",
        f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {READER_ROLE}",
        f"GRANT USAGE ON SCHEMA public TO {READER_ROLE}",
    ]
    for table in sorted(catalog.tables.values(), key=lambda x: x.name):
        if not table.columns:
            continue
        if table.hidden_columns:
            cols = ", ".join(_qi(c) for c in table.columns)
            statements.append(f"GRANT SELECT ({cols}) ON public.{_qi(table.name)} TO {READER_ROLE}")
        else:
            statements.append(f"GRANT SELECT ON public.{_qi(table.name)} TO {READER_ROLE}")
    try:
        async with engine.connect() as conn:
            raw = await conn.get_raw_connection()
            driver = raw.driver_connection
            async with driver.transaction():
                for stmt in statements:
                    await driver.execute(stmt)
        _role_state.update(fingerprint=catalog.fingerprint, available=True, error=None)
    except Exception as exc:  # noqa: BLE001
        logger.warning("CORE QUERY : rôle restreint indisponible (%s)", type(exc).__name__)
        _role_state.update(
            fingerprint=catalog.fingerprint,
            available=False,
            error="Le compte applicatif ne peut pas gérer le rôle restreint ; lecture seule par transaction.",
        )
    return bool(_role_state["available"])


def _kind(type_name: str) -> str:
    t = type_name.lower()
    if t in {"int2", "int4", "int8", "numeric", "float4", "float8", "oid", "money"}:
        return "number"
    if t == "bool":
        return "boolean"
    if t == "date":
        return "date"
    if t in {"timestamp", "timestamptz"}:
        return "datetime"
    if t == "interval":
        return "interval"
    if t in {"json", "jsonb"}:
        return "json"
    return "text"


def _fmt_interval(v: timedelta) -> str:
    total = int(v.total_seconds())
    sign = "-" if total < 0 else ""
    total = abs(total)
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    base = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{sign}{days} j {base}" if days else f"{sign}{base}"


def serialize_cell(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if value == value and value not in (float("inf"), float("-inf")) else str(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            return str(value)
        return int(value) if value == value.to_integral_value() and abs(value) < 10**15 else float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (date, dtime)):
        return value.isoformat()
    if isinstance(value, timedelta):
        return _fmt_interval(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        data = bytes(value)
        return f"<binaire {len(data)} o>" if len(data) > 64 else base64.b64encode(data).decode()
    if isinstance(value, (list, tuple)):
        return [serialize_cell(v) for v in value]
    if isinstance(value, dict):
        return {str(k): serialize_cell(v) for k, v in value.items()}
    return str(value)


def _map_pg_error(exc: Exception) -> QueryExecutionError:
    name = type(exc).__name__
    msg = str(exc).strip().splitlines()[0] if str(exc).strip() else name
    if name == "QueryCanceledError" or "statement timeout" in msg:
        return QueryExecutionError(
            "TIMEOUT",
            f"Requête interrompue : durée maximale de {STATEMENT_TIMEOUT_MS // 1000} s dépassée. "
            "Ajoutez des filtres ou une limite.",
        )
    if name == "InsufficientPrivilegeError":
        return QueryExecutionError("PERMISSION", "Accès refusé par le rôle lecture seule : " + msg)
    if name == "ReadOnlySQLTransactionError":
        return QueryExecutionError("READ_ONLY", "Opération d'écriture bloquée (transaction en lecture seule).")
    if name in {"UndefinedColumnError", "UndefinedTableError", "UndefinedFunctionError"}:
        return QueryExecutionError("SCHEMA", "Élément inconnu dans le schéma : " + msg)
    if name == "PostgresSyntaxError":
        return QueryExecutionError("SYNTAX", "Erreur de syntaxe SQL : " + msg)
    if name == "LockNotAvailableError":
        return QueryExecutionError("LOCKED", "Table verrouillée par une autre opération : réessayez. " + msg)
    if name in {"ForeignKeyViolationError", "UniqueViolationError", "NotNullViolationError", "CheckViolationError"}:
        return QueryExecutionError("CONSTRAINT", "Contrainte d'intégrité violée : " + msg)
    return QueryExecutionError("SQL_ERROR", msg[:500])


def _first_keyword(sql: str) -> str:
    m = re.match(r"\s*(?:\(\s*)*([A-Za-z]+)", re.sub(r"--[^\n]*|/\*.*?\*/", " ", sql, flags=re.S))
    return m[1].upper() if m else ""


def _affected(tag: str | None) -> int | None:
    if not tag:
        return None
    last = tag.rsplit(" ", 1)[-1]
    return int(last) if last.isdigit() else None


async def execute_admin(
    engine: AsyncEngine,
    sql: str,
    *,
    limit: int = DEFAULT_LIMIT,
    dry_run: bool = False,
    timeout_ms: int = ADMIN_TIMEOUT_MS,
) -> ExecResult:
    """Mode administrateur : SQL sans filtre de lecture, une transaction, COMMIT ou ROLLBACK (simulation).

    Les requêtes multiples s'exécutent d'un bloc (atomique) ; seule la dernière
    étiquette de commande est renvoyée.
    """
    limit = max(1, min(int(limit), EXPORT_LIMIT))
    started = time.perf_counter()
    attrs: list = []
    records: list = []
    truncated = False
    tag: str | None = None
    committed = False
    async with engine.connect() as conn:
        raw = await conn.get_raw_connection()
        driver = raw.driver_connection
        tr = driver.transaction()
        await tr.start()
        try:
            await driver.execute(f"SET LOCAL statement_timeout = {int(timeout_ms)}")
            await driver.execute("SET LOCAL lock_timeout = 10000")
            if is_multi_statement(sql):
                tag = await driver.execute(sql)
            else:
                stmt = await driver.prepare(sql)
                attrs = list(stmt.get_attributes())
                if attrs and _first_keyword(sql) in _ROW_KEYWORDS:
                    cur = await stmt.cursor()
                    records = await cur.fetch(limit + 1)
                    truncated = len(records) > limit
                    records = records[:limit]
                    tag = f"SELECT {len(records)}{'+' if truncated else ''}"
                else:
                    records = await stmt.fetch()
                    tag = stmt.get_statusmsg()
                    truncated = len(records) > limit
                    records = records[:limit]
            if dry_run:
                await tr.rollback()
            else:
                await tr.commit()
                committed = True
        except QueryExecutionError:
            await _safe_rollback(tr)
            raise
        except Exception as exc:  # noqa: BLE001
            await _safe_rollback(tr)
            raise _map_pg_error(exc) from None
    duration_ms = int((time.perf_counter() - started) * 1000)
    columns = [{"name": a.name, "type": a.type.name, "kind": _kind(a.type.name)} for a in attrs]
    rows = [[serialize_cell(v) for v in rec.values()] for rec in records]
    return ExecResult(
        columns=columns, rows=rows, total=len(rows), truncated=truncated, duration_ms=duration_ms,
        command_tag=tag, affected_rows=_affected(tag), committed=committed,
    )


async def _safe_rollback(tr) -> None:
    try:
        await tr.rollback()
    except Exception:  # noqa: BLE001
        pass


async def execute_select(
    engine: AsyncEngine,
    sql: str,
    *,
    limit: int = DEFAULT_LIMIT,
    use_reader_role: bool = True,
    timeout_ms: int = STATEMENT_TIMEOUT_MS,
) -> ExecResult:
    limit = max(1, min(int(limit), EXPORT_LIMIT))
    wrapped = f"SELECT * FROM (\n{sql}\n) AS core_query_result LIMIT {limit + 1}"
    started = time.perf_counter()
    async with engine.connect() as conn:
        raw = await conn.get_raw_connection()
        driver = raw.driver_connection
        tr = driver.transaction(readonly=True)
        await tr.start()
        try:
            await driver.execute(f"SET LOCAL statement_timeout = {int(timeout_ms)}")
            await driver.execute("SET LOCAL lock_timeout = 2000")
            await driver.execute("SET LOCAL search_path = public")
            if use_reader_role:
                await driver.execute(f"SET LOCAL ROLE {READER_ROLE}")
            stmt = await driver.prepare(wrapped)
            attrs = stmt.get_attributes()
            records = await stmt.fetch()
            truncated = len(records) > limit
            records = records[:limit]
            total = len(records)
            if truncated:
                total = int(await driver.fetchval(f"SELECT count(*) FROM (\n{sql}\n) AS core_query_count"))
        except QueryExecutionError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise _map_pg_error(exc) from None
        finally:
            try:
                await tr.rollback()
            except Exception:  # noqa: BLE001
                pass
    duration_ms = int((time.perf_counter() - started) * 1000)
    columns = [{"name": a.name, "type": a.type.name, "kind": _kind(a.type.name)} for a in attrs]
    rows = [[serialize_cell(v) for v in rec.values()] for rec in records]
    return ExecResult(columns=columns, rows=rows, total=total, truncated=truncated, duration_ms=duration_ms)
