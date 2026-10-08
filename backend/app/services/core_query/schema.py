"""Connaissance du schéma : tables, colonnes, types, clés primaires et étrangères.

Introspection PostgreSQL (``information_schema`` + ``pg_constraint``), mise en
cache. Les colonnes secrètes (mots de passe, secrets TOTP, jetons) et les
tables de secrets ne sont jamais exposées : elles sont absentes du catalogue
public et refusées par le validateur.
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.services.core_query.labels import column_label, table_label

SCHEMA = "public"

DENIED_TABLES: frozenset[str] = frozenset(
    {
        "alembic_version",
        "password_history",
        "password_reset_jtis",
    }
)

_SENSITIVE_RE = re.compile(r"(password|passwd|secret|token|jti$|^jti|api_key|private_key|credential)")
_SENSITIVE_ALLOW: frozenset[str] = frozenset({"totp_enabled"})

_CACHE_TTL_S = 300.0
_cache: tuple[float, "Catalog"] | None = None


def is_sensitive_column(name: str) -> bool:
    low = name.lower()
    if low in _SENSITIVE_ALLOW:
        return False
    return bool(_SENSITIVE_RE.search(low))


def _kind(data_type: str, udt: str) -> str:
    t = (data_type or "").lower()
    if t in {"smallint", "integer", "bigint", "numeric", "real", "double precision", "decimal"}:
        return "number"
    if t == "boolean":
        return "boolean"
    if t == "date":
        return "date"
    if t.startswith("timestamp"):
        return "datetime"
    if t == "interval":
        return "interval"
    if t == "uuid":
        return "uuid"
    if t in {"json", "jsonb"}:
        return "json"
    if t == "user-defined":
        return "enum" if udt else "text"
    if t in {"character varying", "text", "character"}:
        return "text"
    return "other"


@dataclass
class Column:
    name: str
    data_type: str
    kind: str
    nullable: bool
    enum_values: list[str] | None = None

    @property
    def label(self) -> str:
        return column_label(self.name)


@dataclass
class ForeignKey:
    name: str
    table: str
    columns: list[str]
    ref_table: str
    ref_columns: list[str]


@dataclass
class Table:
    name: str
    columns: dict[str, Column] = field(default_factory=dict)
    hidden_columns: list[str] = field(default_factory=list)
    primary_key: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return table_label(self.name)


@dataclass
class Catalog:
    tables: dict[str, Table]
    foreign_keys: list[ForeignKey]
    denied_tables: frozenset[str]
    fingerprint: str

    def table(self, name: str) -> Table | None:
        return self.tables.get(name)

    def has(self, table: str, column: str) -> bool:
        t = self.tables.get(table)
        return bool(t and column in t.columns)

    def fks_from(self, table: str) -> list[ForeignKey]:
        return [fk for fk in self.foreign_keys if fk.table == table]

    def fks_to(self, table: str) -> list[ForeignKey]:
        return [fk for fk in self.foreign_keys if fk.ref_table == table]

    def fk(self, name: str) -> ForeignKey | None:
        return next((fk for fk in self.foreign_keys if fk.name == name), None)

    def fk_between(self, table: str, column: str) -> ForeignKey | None:
        return next(
            (fk for fk in self.foreign_keys if fk.table == table and fk.columns == [column]),
            None,
        )

    @property
    def sensitive_names(self) -> set[str]:
        names: set[str] = set()
        for t in self.tables.values():
            names.update(c.lower() for c in t.hidden_columns)
        return names

    def to_public(self) -> dict:
        return {
            "fingerprint": self.fingerprint,
            "tables": [
                {
                    "name": t.name,
                    "label": t.label,
                    "primary_key": t.primary_key,
                    "hidden_columns": len(t.hidden_columns),
                    "columns": [
                        {
                            "name": c.name,
                            "label": c.label,
                            "type": c.data_type,
                            "kind": c.kind,
                            "nullable": c.nullable,
                            "enum_values": c.enum_values,
                            "primary_key": c.name in t.primary_key,
                        }
                        for c in t.columns.values()
                    ],
                }
                for t in sorted(self.tables.values(), key=lambda x: x.name)
            ],
            "relations": [
                {
                    "name": fk.name,
                    "table": fk.table,
                    "columns": fk.columns,
                    "ref_table": fk.ref_table,
                    "ref_columns": fk.ref_columns,
                }
                for fk in self.foreign_keys
            ],
        }


async def load_catalog_from_connection(conn: AsyncConnection) -> Catalog:
    cols = (
        await conn.execute(
            text(
                """
                SELECT c.table_name, c.column_name, c.data_type, c.udt_name, c.is_nullable
                FROM information_schema.columns c
                JOIN information_schema.tables t
                  ON t.table_schema = c.table_schema AND t.table_name = c.table_name
                WHERE c.table_schema = :schema AND t.table_type = 'BASE TABLE'
                ORDER BY c.table_name, c.ordinal_position
                """
            ),
            {"schema": SCHEMA},
        )
    ).all()
    enums_rows = (
        await conn.execute(
            text(
                """
                SELECT t.typname, e.enumlabel
                FROM pg_type t
                JOIN pg_enum e ON e.enumtypid = t.oid
                JOIN pg_namespace n ON n.oid = t.typnamespace
                WHERE n.nspname = :schema
                ORDER BY t.typname, e.enumsortorder
                """
            ),
            {"schema": SCHEMA},
        )
    ).all()
    enums: dict[str, list[str]] = {}
    for typname, label in enums_rows:
        enums.setdefault(typname, []).append(label)

    tables: dict[str, Table] = {}
    for table_name, column_name, data_type, udt, nullable in cols:
        if table_name in DENIED_TABLES:
            continue
        t = tables.setdefault(table_name, Table(name=table_name))
        if is_sensitive_column(column_name):
            t.hidden_columns.append(column_name)
            continue
        kind = _kind(data_type, udt if udt in enums else "")
        t.columns[column_name] = Column(
            name=column_name,
            data_type=udt if data_type == "USER-DEFINED" else data_type,
            kind=kind,
            nullable=nullable == "YES",
            enum_values=enums.get(udt) if kind == "enum" else None,
        )

    constraint_rows = (
        await conn.execute(
            text(
                """
                SELECT con.conname, con.contype::text, cl.relname, att.attname,
                       fcl.relname AS ref_table, fatt.attname AS ref_column, k.ord
                FROM pg_constraint con
                JOIN pg_class cl ON cl.oid = con.conrelid
                JOIN pg_namespace ns ON ns.oid = cl.relnamespace
                CROSS JOIN LATERAL unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord)
                JOIN pg_attribute att ON att.attrelid = con.conrelid AND att.attnum = k.attnum
                LEFT JOIN pg_class fcl ON fcl.oid = con.confrelid
                LEFT JOIN pg_attribute fatt
                  ON fatt.attrelid = con.confrelid AND fatt.attnum = con.confkey[k.ord]
                WHERE ns.nspname = :schema AND con.contype IN ('p', 'f')
                ORDER BY con.conname, k.ord
                """
            ),
            {"schema": SCHEMA},
        )
    ).all()
    fks: dict[str, ForeignKey] = {}
    for conname, contype, relname, attname, ref_table, ref_column, _ord in constraint_rows:
        if relname not in tables:
            continue
        if contype == "p":
            tables[relname].primary_key.append(attname)
            continue
        if ref_table not in tables:
            continue
        fk = fks.setdefault(
            conname,
            ForeignKey(name=conname, table=relname, columns=[], ref_table=ref_table, ref_columns=[]),
        )
        fk.columns.append(attname)
        fk.ref_columns.append(ref_column)

    digest = hashlib.sha256()
    for t in sorted(tables.values(), key=lambda x: x.name):
        digest.update(t.name.encode())
        digest.update(",".join(t.columns).encode())
        digest.update(("|" + ",".join(t.hidden_columns)).encode())
    return Catalog(
        tables=tables,
        foreign_keys=list(fks.values()),
        denied_tables=DENIED_TABLES,
        fingerprint=digest.hexdigest()[:16],
    )


async def get_catalog(engine: AsyncEngine, *, refresh: bool = False) -> Catalog:
    global _cache
    now = time.monotonic()
    if not refresh and _cache and now - _cache[0] < _CACHE_TTL_S:
        return _cache[1]
    async with engine.connect() as conn:
        catalog = await load_catalog_from_connection(conn)
    _cache = (now, catalog)
    return catalog


def invalidate_catalog() -> None:
    global _cache
    _cache = None
