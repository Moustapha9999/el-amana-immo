"""Parse PDF banque (tableaux texte) → ParsedBankRow — sans OCR."""

from __future__ import annotations

from io import BytesIO
from typing import Any

from app.core.exceptions import ValidationError
from app.services.bank_immo_import import ParsedBankRow, _parse_sheet_grid


def parse_bank_pdf(
    content: bytes,
    *,
    nature_code: str,
    filename: str = "archive.pdf",
) -> list[ParsedBankRow]:
    """Extrait les tableaux amortissement d'un PDF texte via pdfplumber."""
    try:
        import pdfplumber
    except ImportError as exc:
        raise ValidationError("Le module pdfplumber est requis pour lire les PDF banque") from exc

    if not nature_code or not nature_code.strip():
        raise ValidationError("nature_code obligatoire pour un PDF archive")

    code = nature_code.strip()
    rows: list[ParsedBankRow] = []
    tables_found = 0

    try:
        with pdfplumber.open(BytesIO(content)) as pdf:
            if not pdf.pages:
                raise ValidationError("PDF vide")
            for page_idx, page in enumerate(pdf.pages, start=1):
                tables = page.extract_tables() or []
                for table in tables:
                    if not table or len(table) < 2:
                        continue
                    tables_found += 1
                    grid = _normalize_table(table)
                    parsed = _parse_sheet_grid(
                        f"page-{page_idx}",
                        code,
                        grid,
                        datemode=0,
                    )
                    for r in parsed:
                        r.categorie_code = code
                        r.sheet = f"page-{page_idx}"
                    rows.extend(parsed)
    except ValidationError:
        raise
    except Exception as exc:  # noqa: BLE001 — surface parse errors to caller
        raise ValidationError(f"Lecture PDF impossible ({filename}): {exc}") from exc

    if tables_found == 0:
        raise ValidationError(
            "PDF image non supporté — déposer l'Excel ou un PDF texte avec tableaux extractibles"
        )
    if not rows:
        raise ValidationError("Aucun tableau d'amortissement reconnu dans le PDF")
    return rows


def _normalize_table(table: list[list[Any]]) -> list[list[Any]]:
    grid: list[list[Any]] = []
    for row in table:
        if row is None:
            continue
        grid.append([(c.replace("\n", " ").strip() if isinstance(c, str) else c) for c in row])
    return grid
