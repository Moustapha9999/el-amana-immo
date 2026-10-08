"""NL Parser CORE QUERY — compréhension de questions en français, sans LLM.

Moteur à règles déterministe : dates relatives, plages horaires, intentions
métier connues (connexions, sessions, audit, stock, archives, modules) puis
moteur générique piloté par le catalogue (entité, comptage, somme,
regroupement via clés étrangères). Toute colonne utilisée est vérifiée contre
le schéma réel : si elle n'existe pas, l'intention est ignorée — jamais
inventée. En cas de doute, une demande de précision est renvoyée.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

from app.services.core_query.labels import (
    DATE_COLUMNS,
    DISPLAY_COLUMNS,
    STATUS_COLUMNS,
    TABLE_LABELS,
    column_label,
    table_label,
)
from app.services.core_query.schema import Catalog

TZ = ZoneInfo("Africa/Nouakchott")

STOCK_PENDING_STATUTS = ("SOUMIS", "VISA_AGENCE", "VISA_MG", "PREPARATION")
MEASURE_COLUMNS = ("valeur_brute", "montant_ttc", "montant_total", "total_ttc", "montant", "prix_total", "valeur")

EXAMPLES = [
    "Quels utilisateurs se sont connectés hier entre 8h et 17h ?",
    "Quels utilisateurs sont actuellement actifs ?",
    "Quels utilisateurs ne se sont pas connectés depuis 30 jours ?",
    "Combien d'utilisateurs ?",
    "Immobilisations par agence",
    "Valeur totale des immobilisations",
    "Demandes de stock en attente",
    "Dernières opérations administratives",
    "Dernières connexions au module Stock & Fournitures",
    "Documents ajoutés aux archives ce mois-ci",
    "Modules les plus utilisés aujourd'hui",
]

_MONTHS = {
    "janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
    "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12,
}


def normalize(text: str) -> str:
    s = unicodedata.normalize("NFD", text or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    s = s.replace("’", " ").replace("'", " ").replace("-", " ")
    s = re.sub(r"[^a-z0-9/:\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _has(q: str, pattern: str) -> bool:
    return re.search(pattern, q) is not None


def lit(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def ts_lit(value: datetime) -> str:
    return lit(value.astimezone(TZ).isoformat(sep=" ", timespec="seconds")) + "::timestamptz"


def fr_date(d: datetime) -> str:
    return d.astimezone(TZ).strftime("%d/%m/%Y")


# --------------------------------------------------------------------------- période


@dataclass
class Period:
    label: str
    start: datetime | None = None
    end: datetime | None = None
    hour_from: dtime | None = None
    hour_to: dtime | None = None
    days: int | None = None

    @property
    def single_day(self) -> bool:
        return bool(self.start and self.end and self.end - self.start <= timedelta(days=1))

    def date_label(self) -> str | None:
        if not self.start:
            return None
        if self.single_day:
            return fr_date(self.start)
        end = (self.end - timedelta(seconds=1)) if self.end else None
        return f"du {fr_date(self.start)} au {fr_date(end)}" if end else f"depuis le {fr_date(self.start)}"

    def hours_label(self) -> str | None:
        if self.hour_from is None and self.hour_to is None:
            return None
        a = self.hour_from.strftime("%H:%M") if self.hour_from else "00:00"
        b = self.hour_to.strftime("%H:%M") if self.hour_to else "23:59"
        return f"{a} – {b}"


def _day(now: datetime, delta_days: int = 0) -> datetime:
    d = now.astimezone(TZ) + timedelta(days=delta_days)
    return d.replace(hour=0, minute=0, second=0, microsecond=0)


def _hour(h: str, m: str | None) -> dtime:
    hh = min(int(h), 23)
    mm = min(int(m), 59) if m else 0
    return dtime(hh, mm)


def parse_period(q: str, now: datetime) -> Period | None:
    period: Period | None = None
    today = _day(now)

    m_range = re.search(r"(?:entre le|du) (\d{1,2})/(\d{1,2})/(\d{4}) (?:et le|et|au) (\d{1,2})/(\d{1,2})/(\d{4})", q)
    m_date = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", q)
    m_named = re.search(r"\b(\d{1,2}) (" + "|".join(_MONTHS) + r")(?: (\d{4}))?\b", q)
    m_days = re.search(r"\b(\d{1,3}) (?:derniers? )?jours?\b", q)
    m_last_hours = re.search(r"\b(\d{1,2}) (?:dernieres? )?heures?\b", q)

    try:
        if m_range:
            d1 = datetime(int(m_range[3]), int(m_range[2]), int(m_range[1]), tzinfo=TZ)
            d2 = datetime(int(m_range[6]), int(m_range[5]), int(m_range[4]), tzinfo=TZ)
            period = Period("Période choisie", d1, d2 + timedelta(days=1))
        elif _has(q, r"\bavant hier\b"):
            period = Period("Avant-hier", _day(now, -2), _day(now, -1))
        elif _has(q, r"\bhier\b"):
            period = Period("Hier", _day(now, -1), today)
        elif _has(q, r"\baujourd ?hui\b|\bce jour\b|\bdu jour\b|\bce matin\b"):
            period = Period("Aujourd'hui", today, today + timedelta(days=1))
        elif _has(q, r"\bsemaine (derniere|passee|precedente)\b"):
            monday = today - timedelta(days=today.weekday())
            period = Period("Semaine dernière", monday - timedelta(days=7), monday)
        elif _has(q, r"\bcette semaine\b|\bsemaine en cours\b"):
            monday = today - timedelta(days=today.weekday())
            period = Period("Cette semaine", monday, today + timedelta(days=1))
        elif _has(q, r"\bmois (dernier|passe|precedent)\b"):
            first = today.replace(day=1)
            prev_first = (first - timedelta(days=1)).replace(day=1)
            period = Period("Mois dernier", prev_first, first)
        elif _has(q, r"\bce mois( ci)?\b|\bmois en cours\b|\bdu mois\b"):
            period = Period("Ce mois-ci", today.replace(day=1), today + timedelta(days=1))
        elif _has(q, r"\bannee (derniere|passee|precedente)\b"):
            first = today.replace(month=1, day=1)
            period = Period("Année dernière", first.replace(year=first.year - 1), first)
        elif _has(q, r"\bcette annee\b|\bannee en cours\b"):
            period = Period("Cette année", today.replace(month=1, day=1), today + timedelta(days=1))
        elif m_date:
            d = datetime(int(m_date[3]), int(m_date[2]), int(m_date[1]), tzinfo=TZ)
            period = Period(f"Le {fr_date(d)}", d, d + timedelta(days=1))
        elif m_named:
            year = int(m_named[3]) if m_named[3] else today.year
            d = datetime(year, _MONTHS[m_named[2]], int(m_named[1]), tzinfo=TZ)
            period = Period(f"Le {fr_date(d)}", d, d + timedelta(days=1))
        elif m_days:
            n = int(m_days[1])
            period = Period(f"{n} derniers jours", now - timedelta(days=n), None, days=n)
        elif m_last_hours and not _has(q, r"plus de \d"):
            n = int(m_last_hours[1])
            period = Period(f"{n} dernières heures", now - timedelta(hours=n), None)
        elif _has(q, r"\bderniere heure\b"):
            period = Period("Dernière heure", now - timedelta(hours=1), None)
        else:
            m_year = re.search(r"\ben (20\d{2})\b", q)
            if m_year:
                y = int(m_year[1])
                period = Period(f"Année {y}", datetime(y, 1, 1, tzinfo=TZ), datetime(y + 1, 1, 1, tzinfo=TZ))
    except ValueError:
        period = None

    h = re.search(r"(?:entre|de) (\d{1,2}) ?h ?(\d{2})? (?:et|a) (\d{1,2}) ?h ?(\d{2})?", q)
    h_after = re.search(r"\bapres (\d{1,2}) ?h ?(\d{2})?", q)
    h_before = re.search(r"\bavant (\d{1,2}) ?h ?(\d{2})?", q)
    hour_from = hour_to = None
    if h:
        hour_from, hour_to = _hour(h[1], h[2]), _hour(h[3], h[4])
    else:
        if h_after:
            hour_from = _hour(h_after[1], h_after[2])
        if h_before:
            hour_to = _hour(h_before[1], h_before[2])
    if hour_from or hour_to:
        if period is None:
            period = Period("Aujourd'hui", today, today + timedelta(days=1))
        period.hour_from, period.hour_to = hour_from, hour_to
    return period


# --------------------------------------------------------------------------- résultat


@dataclass
class Interpretation:
    ok: bool
    intent: str
    title: str
    sql: str | None = None
    tables: list[str] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    filters: list[str] = field(default_factory=list)
    relations: list[str] = field(default_factory=list)
    group_by: list[str] = field(default_factory=list)
    order_by: str | None = None
    limit: int | None = None
    period: dict | None = None
    assumptions: list[str] = field(default_factory=list)
    clarification: str | None = None
    suggestions: list[str] = field(default_factory=list)
    confidence: str = "haute"

    def to_dict(self) -> dict:
        return asdict(self)


class _Sql:
    """Assemblage lisible d'un SELECT + traçabilité (tables, colonnes, relations)."""

    def __init__(self, cat: Catalog, table: str, alias: str) -> None:
        self.cat = cat
        self.from_ = f"{table} {alias}"
        self.select: list[str] = []
        self.joins: list[str] = []
        self.where: list[str] = []
        self.group: list[str] = []
        self.order: list[str] = []
        self.limit: int | None = None
        self.tables: list[str] = [table]
        self.columns: list[str] = []
        self.relations: list[str] = []
        self.filters: list[str] = []
        self.aliases: dict[str, str] = {alias: table}

    def col(self, alias: str, column: str) -> str:
        table = self.aliases[alias]
        if not self.cat.has(table, column):
            raise _MissingColumn(f"{table}.{column}")
        ref = f"{table}.{column}"
        if ref not in self.columns:
            self.columns.append(ref)
        return f"{alias}.{column}"

    def join(self, kind: str, table: str, alias: str, on: str, relation: str) -> None:
        if self.cat.table(table) is None:
            raise _MissingColumn(table)
        self.aliases[alias] = table
        self.joins.append(f"{kind} JOIN {table} {alias} ON {on}")
        if table not in self.tables:
            self.tables.append(table)
        self.relations.append(relation)

    def add(self, expr: str, label: str) -> None:
        self.select.append(f'{expr} AS "{label}"')

    def render(self) -> str:
        lines = ["SELECT", ",\n".join(f"  {s}" for s in self.select), f"FROM {self.from_}"]
        lines += self.joins
        if self.where:
            lines.append("WHERE " + "\n  AND ".join(self.where))
        if self.group:
            lines.append("GROUP BY " + ", ".join(self.group))
        if self.order:
            lines.append("ORDER BY " + ", ".join(self.order))
        if self.limit:
            lines.append(f"LIMIT {self.limit}")
        return "\n".join(lines)

    def result(self, intent: str, title: str, *, period: Period | None, assumptions: list[str],
               confidence: str = "haute") -> Interpretation:
        return Interpretation(
            ok=True,
            intent=intent,
            title=title,
            sql=self.render(),
            tables=list(self.tables),
            columns=list(self.columns),
            filters=list(self.filters),
            relations=list(self.relations),
            group_by=list(self.group),
            order_by=", ".join(self.order) or None,
            limit=self.limit,
            period=_period_dict(period),
            assumptions=assumptions,
            confidence=confidence,
        )


