"""Légende D15 — agrégation BAL DET (Cellules SM, oct. 2026).

- solde débiteur = Σ DEB des comptes retenus
- solde créditeur = Σ CRE
- solde net = DEB − CRE
- en devises = devise ∉ {MRU, MRO}

Aucune base SD/SC « naturelle » (max(net, 0)) n'est utilisée ici.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.services.reporting_bcm_sm.engine.amounts import ZERO, quantize_mru

LOCAL_CURRENCIES = frozenset({"MRU", "MRO"})
BASIS_DEBIT = "DEBIT"
BASIS_CREDIT = "CREDIT"
BASIS_NET = "NET"
BASIS_CREDIT_MINUS_DEBIT = "CREDIT_MINUS_DEBIT"


@dataclass(frozen=True)
class DetLine:
    ncg: str
    compte: str
    libelle: str
    devise: str | None
    debit: Decimal
    credit: Decimal


def digits_only(value: str | None) -> str:
    if not value:
        return ""
    return "".join(ch for ch in str(value) if ch.isdigit())


def is_fx(devise: str | None) -> bool:
    if not devise:
        return False
    return devise.strip().upper() not in LOCAL_CURRENCIES


def line_from_row(row: dict) -> DetLine | None:
    ncg = (row.get("ncg") or "").strip()
    if not ncg:
        return None
    debit = row.get("debit")
    credit = row.get("credit")
    return DetLine(
        ncg=ncg,
        compte=(row.get("compte") or "").strip(),
        libelle=(row.get("libelle") or "").strip(),
        devise=(row.get("devise") or None),
        debit=debit if isinstance(debit, Decimal) else Decimal(str(debit or 0)),
        credit=credit if isinstance(credit, Decimal) else Decimal(str(credit or 0)),
    )


def lines_from_rows(rows: list[dict]) -> list[DetLine]:
    out: list[DetLine] = []
    for row in rows:
        line = line_from_row(row)
        if line is not None:
            out.append(line)
    return out


def account_matches(line: DetLine, accounts: tuple[str, ...]) -> bool:
    if not accounts:
        return True
    compte_d = digits_only(line.compte)
    lib_d = digits_only(line.libelle)
    for raw in accounts:
        want = digits_only(raw) or raw.strip()
        if not want:
            continue
        if line.compte == raw or line.compte.endswith(raw):
            return True
        if want and (compte_d == want or compte_d.endswith(want) or want in lib_d):
            return True
    return False


def ncg_matches(
    ncg: str,
    *,
    ncgs: tuple[str, ...] = (),
    ncg_class: str | None = None,
) -> bool:
    if ncg_class:
        return bool(ncg) and ncg[0] == ncg_class
    if not ncgs:
        return True
    return ncg in ncgs


def currency_ok(line: DetLine, currency: str) -> bool:
    mode = (currency or "ALL").upper()
    if mode == "FX":
        return is_fx(line.devise)
    if mode == "LOCAL":
        return not is_fx(line.devise)
    return True


def amount_of(line: DetLine, basis: str) -> Decimal:
    d = line.debit or ZERO
    c = line.credit or ZERO
    b = (basis or BASIS_NET).upper()
    if b == BASIS_DEBIT:
        return d
    if b == BASIS_CREDIT:
        return c
    if b == BASIS_CREDIT_MINUS_DEBIT:
        return c - d
    if b == BASIS_NET:
        return d - c
    raise ValueError(f"basis DET inconnue : {basis}")


def aggregate(
    lines: list[DetLine],
    *,
    ncgs: tuple[str, ...] = (),
    ncg_class: str | None = None,
    accounts: tuple[str, ...] = (),
    currency: str = "ALL",
    basis: str = BASIS_NET,
    sign: int = 1,
) -> tuple[Decimal, int]:
    """Retourne (montant quantifié, nombre de lignes retenues)."""
    total = ZERO
    matched = 0
    for line in lines:
        if not ncg_matches(line.ncg, ncgs=ncgs, ncg_class=ncg_class):
            continue
        if not currency_ok(line, currency):
            continue
        if not account_matches(line, accounts):
            continue
        total += amount_of(line, basis)
        matched += 1
    return quantize_mru(total * Decimal(sign)), matched
