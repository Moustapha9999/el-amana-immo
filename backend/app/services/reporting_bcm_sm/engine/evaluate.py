"""Évaluation du catalogue Cellules SM sur les lignes BAL DET."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.services.reporting_bcm_sm.engine.amounts import ZERO, quantize_mru
from app.services.reporting_bcm_sm.engine.det_basis import DetLine, aggregate, term_ncg_coverage
from app.services.reporting_bcm_sm.engine.rules_catalog import (
    ALL_RULES,
    CellRule,
    ORIGIN_ADJUST,
    ORIGIN_COPY,
    ORIGIN_MANUAL,
    ORIGIN_PCT,
    ORIGIN_REMAINDER,
)

STATUS_AUTO = "AUTOMATIQUE"
STATUS_MANUAL = "SAISIE_MANUELLE"
STATUS_ADJUST = "A_AJUSTER"
STATUS_MISSING = "NON_RENSEIGNE"
STATUS_CORR = "CORRECTION_MANUELLE"

# Totaux structurels utiles aux copies (ETAT C 209, hors-bilan 520).
CHILD_CODES: dict[str, tuple[str, ...]] = {
    "A:326": ("A:327", "A:328", "A:329", "A:330"),
    "A:511": ("A:512", "A:513"),
    "A:514": ("A:515", "A:516"),
    "A:509": ("A:510", "A:511", "A:514", "A:517", "A:518"),
}


@dataclass
class CellValue:
    key: str
    calculated: Decimal | None
    retained: Decimal | None
    status: str
    origin: str
    traces: list = field(default_factory=list)


def _as_dec(value: Decimal | int | str | None) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return quantize_mru(value)
    return quantize_mru(Decimal(str(value)))


def _get(values: dict[str, CellValue], key: str) -> Decimal:
    cell = values.get(key)
    if cell is None:
        return ZERO
    if cell.retained is not None:
        return cell.retained
    if cell.calculated is not None:
        return cell.calculated
    return ZERO


def _present(values: dict[str, CellValue], key: str) -> bool:
    cell = values.get(key)
    if cell is None:
        return False
    return cell.retained is not None or cell.calculated is not None


def _eval_terms(rule: CellRule, lines: list[DetLine]) -> tuple[Decimal, list]:
    total = ZERO
    traces: list = []
    for term in rule.terms:
        amount, n = aggregate(
            lines,
            ncgs=term.ncgs,
            ncg_class=term.ncg_class,
            accounts=term.accounts,
            currency=term.currency,
            basis=term.basis,
            sign=term.sign,
        )
        total += amount
        coverage = term_ncg_coverage(
            lines,
            ncgs=term.ncgs,
            accounts=term.accounts,
            currency=term.currency,
            basis=term.basis,
            sign=term.sign,
        )
        present = sum(1 for row in coverage if row["status"] == "PRESENT")
        absent = sum(1 for row in coverage if row["status"] == "ABSENT")
        traces.append(
            {
                "ncgs": list(term.ncgs) or None,
                "class": term.ncg_class,
                "accounts": list(term.accounts) or None,
                "currency": term.currency,
                "basis": term.basis,
                "sign": term.sign,
                "amount": str(amount),
                "lines": n,
                "ncg_present": present,
                "ncg_absent": absent,
                "coverage": coverage,
            }
        )
    return quantize_mru(total), traces


def mapping_coverage(values: dict[str, CellValue]) -> dict[str, list]:
    """Rubriques du mapping absentes, ou présentes avec un montant nul.

    Une rubrique absente ne retire pas les autres termes de la cellule.
    Un montant nul sur une rubrique présente n'est pas une absence.
    """
    absent: list[dict] = []
    present_zero: list[dict] = []
    filtered: list[dict] = []
    for key, cell in values.items():
        for step in cell.traces:
            if not isinstance(step, dict):
                continue
            for row in step.get("coverage") or []:
                item = {
                    "cell": key,
                    "ncg": row["ncg"],
                    "basis": step.get("basis"),
                    "sign": step.get("sign"),
                    "lines": row["lines"],
                    "debit": row["debit"],
                    "credit": row["credit"],
                    "amount": row["amount"],
                }
                status = row["status"]
                if status == "ABSENT":
                    absent.append(item)
                elif status == "FILTERED":
                    filtered.append(item)
                elif status == "PRESENT" and Decimal(row["amount"]) == 0:
                    present_zero.append(item)
    return {"absent": absent, "present_zero": present_zero, "filtered": filtered}


def _apply_links(
    rule: CellRule,
    base: Decimal,
    values: dict[str, CellValue],
    params: dict[str, Decimal | None],
) -> Decimal:
    total = base
    for key in rule.plus_cells:
        total += _get(values, key)
    for key in rule.minus_cells:
        total -= _get(values, key)
    if rule.plus_param:
        extra = params.get(rule.plus_param)
        if extra is not None:
            total += extra
    if rule.minus_param:
        extra = params.get(rule.minus_param)
        if extra is not None:
            total -= extra
    return quantize_mru(total)


def _eval_rule(
    rule: CellRule,
    lines: list[DetLine],
    values: dict[str, CellValue],
    params: dict[str, Decimal | None],
) -> tuple[Decimal | None, list]:
    if rule.origin == ORIGIN_MANUAL:
        param_code = rule.param_code
        if param_code and params.get(param_code) is not None:
            return params[param_code], [{"param": param_code, "value": str(params[param_code])}]
        return None, [{"manual": True, "param": param_code}]

    if rule.origin == ORIGIN_COPY:
        if not rule.copy_from:
            return ZERO, []
        total = ZERO
        traces = []
        for src in rule.copy_from:
            part = _get(values, src) if _present(values, src) else ZERO
            total += part
            traces.append({"copy": src, "amount": str(part)})
        return quantize_mru(total), traces

    if rule.origin == ORIGIN_PCT:
        base = ZERO
        traces = []
        for src in rule.pct_sources:
            part = _get(values, src)
            base += part
            traces.append({"source": src, "amount": str(part)})
        pct = rule.pct or Decimal("0")
        return quantize_mru(base * pct), traces + [{"pct": str(pct)}]

    if rule.origin == ORIGIN_REMAINDER:
        total = ZERO
        traces = []
        for src in rule.remainder_total:
            part = _get(values, src)
            total += part
            traces.append({"total": src, "amount": str(part)})
        for src in rule.minus_cells:
            part = _get(values, src)
            total -= part
            traces.append({"minus": src, "amount": str(part)})
        return quantize_mru(total), traces

    base, traces = _eval_terms(rule, lines)
    return _apply_links(rule, base, values, params), traces


def _status_for(rule: CellRule, calculated: Decimal | None, decided: bool, from_param: bool) -> str:
    if decided:
        return STATUS_CORR
    if rule.origin == ORIGIN_MANUAL:
        if calculated is not None:
            return STATUS_MANUAL
        return STATUS_MISSING
    if rule.origin == ORIGIN_ADJUST:
        return STATUS_ADJUST
    if calculated is None:
        return STATUS_MISSING
    if from_param:
        return STATUS_MANUAL
    return STATUS_AUTO


def _fill_child_sums(values: dict[str, CellValue]) -> None:
    cols = "CDEFG"
    for _ in range(3):
        for parent, children in CHILD_CODES.items():
            for col in cols + "H":
                key = f"{parent}:{col}"
                if key in values and values[key].calculated is not None:
                    continue
                total = ZERO
                seen = False
                for child in children:
                    ck = f"{child}:{col}" if col != "H" else f"{child}:H"
                    if col == "H":
                        part = ZERO
                        child_seen = False
                        for c in cols:
                            leaf = f"{child}:{c}"
                            if _present(values, leaf):
                                part += _get(values, leaf)
                                child_seen = True
                        if _present(values, f"{child}:H"):
                            part = _get(values, f"{child}:H")
                            child_seen = True
                        if child_seen:
                            total += part
                            seen = True
                    elif _present(values, ck):
                        total += _get(values, ck)
                        seen = True
                if seen:
                    amount = quantize_mru(total)
                    values[key] = CellValue(
                        key=key,
                        calculated=amount,
                        retained=amount,
                        status=STATUS_AUTO,
                        origin=ORIGIN_COPY,
                        traces=[{"child_sum": list(children), "col": col}],
                    )


def _fill_line_totals(values: dict[str, CellValue]) -> None:
    prefixes: set[str] = set()
    for key in values:
        parts = key.split(":")
        # H = total de ligne seulement sur ETAT A. Sur ETAT B, H = non-résidents.
        if len(parts) == 3 and parts[0] == "A":
            prefixes.add(f"{parts[0]}:{parts[1]}")
    for prefix in prefixes:
        hkey = f"{prefix}:H"
        if hkey in values and values[hkey].calculated is not None:
            continue
        total = ZERO
        seen = False
        for col in "CDEFG":
            k = f"{prefix}:{col}"
            if _present(values, k):
                total += _get(values, k)
                seen = True
        if seen:
            amount = quantize_mru(total)
            values[hkey] = CellValue(
                key=hkey,
                calculated=amount,
                retained=amount,
                status=STATUS_AUTO,
                origin=ORIGIN_COPY,
                traces=[{"line_total": True}],
            )


def evaluate_sm(
    lines: list[DetLine],
    *,
    params: dict[str, Decimal | None] | None = None,
    decisions: dict[str, Decimal] | None = None,
    rules: tuple[CellRule, ...] | None = None,
) -> dict[str, CellValue]:
    """Calcule les cellules du catalogue. Les décisions écrasent le retenu, pas le calculé.

    ``rules`` = catalogue effectif (ALL_RULES + orientations VALIDE_ACTIF fusionnées).
    Par défaut : catalogue central seul.
    """
    catalog = rules if rules is not None else ALL_RULES
    params = {k: _as_dec(v) for k, v in (params or {}).items()}
    decided: dict[str, Decimal] = {}
    for key, raw in (decisions or {}).items():
        parsed = _as_dec(raw)
        if parsed is not None:
            decided[key] = parsed
    values: dict[str, CellValue] = {}

    for _pass in range(8):
        changed = False
        for rule in catalog:
            calculated, traces = _eval_rule(rule, lines, values, params)
            from_param = False
            if rule.origin == ORIGIN_MANUAL and calculated is not None:
                from_param = True
            decided_val = decided.get(rule.key)
            retained = decided_val if decided_val is not None else calculated
            status = _status_for(rule, calculated, decided_val is not None, from_param)
            prev = values.get(rule.key)
            if (
                prev
                and prev.calculated == calculated
                and prev.retained == retained
                and prev.status == status
            ):
                continue
            values[rule.key] = CellValue(
                key=rule.key,
                calculated=calculated,
                retained=retained,
                status=status,
                origin=rule.origin,
                traces=traces,
            )
            changed = True
        if not changed:
            break
        _fill_line_totals(values)
        _fill_child_sums(values)

    _fill_line_totals(values)
    _fill_child_sums(values)
    _fill_line_totals(values)

    for key, val in list(decided.items()):
        if key in values:
            cell = values[key]
            values[key] = CellValue(
                key=key,
                calculated=cell.calculated,
                retained=val,
                status=STATUS_CORR,
                origin=cell.origin,
                traces=list(cell.traces) + [{"decision": str(val)}],
            )
        else:
            values[key] = CellValue(
                key=key,
                calculated=None,
                retained=val,
                status=STATUS_CORR,
                origin=ORIGIN_MANUAL,
                traces=[{"decision": str(val)}],
            )
    return values


def det_signed_gap(lines: list[DetLine]) -> Decimal:
    """Déséquilibre BAL DET = Σ DEB − Σ CRE (toutes classes). Jamais de constante."""
    total = ZERO
    for line in lines:
        total += (line.debit or ZERO) - (line.credit or ZERO)
    return quantize_mru(total)


def classes_1_8_gap(lines: list[DetLine]) -> Decimal:
    total = ZERO
    for line in lines:
        if line.ncg and line.ncg[:1] in "12345678":
            total += (line.debit or ZERO) - (line.credit or ZERO)
    return quantize_mru(total)
