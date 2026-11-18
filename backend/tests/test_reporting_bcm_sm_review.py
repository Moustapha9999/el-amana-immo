"""Étapes 5–6 — préparation et vérification : pas de règle D01/D02 inventée."""

from __future__ import annotations

from app.services.reporting_bcm_sm import review_service as rs


def test_preparation_verdict_does_not_block_on_d01():
    assert (
        rs.preparation_verdict(
            det_ok=True,
            control_ok=True,
            calc_ok=True,
            missing_params=0,
            decisions_open=7,
            technical=False,
        )
        == "decision"
    )


def test_preparation_blocked_without_det_or_failed_control():
    assert (
        rs.preparation_verdict(
            det_ok=False,
            control_ok=True,
            calc_ok=True,
            missing_params=0,
            decisions_open=0,
            technical=False,
        )
        == "blocked"
    )
    assert (
        rs.preparation_verdict(
            det_ok=True,
            control_ok=True,
            calc_ok=True,
            missing_params=0,
            decisions_open=0,
            technical=True,
        )
        == "blocked"
    )


def test_preparation_complements_when_params_or_calc_missing():
    assert (
        rs.preparation_verdict(
            det_ok=True,
            control_ok=True,
            calc_ok=False,
            missing_params=0,
            decisions_open=0,
            technical=False,
        )
        == "complements"
    )
    assert (
        rs.preparation_verdict(
            det_ok=True,
            control_ok=True,
            calc_ok=True,
            missing_params=3,
            decisions_open=0,
            technical=False,
        )
        == "complements"
    )


def test_document_never_conforme_while_gates_open():
    assert (
        rs.document_verdict(
            blocking=False,
            to_complete=False,
            decisions=True,
            can_finalize=False,
        )
        == "decision"
    )
    assert (
        rs.document_verdict(
            blocking=False,
            to_complete=False,
            decisions=False,
            can_finalize=False,
        )
        == "decision"
    )


def test_document_conforme_only_when_finalize_allowed():
    assert (
        rs.document_verdict(
            blocking=False,
            to_complete=False,
            decisions=False,
            can_finalize=True,
        )
        == "conforme"
    )


def test_document_blocking_wins_over_decisions():
    assert (
        rs.document_verdict(
            blocking=True,
            to_complete=True,
            decisions=True,
            can_finalize=False,
        )
        == "a_corriger"
    )


def test_official_sheets_are_the_eight_bcm_sheets():
    assert "ETAT A" in rs.OFFICIAL_SHEETS
    assert "ETAT B" in rs.OFFICIAL_SHEETS
    assert "ETAT C" in rs.OFFICIAL_SHEETS
    assert "informations à fournir" in rs.OFFICIAL_SHEETS
    assert len(rs.OFFICIAL_SHEETS) == 8


def test_d01_d02_remain_documented_gates():
    assert "D01" in rs.GATE_LABELS
    assert "D02" in rs.GATE_LABELS
    assert "A_VALIDER" in rs.GATE_LABELS["D01"]
