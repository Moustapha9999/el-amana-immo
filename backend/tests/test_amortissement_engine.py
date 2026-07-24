"""Tests moteur amortissement — note Banque El Amana §2."""

from datetime import date
from decimal import Decimal

from app.models.enums import ModeAmortissement
from app.services.amortissement_engine import (
    build_amortissement_schedule,
    calcul_amortissement,
    days_360,
    duree_prorata,
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


def test_dates_arrete_etats_financiers():
    assert quarter_end(date(2025, 2, 10)) == date(2025, 3, 31)
    assert quarter_end(date(2025, 5, 15)) == date(2025, 6, 30)
    assert quarter_end(date(2025, 8, 1)) == date(2025, 9, 30)
    assert quarter_end(date(2025, 11, 20)) == date(2025, 12, 31)


def test_days_360_full_quarter():
    assert days_360(date(2026, 1, 1), date(2026, 4, 1)) == 90


def test_bank_example_acquisition_15_05_arrete_30_06():
    """Exemple note banque : acquisition 15/05/2025, arrêté 30/06/2025.

    Durée = jours entre 15/05 et 30/06 (base 30/360) = 46
    Amortissement = VB × Taux × (46/360)
    """
    jours = days_360(date(2025, 5, 15), date(2025, 7, 1))
    assert jours == 46
    vb = Decimal("100000")
    taux = Decimal("0.20")  # 20 %
    duree = Decimal(jours) / Decimal("360")
    assert calcul_amortissement(vb, taux, duree) == Decimal("2555.56")

    immo = FakeImmo()
    immo.valeur_brute = vb
    immo.taux = Decimal("20")
    immo.duree_annees = 5
    immo.duree_mois = 60
    immo.date_acquisition = date(2025, 5, 15)
    immo.date_mise_en_service = None
    schedule = build_amortissement_schedule(immo)
    assert schedule[0][0] == "2025-Q2"
    assert schedule[0][1] == Decimal("2555.56")


def test_formule_vb_taux_duree_trimestre_plein():
    """Amortissement = VB × Taux × Durée avec Durée = 90/360."""
    montant = calcul_amortissement(Decimal("100000"), Decimal("0.10"), Decimal("90") / Decimal("360"))
    assert montant == Decimal("2500.00")


def test_linear_quarterly_bank_formula_full_quarter():
    schedule = build_amortissement_schedule(FakeImmo())
    assert schedule[0] == ("2026-Q1", Decimal("2500.00"))
    total = sum(m for _, m in schedule)
    assert total == Decimal("100000.00")
    assert len(schedule) == 40  # 10 ans × 4 trimestres


def test_linear_quarterly_prorata_from_acquisition():
    immo = FakeImmo()
    immo.date_acquisition = date(2026, 2, 15)
    immo.date_mise_en_service = None
    jours = days_360(date(2026, 2, 15), date(2026, 4, 1))
    expect = calcul_amortissement(
        Decimal("100000"),
        Decimal("0.10"),
        Decimal(jours) / Decimal("360"),
    )
    schedule = build_amortissement_schedule(immo)
    assert schedule[0][0] == "2026-Q1"
    assert schedule[0][1] == expect


def test_cumul_and_vnc_identity():
    """VNC = VB − cumul à chaque étape du plan."""
    immo = FakeImmo()
    immo.valeur_brute = Decimal("85000")
    immo.taux = Decimal("20")
    immo.duree_annees = 5
    immo.duree_mois = 60
    immo.date_acquisition = date(2026, 1, 15)
    schedule = build_amortissement_schedule(immo)
    cumul = Decimal("0")
    vb = immo.valeur_brute
    for _, montant in schedule:
        cumul = (cumul + montant).quantize(Decimal("0.01"))
        vnc = (vb - cumul).quantize(Decimal("0.01"))
        assert vnc == vb - cumul
    assert cumul == vb


def test_duree_prorata_positive():
    d = duree_prorata(date(2025, 5, 15), date(2025, 6, 30))
    assert d > 0
    assert d == (Decimal("46") / Decimal("360")).quantize(Decimal("0.0000001"))
