"""Nombres BEA DIGITAL.

Montants et prix : 2 décimales, virgule (``4 500,00``) — restent des ``Decimal``.
Quantités, stocks, entrées, sorties : 3 décimales max. (``1``, ``50000``, ``41,19``),
précision des colonnes ``Numeric(18, 3)``. Une quantité entière reste un entier
partout (JSON, Excel, audit) ; seule une vraie décimale apparaît comme telle.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated, Any

from pydantic import BeforeValidator, PlainSerializer

QTY_DEC = Decimal("0.001")


def as_qty_dec(value: Any) -> Decimal:
    """Quantité arrondie à 3 décimales (half-up), en ``Decimal`` pour les calculs."""
    if isinstance(value, bool) or value is None or value == "":
        raise ValueError("quantité invalide")
    try:
        number = Decimal(str(value).replace(" ", "").replace(",", "."))
    except Exception as exc:
        raise ValueError("quantité invalide") from exc
    if not number.is_finite():
        raise ValueError("quantité invalide")
    return number.quantize(QTY_DEC, rounding=ROUND_HALF_UP)


def as_qty_dec_positive(value: Any) -> Decimal:
    number = as_qty_dec(value)
    if number <= 0:
        raise ValueError("la quantité doit être supérieure à 0")
    return number


def as_qty_dec_non_negative(value: Any) -> Decimal:
    number = as_qty_dec(value)
    if number < 0:
        raise ValueError("la quantité ne peut pas être négative")
    return number


def qty_json(value: Any) -> int | float:
    """Valeur sérialisable (JSON, Excel, audit) : ``12`` reste ``12``, ``41.190`` devient ``41.19``."""
    number = as_qty_dec(value)
    return int(number) if number == number.to_integral_value() else float(number)


def as_qty(value: Any) -> int | float:
    """Quantité ou stock arrondi à 3 décimales, sous forme sérialisable (voir ``qty_json``)."""
    return qty_json(value)


def format_qty(value: Any) -> str:
    """41.190 → « 41,19 » ; 12.000 → « 12 » (séparateur décimal virgule)."""
    try:
        number = as_qty_dec(value if value not in (None, "") else 0)
    except ValueError:
        return "—"
    text = f"{number:f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",")


def format_qty_signe(value: Any) -> str:
    """Écart signé : « +3 », « -41,19 », « +0 »."""
    text = format_qty(value)
    return text if text.startswith("-") else f"+{text}"


_serialiser = PlainSerializer(qty_json, return_type=int | float)

QtyDec = Annotated[Decimal, BeforeValidator(as_qty_dec), _serialiser]
QtyDecPos = Annotated[Decimal, BeforeValidator(as_qty_dec_positive), _serialiser]
QtyDecGe0 = Annotated[Decimal, BeforeValidator(as_qty_dec_non_negative), _serialiser]

Qty = QtyDec
QtyPos = QtyDecPos
QtyGe0 = QtyDecGe0
