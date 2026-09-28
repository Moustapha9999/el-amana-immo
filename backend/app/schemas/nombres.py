"""Nombres BEA DIGITAL.

Montants et prix : 2 décimales, virgule (``4 500,00``) — restent des ``Decimal``.
Quantités, stocks, entrées, sorties : entiers (``1``, ``100``, ``50000``).
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated, Any

from pydantic import BeforeValidator


def as_qty(value: Any) -> int:
    """Arrondit une quantité ou un stock à l'entier le plus proche."""
    if isinstance(value, bool) or value is None or value == "":
        raise ValueError("quantité invalide")
    try:
        number = Decimal(str(value).replace(" ", "").replace(",", "."))
    except Exception as exc:
        raise ValueError("quantité invalide") from exc
    return int(number.to_integral_value(rounding=ROUND_HALF_UP))


def as_qty_positive(value: Any) -> int:
    number = as_qty(value)
    if number <= 0:
        raise ValueError("la quantité doit être un entier supérieur à 0")
    return number


def as_qty_non_negative(value: Any) -> int:
    number = as_qty(value)
    if number < 0:
        raise ValueError("la quantité ne peut pas être négative")
    return number


Qty = Annotated[int, BeforeValidator(as_qty)]
QtyPos = Annotated[int, BeforeValidator(as_qty_positive)]
QtyGe0 = Annotated[int, BeforeValidator(as_qty_non_negative)]
