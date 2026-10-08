"""Query Builder CORE QUERY : spécification JSON → SQL lisible.

Jointures uniquement via les clés étrangères réelles du catalogue (l'utilisateur
n'écrit jamais de JOIN). Les valeurs sont typées selon la colonne puis
échappées ; le SQL produit repasse ensuite par le validateur.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any

from app.services.core_query.labels import column_label, table_label
from app.services.core_query.nl_parser import TZ, lit
from app.services.core_query.schema import Catalog
from app.services.core_query.validator import QueryRefused

AGGREGATES = {"count", "count_distinct", "sum", "avg", "min", "max"}
OPERATORS = {
    "eq": "=",
    "ne": "!=",
    "gt": ">",
    "lt": "<",
    "gte": ">=",
    "lte": "<=",
    "contains": "contient",
    "starts_with": "commence par",
    "between": "entre",
    "is_empty": "est vide",
    "is_not_empty": "n'est pas vide",
}
AGG_LABELS = {
    "count": "Nombre",
    "count_distinct": "Nombre distinct",
    "sum": "Somme",
    "avg": "Moyenne",
    "min": "Minimum",
    "max": "Maximum",
}
MAX_JOINS = 6
MAX_FILTERS = 20


def _refuse(message: str) -> QueryRefused:
    return QueryRefused("BUILDER_INVALID", message)


def _like_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _typed_literal(kind: str, value: Any, *, column: str) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise _refuse(f"Valeur manquante pour le filtre sur « {column} ».")
    text = str(value).strip()
    if kind == "number":
        try:
            num = float(text.replace(",", "."))
        except ValueError:
            raise _refuse(f"« {text} » n'est pas un nombre valide ({column}).") from None
        return str(int(num)) if num.is_integer() and abs(num) < 1e15 else repr(num)
    if kind == "boolean":
        low = text.lower()
        if low in {"true", "1", "oui", "vrai"}:
            return "true"
        if low in {"false", "0", "non", "faux"}:
            return "false"
        raise _refuse(f"Valeur booléenne attendue pour « {column} » (oui / non).")
    if kind == "date":
        try:
            return lit(date.fromisoformat(text[:10]).isoformat()) + "::date"
        except ValueError:
            raise _refuse(f"Date invalide pour « {column} » (AAAA-MM-JJ).") from None
    if kind == "datetime":
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            raise _refuse(f"Date / heure invalide pour « {column} ».") from None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)
        return lit(dt.isoformat(sep=" ", timespec="seconds")) + "::timestamptz"
    if kind == "uuid":
        try:
            return lit(str(uuid.UUID(text)))
        except ValueError:
            raise _refuse(f"Identifiant UUID invalide pour « {column} ».") from None
    return lit(text)


def _is_date_only(value: Any) -> bool:
    return isinstance(value, str) and len(value.strip()) == 10


def build_sql(spec: dict[str, Any], catalog: Catalog) -> dict[str, Any]:
    base = spec.get("table")
    base_table = catalog.table(base or "")
    if base_table is None:
        raise _refuse("Choisissez une table du catalogue.")

    aliases: dict[str, str] = {"t0": base_table.name}
    joins_sql: list[str] = []
    relations: list[str] = []
    for i, j in enumerate((spec.get("joins") or [])[:MAX_JOINS], start=1):
        fk = catalog.fk(str(j.get("relation") or ""))
        src_alias = str(j.get("from") or "t0")
        if fk is None or src_alias not in aliases:
            raise _refuse("Relation inconnue : choisissez une relation proposée.")
        src_table = aliases[src_alias]
        direction = j.get("direction") or "out"
        if direction == "out" and fk.table == src_table:
            target, on_pairs = fk.ref_table, zip(fk.ref_columns, fk.columns)
            relation = f"{fk.table}.{', '.join(fk.columns)} → {fk.ref_table}.{', '.join(fk.ref_columns)}"
        elif direction == "in" and fk.ref_table == src_table:
            target, on_pairs = fk.table, zip(fk.columns, fk.ref_columns)
            relation = f"{fk.ref_table}.{', '.join(fk.ref_columns)} ← {fk.table}.{', '.join(fk.columns)}"
        else:
            raise _refuse("Relation incompatible avec la table de départ.")
        alias = f"t{i}"
        aliases[alias] = target
        kind = "INNER" if j.get("type") == "inner" else "LEFT"
        on = " AND ".join(f"{alias}.{tc} = {src_alias}.{sc}" for tc, sc in on_pairs)
        joins_sql.append(f"{kind} JOIN {target} {alias} ON {on}")
        relations.append(relation)

    def column(alias: str, name: str):
        table = aliases.get(alias)
        if table is None:
            raise _refuse("Alias de table inconnu.")
        col = catalog.tables[table].columns.get(name)
        if col is None:
            raise _refuse(f"Colonne inconnue ou protégée : {table}.{name}.")
        return table, col

    multi = len(aliases) > 1
    select: list[str] = []
    group: list[str] = []
    used_columns: list[str] = []
    labels_seen: set[str] = set()
    has_agg = False
    first_agg_pos = 0
    for c in spec.get("columns") or []:
        alias, name, agg = str(c.get("alias") or "t0"), str(c.get("column") or ""), c.get("aggregate")
        if agg == "count" and name in ("", "*"):
            expr, label = "count(*)", "Nombre"
        else:
            table, col = column(alias, name)
            used_columns.append(f"{table}.{col.name}")
            ref = f"{alias}.{col.name}"
            label = column_label(col.name)
            if multi and alias != "t0":
                label = f"{label} ({table_label(table)})"
            if agg:
                if agg not in AGGREGATES:
                    raise _refuse(f"Agrégat inconnu : {agg}.")
                if agg in {"sum", "avg"} and col.kind != "number":
                    raise _refuse(f"{AGG_LABELS[agg]} impossible sur une colonne non numérique ({col.name}).")
                expr = f"count(DISTINCT {ref})" if agg == "count_distinct" else f"{agg}({ref})"
                label = f"{AGG_LABELS[agg]} — {label}"
            else:
                expr = ref
                group.append(ref)
        if agg:
            if not has_agg:
                first_agg_pos = len(select) + 1
            has_agg = True
        base_label, k = label, 2
        while label in labels_seen:
            label, k = f"{base_label} {k}", k + 1
        labels_seen.add(label)
        select.append(f'{expr} AS "{label.replace(chr(34), "")}"')
    if not select:
        raise _refuse("Sélectionnez au moins une colonne.")

    where: list[str] = []
    filters_desc: list[str] = []
    for f in (spec.get("filters") or [])[:MAX_FILTERS]:
        alias, name, op = str(f.get("alias") or "t0"), str(f.get("column") or ""), str(f.get("operator") or "")
        if op not in OPERATORS:
            raise _refuse(f"Opérateur inconnu : {op}.")
        table, col = column(alias, name)
        ref = f"{alias}.{col.name}"
        value, value2 = f.get("value"), f.get("value2")
        desc = f"{column_label(col.name)} {OPERATORS[op]}"
        if op in ("is_empty", "is_not_empty"):
            if col.kind in ("text", "other"):
                cond = f"({ref} IS NULL OR {ref} = '')" if op == "is_empty" else f"({ref} IS NOT NULL AND {ref} <> '')"
            else:
                cond = f"{ref} IS NULL" if op == "is_empty" else f"{ref} IS NOT NULL"
        elif op in ("contains", "starts_with"):
            text = str(value or "").strip()
            if not text:
                raise _refuse(f"Valeur manquante pour le filtre sur « {col.name} ».")
            pattern = ("%" if op == "contains" else "") + _like_escape(text) + "%"
            cond = f"{ref}::text ILIKE {lit(pattern)}"
            desc += f" « {text} »"
        elif op == "between":
            low = _typed_literal(col.kind, value, column=col.name)
            high_value = value2
            if col.kind == "datetime" and _is_date_only(value2):
                try:
                    high_value = (date.fromisoformat(str(value2)) + timedelta(days=1)).isoformat()
                except ValueError:
                    raise _refuse(f"Date invalide pour « {col.name} ».") from None
                high = _typed_literal(col.kind, high_value, column=col.name)
                cond = f"{ref} >= {low} AND {ref} < {high}"
            else:
                high = _typed_literal(col.kind, high_value, column=col.name)
                cond = f"{ref} BETWEEN {low} AND {high}"
            desc += f" {value} et {value2}"
        else:
            if col.kind == "datetime" and op == "eq" and _is_date_only(value):
                day = _typed_literal("datetime", value, column=col.name)
                nxt = _typed_literal(
                    "datetime", (date.fromisoformat(str(value)) + timedelta(days=1)).isoformat(), column=col.name
                )
                cond = f"{ref} >= {day} AND {ref} < {nxt}"
            else:
                literal = _typed_literal(col.kind if col.kind != "enum" else "text", value, column=col.name)
                cond = f"{ref} {OPERATORS[op]} {literal}"
            desc += f" {value}"
        where.append(cond)
        filters_desc.append(f"{table_label(table)} — {desc}")
        if f"{table}.{col.name}" not in used_columns:
            used_columns.append(f"{table}.{col.name}")

    order: list[str] = []
    for o in (spec.get("order_by") or [])[:5]:
        alias, name = str(o.get("alias") or "t0"), str(o.get("column") or "")
        _table, col = column(alias, name)
        direction = "DESC" if str(o.get("direction") or "").lower() == "desc" else "ASC"
        ref = f"{alias}.{col.name}"
        if has_agg and ref not in group:
            continue
        order.append(f"{ref} {direction}")
    if not order and has_agg and group:
        order.append(f"{first_agg_pos} DESC")

    limit = spec.get("limit")
    try:
        limit = int(limit) if limit not in (None, "") else None
    except (TypeError, ValueError):
        limit = None
    if limit is not None:
        limit = max(1, min(limit, 5000))

    lines = [
        "SELECT DISTINCT" if spec.get("distinct") and not has_agg else "SELECT",
        ",\n".join(f"  {s}" for s in select),
        f"FROM {base_table.name} t0",
        *joins_sql,
    ]
    if where:
        lines.append("WHERE " + "\n  AND ".join(where))
    if has_agg and group:
        lines.append("GROUP BY " + ", ".join(group))
    if order:
        lines.append("ORDER BY " + ", ".join(order))
    if limit:
        lines.append(f"LIMIT {limit}")

    return {
        "sql": "\n".join(lines),
        "tables": list(dict.fromkeys(aliases.values())),
        "columns": used_columns,
        "relations": relations,
        "filters": filters_desc,
        "group_by": group if has_agg else [],
        "order_by": ", ".join(order) or None,
        "limit": limit,
    }
