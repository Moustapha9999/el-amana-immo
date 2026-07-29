"""Moteur d'amortissement — norme bancaire base 360 jours.

Arrêtés trimestriels
--------------------
  T1 : 31/03   T2 : 30/06   T3 : 30/09   T4 : 31/12

Typologie & durée YTD (exercice N)
----------------------------------
  A. Acquisition dans N (D_acq ≥ 01/01/N) :
       Point de départ = D_acq
       Durée jusqu'à l'arrêté = DAYS360(D_acq, D_arrete + 1 j)
         → ex. 06/01 → 30/06 = 175 j ; 01/01 → 30/06 = 180 j

  B. Stock antérieur (D_acq < 01/01/N) :
       Point de départ = 01/01/N
       Durée = 90 / 180 / 270 / 360 selon T1 / T2 / T3 / T4

Formule
-------
  Dotation_YTD = VB × Taux × (Durée_YTD / 360)
  Dotation_période = Dotation_YTD(arrêté) − Dotation_YTD(arrêté précédent)
  (plafond = VNC disponible ; jamais de VNC négative)

Résultats par arrêté
--------------------
  • Dotation de la période (68)
  • Cumul des amortissements (148)
  • VNC = VB − cumul
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from app.models import Immobilisation

PERIODICITES = frozenset({"mensuel", "trimestriel", "annuel"})

JOURS_AN_COMMERCIAL = Decimal("360")
JOURS_MOIS_COMMERCIAL = 30
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
    return quarter_end(d)


def period_key(period_end: date) -> str:
    q = quarter_index(period_end) + 1
    return f"{period_end.year}-Q{q}"


def days_360(start: date, end_exclusive: date) -> int:
    """Jours base 30/360 type Excel ``DAYS360(start, end_exclusive)``."""
    if end_exclusive <= start:
        return 0
    d1 = min(start.day, JOURS_MOIS_COMMERCIAL)
    d2 = min(end_exclusive.day, JOURS_MOIS_COMMERCIAL)
    return (
        360 * (end_exclusive.year - start.year)
        + 30 * (end_exclusive.month - start.month)
        + (d2 - d1)
    )


def point_depart_exercice(date_acquisition: date, annee: int) -> date:
    """Départ de la durée YTD pour l'exercice ``annee``.

    - Acquisition dans N → date d'acquisition
    - Stock antérieur → 01/01/N
    """
    debut_annee = date(annee, 1, 1)
    if date_acquisition >= debut_annee:
        return date_acquisition
    return debut_annee


def duree_jours_360(debut: date, date_arrete: date) -> int:
    """Durée banque jusqu'à l'arrêté : ``DAYS360(debut, arrêté + 1 jour)``.

    Donne la matrice stock : T1=90, T2=180, T3=270, T4=360
    et les proratas Excel (ex. 06/01→30/06 = 175 j).
    """
    if date_arrete < debut:
        return 0
    return days_360(debut, date_arrete + timedelta(days=1))


def jours_entre(debut: date, date_arrete: date) -> int:
    """Alias spécification : durée 360 entre départ et arrêté."""
    return duree_jours_360(debut, date_arrete)


def jours_commerciaux_periode(debut: date, period_start: date, period_end: date) -> int:
    """Jours de la période = YTD(fin) − YTD(arrêté précédent)."""
    if debut > period_end:
        return 0
    debut_eff = max(debut, period_start)
    if debut_eff > period_end:
        return 0
    ytd_fin = duree_jours_360(debut_eff, period_end)
    if debut_eff > period_start:
        # Acquisition en cours de période : pas d'arrêté précédent dans la période
        return ytd_fin
    # Période pleine : YTD jusqu'à fin − YTD jusqu'à arrêté précédent
    prev_arrete = period_start - timedelta(days=1)
    ytd_avant = duree_jours_360(debut_eff, prev_arrete) if prev_arrete >= debut_eff else 0
    return max(0, ytd_fin - ytd_avant)


def duree_prorata(debut: date, date_arrete: date) -> Decimal:
    jours = duree_jours_360(debut, date_arrete)
    if jours <= 0:
        return Decimal("0")
    return (Decimal(jours) / JOURS_AN_COMMERCIAL).quantize(Decimal("0.0000001"))


def _annual_rate_fraction(immo: Immobilisation) -> Decimal:
    if immo.taux is not None and immo.taux > 0:
        return (Decimal(immo.taux) / Decimal("100")).quantize(Decimal("0.0000001"))
    cat = getattr(immo, "categorie", None)
    if cat is not None and getattr(cat, "taux_lineaire_defaut", None):
        return (Decimal(cat.taux_lineaire_defaut) / Decimal("100")).quantize(Decimal("0.0000001"))
    from app.services.nature_immo_referentiel import bank_taux_for_duree

    bank = bank_taux_for_duree(immo.duree_annees)
    if bank is not None and bank > 0:
        return (bank / Decimal("100")).quantize(Decimal("0.0000001"))
    if immo.duree_annees and immo.duree_annees > 0:
        return (Decimal("1") / Decimal(immo.duree_annees)).quantize(Decimal("0.0000001"))
    if immo.duree_mois > 0:
        return (Decimal("12") / Decimal(immo.duree_mois)).quantize(Decimal("0.0000001"))
    return Decimal("0")


def calcul_amortissement(vb: Decimal, taux_fraction: Decimal, duree: Decimal) -> Decimal:
    """Dotation = VB × Taux × (jours/360)."""
    if vb <= 0 or taux_fraction <= 0 or duree <= 0:
        return Decimal("0.00")
    return (vb * taux_fraction * duree).quantize(Decimal("0.01"))


def _max_end_date(immo: Immobilisation, start: date) -> date:
    if immo.duree_annees and immo.duree_annees > 0:
        return add_months(start, immo.duree_annees * 12)
    if immo.duree_mois > 0:
        return add_months(start, immo.duree_mois)
    return add_months(start, 12 * 50)


def _dotation_ytd(
    vb: Decimal,
    taux: Decimal,
    debut_exo: date,
    date_arrete: date,
) -> Decimal:
    jours = duree_jours_360(debut_exo, date_arrete)
    if jours <= 0:
        return Decimal("0.00")
    return calcul_amortissement(vb, taux, Decimal(jours) / JOURS_AN_COMMERCIAL)


def build_amortissement_schedule(immo: Immobilisation) -> list[tuple[str, Decimal]]:
    """Plan trimestriel : chaque ligne = incrément YTD (spécification banque)."""
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
        q_end = quarter_end(cursor)
        next_q = add_months(q_start, 3)

        annee = q_end.year
        debut_exo = point_depart_exercice(start, annee)
        if debut_exo > q_end or debut_exo >= max_end:
            cursor = next_q
            continue

        arrete_eff = min(q_end, max_end - timedelta(days=1)) if max_end <= q_end else q_end
        if arrete_eff < debut_exo:
            cursor = next_q
            continue

        ytd_fin = _dotation_ytd(vb, taux, debut_exo, arrete_eff)
        if debut_exo > q_start:
            ytd_avant = Decimal("0.00")
        else:
            prev = q_start - timedelta(days=1)
            ytd_avant = _dotation_ytd(vb, taux, debut_exo, prev) if prev >= debut_exo else Decimal("0.00")

        montant = (ytd_fin - ytd_avant).quantize(Decimal("0.01"))
        if montant < 0:
            montant = Decimal("0.00")

        restant = (base_max - cumul).quantize(Decimal("0.01"))
        if montant > restant:
            montant = restant
        if montant > 0:
            schedule.append((period_key(q_end), montant))
            cumul = (cumul + montant).quantize(Decimal("0.01"))

        if max_end <= q_end:
            break
        cursor = next_q

    if schedule and cumul < base_max:
        rest = (base_max - cumul).quantize(Decimal("0.01"))
        if rest > 0:
            periode, montant = schedule[-1]
            schedule[-1] = (periode, (montant + rest).quantize(Decimal("0.01")))

    return schedule


def parse_period_end(periode: str) -> date | None:
    raw = periode.strip()
    if raw.isdigit() and len(raw) == 4:
        return date(int(raw), 12, 31)
    quarter = raw.upper().split("-Q")
    if len(quarter) == 2 and quarter[0].isdigit() and quarter[1].isdigit():
        year = int(quarter[0])
        q = int(quarter[1])
        if 1 <= q <= 4:
            end_month = q * 3
            return date(year, end_month, monthrange(year, end_month)[1])
    parts = raw.split("-")
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        year, month = int(parts[0]), int(parts[1])
        if 1 <= month <= 12:
            return date(year, month, monthrange(year, month)[1])
    return None


def period_bounds(periodicite: str, annee: int, index: int) -> tuple[date, date, str]:
    per = (periodicite or "").strip().lower()
    if per not in PERIODICITES:
        raise ValueError(f"Périodicité invalide : {periodicite}")
    if annee < 2000 or annee > 2100:
        raise ValueError(f"Année invalide : {annee}")

    if per == "mensuel":
        if not 1 <= index <= 12:
            raise ValueError("Pour un calcul mensuel, periode_index doit être entre 1 et 12.")
        debut = date(annee, index, 1)
        fin = date(annee, index, monthrange(annee, index)[1])
        return debut, fin, f"{annee}-{index:02d}"

    if per == "trimestriel":
        if not 1 <= index <= 4:
            raise ValueError("Pour un calcul trimestriel, periode_index doit être entre 1 et 4.")
        debut = date(annee, (index - 1) * 3 + 1, 1)
        end_month = index * 3
        fin = date(annee, end_month, monthrange(annee, end_month)[1])
        return debut, fin, f"{annee}-Q{index}"

    if index != 1:
        raise ValueError("Pour un calcul annuel, periode_index doit être égal à 1.")
    return date(annee, 1, 1), date(annee, 12, 31), f"{annee}"


def calcul_dotation_periode(
    immo: Immobilisation,
    date_debut: date,
    date_fin: date,
    cumul_valide: Decimal,
) -> tuple[Decimal, Decimal, Decimal] | None:
    """Dotation d'une période selon la spécification banque (YTD / 360 + plafond VNC).

    Retourne ``(montant, cumul_apres, vnc_apres)`` ou ``None`` si VNC nulle /
    acquisition postérieure à l'arrêté.
    """
    vb = immo.valeur_brute.quantize(Decimal("0.01"))
    residuelle = (immo.valeur_residuelle or Decimal("0")).quantize(Decimal("0.01"))
    cumul = Decimal(cumul_valide).quantize(Decimal("0.01"))
    if cumul < 0:
        cumul = Decimal("0.00")

    # a. VNC disponible
    vnc_disponible = (vb - cumul).quantize(Decimal("0.01"))
    # b. Totalement amortie
    if vnc_disponible <= 0:
        return None

    restant = (vnc_disponible - residuelle).quantize(Decimal("0.01"))
    if restant <= 0:
        return None

    taux = _annual_rate_fraction(immo)
    if taux <= 0 or vb <= 0:
        return None

    acq = immo.date_acquisition
    if acq is None or acq > date_fin:
        return None

    # c.i Point de départ selon typologie
    annee = date_fin.year
    debut_exo = point_depart_exercice(acq, annee)
    if debut_exo > date_fin:
        return None

    # c.ii Dotation YTD à l'arrêté − YTD à l'arrêté précédent (= incrément période)
    ytd_fin = _dotation_ytd(vb, taux, debut_exo, date_fin)
    if date_debut <= debut_exo:
        ytd_avant = Decimal("0.00")
    else:
        prev_arrete = date_debut - timedelta(days=1)
        ytd_avant = _dotation_ytd(vb, taux, debut_exo, prev_arrete)

    dotation_theorique = (ytd_fin - ytd_avant).quantize(Decimal("0.01"))
    if dotation_theorique < 0:
        dotation_theorique = Decimal("0.00")

    # c.iii Plafonnement VNC
    if restant - dotation_theorique >= 0:
        montant = dotation_theorique
    else:
        montant = restant

    if montant <= 0:
        return None

    # d. Compteurs
    cumul_apres = (cumul + montant).quantize(Decimal("0.01"))
    vnc_apres = (vb - cumul_apres).quantize(Decimal("0.01"))
    if vnc_apres < 0:
        vnc_apres = Decimal("0.00")
    return montant, cumul_apres, vnc_apres


def cumul_amortissement_a_date(immo: Immobilisation, date_limite: date) -> Decimal:
    """Cumul jusqu'à ``date_limite`` (prorata inclus)."""
    if immo.date_acquisition is None or date_limite < immo.date_acquisition:
        return Decimal("0.00")

    vb = immo.valeur_brute.quantize(Decimal("0.01"))
    residuelle = (immo.valeur_residuelle or Decimal("0")).quantize(Decimal("0.01"))
    base_max = (vb - residuelle).quantize(Decimal("0.01"))
    taux = _annual_rate_fraction(immo)
    if vb <= 0 or base_max <= 0 or taux <= 0:
        return Decimal("0.00")

    start = immo.date_acquisition
    max_end = min(_max_end_date(immo, start), date_limite + timedelta(days=1))

    cumul = Decimal("0")
    cursor = start
    safety = 0
    while cumul < base_max and cursor < max_end and safety < 500:
        safety += 1
        q_start = quarter_start(cursor)
        q_end = quarter_end(cursor)
        next_q = add_months(q_start, 3)

        annee = q_end.year
        debut_exo = point_depart_exercice(start, annee)
        arrete = min(q_end, date_limite)
        if debut_exo > arrete:
            cursor = next_q
            continue

        ytd_fin = _dotation_ytd(vb, taux, debut_exo, arrete)
        if debut_exo > q_start:
            ytd_avant = Decimal("0.00")
        else:
            prev = q_start - timedelta(days=1)
            ytd_avant = (
                _dotation_ytd(vb, taux, debut_exo, prev) if prev >= debut_exo else Decimal("0.00")
            )

        montant = (ytd_fin - ytd_avant).quantize(Decimal("0.01"))
        if montant < 0:
            montant = Decimal("0.00")
        restant = (base_max - cumul).quantize(Decimal("0.01"))
        if montant > restant:
            montant = restant
        cumul = (cumul + montant).quantize(Decimal("0.01"))

        if date_limite <= q_end:
            break
        cursor = next_q

    return cumul


def vnc_a_date(immo: Immobilisation, date_limite: date) -> tuple[Decimal, Decimal]:
    cumul = cumul_amortissement_a_date(immo, date_limite)
    vnc = (immo.valeur_brute - cumul).quantize(Decimal("0.01"))
    if vnc < 0:
        vnc = Decimal("0.00")
    return cumul, vnc


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
