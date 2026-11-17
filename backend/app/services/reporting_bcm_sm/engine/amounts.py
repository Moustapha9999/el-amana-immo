"""Bases de montants — pas de MAX universel (T2 §5).

D15 (Cellules SM) : solde débiteur = Σ DEB, solde créditeur = Σ CRE,
solde net = DEB−CRE. Le catalogue officiel utilise det_basis (RAW), pas SD/SC NATURAL.
"""

from __future__ import annotations

from decimal import Decimal

ZERO = Decimal("0")
Q2 = Decimal("0.01")


def quantize_mru(value: Decimal) -> Decimal:
    return value.quantize(Q2)


def amount_for_basis(
    *,
    debit: Decimal,
    credit: Decimal,
    amount_basis: str,
    signed_balance_mode: str = "NATURAL",
) -> Decimal:
    d = debit or ZERO
    c = credit or ZERO
    basis = (amount_basis or "SIGNED").upper()
    mode = (signed_balance_mode or "NATURAL").upper()

    if basis == "D":
        return quantize_mru(d)
    if basis == "C":
        return quantize_mru(c)
    if basis == "SIGNED":
        return quantize_mru(d - c)
    if basis == "SD":
        if mode == "NATURAL":
            return quantize_mru(max(d - c, ZERO))
        if mode == "RAW_POSITIVE_LEG":
            # D15 ouverte : traitement provisoire documenté — jambe débitrice brute
            return quantize_mru(d)
        return quantize_mru(max(d - c, ZERO))
    if basis == "SC":
        if mode == "NATURAL":
            return quantize_mru(max(c - d, ZERO))
        if mode == "RAW_POSITIVE_LEG":
            return quantize_mru(c)
        return quantize_mru(max(c - d, ZERO))
    raise ValueError(f"amount_basis inconnu : {amount_basis}")
