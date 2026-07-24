"""Calcul des dotations — logique Banque El Amana.

Dotation = VA × (jours_360 / 360) × taux
- VA = valeur brute
- jours en base commerciale 360 (mois de 30 jours)
- dates d'arrêt trimestrielles : 31/03, 30/06, 30/09, 31/12
- point de départ = date d'acquisition
"""

from calendar import monthrange
from datetime import date
from decimal import Decimal

from app.models import Immobilisation

# Base commerciale banque
JOURS_AN_COMMERCIAL = Decimal("360")
JOURS_MOIS_COMMERCIAL = 30


def months_in_period(periodicite: str) -> int:
    return {"mensuel": 1, "trimestriel": 3, "annuel": 12}.get(periodicite, 3)


def add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, monthrange(year, month)[1])
    return date(year, month, day)


def quarter_index(d: date) -> int:
    return (d.month - 1) // 3


def quarter_start(d: date) -> date:
    return date(d.year, quarter_index(d) * 3 + 1, 1)


def quarter_end(d: date) -> date:
    end_month = quarter_index(d) * 3 + 3
    return date(d.year, end_month, monthrange(d.year, end_month)[1])


def period_start_for_end(period_end: date, periodicite: str) -> date:
    if periodicite == "annuel":
        return date(period_end.year, 1, 1)
    if periodicite == "trimestriel":
        return quarter_start(period_end)
    return date(period_end.year, period_end.month, 1)


def end_of_period(start: date, periodicite: str) -> date:
    if periodicite == "annuel":
        return date(start.year, 12, 31)
    if periodicite == "trimestriel":
        return quarter_end(start)
    return date(start.year, start.month, monthrange(start.year, start.month)[1])


def period_key(period_end: date, periodicite: str) -> str:
    if periodicite == "annuel":
        return str(period_end.year)
    if periodicite == "trimestriel":
        q = quarter_index(period_end) + 1
        return f"{period_end.year}-Q{q}"
    return f"{period_end.year}-{period_end.month:02d}"


def days_360(start: date, end_exclusive: date) -> int:
    """Nombre de jours en base 30/360 entre start (inclus) et end_exclusive (exclu).

    Convention commerciale : chaque mois = 30 jours, année = 360.
    Ex. 01/01 → 01/04 = 90 jours (un trimestre plein).
    """
    if end_exclusive <= start:
        return 0
    d1 = min(start.day, JOURS_MOIS_COMMERCIAL)
    d2 = min(end_exclusive.day, JOURS_MOIS_COMMERCIAL)
    return (
        360 * (end_exclusive.year - start.year)
        + 30 * (end_exclusive.month - start.month)
        + (d2 - d1)
    )


def _annual_rate_percent(immo: Immobilisation) -> Decimal:
    """Taux annuel en % — priorité au taux stocké, sinon dérivé de la durée."""
    if immo.taux is not None and immo.taux > 0:
        return Decimal(immo.taux)
    if immo.duree_annees and immo.duree_annees > 0:
        return (Decimal("100") / Decimal(immo.duree_annees)).quantize(Decimal("0.0001"))
    if immo.duree_mois > 0:
        return (Decimal("100") * Decimal("12") / Decimal(immo.duree_mois)).quantize(Decimal("0.0001"))
    return Decimal("0")


def _max_end_date(immo: Immobilisation, start: date) -> date:
    if immo.duree_annees and immo.duree_annees > 0:
        return add_months(start, immo.duree_annees * 12)
    if immo.duree_mois > 0:
        return add_months(start, immo.duree_mois)
    return add_months(start, 12 * 50)


def build_amortissement_schedule(immo: Immobilisation) -> list[tuple[str, Decimal]]:
    """Plan trimestriel Banque El Amana.

    Dotation période = VA × (jours_360 / 360) × (taux / 100)
    avec VA = valeur brute, départ = date d'acquisition, arrêt = fin de trimestre.
    Le cumul est plafonné à (VA − valeur résiduelle).
    """
    va = immo.valeur_brute.quantize(Decimal("0.01"))
    residuelle = (immo.valeur_residuelle or Decimal("0")).quantize(Decimal("0.01"))
    base_max = (va - residuelle).quantize(Decimal("0.01"))
    if va <= 0 or base_max <= 0:
        return []

    taux = _annual_rate_percent(immo)
    if taux <= 0:
        return []

    start = immo.date_acquisition
    if start is None:
        return []

    max_end = _max_end_date(immo, start)
    schedule: list[tuple[str, Decimal]] = []
    cumul = Decimal("0")
    cursor = start
    safety = 0

    while cumul < base_max and cursor < max_end and safety < 500:
        safety += 1
        q_start = quarter_start(cursor)
        q_end = quarter_end(cursor)
        next_q = add_months(q_start, 3)  # début trimestre suivant (borne exclusive 360)

        debut = max(start, q_start)
        fin_excl = min(next_q, max_end)
        if fin_excl <= debut:
            break

        jours = days_360(debut, fin_excl)
        if jours <= 0:
            cursor = next_q
            continue

        montant = (va * taux / Decimal("100") * Decimal(jours) / JOURS_AN_COMMERCIAL).quantize(
            Decimal("0.01")
        )
        restant = (base_max - cumul).quantize(Decimal("0.01"))
        if montant > restant:
            montant = restant
        if montant > 0:
            schedule.append((period_key(q_end, "trimestriel"), montant))
            cumul = (cumul + montant).quantize(Decimal("0.01"))

        cursor = next_q

    return schedule