class _MissingColumn(Exception):
    pass


def _period_dict(p: Period | None) -> dict | None:
    if p is None:
        return None
    return {
        "label": p.label,
        "date": p.date_label(),
        "hours": p.hours_label(),
        "start": p.start.isoformat() if p.start else None,
        "end": p.end.isoformat() if p.end else None,
    }


def _apply_period(s: _Sql, alias: str, column: str, p: Period | None, what: str) -> None:
    if p is None:
        return
    ref = s.col(alias, column)
    start, end = p.start, p.end
    if p.single_day and start is not None:
        if p.hour_from:
            start = start.replace(hour=p.hour_from.hour, minute=p.hour_from.minute)
        if p.hour_to:
            end = start.replace(hour=p.hour_to.hour, minute=p.hour_to.minute)
    if start is not None:
        s.where.append(f"{ref} >= {ts_lit(start)}")
    if end is not None:
        s.where.append(f"{ref} < {ts_lit(end)}")
    if not p.single_day and (p.hour_from or p.hour_to):
        local = f"({ref} AT TIME ZONE 'Africa/Nouakchott')::time"
        if p.hour_from:
            s.where.append(f"{local} >= {lit(p.hour_from.strftime('%H:%M'))}")
        if p.hour_to:
            s.where.append(f"{local} < {lit(p.hour_to.strftime('%H:%M'))}")
    desc = f"{what} : {p.label.lower()}"
    if p.date_label():
        desc += f" ({p.date_label()})"
    if p.hours_label():
        desc += f", entre {p.hours_label().replace(' – ', ' et ')}"
    s.filters.append(desc)


