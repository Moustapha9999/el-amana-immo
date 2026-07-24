from datetime import date
from decimal import Decimal

from app.models.enums import ModeAmortissement
from app.services.amortissement_engine import build_amortissement_schedule, days_360


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


def test_days_360_full_quarter():
    assert days_360(date(2026, 1, 1), date(2026, 4, 1)) == 90


def test_linear_quarterly_bank_formula_full_quarter():
    """Dotation = VA × taux × 90/360 — trimestre plein depuis le 01/01."""
    schedule = build_amortissement_schedule(FakeImmo())
    assert schedule[0] == ("2026-Q1", Decimal("2500.00"))
    total = sum(m for _, m in schedule)
    assert total == Decimal("100000.00")
    assert len(schedule) == 40  # 10 ans × 4 trimestres


def test_linear_quarterly_prorata_from_acquisition():
    """Acquisition en cours de trimestre : jours 30/360 depuis la date d'acquisition."""
    immo = FakeImmo()
    immo.date_acquisition = date(2026, 2, 15)
    immo.date_mise_en_service = None
    jours = days_360(date(2026, 2, 15), date(2026, 4, 1))
    expect = (Decimal("100000") * Decimal("10") / Decimal("100") * Decimal(jours) / Decimal("360")).quantize(
        Decimal("0.01")
    )
    schedule = build_amortissement_schedule(immo)
    assert schedule[0][0] == "2026-Q1"
    assert schedule[0][1] == expect
