"""Seed idempotent du canevas officiel BEA-SM — métadonnées uniquement (phase B)."""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.cell.cell import Cell
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.reporting_bcm_sm import RbcmTemplate, RbcmTemplateCell
from app.services.reporting_bcm_sm.template_storage import (
    OFFICIAL_FILENAME,
    OFFICIAL_SHA256,
    TEMPLATE_CODE,
    copy_official_template,
    file_sha256,
)

EXPECTED_SHEETS = (
    "informations à fournir",
    "ETAT A",
    "ETAT B",
    "ETAT C",
    "CALCUL FPN",
    "RATIO COUVERTURE DE RISQUE",
    "RATIO DE LIQUIDITE",
    "RATIO FP ET AI",
)
EXPECTED_FORMULA_COUNT = 663
SHEET_PREFIX = {
    "informations à fournir": "INFO",
    "ETAT A": "A",
    "ETAT B": "B",
    "ETAT C": "C",
    "CALCUL FPN": "FPN",
    "RATIO COUVERTURE DE RISQUE": "RCR",
    "RATIO DE LIQUIDITE": "LIQ",
    "RATIO FP ET AI": "FPAI",
}

OCTOBER_CONSTANTS = {
    ("ETAT A", "D9"),
    ("ETAT A", "D21"),
    ("ETAT A", "D38"),
    ("ETAT A", "D75"),
    ("ETAT A", "D76"),
    ("ETAT A", "D106"),
    ("ETAT A", "D112"),
    ("ETAT A", "D123"),
    ("ETAT A", "D167"),
}
SCALE_FORMULAS = {
    ("RATIO COUVERTURE DE RISQUE", "H31"),
    ("RATIO DE LIQUIDITE", "D20"),
    ("CALCUL FPN", "F33"),
}
D09_PCT = {("ETAT B", a) for a in ("E46", "E48", "E49")}
D09_REMAINDER = {("ETAT B", a) for a in ("D46", "D48", "D49")}
CONCORDANCE = {("ETAT B", a) for a in (
    "L11", "L20", "L36", "L40", "L44", "L46", "L47", "L48", "L49", "L51", "L52", "L53",
)} | {("ETAT C", a) for a in (
    "I8", "I9", "I15", "I17", "I19", "I20", "I22", "I23", "I24", "I30", "I31", "I36", "I38", "I39", "I40",
)}
METIER_IF = {
    ("CALCUL FPN", "C27"),
    ("CALCUL FPN", "C36"),
    ("RATIO DE LIQUIDITE", "C48"),
    ("RATIO DE LIQUIDITE", "C49"),
}
RATIO_DIV = {
    ("RATIO COUVERTURE DE RISQUE", "H28"),
    ("RATIO DE LIQUIDITE", "C26"),
    ("RATIO FP ET AI", "C16"),
}
CANVAS_NORM_ADDR = (
    [("RATIO COUVERTURE DE RISQUE", f"G{r}") for r in range(7, 18)]
    + [("RATIO COUVERTURE DE RISQUE", f"G{r}") for r in range(20, 26)]
    + [("RATIO COUVERTURE DE RISQUE", "H29"), ("RATIO DE LIQUIDITE", "C27")]
)
INFO_LEAVES = [f"C{n}" for n in list(range(6, 9)) + list(range(10, 21))]
LIQ_LEAVES = ("D12", "D17", "D18", "D19", "D23")
HEADER_ADDRS = ("A1", "A2", "B2", "B3", "A3")
_ADDR_RE = re.compile(r"^([A-Z]+)(\d+)$")


@dataclass
class CellSpec:
    sheet_name: str
    excel_address: str
    document_cell_key: str
    nature: str
    writable: bool
    formula_text: str | None = None
    bcm_code: str | None = None
    axis: str | None = None
    completeness_group: str | None = None
    extra: dict | None = field(default=None)


def _addr_parts(address: str) -> tuple[str, int]:
    m = _ADDR_RE.match(address)
    if not m:
        raise AppError(f"adresse Excel invalide: {address}", code="TEMPLATE_PATH_UNSAFE")
    return m.group(1), int(m.group(2))


