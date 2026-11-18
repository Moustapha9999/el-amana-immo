"""PHASE 4 — Revue métier Comptabilité (consultation, correction, différé, rejet)."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import AppError
from app.services.reporting_bcm_sm.ncg_orientation_service import (
    STATUS_ACTIVE,
    STATUS_DRAFT,
    STATUS_PENDING,
    STATUS_REJECTED,
    merge_active_orientations,
    reject_orientation,
    update_orientation,
)
from app.services.reporting_bcm_sm.ncg_review_service import decision_timeline
from app.services.reporting_bcm_sm.ncg_structure_service import (
    PeriodNcgRow,
    PeriodSnapshot,
    STATUS_NOUVEAU,
    build_structure_report,
)
from app.services.reporting_bcm_sm.engine.rules_catalog import ALL_RULES
from decimal import Decimal


def test_catalog_still_89_rules():
    assert len(ALL_RULES) == 89


def test_847000_nouveau_without_forced_cell():
    sept = PeriodSnapshot(
        period_year=2026,
        period_month=9,
        campaign_id=uuid4(),
        import_id=uuid4(),
        rows={"210000": PeriodNcgRow("210000", "x", Decimal("1"), Decimal("0"))},
    )
    octo = PeriodSnapshot(
        period_year=2026,
        period_month=10,
        campaign_id=uuid4(),
        import_id=uuid4(),
        rows={
            "210000": PeriodNcgRow("210000", "x", Decimal("2"), Decimal("0")),
            "847000": PeriodNcgRow("847000", "MOINS VALUES  CESSION", Decimal("2785612"), Decimal("0")),
        },
    )
    report = build_structure_report(
        current=octo,
        history=[sept],
        mapped_index={"210000": [{"cell_ref": "A:131:D", "basis": "DEBIT", "sign": 1}]},
        class_prefixes=frozenset({"8"}),
    )
    item = next(i for i in report["items"] if i["ncg"] == "847000")
    assert item["status"] == STATUS_NOUVEAU
    assert item["cells"] == []


def test_decision_timeline_preserves_actors():
    ori = SimpleNamespace(
        prepared_by_id=uuid4(),
        prepared_at=SimpleNamespace(isoformat=lambda: "2026-10-01T10:00:00+00:00"),
        submitted_by_id=uuid4(),
        submitted_at=SimpleNamespace(isoformat=lambda: "2026-10-01T11:00:00+00:00"),
        validated_by_id=None,
        validated_at=None,
        rejected_by_id=uuid4(),
        rejected_at=SimpleNamespace(isoformat=lambda: "2026-10-01T12:00:00+00:00"),
        deactivated_by_id=None,
        deactivated_at=None,
        decision_comment="Motif métier",
        cell_ref="A:408:D",
        operation="ADD_CREDIT",
    )
    events = decision_timeline(ori)
    kinds = [e["kind"] for e in events]
    assert kinds == ["prepared", "submitted", "rejected"]
    assert events[-1]["comment"] == "Motif métier"


@pytest.mark.asyncio
async def test_reject_requires_motif():
    ori = SimpleNamespace(
        status=STATUS_PENDING,
        rejected_by_id=None,
        rejected_at=None,
        decision_comment=None,
    )
    with pytest.raises(AppError) as exc:
        await reject_orientation(SimpleNamespace(), orientation=ori, user=SimpleNamespace(id=uuid4()), comment="  ")
    assert exc.value.code == "NCG_ORI_REJECT_REASON"


@pytest.mark.asyncio
async def test_reject_with_motif_and_trace():
    user = SimpleNamespace(id=uuid4())

    async def _flush():
        return None

    ori = SimpleNamespace(
        status=STATUS_PENDING,
        rejected_by_id=None,
        rejected_at=None,
        decision_comment=None,
    )
    db = SimpleNamespace(flush=_flush)
    row = await reject_orientation(db, orientation=ori, user=user, comment="Cellule incorrecte")
    assert row.status == STATUS_REJECTED
    assert row.decision_comment == "Cellule incorrecte"
    assert row.rejected_by_id == user.id


@pytest.mark.asyncio
async def test_correction_resets_pending_and_keeps_history_note():
    user = SimpleNamespace(id=uuid4())

    async def _flush():
        return None

    ori = SimpleNamespace(
        id=uuid4(),
        ncg="999847",
        status=STATUS_PENDING,
        sheet="ETAT_A",
        cell_ref="A:408:D",
        operation="ADD_CREDIT",
        currency_scope="ALL",
        residence_scope="RESIDENTS",
        notes="Proposition initiale",
        ncg_libelle=None,
        prepared_by_id=None,
        prepared_at=None,
        submitted_by_id=uuid4(),
        submitted_at=object(),
    )
    db = SimpleNamespace(
        flush=_flush,
        scalar=lambda *_a, **_k: None,
    )

    # _find_open_duplicate uses db.scalar — stub OK
    async def _scalar(*_a, **_k):
        return None

    db.scalar = _scalar

    row = await update_orientation(
        db,
        orientation=ori,
        user=user,
        cell_ref="A:402:D",
        operation="ADD_DEBIT",
    )
    assert row.status == STATUS_DRAFT
    assert row.cell_ref == "A:402:D"
    assert row.operation == "ADD_DEBIT"
    assert row.submitted_by_id is None
    assert "correction" in (row.notes or "")
    assert "A:408:D" in (row.notes or "")
    assert "A:402:D" in (row.notes or "")


def test_deferred_draft_not_merged_into_active_catalog():
    deferred = SimpleNamespace(
        id=uuid4(),
        ncg="847000",
        cell_ref=None,
        operation=None,
        currency_scope="ALL",
        status=STATUS_DRAFT,
    )
    merged = merge_active_orientations(orientations=[deferred])
    assert not any("847000" in t.ncgs for r in merged for t in r.terms)
    assert len(merged) == len(ALL_RULES)


def test_active_only_merged():
    active = SimpleNamespace(
        id=uuid4(),
        ncg="999847",
        cell_ref="A:408:D",
        operation="ADD_CREDIT",
        currency_scope="ALL",
        status=STATUS_ACTIVE,
    )
    pending = SimpleNamespace(
        id=uuid4(),
        ncg="999847",
        cell_ref="A:408:D",
        operation="ADD_CREDIT",
        currency_scope="ALL",
        status=STATUS_PENDING,
    )
    merged = merge_active_orientations(orientations=[active, pending])
    rule = next(r for r in merged if r.key == "A:408:D")
    count = sum(1 for t in rule.terms for n in t.ncgs if n == "999847")
    assert count == 1
