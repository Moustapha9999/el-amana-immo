"""Calcul des amortissements — note fonctionnelle Banque El Amana (§2).

Principe
--------
Les amortissements sont calculés automatiquement à chaque arrêté des états
financiers. Dates d'arrêté :
  • 31 mars
  • 30 juin
  • 30 septembre
  • 31 décembre

Durée (prorata temporis)
------------------------
Nombre de jours (base commerciale 30/360) entre :
  • la date d'acquisition (fait générateur), et
  • la date d'établissement des états financiers (arrêté),
pour la portion de période concernée (aucune dotation avant l'acquisition).

Formule
-------
  Amortissement = VB × Taux × Durée

où :
  • VB   = valeur brute
  • Taux = taux annuel (exprimé en décimal, ex. 20 % → 0,20)
  • Durée = jours_360 / 360  (fraction d'année commerciale)

Résultats par arrêté
--------------------
  • Amortissement de la période
  • Cumul des amortissements
  • VNC = VB − amortissements cumulés
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal

from app.models import Immobilisation

# Base commerciale banque (année = 360 j, mois = 30 j)
JOURS_AN_COMMERCIAL = Decimal("360")
JOURS_MOIS_COMMERCIAL = 30

# Dates d'arrêté des états financiers (fin de trimestre)
MOIS_ARRETE = (3, 6, 9, 12)


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
    """Date d'arrêté du trimestre contenant ``d`` (31/03, 30/06, 30/09, 31/12)."""
    end_month = quarter_index(d) * 3 + 3
    return date(d.year, end_month, monthrange(d.year, end_month)[1])


def date_arrete_for(d: date) -> date:
    """Prochaine (ou courante) date d'arrêté des états financiers."""
    return quarter_end(d)


def period_key(period_end: date) -> str:
    q = quarter_index(period_end) + 1
    return f"{period_end.year}-Q{q}"


def days_360(start: date, end_exclusive: date) -> int:
    """Jours en base 30/360 entre ``start`` (inclus) et ``end_exclusive`` (exclu).

    Ex. 01/01 → 01/04 = 90 jours (trimestre plein).
    Ex. 15/05 → 01/07 = 46 jours (prorata jusqu'à l'arrêté du 30/06).
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


def jours_entre(debut: date, date_arrete: date) -> int:
    """Jours 30/360 entre ``debut`` (inclus) et l'arrêté ``date_arrete`` (inclus)."""
    fin_excl = add_months(quarter_start(date_arrete), 3)
    return days_360(debut, fin_excl)


def duree_prorata(debut: date, date_arrete: date) -> Decimal:
    """Durée proratisée = jours_360 / 360 entre début et arrêté (inclus)."""
    jours = jours_entre(debut, date_arrete)
    if jours <= 0:
        return Decimal("0")
    return (Decimal(jours) / JOURS_AN_COMMERCIAL).quantize(Decimal("0.0000001"))


def _annual_rate_fraction(immo: Immobilisation) -> Decimal:
    """Taux annuel en fraction (20 % → 0.20)."""
    if immo.taux is not None and immo.taux > 0:
        return (Decimal(immo.taux) / Decimal("100")).quantize(Decimal("0.0000001"))
    if immo.duree_annees and immo.duree_annees > 0:
        return (Decimal("1") / Decimal(immo.duree_annees)).quantize(Decimal("0.0000001"))
    if immo.duree_mois > 0:
        return (Decimal("12") / Decimal(immo.duree_mois)).quantize(Decimal("0.0000001"))
    return Decimal("0")


def calcul_amortissement(vb: Decimal, taux_fraction: Decimal, duree: Decimal) -> Decimal:
    """Amortissement = VB × Taux × Durée (arrondi au centime)."""
    if vb <= 0 or taux_fraction <= 0 or duree <= 0:
        return Decimal("0.00")
    return (vb * taux_fraction * duree).quantize(Decimal("0.01"))


def _max_end_date(immo: Immobilisation, start: date) -> date:
    if immo.duree_annees and immo.duree_annees > 0:
        return add_months(start, immo.duree_annees * 12)
    if immo.duree_mois > 0:
        return add_months(start, immo.duree_mois)
    return add_months(start, 12 * 50)


