from decimal import Decimal

from app.services.compte_nature_service import suggest_paired_accounts
from app.services.nature_immo_referentiel import bank_taux_for_duree, normalize_taux_for_categorie


def test_suggest_paired_accounts_officiels():
    assert suggest_paired_accounts("147030") == ("148030", "681030")
    assert suggest_paired_accounts("142010") == ("148211", "681211")
    assert suggest_paired_accounts("142041") == ("148240", "681240")


def test_bank_taux_3_ans_est_33_33():
    assert bank_taux_for_duree(3) == Decimal("33.3300")


def test_normalize_excel_33_frais():
    assert normalize_taux_for_categorie("TY-147030", Decimal("33")) == Decimal("33.3300")
    assert normalize_taux_for_categorie("TY-147050", Decimal("33.00")) == Decimal("33.3300")
