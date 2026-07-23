from datetime import date
from decimal import Decimal

from app.models.enums import ModeAmortissement
from app.services.amortissement_engine import build_amortissement_schedule


class FakeImmo:
    valeur_brute = Decimal("120000")
    valeur_residuelle = Decimal("0")
    duree_mois = 36
    duree_annees = 3
    date_acquisition = date(2026, 1, 1)
    date_mise_en_service = date(2026, 1, 1)
    periodicite = "annuel"
    prorata_temporis = False
    mode_amortissement = ModeAmortissement.LINEAIRE
    taux = Decimal("33.3333")


def test_linear_annual_schedule_sums_to_base():
    schedule = build_amortissement_schedule(FakeImmo())
    assert len(schedule) == 3
    total = sum(m for _, m in schedule)
    assert total == Decimal("120000.00")