def _top_n(q: str, default: int | None = None) -> int | None:
    m = re.search(r"\b(?:les|top|des) (\d{1,4}) (?:derni|premi|plus|prem)", q) or re.search(r"\btop (\d{1,4})\b", q)
    if m:
        return max(1, min(int(m[1]), 1000))
    return default


def _wants_count(q: str) -> bool:
    return _has(q, r"\bcombien\b|\bnombre (de|d)\b|\bcompter\b|\bnombre total\b|\btotal (des|de|d) ")


def _wants_latest(q: str) -> bool:
    return _has(q, r"\bderni(er|ers|ere|eres)\b|\brecent(e|es|s)?\b|\bplus recent")


def _match_module(q: str, modules: dict[str, str]) -> tuple[list[tuple[str, str]], bool]:
    """Modules cités dans la question → (candidats, mention explicite du mot « module »)."""
    explicit = _has(q, r"\bmodules?\b")
    best: list[tuple[int, str, str]] = []
    for code, label in modules.items():
        nl = normalize(label)
        nc = code.replace("-", " ")
        score = 0
        for needle in {nl, nc}:
            if not needle:
                continue
            generic = len(needle.split()) == 1 and needle in {"demandes", "archives", "formation", "documents"}
            pattern = rf"\b{re.escape(needle)}\b"
            if generic:
                pattern = rf"\bmodules? {re.escape(needle)}\b"
            if re.search(pattern, q):
                score = max(score, len(needle))
        if score:
            best.append((score, code, label))
    if not best:
        return [], explicit
    top = max(b[0] for b in best)
    return [(c, lbl) for sc, c, lbl in best if sc == top], explicit


def _session_space_expr(s: _Sql) -> str:
    s.join(
        "LEFT", "plateforme_modules", "m", "m.code = s.module_code",
        "auth_sessions.module_code → plateforme_modules.code",
    )
    return "CASE WHEN s.kind = 'platform' THEN 'BEA DIGITAL (Login 1)' ELSE COALESCE(m.label, s.module_code) END"


# --------------------------------------------------------------------------- intentions


def _intent_modules_usage(q: str, cat: Catalog, p: Period | None) -> Interpretation:
    s = _Sql(cat, "auth_sessions", "s")
    s.join("LEFT", "plateforme_modules", "m", "m.code = s.module_code",
           "auth_sessions.module_code → plateforme_modules.code")
    s.join("LEFT", "plateforme_espaces", "e", "e.id = m.espace_id",
           "plateforme_modules.espace_id → plateforme_espaces.id")
    s.col("s", "module_code")
    s.col("s", "user_id")
    s.col("m", "label")
    s.col("e", "label")
    s.add("COALESCE(m.label, s.module_code)", "Module")
    s.add("e.label", "Département")
    s.add("count(*)", "Connexions")
    s.add("count(DISTINCT s.user_id)", "Utilisateurs distincts")
    s.where.append(f"{s.col('s', 'kind')} = 'module'")
    s.filters.append("Sessions de type module (Login 2)")
    _apply_period(s, "s", "created_at", p, "Connexion")
    s.group = ["COALESCE(m.label, s.module_code)", "e.label"]
    s.order = ['"Connexions" DESC']
    s.limit = _top_n(q)
    return s.result(
        "modules_usage", "Modules les plus utilisés", period=p,
        assumptions=["Utilisation = nombre de connexions (sessions Login 2) par module."],
    )


def _intent_active_sessions(q: str, cat: Catalog, p: Period | None, module: tuple[str, str] | None) -> Interpretation:
    s = _Sql(cat, "auth_sessions", "s")
    s.join("INNER", "users", "u", "u.id = s.user_id", "auth_sessions.user_id → users.id")
    space = _session_space_expr(s)
    s.where.append(f"{s.col('s', 'revoked_at')} IS NULL")
    s.where.append(f"{s.col('s', 'expires_at')} > now()")
    s.filters.append("Session non révoquée et non expirée")
    if module:
        s.where.append(f"{s.col('s', 'module_code')} = {lit(module[0])}")
        s.filters.append(f"Module : {module[1]}")
    if _wants_count(q):
        s.add(f"count(DISTINCT {s.col('s', 'user_id')})", "Utilisateurs actifs")
        s.add("count(*)", "Sessions actives")
    else:
        s.add(s.col("u", "full_name"), "Utilisateur")
        s.add(s.col("u", "email"), "E-mail")
        s.add(f"string_agg(DISTINCT {space}, ', ')", "Espaces")
        s.add("count(*)", "Sessions actives")
        s.add(f"max({s.col('s', 'created_at')})", "Dernière connexion")
        s.add(f"max({s.col('s', 'expires_at')})", "Expiration")
        s.group = [s.col("u", "id"), "u.full_name", "u.email"]
        s.order = ["max(s.created_at) DESC"]
    return s.result(
        "active_sessions", "Utilisateurs actuellement connectés", period=None,
        assumptions=[
            "Actif = session ouverte (non révoquée, non expirée) à l'instant de l'exécution.",
            "Une ligne par utilisateur ; ses sessions ouvertes sont comptées.",
        ],
    )


