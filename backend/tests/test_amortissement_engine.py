"""Tests moteur amortissement — spécification banque base 360."""

from datetime import date
from decimal import Decimal

from app.models.enums import ModeAmortissement
from app.services.amortissement_engine import (
    build_amortissement_schedule,
    calcul_amortissement,
    calcul_dotation_periode,
    duree_jours_360,
    duree_prorata,
    point_depart_exercice,
    period_bounds,
    quarter_end,
)


class FakeImmo:
    valeur_brute = Decimal("100000")
    valeur_residuelle = Decimal("0")
    duree_mois = 120
    duree_annees = 10
    date_acquisition = date(2026, 1, 1)
    date_mise_en_service = date(2026, 1, 1)
    periodicite = "trimestriel"
    prorata_temporis = True
    mode_amortissement = ModeAmortissement.LINEAIRE
    taux = Decimal("10")


def test_dates_arrete():
    assert quarter_end(date(2025, 2, 10)) == date(2025, 3, 31)
    assert quarter_end(date(2025, 5, 15)) == date(2025, 6, 30)
    assert quarter_end(date(2025, 8, 1)) == date(2025, 9, 30)
    assert quarter_end(date(2025, 11, 20)) == date(2025, 12, 31)


def test_matrice_stock_durees_ytd():
    """Actifs antérieurs : T1=90, T2=180, T3=270, T4=360."""
    debut = date(2026, 1, 1)
    assert duree_jours_360(debut, date(2026, 3, 31)) == 90
    assert duree_jours_360(debut, date(2026, 6, 30)) == 180
    assert duree_jours_360(debut, date(2026, 9, 30)) == 270
    assert duree_jours_360(debut, date(2026, 12, 31)) == 360


def test_point_depart_typologie():
    assert point_depart_exercice(date(2026, 1, 6), 2026) == date(2026, 1, 6)
    assert point_depart_exercice(date(2025, 5, 15), 2026) == date(2026, 1, 1)


def test_excel_kerim_30_06_9892_36():
    """Acquisition 06/01/2026, arrêté 30/06 → 175 j → 9 892,36."""
    assert duree_jours_360(date(2026, 1, 6), date(2026, 6, 30)) == 175
    assert calcul_amortissement(
        Decimal("203500"), Decimal("0.10"), Decimal("175") / Decimal("360")
    ) == Decimal("9892.36")

    immo = FakeImmo()
    immo.valeur_brute = Decimal("203500")
    immo.taux = Decimal("10")
    immo.date_acquisition = date(2026, 1, 6)
    immo.date_mise_en_service = None

    r1 = calcul_dotation_periode(immo, date(2026, 1, 1), date(2026, 3, 31), Decimal("0"))
    assert r1 is not None
    assert r1[0] == Decimal("4804.86")  # 85 j

    r2 = calcul_dotation_periode(immo, date(2026, 4, 1), date(2026, 6, 30), r1[1])
    assert r2 is not None
    assert r2[0] == Decimal("5087.50")  # incrément
    assert r2[1] == Decimal("9892.36")  # cumul = Excel


def test_excel_moulaye_566_67():
    """Acquisition 06/04/2026, arrêté 30/06 → 85 j → 566,67."""
    assert duree_jours_360(date(2026, 4, 6), date(2026, 6, 30)) == 85
    immo = FakeImmo()
    immo.valeur_brute = Decimal("24000")
    immo.taux = Decimal("10")
    immo.date_acquisition = date(2026, 4, 6)
    assert calcul_dotation_periode(immo, date(2026, 1, 1), date(2026, 3, 31), Decimal("0")) is None
    r = calcul_dotation_periode(immo, date(2026, 4, 1), date(2026, 6, 30), Decimal("0"))
    assert r is not None
    assert r[0] == Decimal("566.67")


def test_stock_dotation_t2_90_jours_increment():
    """Stock : YTD 180 à T2 − YTD 90 à T1 = 90 j de période."""
    immo = FakeImmo()
    immo.date_acquisition = date(2020, 1, 1)
    cumul_n1 = Decimal("50000")  # déjà amorti
    r1 = calcul_dotation_periode(immo, date(2026, 1, 1), date(2026, 3, 31), cumul_n1)
    assert r1 is not None
    assert r1[0] == Decimal("2500.00")  # 90/360 × 10 % × 100000
    r2 = calcul_dotation_periode(immo, date(2026, 4, 1), date(2026, 6, 30), r1[1])
    assert r2 is not None
    assert r2[0] == Decimal("2500.00")


def test_plafond_vnc():
    immo = FakeImmo()
    result = calcul_dotation_periode(immo, date(2026, 1, 1), date(2026, 3, 31), Decimal("99600"))
    assert result is not None
    assert result[0] == Decimal("400.00")
    assert result[2] == Decimal("0.00")


def test_vnc_nulle_ignore():
    immo = FakeImmo()
    assert calcul_dotation_periode(immo, date(2026, 1, 1), date(2026, 3, 31), Decimal("100000")) is None


def test_schedule_sums_to_vb():
    schedule = build_amortissement_schedule(FakeImmo())
    assert schedule[0][0] == "2026-Q1"
    assert sum(m for _, m in schedule) == Decimal("100000.00")


def test_kerim_schedule_cumul_t2():
    immo = FakeImmo()
    immo.valeur_brute = Decimal("203500")
    immo.taux = Decimal("10")
    immo.date_acquisition = date(2026, 1, 6)
    immo.date_mise_en_service = None
    schedule = build_amortissement_schedule(immo)
    assert schedule[0] == ("2026-Q1", Decimal("4804.86"))
    assert schedule[1] == ("2026-Q2", Decimal("5087.50"))
    assert schedule[0][1] + schedule[1][1] == Decimal("9892.36")


def test_duree_prorata():
    assert duree_prorata(date(2026, 1, 1), date(2026, 6, 30)) == (
        Decimal("180") / Decimal("360")
    ).quantize(Decimal("0.0000001"))


def test_period_bounds():
    assert period_bounds("trimestriel", 2026, 2) == (
        date(2026, 4, 1),
        date(2026, 6, 30),
        "2026-Q2",
    )
