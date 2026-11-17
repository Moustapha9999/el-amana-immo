"""Graphe Decimal documentaire — jamais le cache Excel, jamais runner.py."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, DivisionByZero, InvalidOperation
from pathlib import Path
from typing import Iterable

from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.reporting_bcm_sm import (
    RbcmDocumentDecision,
    RbcmMappingRule,
    RbcmTemplate,
    RbcmTemplateCell,
)
from app.services.reporting_bcm_sm.document_keys import decision_allowed
from app.services.reporting_bcm_sm.engine.amounts import Q2
from app.services.reporting_bcm_sm.formula_parser import (
    BinOp,
    BoolLit,
    Call,
    CellRef,
    Compare,
    FormulaSyntaxError,
    Number,
    RangeRef,
    Unary,
    collect_cell_refs,
    expand_range,
    parse_formula,
)
from app.services.reporting_bcm_sm.template_storage import verify_stored_template

STAT_NON_RENSEIGNE = "NON_RENSEIGNE"
STAT_ZERO_CONFIRME = "ZERO_CONFIRME"
STAT_ZERO_MANUEL = "ZERO_MANUEL"
STAT_VALEUR_DECIDEE = "VALEUR_DECIDEE"
STAT_NORME = "NORME_CANEVAS"
STAT_PROVISOIRE_D09 = "PROVISOIRE_D09"
STAT_COMPLETE = "FORMULE_COMPLETE"
STAT_PARTIELLE = "FORMULE_PARTIELLE"
STAT_NON_INTERP = "FORMULE_NON_INTERPRETABLE"
STAT_CONTROLE = "CONTROLE_NON_INTERPRETABLE"
STAT_HEADER = "HEADER"

_DECISION_STATUS = {
    "ZERO_CONFIRME": STAT_ZERO_CONFIRME,
    "ZERO_MANUEL": STAT_ZERO_MANUEL,
    "VALEUR_DECIDEE": STAT_VALEUR_DECIDEE,
}


@dataclass
class GateState:
    d01_open: bool = True
    d02_open: bool = True
    d06_open: bool = True
    d09_open: bool = True
    d15_open: bool = True
    d16_d17_open: bool = True
    d22_open: bool = True

    def as_dict(self) -> dict:
        return {
            "D01": self.d01_open,
            "D02": self.d02_open,
            "D06": self.d06_open,
            "D09": self.d09_open,
            "D15": self.d15_open,
            "D16_D17": self.d16_d17_open,
            "D22": self.d22_open,
        }


@dataclass
class CellEval:
    key: str
    nature: str
    status: str
    value: Decimal | None = None
    boolean: bool | None = None
    formula_text: str | None = None
    writable: bool = False
    decision_allowed: bool = False
    depends_on: list[str] = field(default_factory=list)


@dataclass
class GraphResult:
    cells: dict[str, CellEval]
    gates: GateState
    parse_errors: list[str] = field(default_factory=list)

    def get(self, key: str) -> CellEval | None:
        return self.cells.get(key)


def _q(value: Decimal) -> Decimal:
    return value.quantize(Q2)


class _Sentinel:
    PARTIAL = object()
    MISSING = object()
    BAD = object()


def _addr_index(cells: Iterable[RbcmTemplateCell]) -> dict[tuple[str, str], RbcmTemplateCell]:
    return {(c.sheet_name, c.excel_address): c for c in cells}


def _current_decisions(rows: list[RbcmDocumentDecision]) -> dict[str, RbcmDocumentDecision]:
    by_key: dict[str, RbcmDocumentDecision] = {}
    for row in sorted(rows, key=lambda r: r.decided_at):
        by_key[row.document_cell_key] = row
    return {k: v for k, v in by_key.items() if v.decision_type != "RETRAIT"}


async def load_gate_state(db: AsyncSession) -> GateState:
    a_valider = await db.scalar(
        select(RbcmMappingRule.id).where(RbcmMappingRule.lifecycle_status == "A_VALIDER").limit(1)
    )
    # Mapping global : 242 A_VALIDER / 0 ACTIVE → D01 ouverte. Autres portes métier ouvertes (O1).
    return GateState(
        d01_open=a_valider is not None,
        d02_open=True,
        d06_open=True,
        d09_open=True,
        d15_open=True,
        d16_d17_open=True,
        d22_open=True,
    )


def _canvas_values(path: Path, cells: list[RbcmTemplateCell]) -> dict[str, Decimal]:
    needed = [c for c in cells if c.nature == "CANVAS_NORM"]
    if not needed:
        return {}
    wb = load_workbook(path, data_only=False, read_only=True)
    out: dict[str, Decimal] = {}
    try:
        for c in needed:
            raw = wb[c.sheet_name][c.excel_address].value
            if isinstance(raw, (int, float, Decimal)):
                out[c.document_cell_key] = _q(Decimal(str(raw)))
    finally:
        wb.close()
    return out


async def evaluate_campaign_graph(
    db: AsyncSession,
    *,
    template: RbcmTemplate,
    overlay: dict[str, Decimal] | None = None,
    gates: GateState | None = None,
) -> GraphResult:
    cells = list(
        (await db.scalars(select(RbcmTemplateCell).where(RbcmTemplateCell.template_id == template.id))).all()
    )
    return evaluate_graph(
        cells,
        template=template,
        overlay=overlay or {},
        gates=gates or await load_gate_state(db),
    )


def evaluate_graph(
    cells: list[RbcmTemplateCell],
    *,
    template: RbcmTemplate | None = None,
    overlay: dict[str, Decimal] | None = None,
    decisions: dict[str, RbcmDocumentDecision] | None = None,
    gates: GateState | None = None,
    canvas: dict[str, Decimal] | None = None,
) -> GraphResult:
    gates = gates or GateState()
    overlay = dict(overlay or {})
    idx = _addr_index(cells)
    by_key = {c.document_cell_key: c for c in cells}
    parse_errors: list[str] = []
    depends: dict[str, list[str]] = {}
    asts: dict[str, object] = {}

    if canvas is None and template is not None:
        try:
            path = verify_stored_template(template.stored_path, template.sha256)
            canvas = _canvas_values(path, cells)
        except AppError:
            canvas = {}
    canvas = canvas or {}

    for c in cells:
        if not c.formula_text:
            continue
        # WORK : constantes et feuilles d'octobre vidées — la formule officielle
        # reste en métadonnée, elle n'est pas un graphe vivant.
        if c.nature in ("OCTOBER_CONSTANT_FORMULA", "OCTOBER_LEAF"):
            continue
        try:
            ast = parse_formula(c.formula_text)
            asts[c.document_cell_key] = ast
            refs = collect_cell_refs(ast, c.sheet_name)
            deps: list[str] = []
            for sheet, addr in refs:
                tgt = idx.get((sheet, addr))
                if tgt is not None:
                    deps.append(tgt.document_cell_key)
            depends[c.document_cell_key] = deps
        except FormulaSyntaxError as exc:
            parse_errors.append(f"{c.document_cell_key}: {exc}")

    memo: dict[str, CellEval] = {}
    stack: set[str] = set()

    def leaf_status(cell: RbcmTemplateCell) -> CellEval:
        allowed = decision_allowed(cell)
        key = cell.document_cell_key
        if cell.nature == "HEADER":
            return CellEval(key, cell.nature, STAT_HEADER, decision_allowed=False, writable=cell.writable)
        if cell.nature == "CANVAS_NORM":
            val = canvas.get(key)
            return CellEval(key, cell.nature, STAT_NORME, value=val, writable=False)
        if key in overlay:
            val = overlay[key]
            st = STAT_VALEUR_DECIDEE
            if decisions and key in decisions:
                st = _DECISION_STATUS.get(decisions[key].decision_type, STAT_VALEUR_DECIDEE)
            return CellEval(key, cell.nature, st, value=_q(val), writable=cell.writable, decision_allowed=allowed)
        if decisions and key in decisions:
            d = decisions[key]
            st = _DECISION_STATUS.get(d.decision_type, STAT_VALEUR_DECIDEE)
            return CellEval(
                key,
                cell.nature,
                st,
                value=None if d.decided_value is None else _q(d.decided_value),
                writable=cell.writable,
                decision_allowed=allowed,
            )
        if cell.nature in ("OCTOBER_LEAF", "LEAF", "OCTOBER_CONSTANT_FORMULA"):
            return CellEval(
                key,
                cell.nature,
                STAT_NON_RENSEIGNE,
                writable=cell.writable,
                decision_allowed=allowed,
            )
        return CellEval(key, cell.nature, STAT_NON_RENSEIGNE, writable=cell.writable, decision_allowed=allowed)

    def eval_key(key: str) -> CellEval:
        if key in memo:
            return memo[key]
        if key in stack:
            node = CellEval(key, "STRUCTURAL_FORMULA", STAT_NON_INTERP)
            memo[key] = node
            return node
        cell = by_key.get(key)
        if cell is None:
            node = CellEval(key, "LEAF", STAT_NON_RENSEIGNE)
            memo[key] = node
            return node
        if cell.document_cell_key not in asts:
            node = leaf_status(cell)
            memo[key] = node
            return node
        stack.add(key)
        raw = _eval_ast(asts[key], cell.sheet_name)
        stack.remove(key)
        deps = depends.get(key, [])
        node = _status_from_raw(cell, raw, deps, [eval_key(d) for d in deps], gates)
        node.depends_on = deps
        node.formula_text = cell.formula_text
        node.writable = cell.writable
        node.decision_allowed = decision_allowed(cell)
        memo[key] = node
        return node

    def _eval_ast(node: object, sheet: str):
        if isinstance(node, Number):
            return node.value
        if isinstance(node, BoolLit):
            return node.value
        if isinstance(node, CellRef):
            tgt = idx.get((node.sheet or sheet, node.address))
            if tgt is None:
                return _Sentinel.MISSING
            ev = eval_key(tgt.document_cell_key)
            return _from_eval(ev)
        if isinstance(node, RangeRef):
            vals = []
            sh = node.sheet or sheet
            for addr in expand_range(node.start, node.end):
                tgt = idx.get((sh, addr))
                if tgt is None:
                    vals.append(_Sentinel.MISSING)
                else:
                    vals.append(_from_eval(eval_key(tgt.document_cell_key)))
            return vals
        if isinstance(node, Unary):
            v = _eval_ast(node.expr, sheet)
            if v in (_Sentinel.MISSING, _Sentinel.PARTIAL, _Sentinel.BAD):
                return v
            if not isinstance(v, Decimal):
                return _Sentinel.BAD
            return -v if node.op == "-" else v
        if isinstance(node, BinOp):
            a = _eval_ast(node.left, sheet)
            b = _eval_ast(node.right, sheet)
            return _binop(node.op, a, b)
        if isinstance(node, Compare):
            a = _eval_ast(node.left, sheet)
            b = _eval_ast(node.right, sheet)
            return _compare(node.op, a, b)
        if isinstance(node, Call):
            return _call(node, sheet)
        return _Sentinel.BAD

    def _call(node: Call, sheet: str):
        if node.name == "SUM":
            acc = None
            saw_num = False
            saw_miss = False
            for arg in node.args:
                raw = _eval_ast(arg, sheet)
                seq = raw if isinstance(raw, list) else [raw]
                for item in seq:
                    if item in (_Sentinel.MISSING, _Sentinel.PARTIAL):
                        saw_miss = True
                        continue
                    if item is _Sentinel.BAD or not isinstance(item, Decimal):
                        return _Sentinel.BAD
                    acc = item if acc is None else acc + item
                    saw_num = True
            if saw_miss and saw_num:
                return _Sentinel.PARTIAL
            if saw_miss or acc is None:
                return _Sentinel.MISSING
            return acc
        if node.name == "IF":
            if len(node.args) != 3:
                return _Sentinel.BAD
            cond = _eval_ast(node.args[0], sheet)
            if cond in (_Sentinel.MISSING, _Sentinel.PARTIAL, _Sentinel.BAD):
                return cond if cond is not _Sentinel.PARTIAL else _Sentinel.MISSING
            t = _eval_ast(node.args[1], sheet)
            f = _eval_ast(node.args[2], sheet)
            if cond is True:
                return t
            if cond is False:
                return f
            if isinstance(cond, Decimal):
                return t if cond != 0 else f
            return _Sentinel.BAD
        return _Sentinel.BAD

    def _from_eval(ev: CellEval):
        if ev.status in (STAT_NON_RENSEIGNE, STAT_HEADER):
            return _Sentinel.MISSING
        if ev.status in (STAT_PARTIELLE,):
            return _Sentinel.PARTIAL if ev.value is None else ev.value
        if ev.status in (STAT_NON_INTERP, STAT_CONTROLE, STAT_PROVISOIRE_D09) and ev.value is None:
            return _Sentinel.MISSING
        if ev.boolean is not None:
            return ev.boolean
        if ev.value is None:
            return _Sentinel.MISSING
        return ev.value

    def _binop(op: str, a, b):
        flags = {a, b}
        if _Sentinel.BAD in flags:
            return _Sentinel.BAD
        if _Sentinel.PARTIAL in flags:
            return _Sentinel.PARTIAL
        if _Sentinel.MISSING in flags:
            if any(isinstance(x, Decimal) for x in (a, b)):
                return _Sentinel.PARTIAL
            return _Sentinel.MISSING
        if not isinstance(a, Decimal) or not isinstance(b, Decimal):
            return _Sentinel.BAD
        try:
            if op == "+":
                return a + b
            if op == "-":
                return a - b
            if op == "*":
                return a * b
            if op == "/":
                if b == 0:
                    return _Sentinel.BAD
                return a / b
        except (DivisionByZero, InvalidOperation):
            return _Sentinel.BAD
        return _Sentinel.BAD

    def _compare(op: str, a, b):
        if a in (_Sentinel.MISSING, _Sentinel.PARTIAL, _Sentinel.BAD) or b in (
            _Sentinel.MISSING,
            _Sentinel.PARTIAL,
            _Sentinel.BAD,
        ):
            if _Sentinel.BAD in (a, b):
                return _Sentinel.BAD
            if _Sentinel.PARTIAL in (a, b) or _Sentinel.MISSING in (a, b):
                return _Sentinel.MISSING
        if type(a) is not type(b) and not (isinstance(a, Decimal) and isinstance(b, Decimal)):
            return _Sentinel.BAD
        if op == "=":
            return a == b
        if op == "<>":
            return a != b
        if not isinstance(a, Decimal) or not isinstance(b, Decimal):
            return _Sentinel.BAD
        if op == "<":
            return a < b
        if op == ">":
            return a > b
        if op == "<=":
            return a <= b
        if op == ">=":
            return a >= b
        return _Sentinel.BAD

    for c in cells:
        eval_key(c.document_cell_key)

    return GraphResult(cells=memo, gates=gates, parse_errors=parse_errors)


def _axis_d16(cell: RbcmTemplateCell) -> bool:
    if cell.sheet_name != "ETAT A":
        return False
    return (cell.axis or "") in "DEFGH" or (cell.excel_address[:1] in "DEFGH")


def _status_from_raw(
    cell: RbcmTemplateCell,
    raw,
    deps: list[str],
    dep_evals: list[CellEval],
    gates: GateState,
) -> CellEval:
    key = cell.document_cell_key
    nature = cell.nature
    base = CellEval(key, nature, STAT_NON_INTERP, formula_text=cell.formula_text)

    if nature == "CONCORDANCE_IF":
        incomplete = any(
            d.status in (STAT_NON_RENSEIGNE, STAT_PARTIELLE, STAT_NON_INTERP, STAT_CONTROLE) for d in dep_evals
        ) or raw in (_Sentinel.MISSING, _Sentinel.PARTIAL, _Sentinel.BAD)
        if incomplete:
            base.status = STAT_CONTROLE
            return base
        if gates.d09_open:
            base.status = STAT_PROVISOIRE_D09
            if isinstance(raw, bool):
                base.boolean = raw
            return base
        if isinstance(raw, bool):
            base.boolean = raw
            base.status = STAT_COMPLETE
            return base

    if nature in ("D09_PCT", "D09_REMAINDER") or (cell.completeness_group == "D09"):
        if gates.d09_open:
            base.status = STAT_PROVISOIRE_D09
            if isinstance(raw, Decimal):
                base.value = _q(raw)
            return base

    if nature in ("RATIO_DIV", "CANVAS_SCALE_FORMULA") and raw in (
        _Sentinel.PARTIAL,
        _Sentinel.MISSING,
        _Sentinel.BAD,
    ):
        base.status = STAT_NON_INTERP
        return base
    if raw is _Sentinel.PARTIAL:
        base.status = STAT_PARTIELLE
        return base
    if raw is _Sentinel.MISSING:
        if any(d.status in (STAT_VALEUR_DECIDEE, STAT_ZERO_CONFIRME, STAT_ZERO_MANUEL, STAT_COMPLETE, STAT_NORME) for d in dep_evals):
            base.status = STAT_PARTIELLE
        else:
            base.status = STAT_NON_INTERP
        return base
    if raw is _Sentinel.BAD:
        base.status = STAT_NON_INTERP
        return base

    if isinstance(raw, bool):
        base.boolean = raw
        base.status = STAT_COMPLETE
    elif isinstance(raw, Decimal):
        base.value = _q(raw)
        base.status = STAT_COMPLETE
    else:
        base.status = STAT_NON_INTERP
        return base

    if base.status == STAT_COMPLETE and gates.d16_d17_open and _axis_d16(cell):
        # Dépendances incomplètes déjà traitées. Si la formule serait close mais D16 ouverte :
        # on ne rétrograde PARTIELLE. Ici COMPLETE → NON_INTERPRETABLE.
        if not any(d.status in (STAT_NON_RENSEIGNE, STAT_PARTIELLE) for d in dep_evals):
            base.status = STAT_NON_INTERP
    return base


async def evaluate_for_campaign(
    db: AsyncSession,
    *,
    campaign_id,
    template: RbcmTemplate,
    overlay: dict[str, Decimal] | None = None,
    gates: GateState | None = None,
) -> GraphResult:
    cells = list(
        (await db.scalars(select(RbcmTemplateCell).where(RbcmTemplateCell.template_id == template.id))).all()
    )
    rows = list(
        (
            await db.scalars(
                select(RbcmDocumentDecision).where(RbcmDocumentDecision.campaign_id == campaign_id)
            )
        ).all()
    )
    current = _current_decisions(rows)
    merged = {k: v.decided_value for k, v in current.items() if v.decided_value is not None}
    if overlay:
        merged.update(overlay)
    return evaluate_graph(
        cells,
        template=template,
        overlay=merged,
        decisions=current,
        gates=gates or await load_gate_state(db),
    )
