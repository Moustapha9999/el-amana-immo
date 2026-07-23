"""Taux linéaire dérivé de la durée d'utilisation (source métier banque)."""

from decimal import Decimal


def taux_lineaire_from_duree_annees(annees: int | None) -> Decimal | None:
    if annees is None or annees <= 0:
        return None
    return (Decimal("100") / Decimal(annees)).quantize(Decimal("0.0001"))