def _intent_inactive_users(q: str, cat: Catalog, p: Period | None) -> Interpretation:
    s = _Sql(cat, "users", "u")
    never = _has(q, r"jamais")
    m = re.search(r"(\d{1,4}) ?(jours?|mois|semaines?)", q)
    days = 30
    if m:
        n = int(m[1])
        days = n * 30 if m[2] == "mois" else n * 7 if m[2].startswith("semaine") else n
    s.join("LEFT", "agences", "a", "a.id = u.agence_id", "users.agence_id → agences.id")
    last = s.col("u", "last_login_at")
    s.add(s.col("u", "full_name"), "Utilisateur")
    s.add(s.col("u", "email"), "E-mail")
    s.add(s.col("a", "libelle"), "Agence")
    s.add(last, "Dernière connexion")
    s.add(f"CASE WHEN {last} IS NULL THEN NULL ELSE date_part('day', now() - {last})::int END", "Jours sans connexion")
    s.where.append(f"{s.col('u', 'deleted_at')} IS NULL")
    s.where.append(f"{s.col('u', 'is_active')} = true")
    s.filters.append("Comptes actifs non supprimés")
    if never:
        s.where.append(f"{last} IS NULL")
        s.filters.append("Jamais connectés")
        title = "Utilisateurs jamais connectés"
    else:
        s.where.append(f"({last} IS NULL OR {last} < now() - interval '{days} days')")
        s.filters.append(f"Aucune connexion depuis {days} jours (ou jamais)")
        title = f"Utilisateurs sans connexion depuis {days} jours"
    s.order = [f"{last} ASC NULLS FIRST"]
    if _wants_count(q):
        s.select = ['count(*) AS "Utilisateurs"']
        s.order = []
    return s.result(
        "inactive_users", title, period=None,
        assumptions=["Dernière connexion = users.last_login_at (mise à jour à chaque Login 1)."],
    )


def _intent_long_sessions(q: str, cat: Catalog, p: Period | None) -> Interpretation:
    m = re.search(r"plus de (\d{1,3}) ?(h|heures?)", q)
    hours = int(m[1]) if m else 8
    s = _Sql(cat, "auth_sessions", "s")
    s.join("INNER", "users", "u", "u.id = s.user_id", "auth_sessions.user_id → users.id")
    space = _session_space_expr(s)
    end = f"COALESCE({s.col('s', 'revoked_at')}, LEAST({s.col('s', 'expires_at')}, now()))"
    start = s.col("s", "created_at")
    s.add(s.col("u", "full_name"), "Utilisateur")
    s.add(space, "Espace")
    s.add(start, "Connexion")
    s.add(end, "Fin")
    s.add(f"{end} - {start}", "Durée")
    s.where.append(f"{end} - {start} > interval '{hours} hours'")
    s.filters.append(f"Durée de session supérieure à {hours} h")
    _apply_period(s, "s", "created_at", p, "Connexion")
    s.order = ['"Durée" DESC']
    if _wants_count(q):
        s.select = ['count(*) AS "Sessions"']
        s.order = []
    return s.result(
        "long_sessions", f"Sessions de plus de {hours} heures", period=p,
        assumptions=["Fin de session = déconnexion, sinon expiration (ou maintenant si encore ouverte)."],
    )


def _intent_login_attempts(q: str, cat: Catalog, p: Period | None) -> Interpretation:
    s = _Sql(cat, "auth_login_attempts", "t")
    s.add(s.col("t", "created_at"), "Date")
    s.add(s.col("t", "email"), "E-mail saisi")
    s.add(s.col("t", "login_kind"), "Type de connexion")
    s.add(s.col("t", "module_code"), "Module")
    s.add(s.col("t", "ip_address"), "Adresse IP")
    s.where.append(f"{s.col('t', 'success')} = false")
    s.filters.append("Tentatives échouées")
    _apply_period(s, "t", "created_at", p, "Tentative")
    s.order = ["t.created_at DESC"]
    if _wants_count(q):
        s.select = ['count(*) AS "Échecs"', 'count(DISTINCT t.email) AS "Comptes distincts"']
        s.order = []
    return s.result("login_failures", "Tentatives de connexion échouées", period=p, assumptions=[])


