"""Validateur SQL CORE QUERY — lecture seule stricte.

Analyse lexicale PostgreSQL (chaînes, identifiants quotés, commentaires) puis
contrôles : une seule requête SELECT/WITH, aucun mot-clé d'écriture / DDL /
session, fonctions sur liste blanche, tables du catalogue public uniquement,
colonnes secrètes refusées, colonnes qualifiées vérifiées contre le schéma.

Seconde barrière à l'exécution : transaction READ ONLY + rôle PostgreSQL
restreint (voir ``executor.py``).

``check_admin_sql`` (mode administrateur) ne bloque que l'accès au serveur
PostgreSQL (fichiers, configuration, bases) et le contrôle de transaction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services.core_query.schema import Catalog

MAX_SQL_LENGTH = 20_000


class QueryRefused(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Tok:
    kind: str  # ident | qident | string | number | op | punct
    value: str
    pos: int

    @property
    def upper(self) -> str:
        return self.value.upper() if self.kind == "ident" else ""

    @property
    def name(self) -> str:
        """Nom d'objet normalisé (identifiant non quoté → minuscules)."""
        return self.value.lower() if self.kind == "ident" else self.value


@dataclass
class ValidatedQuery:
    sql: str
    tables: list[str]
    ctes: list[str] = field(default_factory=list)


FORBIDDEN_KEYWORDS: frozenset[str] = frozenset(
    {
        "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "CREATE", "GRANT", "REVOKE",
        "COPY", "MERGE", "CALL", "DO", "EXECUTE", "PREPARE", "DEALLOCATE", "LISTEN", "NOTIFY",
        "UNLISTEN", "VACUUM", "CLUSTER", "REINDEX", "REFRESH", "LOCK", "SET", "RESET", "SHOW",
        "DISCARD", "LOAD", "IMPORT", "BEGIN", "COMMIT", "ROLLBACK", "SAVEPOINT", "RELEASE",
        "INTO", "CHECKPOINT", "SECURITY", "OWNER", "RETURNING",
    }
)

ALLOWED_FUNCTIONS: frozenset[str] = frozenset(
    {
        # agrégats
        "count", "sum", "avg", "min", "max", "string_agg", "array_agg", "bool_and", "bool_or",
        "every", "stddev", "stddev_pop", "stddev_samp", "variance", "var_pop", "var_samp",
        "percentile_cont", "percentile_disc", "mode", "json_agg", "jsonb_agg",
        "json_object_agg", "jsonb_object_agg",
        # fenêtrage
        "row_number", "rank", "dense_rank", "ntile", "lag", "lead", "first_value", "last_value",
        "nth_value", "percent_rank", "cume_dist",
        # conditionnels / texte
        "coalesce", "nullif", "greatest", "least", "lower", "upper", "initcap", "trim", "btrim",
        "ltrim", "rtrim", "length", "char_length", "character_length", "octet_length",
        "substring", "substr", "left", "right", "replace", "concat", "concat_ws", "position",
        "strpos", "split_part", "lpad", "rpad", "reverse", "translate", "format", "unaccent",
        "regexp_replace", "regexp_match", "regexp_matches", "starts_with",
        # dates
        "to_char", "to_date", "to_timestamp", "to_number", "date_trunc", "date_part", "extract",
        "age", "now", "justify_interval", "justify_hours", "justify_days", "make_date",
        "make_interval", "make_timestamp", "make_timestamptz", "timezone", "isfinite",
        "date_bin",
        # numériques
        "abs", "round", "ceil", "ceiling", "floor", "trunc", "mod", "power", "sqrt", "sign",
        "div", "width_bucket",
        # tableaux / json
        "generate_series", "unnest", "array_length", "cardinality", "array_to_string",
        "array_position", "jsonb_array_length", "json_array_length", "jsonb_typeof",
        "json_typeof", "jsonb_extract_path_text", "json_extract_path_text", "jsonb_build_object",
        "json_build_object", "to_jsonb", "to_json", "jsonb_array_elements",
        "jsonb_array_elements_text", "jsonb_object_keys", "jsonb_pretty",
        # types utilisés en écriture fonctionnelle
        "numeric", "decimal", "varchar", "char", "character", "float", "time", "timestamp",
        "timestamptz", "interval", "date", "text", "int", "integer", "bigint",
    }
)