def _as_code(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip().isdigit():
        return f"{int(value.strip()):03d}"
    if isinstance(value, (int, float)) and float(value).is_integer():
        n = int(value)
        if 1 <= n <= 999:
            return f"{n:03d}"
    return None


def _formula_of(cell: Cell) -> str | None:
    val = cell.value
    if val is None:
        return None
    if cell.data_type == "f" or (isinstance(val, str) and val.startswith("=")):
        return str(val)
    return None


def _row_code(ws, row: int) -> str | None:
    return _as_code(ws.cell(row=row, column=2).value)


def _document_key(sheet: str, address: str, bcm_code: str | None, col: str, *, header: bool = False) -> str:
    if sheet == "ETAT A" and address == "I147":
        return "A:CTRL:I147"
    if header:
        prefix = SHEET_PREFIX[sheet]
        if prefix in ("A", "B", "C"):
            return f"{prefix}:HDR:{address}"
        return f"{prefix}:{address}"
    if sheet == "ETAT A" and col in "CDEFGH" and bcm_code:
        return f"A:{bcm_code}:{col}"
    if sheet == "ETAT B" and col in "CDEFGHI" + "L" and bcm_code:
        return f"B:{bcm_code}:{col}"
    if sheet == "ETAT C" and col in "CDEFI" and bcm_code:
        return f"C:{bcm_code}:{col}"
    prefix = SHEET_PREFIX[sheet]
    if prefix in ("A", "B", "C"):
        # Formule / cellule A/B/C sans code BCM : STRUCT, jamais HDR (R-B1).
        return f"{prefix}:STRUCT:{address}"
    return f"{prefix}:{address}"


def _formula_nature(sheet: str, address: str) -> str:
    key = (sheet, address)
    if key in OCTOBER_CONSTANTS:
        return "OCTOBER_CONSTANT_FORMULA"
    if key in SCALE_FORMULAS:
        return "CANVAS_SCALE_FORMULA"
    if key in D09_PCT:
        return "D09_PCT"
    if key in D09_REMAINDER:
        return "D09_REMAINDER"
    if key in CONCORDANCE:
        return "CONCORDANCE_IF"
    if key in METIER_IF:
        return "METIER_IF"
    if key in RATIO_DIV:
        return "RATIO_DIV"
    return "STRUCTURAL_FORMULA"


def _writable(nature: str) -> bool:
    return nature in ("OCTOBER_LEAF", "LEAF")


def _group(nature: str, sheet: str) -> str | None:
    if nature in ("D09_PCT", "D09_REMAINDER"):
        return "D09"
    if sheet == "informations à fournir":
        return "INFO"
    return None


def inventory_official_xlsx(path: Path) -> tuple[list[CellSpec], dict]:
    wb = load_workbook(path, data_only=False, read_only=False)
    names = list(wb.sheetnames)
    if names != list(EXPECTED_SHEETS):
        wb.close()
        raise AppError(
            f"feuilles inattendues: {names}",
            code="TEMPLATE_SHA_MISMATCH",
        )
    if "AVERTISSEMENT" in names or "À LIRE" in names:
        wb.close()
        raise AppError(
            "feuille explicative interdite dans le canevas source",
            code="TEMPLATE_SHA_MISMATCH",
        )

    specs: dict[tuple[str, str], CellSpec] = {}

    def add(spec: CellSpec) -> None:
        k = (spec.sheet_name, spec.excel_address)
        prev = specs.get(k)
        if prev and prev.nature != spec.nature and prev.formula_text and not spec.formula_text:
            return
        specs[k] = spec

    formula_count = 0
    coverage_e = []

    for sheet in EXPECTED_SHEETS:
        ws = wb[sheet]
        prefix = SHEET_PREFIX[sheet]
        for row in ws.iter_rows():
            for cell in row:
                if not isinstance(cell, Cell):
                    continue
                addr = cell.coordinate
                col, row_n = _addr_parts(addr)
                formula = _formula_of(cell)
                bcm = _row_code(ws, row_n) if sheet in ("ETAT A", "ETAT B", "ETAT C") else None
                if formula:
                    formula_count += 1
                    nature = _formula_nature(sheet, addr)
                    add(
                        CellSpec(
                            sheet_name=sheet,
                            excel_address=addr,
                            document_cell_key=_document_key(sheet, addr, bcm, col),
                            nature=nature,
                            writable=_writable(nature),
                            formula_text=formula,
                            bcm_code=bcm,
                            axis=col if col in "CDEFGHIL" else None,
                            completeness_group=_group(nature, sheet),
                        )
                    )

        for addr in HEADER_ADDRS:
            col, _rn = _addr_parts(addr)
            add(
                CellSpec(
                    sheet_name=sheet,
                    excel_address=addr,
                    document_cell_key=_document_key(sheet, addr, None, col, header=True),
                    nature="HEADER",
                    writable=False,
                    axis=None,
                )
            )

        if sheet == "informations à fournir":
            for addr in INFO_LEAVES:
                cell = ws[addr]
                if _formula_of(cell):
                    continue
                add(
                    CellSpec(
                        sheet_name=sheet,
                        excel_address=addr,
                        document_cell_key=f"INFO:{addr}",
                        nature="OCTOBER_LEAF",
                        writable=True,
                        completeness_group="INFO",
                        axis="C",
                    )
                )

        if sheet == "RATIO COUVERTURE DE RISQUE":
            for r in range(7, 26):
                addr = f"E{r}"
                cell = ws[addr]
                if _formula_of(cell):
                    continue
                val = cell.value
                if val is None and r in (18, 19):
                    continue
                if val is None:
                    continue
                coverage_e.append(addr)
                add(
                    CellSpec(
                        sheet_name=sheet,
                        excel_address=addr,
                        document_cell_key=f"RCR:{addr}",
                        nature="OCTOBER_LEAF",
                        writable=True,
                        extra={"october_value": str(val)},
                    )
                )
            for sh, addr in CANVAS_NORM_ADDR:
                if sh != sheet:
                    continue
                add(
                    CellSpec(
                        sheet_name=sheet,
                        excel_address=addr,
                        document_cell_key=f"RCR:{addr}",
                        nature="CANVAS_NORM",
                        writable=False,
                    )
                )

        if sheet == "RATIO DE LIQUIDITE":
            add(
                CellSpec(
                    sheet_name=sheet,
                    excel_address="C27",
                    document_cell_key="LIQ:C27",
                    nature="CANVAS_NORM",
                    writable=False,
                )
            )
            for addr in LIQ_LEAVES:
                cell = ws[addr]
                if _formula_of(cell):
                    continue
                add(
                    CellSpec(
                        sheet_name=sheet,
                        excel_address=addr,
                        document_cell_key=f"LIQ:{addr}",
                        nature="OCTOBER_LEAF",
                        writable=True,
                    )
                )

        if sheet == "ETAT A":
            for row_n in range(8, 172):
                bcm = _row_code(ws, row_n)
                if not bcm:
                    continue
                for col in "CDEFGH":
                    cell = ws[f"{col}{row_n}"]
                    if _formula_of(cell):
                        continue
                    addr = f"{col}{row_n}"
                    add(
                        CellSpec(
                            sheet_name=sheet,
                            excel_address=addr,
                            document_cell_key=f"A:{bcm}:{col}",
                            nature="OCTOBER_LEAF",
                            writable=True,
                            bcm_code=bcm,
                            axis=col,
                        )
                    )

        if sheet == "ETAT B":
            for row_n in range(1, (ws.max_row or 1) + 1):
                bcm = _row_code(ws, row_n)
                if not bcm:
                    continue
                for col in "CDEFGH":
                    cell = ws[f"{col}{row_n}"]
                    if _formula_of(cell):
                        continue
                    addr = f"{col}{row_n}"
                    add(
                        CellSpec(
                            sheet_name=sheet,
                            excel_address=addr,
                            document_cell_key=f"B:{bcm}:{col}",
                            nature="OCTOBER_LEAF",
                            writable=True,
                            bcm_code=bcm,
                            axis=col,
                        )
                    )

        if sheet == "ETAT C":
            for row_n in range(1, (ws.max_row or 1) + 1):
                bcm = _row_code(ws, row_n)
                if not bcm:
                    continue
                for col in "CDE":
                    cell = ws[f"{col}{row_n}"]
                    if _formula_of(cell):
                        continue
                    addr = f"{col}{row_n}"
                    add(
                        CellSpec(
                            sheet_name=sheet,
                            excel_address=addr,
                            document_cell_key=f"C:{bcm}:{col}",
                            nature="OCTOBER_LEAF",
                            writable=True,
                            bcm_code=bcm,
                            axis=col,
                        )
                    )

    wb.close()
    if formula_count != EXPECTED_FORMULA_COUNT:
        raise AppError(
            f"nombre de formules {formula_count} ≠ {EXPECTED_FORMULA_COUNT}",
            code="TEMPLATE_SHA_MISMATCH",
        )

    cells = list(specs.values())
    keys = [c.document_cell_key for c in cells]
    if len(keys) != len(set(keys)):
        dup = [k for k, n in _count(keys).items() if n > 1]
        raise AppError(f"clés documentaires dupliquées: {dup[:8]}", code="TEMPLATE_SHA_MISMATCH")

    natures = defaultdict(int)
    for c in cells:
        natures[c.nature] += 1
    report = {
        "sheets": list(EXPECTED_SHEETS),
        "sheet_count": len(EXPECTED_SHEETS),
        "formula_count": formula_count,
        "cell_count": len(cells),
        "natures": dict(natures),
        "october_constants": natures["OCTOBER_CONSTANT_FORMULA"],
        "coverage_e_cells": coverage_e,
        "has_i147": any(c.document_cell_key == "A:CTRL:I147" for c in cells),
        "h31_nature": next(
            (c.nature for c in cells if c.document_cell_key == "RCR:H31"),
            None,
        ),
        "info_c9_formula": next(
            (c.formula_text for c in cells if c.document_cell_key == "INFO:C9"),
            None,
        ),
        "info_leaves": sum(1 for c in cells if c.document_cell_key.startswith("INFO:") and c.nature == "OCTOBER_LEAF"),
    }
    return cells, report


def _count(items: list[str]) -> dict[str, int]:
    d: dict[str, int] = defaultdict(int)
    for i in items:
        d[i] += 1
    return d


async def apply_struct_key_convention(db: AsyncSession) -> int:
    """R-B1 : formules A/B/C sans code BCM → `:STRUCT:`, HEADER inchangés (`:HDR:`).

    Idempotent. Ne touche pas aux campagnes ni au mapping.
    """
    result = await db.execute(
        text(
            """
            UPDATE rbcm_template_cell
            SET document_cell_key = regexp_replace(document_cell_key, '^(A|B|C):HDR:', '\\1:STRUCT:')
            WHERE nature <> 'HEADER'
              AND document_cell_key ~ '^(A|B|C):HDR:'
            """
        )
    )
    return int(result.rowcount or 0)


async def seed_official_template(
    db: AsyncSession,
    source: Path,
    *,
    expected_sha256: str = OFFICIAL_SHA256,
    template_code: str = TEMPLATE_CODE,
    created_by_id: uuid.UUID | None = None,
) -> dict:
    source = source.resolve()
    if not source.is_file():
        raise AppError(f"canevas introuvable: {source}", status_code=404, code="TEMPLATE_NOT_FOUND")
    sha = file_sha256(source)
    if expected_sha256 and sha.lower() != expected_sha256.lower():
        raise AppError(
            f"SHA {sha} ≠ {expected_sha256}",
            status_code=409,
            code="TEMPLATE_SHA_MISMATCH",
        )

    existing = await db.scalar(select(RbcmTemplate).where(RbcmTemplate.sha256 == sha))
    if existing is not None:
        repaired = await apply_struct_key_convention(db)
        cell_n = len(
            (await db.scalars(select(RbcmTemplateCell).where(RbcmTemplateCell.template_id == existing.id))).all()
        )
        return {
            "idempotent": True,
            "template_id": str(existing.id),
            "version": existing.version,
            "sha256": existing.sha256,
            "stored_path": existing.stored_path,
            "cell_count": cell_n,
            "created": False,
            "struct_keys_repaired": repaired,
        }

    cells, inventory = inventory_official_xlsx(source)
    current = await db.scalar(
        select(RbcmTemplate).where(
            RbcmTemplate.template_code == template_code,
            RbcmTemplate.status == "CURRENT",
        )
    )
    new_version = 1 if current is None else current.version + 1
    template_id = uuid.uuid4()
    copied = copy_official_template(source, template_id, expected_sha256=sha)

    if current is not None:
        current.status = "SUPERSEDED"

    tpl = RbcmTemplate(
        id=template_id,
        template_code=template_code,
        version=new_version,
        filename=source.name or OFFICIAL_FILENAME,
        sha256=sha,
        stored_path=copied["stored_path"],
        status="CURRENT",
        created_by_id=created_by_id,
        extra={"inventory": {k: inventory[k] for k in inventory if k != "prefix"}},
    )
    db.add(tpl)
    for spec in cells:
        db.add(
            RbcmTemplateCell(
                id=uuid.uuid4(),
                template_id=template_id,
                sheet_name=spec.sheet_name,
                excel_address=spec.excel_address,
                document_cell_key=spec.document_cell_key,
                bcm_code=spec.bcm_code,
                axis=spec.axis,
                nature=spec.nature,
                formula_text=spec.formula_text,
                writable=spec.writable,
                completeness_group=spec.completeness_group,
                extra=spec.extra,
            )
        )
    await db.flush()
    return {
        "idempotent": False,
        "template_id": str(template_id),
        "version": new_version,
        "sha256": sha,
        "stored_path": copied["stored_path"],
        "copied": copied["copied"],
        "cell_count": len(cells),
        "superseded_previous": current is not None,
        "inventory": inventory,
        "created": True,
    }