def _intent_connections(
    q: str, cat: Catalog, p: Period | None, module: tuple[str, str] | None, module_explicit: bool
) -> Interpretation:
    s = _Sql(cat, "auth_sessions", "s")
    s.join("INNER", "users", "u", "u.id = s.user_id", "auth_sessions.user_id → users.id")
    space = _session_space_expr(s)
    assumptions: list[str] = []
    kind = s.col("s", "kind")
    if module:
        s.where.append(f"{kind} = 'module'")
        s.where.append(f"{s.col('s', 'module_code')} = {lit(module[0])}")
        s.filters.append(f"Module : {module[1]} (Login 2)")
        title = f"Connexions au module {module[1]}"
    elif module_explicit:
        s.where.append(f"{kind} = 'module'")
        s.filters.append("Connexions aux modules (Login 2)")
        title = "Connexions aux modules"
    else:
        s.where.append(f"{kind} = 'platform'")
        s.filters.append("Connexions à BEA DIGITAL (Login 1)")
        assumptions.append("Connexion = ouverture de session BEA DIGITAL (Login 1). Précisez un module pour Login 2.")
        title = "Utilisateurs connectés"
    _apply_period(s, "s", "created_at", p, "Connexion")
    latest = _wants_latest(q)
    if _wants_count(q):
        s.add(f"count(DISTINCT {s.col('s', 'user_id')})", "Utilisateurs distincts")
        s.add("count(*)", "Connexions")
        title = "Nombre de " + title[0].lower() + title[1:]
    else:
        s.add(s.col("u", "full_name"), "Utilisateur")
        s.add(s.col("u", "email"), "E-mail")
        s.add(space, "Espace")
        s.add(s.col("s", "created_at"), "Connexion")
        s.add(s.col("s", "revoked_at"), "Déconnexion")
        s.add(s.col("s", "ip_address"), "Adresse IP")
        s.order = ["s.created_at DESC"]
        if latest:
            s.limit = _top_n(q, 50)
            title = "Dernières c" + title[1:] if title.startswith("C") else "Dernières connexions"
    if p is None and not latest and not _wants_count(q):
        assumptions.append("Aucune période précisée : toutes les connexions, les plus récentes d'abord.")
    return s.result("connections", title, period=p, assumptions=assumptions)


def _intent_admin_activity(q: str, cat: Catalog, p: Period | None) -> Interpretation:
    s = _Sql(cat, "audit_logs", "l")
    s.join("INNER", "users", "u", "u.id = l.user_id", "audit_logs.user_id → users.id")
    for t, c in (("user_roles", "role_id"), ("role_permissions", "permission_id"), ("permissions", "code")):
        if not cat.has(t, c):
            raise _MissingColumn(f"{t}.{c}")
    s.add(s.col("l", "created_at"), "Date")
    s.add(s.col("u", "full_name"), "Administrateur")
    s.add(s.col("l", "action"), "Action")
    s.add(s.col("l", "entity"), "Objet")
    s.add(s.col("l", "entity_id"), "Référence")
    s.add(s.col("l", "module_code"), "Module")
    s.add(s.col("l", "ip_address"), "Adresse IP")
    s.where.append(
        f"({s.col('u', 'is_superuser')} = true OR EXISTS (\n"
        "    SELECT 1 FROM user_roles ur\n"
        "    JOIN role_permissions rp ON rp.role_id = ur.role_id\n"
        "    JOIN permissions pe ON pe.id = rp.permission_id\n"
        "    WHERE ur.user_id = u.id AND pe.code = 'core.admin.access'\n"
        "  ))"
    )
    for t in ("user_roles", "role_permissions", "permissions"):
        if t not in s.tables:
            s.tables.append(t)
    s.relations += ["users.id → user_roles.user_id", "user_roles.role_id → role_permissions.role_id",
                    "role_permissions.permission_id → permissions.id"]
    s.filters.append("Utilisateurs super administrateurs ou titulaires de core.admin.access")
    _apply_period(s, "l", "created_at", p, "Date de l'action")
    s.order = ["l.created_at DESC"]
    s.limit = _top_n(q, None if p else 200)
    if _wants_count(q):
        s.select = ['u.full_name AS "Administrateur"', 'count(*) AS "Actions"']
        s.group = ["u.full_name"]
        s.order = ['"Actions" DESC']
        s.limit = None
    return s.result(
        "admin_activity", "Activité des administrateurs", period=p,
        assumptions=["Administrateur = super administrateur ou permission core.admin.access."],
    )


def _intent_admin_operations(q: str, cat: Catalog, p: Period | None, admin_only: bool) -> Interpretation:
    s = _Sql(cat, "audit_logs", "l")
    s.join("LEFT", "users", "u", "u.id = l.user_id", "audit_logs.user_id → users.id")
    s.add(s.col("l", "created_at"), "Date")
    s.add(s.col("u", "full_name"), "Utilisateur")
    s.add(s.col("l", "action"), "Action")
    s.add(s.col("l", "entity"), "Objet")
    s.add(s.col("l", "entity_id"), "Référence")
    s.add(s.col("l", "module_code"), "Module")
    s.add(s.col("l", "ip_address"), "Adresse IP")
    assumptions: list[str] = []
    if admin_only:
        s.where.append(f"{s.col('l', 'module_code')} = 'core'")
        s.filters.append("Opérations CORE / CORE ADMIN (module_code = core)")
        assumptions.append("Opération administrative = entrée d'audit du module core.")
    _apply_period(s, "l", "created_at", p, "Date")
    s.order = ["l.created_at DESC"]
    s.limit = _top_n(q, 50 if _wants_latest(q) or p is None else None)
    if _wants_count(q):
        s.select = ['l.action AS "Action"', 'count(*) AS "Nombre"']
        s.group = ["l.action"]
        s.order = ['"Nombre" DESC']
        s.limit = None
    title = "Dernières opérations administratives" if admin_only else "Dernières opérations (audit)"
    return s.result("admin_operations", title, period=p, assumptions=assumptions)


def _intent_archives(q: str, cat: Catalog, p: Period | None) -> Interpretation:
    s = _Sql(cat, "archive_fichiers", "f")
    s.join("LEFT", "archive_dossiers", "d", "d.id = f.dossier_id", "archive_fichiers.dossier_id → archive_dossiers.id")
    s.join("LEFT", "users", "u", "u.id = f.uploaded_by_id", "archive_fichiers.uploaded_by_id → users.id")
    _apply_period(s, "f", "created_at", p, "Ajout")
    if _wants_count(q):
        s.add("count(*)", "Fichiers")
        s.add(f"count(DISTINCT {s.col('f', 'dossier_id')})", "Dossiers")
    else:
        s.add(s.col("f", "filename"), "Fichier")
        s.add(s.col("d", "libelle"), "Dossier")
        s.add(s.col("d", "annee"), "Année")
        s.add(s.col("f", "kind"), "Type")
        s.add(s.col("u", "full_name"), "Ajouté par")
        s.add(s.col("f", "created_at"), "Ajouté le")
        s.order = ["f.created_at DESC"]
        s.limit = _top_n(q)
    return s.result(
        "archives_documents", "Documents ajoutés aux archives", period=p,
        assumptions=["Archives = fichiers du module Archive Générale (archive_fichiers)."],
    )


