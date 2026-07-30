from decimal import Decimal
from types import SimpleNamespace

from app.services.ecriture_sortie import plan_ecritures_cession, plan_ecritures_rebut


def _immo(compte_immo="142041", compte_amort="148240"):
    return SimpleNamespace(compte_immobilisation=compte_immo, compte_amortissement=compte_amort, categorie=None)


def test_cession_plus_value_generates_three_lines():
    lines = plan_ecritures_cession(
        _immo(),
        cumul=Decimal("40000"),
        valeur_brute=Decimal("120000"),
        vnc=Decimal("80000"),
        prix_cession=Decimal("95000"),
        plus_value=Decimal("15000"),
        moins_value=Decimal("0"),
    )
    amounts = {credit: montant for _, credit, montant, _ in lines}
    assert amounts.get("775000") == Decimal("15000")


def test_rebut_covers_vnc_and_cumul():
    lines = plan_ecritures_rebut(_immo(), cumul=Decimal("30000"), vnc=Decimal("70000"))
    total_credit_immo = sum(m for _, c, m, _ in lines if c == "142041")
    assert total_credit_immo == Decimal("100000")
