"""Étape 7 — soumission / approbation : aucun contournement D01/D02."""

from __future__ import annotations

import uuid

from app.services.reporting_bcm_sm import workflow_service as wf
from app.services.reporting_bcm_sm.review_service import GATE_LABELS


def _facts(**overrides):
    base = {
        "status": "CALCULEE",
        "det_ok": True,
        "control_ok": True,
        "calc_ok": True,
        "missing_params": 0,
        "pending_manual": [],
        "work_id": str(uuid.uuid4()),
        "work_stale": False,
        "params_stale": False,
        "open_gates": ["D01", "D02", "D09"],
        "can_finalize": False,
        "blocking_controls": False,
        "preparer_id": str(uuid.uuid4()),
        "reporting_owner_id": str(uuid.uuid4()),
        "user_id": str(uuid.uuid4()),
        "approved_work_id": None,
    }
    base.update(overrides)
    return base


def test_submit_blocked_while_gates_open_and_finalize_false():
    blockers = wf.submit_blockers(_facts())
    codes = {b["code"] for b in blockers}
    assert "GATE_D01" in codes
    assert "GATE_D02" in codes
    assert "GATE_D09" in codes
    assert "FINALIZE" in codes
    assert not wf.submit_blockers(_facts(open_gates=[], can_finalize=True))


def test_submit_blocked_when_verification_stale_or_params_missing():
    codes = {b["code"] for b in wf.submit_blockers(_facts(work_stale=True, missing_params=7))}
    assert "STALE" in codes
    assert "PARAMETRES" in codes


def test_submit_repeat_from_a_controler():
    blockers = wf.submit_blockers(_facts(status="A_CONTROLER"))
    assert blockers[0]["code"] == "ALREADY_SUBMITTED"


def test_approve_requires_submitted_status():
    codes = {b["code"] for b in wf.approve_blockers(_facts(status="CALCULEE"))}
    assert "NOT_SUBMITTED" in codes
    assert "GATE_D01" in codes
    assert "FINALIZE" in codes


def test_approve_sod_preparer_and_owner():
    uid = str(uuid.uuid4())
    blockers = wf.approve_blockers(
        _facts(
            status="A_CONTROLER",
            user_id=uid,
            preparer_id=uid,
            reporting_owner_id=uid,
            open_gates=[],
            can_finalize=True,
        )
    )
    codes = {b["code"] for b in blockers}
    assert "SOD_PREPARER" in codes
    assert "SOD_OWNER" in codes


def test_approve_mechanism_empty_only_when_all_official_conditions_hold():
    """Mécanisme technique — ne constitue pas une validation métier D01/D02."""
    uid = str(uuid.uuid4())
    other = str(uuid.uuid4())
    assert not wf.approve_blockers(
        _facts(
            status="A_CONTROLER",
            user_id=uid,
            preparer_id=other,
            reporting_owner_id=other,
            open_gates=[],
            can_finalize=True,
        )
    )


def test_reject_requires_submitted_and_reason():
    codes = {b["code"] for b in wf.reject_blockers(_facts(status="CALCULEE"), comment=None)}
    assert "NOT_SUBMITTED" in codes
    assert "REJECT_REASON_REQUIRED" in codes
    assert not wf.reject_blockers(_facts(status="A_CONTROLER"), comment="Écart D02 non tranché")


def test_final_download_blocked_until_approval():
    codes = {b["code"] for b in wf.final_download_blockers(_facts(status="CALCULEE"))}
    assert "NOT_APPROVED" in codes
    assert "NO_FINAL" in codes
    assert not wf.final_download_blockers(
        _facts(status="APPROUVEE", approved_work_id=str(uuid.uuid4()))
    )


def test_assert_editable_blocks_submitted_and_approved():
    class C:
        def __init__(self, status):
            self.status = status

    wf.assert_campaign_editable(C("CALCULEE"))
    try:
        wf.assert_campaign_editable(C("A_CONTROLER"))
        raise AssertionError("expected submitted lock")
    except Exception as exc:
        assert getattr(exc, "code", None) == "CAMPAIGN_SUBMITTED"
    try:
        wf.assert_campaign_editable(C("APPROUVEE"))
        raise AssertionError("expected locked")
    except Exception as exc:
        assert getattr(exc, "code", None) == "CAMPAIGN_LOCKED"


def test_gate_labels_cover_d01_d02_without_inventing_rules():
    assert "A_VALIDER" in GATE_LABELS["D01"]
    assert "ECART" in GATE_LABELS["D02"]
