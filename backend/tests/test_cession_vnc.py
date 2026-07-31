"""Tests cession — VNC à date, PV/MV, formule banque."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.models.enums import ModeAmortissement
from app.services.amortissement_engine import cumul_amortissement_a_date, vnc_a_date
from app.services.immobilisation_vnc import cumul_cession_depuis_stock
from app.services.operations_service import _resultat_cession


class FakeImmo:
    valeur_brute = Decimal("85000")
    valeur_residuelle = Decimal("0")
    duree_mois = 60
    duree_annees = 5
    date_acquisition = date(2026, 1, 15)
    date_mise_en_service = date(2026, 1, 20)
    periodicite = "trimestriel"
    prorata_temporis = True
    mode_amortissement = ModeAmortissement.LINEAIRE
    taux = Decimal("20")
    metadata_json = None


def test_resultat_plus_value():
    resultat, pv, mv, cas = _resultat_cession(Decimal("90000"), Decimal("80000"))
    assert cas == "plus_value"
    assert pv == Decimal("10000.00")
    assert mv == Decimal("0.00")
    assert resultat == Decimal("10000.00")


def test_resultat_moins_value():
    resultat, pv, mv, cas = _resultat_cession(Decimal("70000"), Decimal("80000"))
    assert cas == "moins_value"
    assert pv == Decimal("0.00")
    assert mv == Decimal("10000.00")
    assert resultat == Decimal("-10000.00")


def test_resultat_equilibre():
    resultat, pv, mv, cas = _resultat_cession(Decimal("80000"), Decimal("80000"))
    assert cas == "equilibre"
    assert pv == mv == resultat == Decimal("0.00")


def test_vnc_a_date_cession_after_full_q1():
    """Cession au 31/03 : cumul = amortissement Q1 prorata depuis le 15/01."""
    immo = FakeImmo()
    cumul, vnc = vnc_a_date(immo, date(2026, 3, 31))
    assert cumul > 0
    assert vnc == (immo.valeur_brute - cumul).quantize(Decimal("0.01"))
    # Même montant que la 1re ligne du plan (arrêté 31/03)
    assert cumul == cumul_amortissement_a_date(immo, date(2026, 3, 31))


def test_vnc_a_date_before_acquisition_is_zero_cumul():
    immo = FakeImmo()
    cumul = cumul_amortissement_a_date(immo, date(2025, 12, 31))
    assert cumul == Decimal("0.00")


def test_vnc_mid_quarter_less_than_full_quarter():
    immo = FakeImmo()
    cumul_mid = cumul_amortissement_a_date(immo, date(2026, 2, 15))
    cumul_q1 = cumul_amortissement_a_date(immo, date(2026, 3, 31))
    assert 0 < cumul_mid < cumul_q1


def test_cession_stock_banque_utilise_amt_fin_2025():
    """TF 13383 : cumul cession = 120 000 (fin 2025), pas le théorique 161 000."""
    immo = FakeImmo()
    immo.valeur_brute = Decimal("3000000")
    immo.taux = Decimal("4")
    immo.duree_annees = 25
    immo.duree_mois = 300
    immo.date_acquisition = date(2024, 12, 19)
    immo.date_mise_en_service = date(2024, 12, 19)
    immo.metadata_json = {
        "bank": {
            "amt_n1": "120000.00",
            "amt_fin": "120000.00",
            "dotation": "0",
            "vnc": "2880000.00",
        }
    }
    amorts = [
        SimpleNamespace(
            periode="2026-Q1",
            montant=Decimal("0.00"),
            cumul=Decimal("120000.00"),
            valide=True,
            annule=False,
            simule=False,
        ),
        SimpleNamespace(
            periode="2026-Q2",
            montant=Decimal("0.00"),
            cumul=Decimal("120000.00"),
            valide=True,
            annule=False,
            simule=False,
        ),
    ]
    cumul = cumul_cession_depuis_stock(immo, date(2026, 4, 21), amorts)
    assert cumul == Decimal("120000.00")
    assert vnc_a_date(immo, date(2026, 4, 21))[0] == Decimal("161000.00")
