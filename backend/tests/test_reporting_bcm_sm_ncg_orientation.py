"""Orientations NCG → cellules SM — fusion catalogue, opérations, conflits."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import AppError
from app.services.reporting_bcm_sm.engine.det_basis import DetLine
from app.services.reporting_bcm_sm.engine.evaluate import evaluate_sm
from app.services.reporting_bcm_sm.engine.rules_catalog import RULES_BY_KEY
from app.services.reporting_bcm_sm.ncg_orientation_service import (
    STATUS_ACTIVE,
    STATUS_DISABLED,
    STATUS_DRAFT,
    STATUS_PENDING,
    STATUS_REJECTED,
    merge_active_orientations,
    operation_to_term_parts,
    sheet_from_cell_ref,
    static_catalog_hits,
)


def _ori(**kwargs):
    base = {
        "id": uuid4(),
        "ncg": "847000",
        "cell_ref": "A:408:D",
        "operation": "ADD_CREDIT",
        "currency_scope": "ALL",
        "status": STATUS_ACTIVE,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_operation_mapping():
    assert operation_to_term_parts("ADD_DEBIT") == ("DEBIT", 1)
    assert operation_to_term_parts("ADD_CREDIT") == ("CREDIT", 1)
    assert operation_to_term_parts("SUB_DEBIT") == ("DEBIT", -1)
    assert operation_to_term_parts("SUB_CREDIT") == ("CREDIT", -1)


def test_sheet_from_cell():
    assert sheet_from_cell_ref("A:402:D") == "ETAT_A"
    assert sheet_from_cell_ref("B:207:E") == "ETAT_B"


def test_merge_does_not_alter_static_catalog_object():
    before = RULES_BY_KEY["A:408:D"].terms
    merged = merge_active_orientations(
        orientations=[_ori(ncg="847000", cell_ref="A:408:D", operation="ADD_CREDIT")]
    )
    assert RULES_BY_KEY["A:408:D"].terms == before
    new_rule = next(r for r in merged if r.key == "A:408:D")
    assert any("847000" in t.ncgs for t in new_rule.terms)
    assert not any("847000" in t.ncgs for t in before)


def test_mixed_operations_same_cell():
    merged = merge_active_orientations(
        orientations=[
            _ori(ncg="847000", cell_ref="A:408:D", operation="ADD_CREDIT"),
            _ori(ncg="847001", cell_ref="A:408:D", operation="SUB_DEBIT"),
            _ori(ncg="847002", cell_ref="A:408:D", operation="ADD_DEBIT"),
        ]
    )
    rule = next(r for r in merged if r.key == "A:408:D")
    lines = [
        DetLine("847000", "1", "a", "MRU", Decimal("0"), Decimal("100")),
        DetLine("847001", "2", "b", "MRU", Decimal("30"), Decimal("0")),
        DetLine("847002", "3", "c", "MRU", Decimal("10"), Decimal("0")),
        DetLine("351047", "4", "base", "MRU", Decimal("0"), Decimal("5")),
    ]
    base = evaluate_sm(lines)
    with_ori = evaluate_sm(lines, rules=merged)
    # Catalogue de base : 351047 CREDIT = 5. Orientations : +100 CRE − 30 DEB + 10 DEB = +80
    assert base["A:408:D"].calculated == Decimal("5.00")
    assert with_ori["A:408:D"].calculated == Decimal("85.00")
    assert len([t for t in rule.terms if "847000" in t.ncgs or "847001" in t.ncgs or "847002" in t.ncgs]) == 3


def test_inactive_orientations_ignored():
    merged = merge_active_orientations(
        orientations=[
            _ori(status=STATUS_DRAFT),
            _ori(status=STATUS_PENDING),
            _ori(status=STATUS_REJECTED),
            _ori(status=STATUS_DISABLED),
        ]
    )
    rule = next(r for r in merged if r.key == "A:408:D")
    assert not any("847000" in t.ncgs for t in rule.terms)


def test_duplicate_merge_is_idempotent():
    ori = _ori()
    once = merge_active_orientations(orientations=[ori])
    twice = merge_active_orientations(orientations=[ori, ori])
    r1 = next(r for r in once if r.key == "A:408:D")
    r2 = next(r for r in twice if r.key == "A:408:D")
    count1 = sum(1 for t in r1.terms for n in t.ncgs if n == "847000")
    count2 = sum(1 for t in r2.terms for n in t.ncgs if n == "847000")
    assert count1 == count2 == 1


def test_static_catalog_still_lists_existing_mappings():
    hits = static_catalog_hits("315100")
    assert any(h["cell_ref"] == "A:402:D" for h in hits)


def test_847000_not_in_static_catalog():
    assert static_catalog_hits("847000") == []


def test_conflict_helper_raises_for_existing_catalog_term():
    from app.services.reporting_bcm_sm.ncg_orientation_service import _assert_no_static_conflict

    with pytest.raises(AppError) as exc:
        _assert_no_static_conflict("315100", "A:402:D", "ADD_CREDIT", "ALL")
    assert exc.value.code == "NCG_ORI_CATALOG_CONFLICT"
