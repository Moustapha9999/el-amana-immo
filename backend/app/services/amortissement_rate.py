"""Taux linéaire — priorise le référentiel banque (Types), sinon 100/durée."""

from decimal import Decimal

from app.services.nature_immo_referentiel import bank_taux_for_duree


def taux_lineaire_from_duree_annees(annees: int | None) -> Decimal | None:
    """Taux annuel (%). Pour 3 ans → 33.33 (banque), pas 33.3333."""
    return bank_taux_for_duree(annees)