# Mots-clés suivis d'une parenthèse qui ne sont pas des appels de fonction.
PAREN_KEYWORDS: frozenset[str] = frozenset(
    {
        "IN", "EXISTS", "ANY", "ALL", "SOME", "ARRAY", "VALUES", "OVER", "FILTER", "AS", "ON",
        "USING", "FROM", "JOIN", "SELECT", "WHERE", "AND", "OR", "NOT", "CASE", "WHEN", "THEN",
        "ELSE", "BETWEEN", "LIKE", "ILIKE", "IS", "LATERAL", "CAST", "ROW", "WITHIN", "GROUP",
        "BY", "HAVING", "UNION", "INTERSECT", "EXCEPT", "WITH", "RECURSIVE", "MATERIALIZED",
        "DISTINCT", "PARTITION", "ORDER", "LIMIT", "OFFSET", "SIMILAR", "TO", "END",
    }
)

# Fonctions SQL standard dont la syntaxe interne contient FROM.
FROM_FUNCTIONS: frozenset[str] = frozenset({"EXTRACT", "SUBSTRING", "TRIM", "POSITION", "OVERLAY"})

CLAUSE_END: frozenset[str] = frozenset(
    {"WHERE", "GROUP", "HAVING", "ORDER", "LIMIT", "OFFSET", "WINDOW", "UNION", "INTERSECT",
     "EXCEPT", "FETCH", "SELECT"}
)

# Mots ne pouvant pas être un alias de table.
NOT_ALIAS: frozenset[str] = CLAUSE_END | frozenset(
    {"ON", "USING", "JOIN", "INNER", "LEFT", "RIGHT", "FULL", "CROSS", "NATURAL", "OUTER",
     "LATERAL", "AS", "TABLESAMPLE"}
)

_OP_CHARS = set("+-*/<>=~!@#%^&|?:")


def tokenize(sql: str) -> list[Tok]:
    toks: list[Tok] = []
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        if ch.isspace():
            i += 1
            continue
        if sql.startswith("--", i):
            j = sql.find("\n", i)
            i = n if j < 0 else j + 1
            continue
        if sql.startswith("/*", i):
            depth, j = 1, i + 2
            while j < n and depth:
                if sql.startswith("/*", j):
                    depth, j = depth + 1, j + 2
                elif sql.startswith("*/", j):
                    depth, j = depth - 1, j + 2
                else:
                    j += 1
            if depth:
                raise QueryRefused("SYNTAX", "Commentaire non terminé.")
            i = j
            continue
        if ch == "'" or (ch in "eE" and i + 1 < n and sql[i + 1] == "'"):
            escape = ch in "eE"
            j = i + (2 if escape else 1)
            buf: list[str] = []
            while True:
                if j >= n:
                    raise QueryRefused("SYNTAX", "Chaîne de caractères non terminée.")
                c = sql[j]
                if escape and c == "\\" and j + 1 < n:
                    buf.append(sql[j + 1])
                    j += 2
                    continue
                if c == "'":
                    if j + 1 < n and sql[j + 1] == "'":
                        buf.append("'")
                        j += 2
                        continue
                    j += 1
                    break
                buf.append(c)
                j += 1
            toks.append(Tok("string", "".join(buf), i))
            i = j
            continue
        if ch == '"':
            j = i + 1
            buf = []
            while True:
                if j >= n:
                    raise QueryRefused("SYNTAX", "Identifiant entre guillemets non terminé.")
                if sql[j] == '"':
                    if j + 1 < n and sql[j + 1] == '"':
                        buf.append('"')
                        j += 2
                        continue
                    j += 1
                    break
                buf.append(sql[j])
                j += 1
            toks.append(Tok("qident", "".join(buf), i))
            i = j
            continue
        if ch == "$":
            raise QueryRefused(
                "DOLLAR_QUOTE",
                "Les paramètres $n et chaînes $$…$$ ne sont pas autorisés.",
            )
        if ch == "\\":
            raise QueryRefused("SYNTAX", "Les commandes « \\ » ne sont pas autorisées.")
        if ch in "uU" and sql.startswith("&", i + 1):
            raise QueryRefused("SYNTAX", "Les chaînes Unicode U& ne sont pas autorisées.")
        if ch.isdigit() or (ch == "." and i + 1 < n and sql[i + 1].isdigit()):
            j = i
            while j < n and (sql[j].isdigit() or sql[j] == "."):
                j += 1
            if j < n and sql[j] in "eE" and j + 1 < n and (sql[j + 1].isdigit() or sql[j + 1] in "+-"):
                j += 2
                while j < n and sql[j].isdigit():
                    j += 1
            toks.append(Tok("number", sql[i:j], i))
            i = j
            continue
        if ch.isalpha() or ch == "_" or ord(ch) > 127:
            j = i + 1
            while j < n and (sql[j].isalnum() or sql[j] in "_" or ord(sql[j]) > 127):
                j += 1
            toks.append(Tok("ident", sql[i:j], i))
            i = j
            continue
        if ch in "(),;.[]":
            toks.append(Tok("punct", ch, i))
            i += 1
            continue
        if ch in _OP_CHARS:
            j = i
            while j < n and sql[j] in _OP_CHARS:
                if sql.startswith("--", j) or sql.startswith("/*", j):
                    break
                j += 1
            toks.append(Tok("op", sql[i:j], i))
            i = j
            continue
        raise QueryRefused("SYNTAX", f"Caractère non autorisé : « {ch} ».")
    return toks


