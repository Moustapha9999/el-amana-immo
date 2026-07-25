"""Tests moteur amortissement — note Banque El Amana §2 + Excel DAYS360."""

from datetime import date
from decimal import Decimal

from app.models.enums import ModeAmortissement
from app.services.amortissement_engine import (
    build_amortissement_schedule,
    calcul_amortissement,
    calcul_dotation_periode,
    days_360,
    duree_prorata,
    jours_commerciaux_periode,
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


def test_dates_arrete_etats_financiers():
    assert quarter_end(date(2025, 2, 10)) == date(2025, 3, 31)
    assert quarter_end(date(2025, 5, 15)) == date(2025, 6, 30)
    assert quarter_end(date(2025, 8, 1)) == date(2025, 9, 30)
    assert quarter_end(date(2025, 11, 20)) == date(2025, 12, 31)


def test_days_360_full_quarter():
    assert days_360(date(2026, 1, 1), date(2026, 4, 1)) == 90


def test_jours_commerciaux_periode_pleine_et_prorata():
    assert jours_commerciaux_periode(date(2026, 4, 1), date(2026, 4, 1), date(2026, 6, 30)) == 90
    assert jours_commerciaux_periode(date(2026, 6, 26), date(2026, 4, 1), date(2026, 6, 30)) == 4


def test_bank_excel_construction_26_06_arrete_30_06():
    """Tableau amortissement construction Excel : 26/06/2026 → 30/06/2026.

    VB 6 405 768 × 4 % × (4/360) = 2 847,01
    """
    jours = jours_commerciaux_periode(date(2026, 6, 26), date(2026, 4, 1), date(2026, 6, 30))
    assert jours == 4
    vb = Decimal("6405768.00")
    taux = Decimal("0.04")
    duree = Decimal(jours) / Decimal("360")
    assert calcul_amortissement(vb, taux, duree) == Decimal("2847.01")

    immo = FakeImmo()
    immo.valeur_brute = vb
    immo.taux = Decimal("4")
    immo.duree_annees = 25
    immo.duree_mois = 300
    immo.date_acquisition = date(2026, 6, 26)
    immo.date_mise_en_service = None
    schedule = build_amortissement_schedule(immo)
    assert schedule[0][0] == "2026-Q2"
    assert schedule[0][1] == Decimal("2847.01")


def test_bank_example_acquisition_15_05_arrete_30_06():
    """Acquisition 15/05, arrêté 30/06 — Excel DAYS360 = 45 jours."""
    jours = jours_commerciaux_periode(date(2025, 5, 15), date(2025, 4, 1), date(2025, 6, 30))
    assert jours == 45
    vb = Decimal("100000")
    taux = Decimal("0.20")
    duree = Decimal(jours) / Decimal("360")
    assert calcul_amortissement(vb, taux, duree) == Decimal("2500.00")

    immo = FakeImmo()
    immo.valeur_brute = vb
    immo.taux = Decimal("20")
    immo.duree_annees = 5
    immo.duree_mois = 60
    immo.date_acquisition = date(2025, 5, 15)
    immo.date_mise_en_service = None
    schedule = build_amortissement_schedule(immo)
    assert schedule[0][0] == "2025-Q2"
    assert schedule[0][1] == Decimal("2500.00")


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
    jours = jours_commerciaux_periode(date(2026, 2, 15), date(2026, 1, 1), date(2026, 3, 31))
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
    assert d == (Decimal("45") / Decimal("360")).quantize(Decimal("0.0000001"))


def test_period_bounds_mensuel_trimestriel_annuel():
    debut, fin, key = period_bounds("mensuel", 2026, 7)
    assert (debut, fin, key) == (date(2026, 7, 1), date(2026, 7, 31), "2026-07")

    debut, fin, key = period_bounds("trimestriel", 2026, 2)
    assert (debut, fin, key) == (date(2026, 4, 1), date(2026, 6, 30), "2026-Q2")

    debut, fin, key = period_bounds("annuel", 2026, 1)
    assert (debut, fin, key) == (date(2026, 1, 1), date(2026, 12, 31), "2026")


def test_calcul_dotation_periode_ignore_vnc_zero():
    immo = FakeImmo()
    assert calcul_dotation_periode(immo, date(2026, 1, 1), date(2026, 3, 31), Decimal("100000")) is None


def test_calcul_dotation_periode_trimestre_plein():
    immo = FakeImmo()
    result = calcul_dotation_periode(immo, date(2026, 1, 1), date(2026, 3, 31), Decimal("0"))
    assert result is not None
    montant, cumul, vnc = result
    assert montant == Decimal("2500.00")
    assert cumul == Decimal("2500.00")
    assert vnc == Decimal("97500.00")


def test_calcul_dotation_periode_plafond_vnc():
    """Si la dotation théorique dépasse la VNC restante, plafonner → VNC finale = 0."""
    immo = FakeImmo()
    # VNC restante = 400 ; trimestre plein = 2500 → plafonné à 400
    result = calcul_dotation_periode(immo, date(2026, 1, 1), date(2026, 3, 31), Decimal("99600"))
    assert result is not None
    montant, cumul, vnc = result
    assert montant == Decimal("400.00")
    assert cumul == Decimal("100000.00")
    assert vnc == Decimal("0.00")


def test_calcul_dotation_periode_mensuel():
    immo = FakeImmo()
    result = calcul_dotation_periode(immo, date(2026, 7, 1), date(2026, 7, 31), Decimal("0"))
    assert result is not None
    montant, _, _ = result
    # 30/360 × 10 % × 100000 = 833.33
    assert montant == Decimal("833.33")


def test_calcul_dotation_periode_construction_excel():
    immo = FakeImmo()
    immo.valeur_brute = Decimal("6405768.00")
    immo.taux = Decimal("4")
    immo.duree_annees = 25
    immo.duree_mois = 300
    immo.date_acquisition = date(2026, 6, 26)
    result = calcul_dotation_periode(immo, date(2026, 4, 1), date(2026, 6, 30), Decimal("0"))
    assert result is not None
    montant, cumul, vnc = result
    assert montant == Decimal("2847.01")
    assert cumul == Decimal("2847.01")
    assert vnc == Decimal("6402920.99")
