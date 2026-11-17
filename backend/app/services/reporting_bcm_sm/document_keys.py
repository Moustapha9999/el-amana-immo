"""Clés documentaires — regex gelées T3.5-3-C (R5, R-B1)."""

from __future__ import annotations

import re

from app.models.reporting_bcm_sm import RbcmTemplateCell

KEY_PATTERNS = (
    re.compile(r"^A:[0-9]{3}:[C-H]$"),
    re.compile(r"^A:CTRL:I147$"),
    re.compile(r"^B:[0-9]{3}:([C-H]|I|L)$"),
    re.compile(r"^C:[0-9]{3}:([C-F]|I)$"),
    re.compile(r"^(A|B|C):HDR:[A-Z]{1,3}[0-9]{1,4}$"),
    re.compile(r"^(A|B|C):STRUCT:[A-Z]{1,3}[0-9]{1,4}$"),
    re.compile(r"^(FPN|RCR|LIQ|FPAI|INFO):[A-Z]{1,3}[0-9]{1,4}$"),
)

STRUCT_KEYS_C = ("C:STRUCT:F44", "C:STRUCT:F46", "C:STRUCT:F48")


def document_key_ok(key: str) -> bool:
    return any(p.match(key) for p in KEY_PATTERNS)


def decision_allowed(cell: RbcmTemplateCell) -> bool:
    """Dérivé — ne jamais muter template_cell.writable."""
    return bool(cell.writable) or cell.nature == "OCTOBER_CONSTANT_FORMULA"
