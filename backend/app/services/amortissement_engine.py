"""Calcul des dotations (linéaire / dégressif) avec prorata temporis."""

from calendar import monthrange
from datetime import date
from decimal import Decimal

from app.models import Immobilisation
from app.models.enums import ModeAmortissement


def months_in_period(periodicite: str) -> int:
    return {"mensuel": 1, "trimestriel": 3, "annuel": 12}.get(periodicite, 12)


def add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, monthrange(year, month)[1])
    return date(year, month, day)


def period_start_for_end(period_end: date, periodicite: str) -> date:
    if periodicite == "annuel":
        return date(period_end.year, 1, 1)
    if periodicite == "trimestriel":
        q_start_month = ((period_end.month - 1) // 3) * 3 + 1
        return date(period_end.year, q_start_month, 1)
    return date(period_end.year, period_end.month, 1)


def end_of_period(start: date, periodicite: str) -> date:
    if periodicite == "annuel":
        return date(start.year, 12, 31)
    if periodicite == "trimestriel":
        q_end_month = ((start.month - 1) // 3 + 1) * 3
        return date(start.year, q_end_month, monthrange(start.year, q_end_month)[1])
    return date(start.year, start.month, monthrange(start.year, start.month)[1])


def period_key(period_end: date, periodicite: str) -> str:
    if periodicite == "annuel":
        return str(period_end.year)
    return f"{period_end.year}-{period_end.month:02d}"


def prorata_fraction(period_start: date, period_end: date, periodicite: str) -> Decimal:
    if period_start > period_end:
        return Decimal("0")
    full_start = period_start_for_end(period_end, periodicite)
    used_days = (period_end - period_start).days + 1
    full_days = (period_end - full_start).days + 1
    if full_days <= 0:
        return Decimal("1")
    return min(Decimal("1"), (Decimal(used_days) / Decimal(full_days)).quantize(Decimal("0.0001")))


def _annual_rate(immo: Immobilisation) -> Decimal:
    if immo.duree_annees and immo.duree_annees > 0:
        return (Decimal("100") / Decimal(immo.duree_annees)).quantize(Decimal("0.0001"))
    if immo.duree_mois > 0:
        return (Decimal("100") * Decimal("12") / Decimal(immo.duree_mois)).quantize(Decimal("0.0001"))
    if immo.taux is not None and immo.taux > 0:
        return immo.taux
    return Decimal("0")


def build_amortissement_schedule(immo: Immobilisation) -> list[tuple[str, Decimal]]:
    """Retourne (clé période, montant) pour toute la durée d'utilisation."""
    base = (immo.valeur_brute - immo.valeur_residuelle).quantize(Decimal("0.01"))
    if base <= 0 or immo.duree_mois <= 0:
        return []

    start = immo.date_mise_en_service or immo.date_acquisition
    periodicite = immo.periodicite or "annuel"
    mip = months_in_period(periodicite)
    n_periods = max(1, (immo.duree_mois + mip - 1) // mip)

    if immo.mode_amortissement == ModeAmortissement.DEGRESSIF:
        return _schedule_degressif(immo, base, start, periodicite, mip, n_periods)

    return _schedule_lineaire(immo, base, start, periodicite, mip, n_periods)


def _schedule_lineaire(
    immo: Immobilisation,
    base: Decimal,
    start: date,
    periodicite: str,
    mip: int,
    n_periods: int,
) -> list[tuple[str, Decimal]]:
    full_amount = (base / Decimal(n_periods)).quantize(Decimal("0.01"))
    amounts: list[Decimal] = [full_amount] * n_periods
    diff = base - sum(amounts)
    if amounts:
        amounts[-1] = (amounts[-1] + diff).quantize(Decimal("0.01"))

    cursor = start
    schedule: list[tuple[str, Decimal]] = []
    for i, amount in enumerate(amounts):
        p_end = end_of_period(cursor, periodicite)
        key = period_key(p_end, periodicite)
        montant = amount
        if i == 0 and immo.prorata_temporis:
            frac = prorata_fraction(cursor, p_end, periodicite)
            if frac < Decimal("1"):
                montant = (amount * frac).quantize(Decimal("0.01"))
        schedule.append((key, montant))
        next_month = add_months(p_end, 1)
        cursor = date(next_month.year, next_month.month, 1)
    return schedule


def _schedule_degressif(
    immo: Immobilisation,
    base: Decimal,
    start: date,
    periodicite: str,
    mip: int,
    n_periods: int,
) -> list[tuple[str, Decimal]]:
    annual = _annual_rate(immo)
    periods_per_year = Decimal(12) / Decimal(mip)
    vnc = base
    cursor = start
    schedule: list[tuple[str, Decimal]] = []

    for i in range(n_periods):
        if vnc <= 0:
            break
        p_end = end_of_period(cursor, periodicite)
        key = period_key(p_end, periodicite)
        montant = (vnc * annual / Decimal("100") / periods_per_year).quantize(Decimal("0.01"))
        if i == 0 and immo.prorata_temporis:
            frac = prorata_fraction(cursor, p_end, periodicite)
            if frac < Decimal("1"):
                montant = (montant * frac).quantize(Decimal("0.01"))
        montant = min(montant, vnc)
        schedule.append((key, montant))
        vnc = (vnc - montant).quantize(Decimal("0.01"))
        next_month = add_months(p_end, 1)
        cursor = date(next_month.year, next_month.month, 1)

    return schedule