def build_amortissement_schedule(immo: Immobilisation) -> list[tuple[str, Decimal]]:
    """Plan d'amortissement aux dates d'arrêté (prorata temporis automatique).

    Pour chaque arrêté :
      Durée = jours (acquisition→arrêté pour le 1er, sinon trimestre plein) / 360
      Amortissement période = VB × Taux × Durée
    Cumul et VNC sont dérivés à la génération du plan (service).
    """
    vb = immo.valeur_brute.quantize(Decimal("0.01"))
    residuelle = (immo.valeur_residuelle or Decimal("0")).quantize(Decimal("0.01"))
    base_max = (vb - residuelle).quantize(Decimal("0.01"))
    if vb <= 0 or base_max <= 0:
        return []

    taux = _annual_rate_fraction(immo)
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
        q_end = quarter_end(cursor)  # date d'arrêté
        next_q = add_months(q_start, 3)  # début trimestre suivant = borne exclusive

        # Début de la durée : max(acquisition, début de trimestre) — pas avant le fait générateur
        debut = max(start, q_start)
        fin_excl = min(next_q, max_end)
        if fin_excl <= debut:
            break

        jours = days_360(debut, fin_excl)
        if jours <= 0:
            cursor = next_q
            continue

        duree = Decimal(jours) / JOURS_AN_COMMERCIAL
        montant = calcul_amortissement(vb, taux, duree)
        restant = (base_max - cumul).quantize(Decimal("0.01"))
        if montant > restant:
            montant = restant
        if montant > 0:
            schedule.append((period_key(q_end), montant))
            cumul = (cumul + montant).quantize(Decimal("0.01"))

        cursor = next_q

    return schedule


def parse_period_end(periode: str) -> date | None:
    """Convertit une clé période (`2026-Q2`, `2026-03`) en date de fin."""
    quarter = periode.strip().upper().split("-Q")
    if len(quarter) == 2 and quarter[0].isdigit() and quarter[1].isdigit():
        year = int(quarter[0])
        q = int(quarter[1])
        if 1 <= q <= 4:
            end_month = q * 3
            return date(year, end_month, monthrange(year, end_month)[1])
    parts = periode.strip().split("-")
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        year, month = int(parts[0]), int(parts[1])
        if 1 <= month <= 12:
            return date(year, month, monthrange(year, month)[1])
    return None


def cumul_amortissement_a_date(immo: Immobilisation, date_limite: date) -> Decimal:
    """Cumul des amortissements jusqu'à ``date_limite`` (prorata inclus).

    Note banque cession : avant la sortie, calculer les amortissements jusqu'à
    la date de cession pour déterminer la VNC.
    """
    if immo.date_acquisition is None or date_limite < immo.date_acquisition:
        return Decimal("0.00")

    vb = immo.valeur_brute.quantize(Decimal("0.01"))
    residuelle = (immo.valeur_residuelle or Decimal("0")).quantize(Decimal("0.01"))
    base_max = (vb - residuelle).quantize(Decimal("0.01"))
    taux = _annual_rate_fraction(immo)
    if vb <= 0 or base_max <= 0 or taux <= 0:
        return Decimal("0.00")

    start = immo.date_acquisition
    max_end = min(_max_end_date(immo, start), date_limite)
    # Borne exclusive pour inclure le jour de cession (30/06 → 01/07)
    from datetime import timedelta

    fin_globale_excl = date_limite + timedelta(days=1)

    cumul = Decimal("0")
    cursor = start
    safety = 0
    while cumul < base_max and cursor <= date_limite and safety < 500:
        safety += 1
        q_start = quarter_start(cursor)
        q_end = quarter_end(cursor)
        next_q = add_months(q_start, 3)

        debut = max(start, q_start)
        if debut > date_limite:
            break

        # Fin de la portion : min(fin trimestre, lendemain de date_limite, fin durée)
        fin_excl = min(next_q, fin_globale_excl, _max_end_date(immo, start))
        if fin_excl <= debut:
            break

        jours = days_360(debut, fin_excl)
        if jours <= 0:
            cursor = next_q
            continue

        duree = Decimal(jours) / JOURS_AN_COMMERCIAL
        montant = calcul_amortissement(vb, taux, duree)
        restant = (base_max - cumul).quantize(Decimal("0.01"))
        if montant > restant:
            montant = restant
        cumul = (cumul + montant).quantize(Decimal("0.01"))

        if date_limite <= q_end:
            break
        cursor = next_q

    return cumul


def vnc_a_date(immo: Immobilisation, date_limite: date) -> tuple[Decimal, Decimal]:
    """Retourne (cumul_amortissement, vnc) à ``date_limite``."""
    cumul = cumul_amortissement_a_date(immo, date_limite)
    vnc = (immo.valeur_brute - cumul).quantize(Decimal("0.01"))
    if vnc < 0:
        vnc = Decimal("0.00")
    return cumul, vnc


# --- Compatibilité API historique -------------------------------------------------

def months_in_period(periodicite: str) -> int:
    return {"mensuel": 1, "trimestriel": 3, "annuel": 12}.get(periodicite, 3)


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