def _is(t: Tok | None, *values: str) -> bool:
    if t is None:
        return False
    if t.kind == "ident":
        return t.upper in values
    return t.kind in ("punct", "op") and t.value in values


def validate_sql(sql: str, catalog: Catalog) -> ValidatedQuery:
    raw = (sql or "").strip()
    if not raw:
        raise QueryRefused("EMPTY", "La requête est vide.")
    if len(raw) > MAX_SQL_LENGTH:
        raise QueryRefused("TOO_LONG", f"Requête trop longue (max {MAX_SQL_LENGTH} caractères).")

    toks = tokenize(raw)
    while toks and _is(toks[-1], ";"):
        raw = raw[: toks[-1].pos].rstrip()
        toks.pop()
    if not toks:
        raise QueryRefused("EMPTY", "La requête est vide.")
    if any(_is(t, ";") for t in toks):
        raise QueryRefused("MULTI_STATEMENT", "Une seule requête est autorisée (pas de « ; » intermédiaire).")

    first = next((t for t in toks if not _is(t, "(")), None)
    if not (_is(first, "SELECT") or _is(first, "WITH")):
        raise QueryRefused("NOT_SELECT", "Seules les requêtes de lecture (SELECT / WITH) sont autorisées.")

    sensitive = catalog.sensitive_names
    for idx, t in enumerate(toks):
        if t.kind == "ident" and t.upper in FORBIDDEN_KEYWORDS:
            raise QueryRefused(
                "FORBIDDEN_KEYWORD",
                f"Instruction interdite : {t.upper}. CORE QUERY est en lecture seule.",
            )
        if _is(t, "FOR"):
            nxt = toks[idx + 1] if idx + 1 < len(toks) else None
            if _is(nxt, "SHARE", "NO", "KEY", "UPDATE"):
                raise QueryRefused("LOCKING", "Les verrous (FOR SHARE / FOR UPDATE) ne sont pas autorisés.")
        if t.kind in ("ident", "qident") and t.value.lower() in sensitive:
            raise QueryRefused(
                "SENSITIVE_COLUMN",
                f"La colonne « {t.value} » est protégée (secret) et ne peut pas être lue.",
            )

    relations: list[tuple[str, int]] = []
    aliases: dict[str, set[str]] = {}
    decl_positions: set[int] = set()
    ctes: set[str] = set()
    paren_kinds: list[str] = []
    from_depths: set[int] = set()
    with_state: dict[int, str] = {}
    expect_relation = False
    star_select = False

    def prev(k: int, back: int = 1) -> Tok | None:
        j = k - back
        return toks[j] if j >= 0 else None

    for idx, t in enumerate(toks):
        depth = len(paren_kinds)
        nxt = toks[idx + 1] if idx + 1 < len(toks) else None

        if _is(t, "("):
            p = prev(idx)
            if p is not None and p.kind == "ident" and p.upper in FROM_FUNCTIONS:
                kind = "fromfunc"
            elif p is not None and p.kind in ("ident", "qident") and p.upper not in PAREN_KEYWORDS:
                kind = "func"
            else:
                kind = "group"
            paren_kinds.append(kind)
            if expect_relation:
                expect_relation = False
            continue
        if _is(t, ")"):
            from_depths.discard(depth)
            with_state.pop(depth, None)
            if paren_kinds:
                paren_kinds.pop()
            continue

        if t.kind in ("ident", "qident") and nxt is not None and _is(nxt, "("):
            p = prev(idx)
            is_cast_type = _is(p, "::") or _is(p, "AS")
            is_cte_cols = with_state.get(depth) == "name"
            if not is_cast_type and not is_cte_cols and t.upper not in PAREN_KEYWORDS:
                if _is(p, "."):
                    raise QueryRefused(
                        "FORBIDDEN_FUNCTION",
                        "Les appels de fonctions qualifiés (schema.fonction) ne sont pas autorisés.",
                    )
                if t.name not in ALLOWED_FUNCTIONS:
                    raise QueryRefused(
                        "FORBIDDEN_FUNCTION",
                        f"Fonction non autorisée : {t.value}().",
                    )

        if _is(t, "WITH"):
            with_state[depth] = "name"
            continue
        if with_state.get(depth) == "name" and t.kind in ("ident", "qident"):
            if _is(t, "RECURSIVE"):
                continue
            ctes.add(t.name)
            with_state[depth] = "after"
            continue
        if _is(t, ",") and with_state.get(depth) == "after":
            with_state[depth] = "name"
            continue
        if _is(t, "SELECT"):
            with_state.pop(depth, None)
            from_depths.discard(depth)
            nxt2 = nxt
            if _is(nxt2, "DISTINCT", "ALL"):
                nxt2 = toks[idx + 2] if idx + 2 < len(toks) else None
            if _is(nxt2, "*"):
                star_select = True
            continue

        if _is(t, "*"):
            p = prev(idx)
            if _is(p, ",", ".") and (nxt is None or _is(nxt, ",", "FROM", ")")):
                star_select = True

        if _is(t, "FROM"):
            in_from_func = bool(paren_kinds) and paren_kinds[-1] == "fromfunc"
            p, p2 = prev(idx), prev(idx, 2)
            is_distinct_from = _is(p, "DISTINCT") and (_is(p2, "IS") or _is(p2, "NOT"))
            if not in_from_func and not is_distinct_from:
                expect_relation = True
                from_depths.add(depth)
            continue
        if _is(t, "JOIN"):
            expect_relation = True
            from_depths.add(depth)
            continue
        if _is(t, ",") and depth in from_depths:
            expect_relation = True
            continue
        if t.kind == "ident" and t.upper in CLAUSE_END:
            from_depths.discard(depth)
            expect_relation = False
            continue

        if expect_relation and t.kind in ("ident", "qident"):
            if _is(t, "LATERAL", "ONLY"):
                continue
            expect_relation = False
            name = t.name
            schema: str | None = None
            k = idx
            if nxt is not None and _is(nxt, ".") and idx + 2 < len(toks):
                schema, name = name, toks[idx + 2].name
                k = idx + 2
            after = toks[k + 1] if k + 1 < len(toks) else None
            if _is(after, "("):
                continue  # fonction table (generate_series…) contrôlée plus haut
            if schema is not None and schema.lower() != "public":
                raise QueryRefused(
                    "FORBIDDEN_TABLE",
                    f"Schéma non autorisé : {schema}. Seul le schéma public est interrogeable.",
                )
            relations.append((name, t.pos))
            decl_positions.update(range(idx, k + 1))
            alias_idx = k + 1
            alias_tok = after
            if _is(alias_tok, "AS"):
                alias_idx = k + 2
                alias_tok = toks[alias_idx] if alias_idx < len(toks) else None
            if (
                alias_tok is not None
                and alias_tok.kind in ("ident", "qident")
                and alias_tok.upper not in NOT_ALIAS
                and alias_tok.upper not in PAREN_KEYWORDS
            ):
                aliases.setdefault(alias_tok.name, set()).add(name)
                decl_positions.add(alias_idx)
            aliases.setdefault(name, set()).add(name)

    tables: set[str] = set()
    for name, _pos in relations:
        if name in ctes:
            continue
        if name in catalog.denied_tables:
            raise QueryRefused("FORBIDDEN_TABLE", f"La table « {name} » contient des secrets et n'est pas interrogeable.")
        if catalog.table(name) is None:
            raise QueryRefused("UNKNOWN_TABLE", f"Table inconnue ou non autorisée : « {name} ».")
        tables.add(name)

    def alias_tables(name: str) -> list[str]:
        return [x for x in aliases.get(name, set()) if x in tables and x not in ctes]

    for idx in range(len(toks) - 2):
        a, dot, b = toks[idx], toks[idx + 1], toks[idx + 2]
        if a.kind not in ("ident", "qident") or not _is(dot, ".") or b.kind not in ("ident", "qident"):
            continue
        if idx + 3 < len(toks) and _is(toks[idx + 3], "("):
            continue
        targets = alias_tables(a.name)
        if not targets:
            continue
        if not any(b.name in catalog.tables[x].columns for x in targets):
            raise QueryRefused(
                "UNKNOWN_COLUMN",
                f"Colonne inconnue : « {a.value}.{b.value} » (table {', '.join(sorted(targets))}).",
            )

    for idx, t in enumerate(toks):
        if idx in decl_positions or t.kind not in ("ident", "qident"):
            continue
        nxt = toks[idx + 1] if idx + 1 < len(toks) else None
        p = toks[idx - 1] if idx else None
        if _is(nxt, ".") or _is(p, ".") or _is(p, "AS"):
            continue
        protected = [x for x in alias_tables(t.name) if catalog.tables[x].hidden_columns]
        if protected:
            raise QueryRefused(
                "SENSITIVE_COLUMN",
                f"Référence à la ligne entière « {t.value} » interdite (table {protected[0]} "
                "contenant des secrets) : listez les colonnes souhaitées.",
            )

    if star_select:
        protected = sorted(t for t in tables if catalog.tables[t].hidden_columns)
        if protected:
            raise QueryRefused(
                "SENSITIVE_COLUMN",
                "SELECT * interdit sur une table contenant des secrets ("
                + ", ".join(protected)
                + ") : listez les colonnes souhaitées.",
            )

    return ValidatedQuery(sql=raw, tables=sorted(tables), ctes=sorted(ctes))


