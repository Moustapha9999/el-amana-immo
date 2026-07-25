"""Tests unitaires — récapitulatif tableau d'amortissement."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.services.recap_amortissement import _mouvements_immo, compte_immo_in_scope, dotation_exercice


def _immo(**kwargs):
    base = dict(
        date_acquisition=date(2025, 1, 1),
        date_fin=None,
        valeur_brute=Decimal("100000.00"),
        valeur_residuelle=Decimal("0"),
        taux=Decimal("10.0000"),
        duree_annees=10,
        duree_mois=0,
        compte_immobilisation="142041",
        compte_amortissement="148240",
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_compte_scope():
    assert compte_immo_in_scope("142000")
    assert compte_immo_in_scope("147030")
    assert compte_immo_in_scope("145300")
    assert not compte_immo_in_scope("148240")
    assert not compte_immo_in_scope("140000")


def test_dotation_exercice_sum_of_year_periods():
    """Sans filtre comptabilisé : somme des trimestres du plan théorique."""
    immo = _immo(date_acquisition=date(2024, 1, 1))
    assert dotation_exercice(immo, 2025) == Decimal("10000.00")


def test_dotation_exercice_only_comptabilisees():
    immo = _immo(date_acquisition=date(2024, 1, 1))
    # Uniquement les montants validés fournis — pas de repli sur le plan théorique
    assert (
        dotation_exercice(
            immo,
            2026,
            montants_db=[Decimal("4804.86"), Decimal("5087.50")],
            uniquement_comptabilisees=True,
        )
        == Decimal("9892.36")
    )
    assert (
        dotation_exercice(immo, 2026, montants_db=[], uniquement_comptabilisees=True)
        == Decimal("0.00")
    )


def test_dotation_exercice_from_db_lines():
    immo = _immo(date_acquisition=date(2024, 1, 1))
    assert dotation_exercice(
        immo,
        2026,
        montants_db=[Decimal("2500"), Decimal("2500"), Decimal("2500"), Decimal("2500")],
    ) == Decimal("10000.00")


def test_mouvements_held_full_year():
    immo = _immo(date_acquisition=date(2024, 1, 1))
    # Sans lignes comptabilisées → dotation = 0
    mvts = _mouvements_immo(immo, 2025, montants_dotation_db=[])
    assert mvts is not None
    assert mvts["valeur_brute"] == Decimal("100000.00")
    assert mvts["cessions_annee"] == Decimal("0.00")
    assert mvts["dotations_annee"] == Decimal("0.00")
    assert mvts["amorts_cumules_n"] == mvts["amorts_cumules_n1"]


def test_mouvements_dotations_comptabilisees():
    immo = _immo(date_acquisition=date(2026, 1, 6))
    mvts = _mouvements_immo(
        immo,
        2026,
        montants_dotation_db=[Decimal("4804.86"), Decimal("5087.50")],
    )
    assert mvts is not None
    assert mvts["dotations_annee"] == Decimal("9892.36")
    assert mvts["amorts_cumules_n"] == Decimal("9892.36")


def test_mouvements_cession_year():
    immo = _immo(date_acquisition=date(2024, 1, 1), date_fin=date(2025, 6, 30))
    mvts = _mouvements_immo(immo, 2025, montants_dotation_db=[Decimal("5000.00")])
    assert mvts is not None
    assert mvts["valeur_brute"] == Decimal("0.00")
    assert mvts["cessions_annee"] > 0
    assert mvts["dotations_annee"] == Decimal("5000.00")
    assert mvts["amorts_cumules_n"] == (
        mvts["amorts_cumules_n1"] - mvts["cessions_annee"] + mvts["dotations_annee"]
    ).quantize(Decimal("0.01"))


def test_mouvements_exited_before_year_excluded():
    immo = _immo(date_acquisition=date(2023, 1, 1), date_fin=date(2024, 12, 31))
    assert _mouvements_immo(immo, 2025) is None