def _intent_stock_demands(q: str, cat: Catalog, p: Period | None) -> Interpretation:
    s = _Sql(cat, "mg_demandes_fourniture", "d")
    s.join("LEFT", "agences", "a", "a.id = d.agence_id", "mg_demandes_fourniture.agence_id → agences.id")
    statut = s.col("d", "statut")
    assumptions: list[str] = []
    title = "Demandes de fournitures"
    if _has(q, r"en attente|a traiter|en cours|pendante|non trait"):
        s.where.append(f"{statut} IN ({', '.join(lit(x) for x in STOCK_PENDING_STATUTS)})")
        s.filters.append("Statut en attente : " + ", ".join(STOCK_PENDING_STATUTS))
        assumptions.append("En attente = soumise, visas ou préparation (ni servie, ni clôturée, ni rejetée).")
        title += " en attente"
    elif _has(q, r"rejet"):
        s.where.append(f"{statut} = 'REJETEE'")
        s.filters.append("Statut : REJETEE")
        title += " rejetées"
    elif _has(q, r"servi"):
        s.where.append(f"{statut} = 'SERVIE'")
        s.filters.append("Statut : SERVIE")
        title += " servies"
    if cat.has("mg_demandes_fourniture", "deleted_at"):
        s.where.append(f"{s.col('d', 'deleted_at')} IS NULL")
    _apply_period(s, "d", "date_demande" if cat.has("mg_demandes_fourniture", "date_demande") else "created_at",
                  p, "Date de demande")
    if _has(q, r"par statut"):
        s.add(statut, "Statut")
        s.add("count(*)", "Demandes")
        s.group = [statut]
        s.order = ['"Demandes" DESC']
    elif _has(q, r"par agence"):
        s.add("COALESCE(a.libelle, 'Sans agence')", "Agence")
        s.col("a", "libelle")
        s.add("count(*)", "Demandes")
        s.group = ["COALESCE(a.libelle, 'Sans agence')"]
        s.order = ['"Demandes" DESC']
    elif _wants_count(q):
        s.add("count(*)", "Demandes")
    else:
        s.add(s.col("d", "reference"), "Référence")
        s.add(s.col("d", "date_demande"), "Date de demande")
        s.add(s.col("d", "demandeur_nom"), "Demandeur")
        s.add(s.col("a", "libelle"), "Agence")
        s.add(statut, "Statut")
        s.order = ["d.date_demande DESC"]
        s.limit = _top_n(q)
    return s.result("stock_demands", title, period=p, assumptions=assumptions)


# --------------------------------------------------------------------------- moteur générique


def _find_entity(q: str, cat: Catalog) -> str | None:
    best: tuple[int, str] | None = None
    for table, (_label, synonyms) in TABLE_LABELS.items():
        if cat.table(table) is None:
            continue
        for syn in synonyms + [table.replace("_", " ")]:
            if re.search(rf"\b{re.escape(syn)}\b", q):
                score = len(syn)
                if best is None or score > best[0]:
                    best = (score, table)
    if best:
        return best[1]
    for table in cat.tables:
        if re.search(rf"\b{re.escape(table)}\b", q.replace(" ", "_")) and len(table) > 3:
            return table
    return None


def _display_column(cat: Catalog, table: str) -> str | None:
    t = cat.table(table)
    if t is None:
        return None
    return next((c for c in DISPLAY_COLUMNS if c in t.columns), None)


def _date_column(cat: Catalog, table: str) -> str | None:
    t = cat.table(table)
    if t is None:
        return None
    return next((c for c in DATE_COLUMNS if c in t.columns), None)


def _measure_column(cat: Catalog, table: str) -> str | None:
    t = cat.table(table)
    if t is None:
        return None
    return next((c for c in MEASURE_COLUMNS if c in t.columns and t.columns[c].kind == "number"), None)


def _status_column(cat: Catalog, table: str) -> str | None:
    t = cat.table(table)
    if t is None:
        return None
    return next((c for c in STATUS_COLUMNS if c in t.columns), None)


def _resolve_dimension(word: str, cat: Catalog, table: str) -> tuple[str, str] | None:
    """« par X » → ('fk', fk_name) | ('status', col) | ('date', unit) | ('column', col)."""
    w = word.strip()
    if re.match(r"(mois|jour|annee|semaine)s?$", w):
        unit = {"mois": "month", "jour": "day", "annee": "year", "semaine": "week"}[w.rstrip("s") if w != "mois" else w]
        return ("date", unit)
    if w in ("statut", "statuts", "etat", "etats"):
        col = _status_column(cat, table)
        return ("status", col) if col else None
    for fk in cat.fks_from(table):
        if len(fk.columns) != 1:
            continue
        entry = TABLE_LABELS.get(fk.ref_table)
        synonyms = (entry[1] if entry else []) + [fk.ref_table.replace("_", " "), fk.columns[0].replace("_id", "")]
        if any(re.fullmatch(rf"{re.escape(syn)}s?", w) for syn in synonyms if syn):
            return ("fk", fk.name)
    t = cat.table(table)
    if t:
        for col in t.columns:
            if col.replace("_", " ") == w or col.replace("_", " ") == w.rstrip("s"):
                return ("column", col)
    return None