# ---------------------------------------------------------------------------
# Mode administrateur : SQL libre (écriture, DDL), sauf accès au serveur.
# ---------------------------------------------------------------------------

ADMIN_MAX_SQL_LENGTH = 200_000

_ADMIN_STRIP = re.compile(
    r"--[^\n]*|/\*.*?\*/|\$([A-Za-z_]\w*|)\$.*?\$\1\$|'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"",
    re.S,
)
_ADMIN_BLOCKED: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"\bCOPY\b", re.I), "SERVER_ACCESS",
     "COPY lit / écrit des fichiers sur le serveur PostgreSQL : utilisez les exports CORE QUERY."),
    (re.compile(r"\bALTER\s+SYSTEM\b", re.I), "SERVER_ACCESS",
     "ALTER SYSTEM modifie la configuration du serveur PostgreSQL (hors périmètre de l'application)."),
    (re.compile(r"\b(CREATE|DROP|ALTER)\s+DATABASE\b", re.I), "SERVER_ACCESS",
     "La création / suppression de bases se fait hors application (DSI)."),
    (re.compile(r"\bLOAD\s+'", re.I), "SERVER_ACCESS", "LOAD charge une bibliothèque sur le serveur."),
    (re.compile(
        r"\b(pg_read_file|pg_read_binary_file|pg_ls_\w+|pg_stat_file|pg_file_\w+|lo_import|lo_export"
        r"|dblink\w*|pg_reload_conf|pg_rotate_logfile|pg_promote)\s*\(", re.I),
     "SERVER_ACCESS", "Fonction d'accès aux fichiers / au serveur PostgreSQL non autorisée."),
    (re.compile(r"(^|;)\s*(BEGIN|COMMIT|ROLLBACK|END|ABORT|START\s+TRANSACTION|SAVEPOINT|RELEASE|PREPARE\s+TRANSACTION)\b",
                re.I), "TRANSACTION",
     "Contrôle de transaction inutile : CORE QUERY exécute tout le script dans une transaction "
     "(Exécuter = COMMIT, Simuler = ROLLBACK)."),
]
_ADMIN_WRITE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|TRUNCATE|CREATE|ALTER|DROP|GRANT|REVOKE|COMMENT|CALL|DO|REINDEX|CLUSTER"
    r"|VACUUM|REFRESH|SECURITY|LOCK|SET|RESET|DISCARD|NOTIFY|SELECT\s+.*\bINTO)\b",
    re.I | re.S,
)


@dataclass
class AdminCheck:
    sql: str
    is_write: bool


def is_multi_statement(sql: str) -> bool:
    """Plusieurs instructions (``;`` hors chaînes, commentaires et blocs ``$$``)."""
    return ";" in _ADMIN_STRIP.sub(" ", sql or "").strip().rstrip(";")


def check_admin_sql(sql: str) -> AdminCheck:
    """Contrôle minimal du mode administrateur : protège le serveur, pas les données."""
    text = (sql or "").strip()
    if not text:
        raise QueryRefused("EMPTY", "Saisissez une requête.")
    if len(text) > ADMIN_MAX_SQL_LENGTH:
        raise QueryRefused("TOO_LONG", f"Script trop long (> {ADMIN_MAX_SQL_LENGTH} caractères).")
    bare = _ADMIN_STRIP.sub(" ", text)
    for pattern, code, message in _ADMIN_BLOCKED:
        if pattern.search(bare):
            raise QueryRefused(code, message)
    return AdminCheck(sql=text, is_write=bool(_ADMIN_WRITE.search(bare)))