def _generic(q: str, cat: Catalog, p: Period | None, entity: str) -> Interpretation:
    t = cat.tables[entity]
    s = _Sql(cat, entity, "t")
    assumptions: list[str] = []
    title = table_label(entity)

    if "deleted_at" in t.columns:
        s.where.append(f"{s.col('t', 'deleted_at')} IS NULL")
        s.filters.append("Lignes non supprimées")
    if "is_active" in t.columns:
        if _has(q, r"\binacti(f|fs|ve|ves)\b|\bdesactive(s|e|es)?\b"):
            s.where.append(f"{s.col('t', 'is_active')} = false")
            s.filters.append("Inactifs")
            title += " inactifs"
        elif _has(q, r"\bacti(f|fs|ve|ves)\b"):
            s.where.append(f"{s.col('t', 'is_active')} = true")
            s.filters.append("Actifs")
            title += " actifs"
            if entity == "users":
                assumptions.append("Actif = compte activé. Pour les sessions ouvertes : « utilisateurs actuellement connectés ».")
    if entity == "users" and _has(q, r"super ?admin|administrateurs?\b|admins?\b"):
        s.where.append(f"{s.col('t', 'is_superuser')} = true")
        s.filters.append("Super administrateurs")
    status_col = _status_column(cat, entity)
    if status_col and t.columns[status_col].enum_values:
        for value in t.columns[status_col].enum_values:
            words = normalize(value.replace("_", " "))
            if re.search(rf"\b{re.escape(words)}(s|es)?\b", q) or re.search(rf"\b{re.escape(words.rstrip('e'))}(e|es|s)?\b", q):
                s.where.append(f"{s.col('t', status_col)} = {lit(value)}")
                s.filters.append(f"{column_label(status_col)} : {value}")
                break

    date_col = _date_column(cat, entity)
    if p is not None:
        if date_col is None:
            return Interpretation(
                ok=False, intent="clarification", title=title,
                clarification=f"La table {table_label(entity)} n'a pas de colonne de date : la période ne peut pas s'appliquer.",
                suggestions=EXAMPLES[:4], tables=[entity], confidence="faible",
            )
        _apply_period(s, "t", date_col, p, column_label(date_col))

    measure = _measure_column(cat, entity)
    m_group = re.search(r"\b(?:par|pour chaque|selon|groupe(?:s|es)? par) ([a-z0-9 ]+?)(?:\s+(?:et|en|sur|du|de|des|pour|avec|ce|cette|depuis|hier|aujourd)\b|$)", q)
    if m_group:
        dim = _resolve_dimension(m_group[1].split()[0] if m_group[1].split() else "", cat, entity)
        if dim is None:
            options = sorted({TABLE_LABELS.get(fk.ref_table, (fk.ref_table, []))[0].lower()
                              for fk in cat.fks_from(entity) if len(fk.columns) == 1})
            return Interpretation(
                ok=False, intent="clarification", title=title,
                clarification=(
                    f"Je ne sais pas regrouper {table_label(entity).lower()} par « {m_group[1].strip()} ». "
                    "Regroupements possibles : statut, mois, " + ", ".join(options[:8]) + "."
                ),
                tables=[entity], confidence="faible",
            )
        kind, ref = dim
        if kind == "fk":
            fk = cat.fk(ref)
            disp = _display_column(cat, fk.ref_table) or fk.ref_columns[0]
            s.join("LEFT", fk.ref_table, "g", f"g.{fk.ref_columns[0]} = t.{fk.columns[0]}",
                   f"{entity}.{fk.columns[0]} → {fk.ref_table}.{fk.ref_columns[0]}")
            expr = f"COALESCE({s.col('g', disp)}::text, 'Non renseigné')"
            label = table_label(fk.ref_table).split(" (")[0].rstrip("s")
        elif kind == "status":
            expr, label = s.col("t", ref), column_label(ref)
        elif kind == "date":
            if date_col is None:
                raise _MissingColumn(f"{entity}.created_at")
            expr = f"date_trunc('{ref}', {s.col('t', date_col)})"
            label = {"month": "Mois", "day": "Jour", "year": "Année", "week": "Semaine"}[ref]
        else:
            expr, label = s.col("t", ref), column_label(ref)
        s.add(expr, label)
        s.add("count(*)", "Nombre")
        if measure:
            s.add(f"sum({s.col('t', measure)})", f"{column_label(measure)} totale")
        s.group = [expr]
        s.order = [f'"{label}" ASC' if kind == "date" else ('"' + f"{column_label(measure)} totale" + '" DESC NULLS LAST' if measure else '"Nombre" DESC')]
        title += f" par {label.lower()}"
        return s.result("generic_group", title, period=p, assumptions=assumptions, confidence="moyenne")

    wants_sum = _has(q, r"\bvaleur\b|\bmontant\b|\bsomme\b|\bvaleurs\b")
    wants_avg = _has(q, r"\bmoyen(ne)?\b")
    if (wants_sum or wants_avg) and measure:
        agg = "avg" if wants_avg else "sum"
        label = column_label(measure) + (" moyenne" if wants_avg else " totale")
        s.add("count(*)", "Nombre")
        s.add(f"{agg}({s.col('t', measure)})", label)
        if measure == "valeur_brute":
            assumptions.append("Valeur = valeur brute d'acquisition (la VNC dépend des amortissements calculés).")
        return s.result("generic_aggregate", f"{label} — {table_label(entity)}", period=p, assumptions=assumptions)
    if (wants_sum or wants_avg) and not measure:
        assumptions.append(f"Aucune colonne de montant dans {entity} : comptage uniquement.")

    if _wants_count(q) or wants_sum or wants_avg:
        s.add("count(*)", table_label(entity).split(" (")[0])
        if "deleted_at" in t.columns:
            assumptions.append("Les lignes supprimées (deleted_at) sont exclues.")
        return s.result("generic_count", f"Nombre — {title}", period=p, assumptions=assumptions)

    cols: list[str] = []
    for c in DISPLAY_COLUMNS:
        if c in t.columns and c not in cols and len(cols) < 2:
            cols.append(c)
    for c in s.cat.tables[entity].columns:
        if c in ("email", "phone") and entity == "users" and c not in cols:
            cols.append(c)
    for c in cols:
        s.add(s.col("t", c), column_label(c))
    for fk in cat.fks_from(entity):
        if len(fk.columns) == 1 and fk.ref_table in ("agences", "departements") and len(s.joins) < 2:
            disp = _display_column(cat, fk.ref_table)
            if disp:
                alias = f"j{len(s.joins)}"
                s.join("LEFT", fk.ref_table, alias, f"{alias}.{fk.ref_columns[0]} = t.{fk.columns[0]}",
                       f"{entity}.{fk.columns[0]} → {fk.ref_table}.{fk.ref_columns[0]}")
                s.add(s.col(alias, disp), table_label(fk.ref_table).split(" (")[0].rstrip("s"))
    if status_col:
        s.add(s.col("t", status_col), column_label(status_col))
    if measure:
        s.add(s.col("t", measure), column_label(measure))
    if "is_active" in t.columns:
        s.add(s.col("t", "is_active"), "Actif")
    if entity == "users" and "last_login_at" in t.columns:
        s.add(s.col("t", "last_login_at"), "Dernière connexion")
    if date_col:
        s.add(s.col("t", date_col), column_label(date_col))
        s.order = [f"t.{date_col} DESC"]
    if not s.select:
        pk = t.primary_key[0] if t.primary_key else next(iter(t.columns))
        s.add(s.col("t", pk), column_label(pk))
    s.limit = _top_n(q, 50 if _wants_latest(q) else None)
    if _wants_latest(q):
        title = f"Derniers enregistrements — {title}"
    return s.result("generic_list", title, period=p, assumptions=assumptions, confidence="moyenne")


# --------------------------------------------------------------------------- point d'entrée


def interpret(
    question: str,
    catalog: Catalog,
    *,
    now: datetime | None = None,
    modules: dict[str, str] | None = None,
) -> Interpretation:
    q = normalize(question)
    now = now or datetime.now(TZ)
    modules = modules or {}
    if len(q) < 3:
        return Interpretation(
            ok=False, intent="clarification", title="Question trop courte",
            clarification="Décrivez ce que vous voulez rechercher (données, période, filtres).",
            suggestions=EXAMPLES, confidence="faible",
        )
    p = parse_period(q, now)
    try:
        return _dispatch(q, catalog, p, modules)
    except _MissingColumn as exc:
        return Interpretation(
            ok=False, intent="clarification", title="Schéma incompatible",
            clarification=(
                f"Cette question nécessite « {exc} », absent du schéma actuel. "
                "Reformulez ou utilisez le Query Builder."
            ),
            suggestions=EXAMPLES[:5], confidence="faible",
        )


def _dispatch(q: str, cat: Catalog, p: Period | None, modules: dict[str, str]) -> Interpretation:
    entity = _find_entity(q, cat)
    session_words = _has(q, r"connect|connexion|session|login|en ligne|authentifi")
    candidates, module_explicit = _match_module(q, modules)
    module = candidates[0] if len(candidates) == 1 else None

    if _has(q, r"\bmodules?\b") and _has(q, r"plus utilis|utilisation|plus actif|plus frequent|plus consult|utilises|par module"):
        return _intent_modules_usage(q, cat, p)

    if session_words or (entity in (None, "users") and _has(q, r"\binactifs?\b|actuellement|en ce moment")):
        if len(candidates) > 1 and module_explicit:
            return Interpretation(
                ok=False, intent="clarification", title="Module ambigu",
                clarification="Plusieurs modules correspondent : "
                + ", ".join(f"{lbl} ({code})" for code, lbl in candidates)
                + ". Précisez le code du module.",
                confidence="faible",
            )
        if _has(q, r"pas (ete )?connect|jamais connect|\binactifs?\b|sans connexion|plus connect|non connect|aucune connexion"):
            return _intent_inactive_users(q, cat, p)
        if _has(q, r"echec|echou|tentative|refus"):
            return _intent_login_attempts(q, cat, p)
        if _has(q, r"session") and _has(q, r"plus de \d{1,3} ?(h|heure)|longue"):
            return _intent_long_sessions(q, cat, p)
        if _has(q, r"actuellement|en ce moment|en ligne|maintenant|sessions? (actives?|ouvertes?|en cours)|\bactifs?\b"):
            return _intent_active_sessions(q, cat, p, module)
        return _intent_connections(q, cat, p, module, module_explicit and not candidates)

    if _has(q, r"activite (des|d) ?(admin|administrateur)|admins? (actifs|activite)|actions? des administrateurs"):
        return _intent_admin_activity(q, cat, p)
    if _has(q, r"operations? (administratives?|d administration|core)|actions? administratives?|operations? admin\b"):
        return _intent_admin_operations(q, cat, p, admin_only=True)
    if _has(q, r"\boperations?\b|\baudit\b|\bjournal\b") and entity in (None, "audit_logs"):
        return _intent_admin_operations(q, cat, p, admin_only=False)
    if _has(q, r"\barchives?\b"):
        return _intent_archives(q, cat, p)
    if _has(q, r"demandes? (de|d) (stock|fournitures?)|stock en attente"):
        return _intent_stock_demands(q, cat, p)

    if entity:
        return _generic(q, cat, p, entity)

    return Interpretation(
        ok=False, intent="clarification", title="Question non comprise",
        clarification=(
            "Je n'ai pas identifié les données concernées. Précisez l'objet (utilisateurs, connexions, "
            "immobilisations, demandes de stock, audit, archives, modules…) et éventuellement la période."
        ),
        suggestions=EXAMPLES, confidence="faible",
    )
