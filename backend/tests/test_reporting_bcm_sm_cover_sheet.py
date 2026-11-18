"""Feuille « À LIRE » — documentaire, hors canevas officiel."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from openpyxl import Workbook

from app.services.reporting_bcm_sm.work_cover_sheet import (
    COVER_SHEET_NAME,
    DOCUMENT_STATUS,
    NONE_ISSUE_MSG,
    NONE_MANUAL_MSG,
    build_cover_payload,
    classify_issue,
    parse_engine_cell_ref,
    write_a_lire_sheet,
)


def test_parse_engine_cell_ref():
    assert parse_engine_cell_ref("A:114:D") == ("ETAT A", "D114")
    assert parse_engine_cell_ref("A:235:C") == ("ETAT A", "C235")
    assert parse_engine_cell_ref("INFO:C9") == ("informations à fournir", "C9")
    assert parse_engine_cell_ref("not-a-ref") == (None, None)


def test_classify_issue_does_not_promote_warning_to_blocking():
    assert (
        classify_issue(severity="WARNING", resolution="OPEN", code="DET_LINE", category="A")
        == "Avertissement"
    )
    assert (
        classify_issue(severity="BLOCKING", resolution="OPEN", code="X", category="A")
        == "Anomalie bloquante"
    )
    assert (
        classify_issue(severity="WARNING", resolution="OPEN", code="DET_CLASSES_1_8", category="A")
        == "Écart constaté à examiner"
    )
    assert (
        classify_issue(severity="INFO", resolution="PENDING_DECISION", code="D01", category="D")
        == "Décision métier encore attendue"
    )
    assert (
        classify_issue(
            severity="BLOCKING",
            resolution="PENDING_DECISION",
            code="D01_MAPPING",
            category="D",
        )
        == "Décision métier encore attendue"
    )


def _campaign(**kwargs):
    data = dict(
        id=uuid4(),
        period_year=2026,
        period_month=8,
        campaign_version=1,
        bank_code="BEA",
    )
    data.update(kwargs)
    return SimpleNamespace(**data)


def _template():
    return SimpleNamespace(
        template_code="SM-BCM",
        version=1,
        filename="BEA-SM-10-2026.xlsx",
        sha256="abc123def4567890" * 4,
    )


def test_cover_sheet_is_first_and_does_not_touch_official_cells():
    wb = Workbook()
    ws = wb.active
    ws.title = "ETAT A"
    ws["D9"] = "=H9-H8"
    ws["I147"] = "=+H147-H81"
    payload = build_cover_payload(
        campaign=_campaign(),
        template=_template(),
        run=None,
        det=None,
        control_run=None,
        issues=[],
        gates_open={"D01": True, "D02": True},
        cell_results=[],
        generated_at=datetime(2026, 11, 18, 11, 0, tzinfo=timezone.utc),
        wb=wb,
    )
    write_a_lire_sheet(wb, payload)
    assert wb.sheetnames[0] == COVER_SHEET_NAME
    assert "ETAT A" in wb.sheetnames
    assert wb["ETAT A"]["D9"].value == "=H9-H8"
    assert wb["ETAT A"]["I147"].value == "=+H147-H81"
    blob = " ".join(
        str(wb[COVER_SHEET_NAME].cell(row=r, column=1).value or "")
        + " "
        + str(wb[COVER_SHEET_NAME].cell(row=r, column=2).value or "")
        for r in range(1, 20)
    )
    assert DOCUMENT_STATUS in blob
    assert "août 2026" in blob
    assert "SM-08-2026" in blob


def test_filled_manual_zero_is_not_presented_as_empty():
    filled = SimpleNamespace(
        cell_ref="A:322:D",
        retained_value=Decimal("0.00"),
        calculated_value=None,
        value_status="SAISIE_MANUELLE",
    )
    missing = SimpleNamespace(
        cell_ref="A:114:D",
        retained_value=None,
        calculated_value=None,
        value_status="NON_RENSEIGNE",
    )
    run = SimpleNamespace(id=uuid4(), report={"pending_manual": ["A:114:D"], "ecart_amount": "0"})
    payload = build_cover_payload(
        campaign=_campaign(),
        template=_template(),
        run=run,
        det=None,
        control_run=None,
        issues=[],
        gates_open={},
        cell_results=[filled, missing],
        generated_at=datetime(2026, 11, 18, 11, 0, tzinfo=timezone.utc),
    )
    by_addr = {r.excel_address: r for r in payload.manual_rows}
    d322 = by_addr["D322"]
    assert d322.filled is True
    assert d322.pending is False
    assert d322.current_display != "—"
    assert "0" in d322.current_display
    d114 = by_addr["D114"]
    assert d114.pending is True
    assert d114.current_display == "—"
    assert "Compléter" in d114.action


def test_ecart_is_observed_gap_not_blocking():
    run = SimpleNamespace(
        id=uuid4(),
        report={"pending_manual": [], "ecart_amount": "15.05"},
    )
    payload = build_cover_payload(
        campaign=_campaign(),
        template=_template(),
        run=run,
        det=None,
        control_run=None,
        issues=[],
        gates_open={},
        cell_results=[],
        generated_at=datetime(2026, 11, 18, 11, 0, tzinfo=timezone.utc),
    )
    assert payload.issue_rows
    row = payload.issue_rows[0]
    assert row.kind == "ecart"
    assert row.nature == "Écart constaté à examiner"
    assert "bloquan" not in row.nature.lower()
    assert "15,05" in row.explanation or "15.05" in row.explanation


def test_no_issue_short_message_and_open_gates_are_decisions():
    payload = build_cover_payload(
        campaign=_campaign(),
        template=_template(),
        run=SimpleNamespace(id=uuid4(), report={"pending_manual": [], "ecart_amount": "0"}),
        det=None,
        control_run=None,
        issues=[],
        gates_open={"D01": True, "D02": False},
        cell_results=[],
        generated_at=datetime(2026, 11, 18, 11, 0, tzinfo=timezone.utc),
    )
    assert payload.issue_rows == []
    wb = Workbook()
    wb.active.title = "ETAT A"
    write_a_lire_sheet(wb, payload)
    values = [
        str(wb[COVER_SHEET_NAME].cell(row=r, column=1).value or "")
        for r in range(1, 80)
    ]
    assert any(NONE_ISSUE_MSG in v for v in values)
    assert any("Décisions métier" in v for v in values)
    assert any("D01" in v or "Correspondances" in v for v in values)


def test_det_fields_come_from_the_linked_import_only():
    det = SimpleNamespace(
        id=uuid4(),
        filename="BAL_DET_202608.xlsx",
        status="VALIDATED",
        period_year_detected=2026,
        period_month_detected=8,
        created_at=datetime(2026, 9, 2, 8, 0, tzinfo=timezone.utc),
        validated_at=datetime(2026, 9, 2, 9, 0, tzinfo=timezone.utc),
        row_count=412,
        control_report={
            "ncg_count": 88,
            "compte_count": 390,
            "ready_to_confirm": True,
            "error_count": 0,
            "errors": [],
            "blocking_reasons": [],
        },
    )
    payload = build_cover_payload(
        campaign=_campaign(),
        template=_template(),
        run=SimpleNamespace(id=uuid4(), report={"pending_manual": [], "ecart_amount": "0"}),
        det=det,
        control_run=SimpleNamespace(
            id=uuid4(),
            result="WARNINGS",
            created_at=datetime(2026, 9, 2, 9, 10, tzinfo=timezone.utc),
        ),
        issues=[],
        gates_open={},
        cell_results=[],
        generated_at=datetime(2026, 11, 18, 11, 0, tzinfo=timezone.utc),
    )
    assert payload.det_filename == "BAL_DET_202608.xlsx"
    assert payload.det_period == "08/2026"
    assert payload.det_row_count == "412"
    assert payload.det_ncg_count == "88"
    assert payload.det_compte_count == "390"
    assert payload.det_import_id == str(det.id)
    assert "Confirmé" in (payload.det_analysis or "")
    assert "Avertissements" in (payload.det_controls or "")


def test_none_manual_message_when_manuals_are_filled():
    results = [
        SimpleNamespace(
            cell_ref=key,
            retained_value=Decimal("1.00"),
            calculated_value=None,
            value_status="SAISIE_MANUELLE",
        )
        for key in ("A:114:D", "A:234:C", "A:322:D", "A:322:F", "A:327:D")
    ]
    payload = build_cover_payload(
        campaign=_campaign(),
        template=_template(),
        run=SimpleNamespace(id=uuid4(), report={"pending_manual": [], "ecart_amount": "0"}),
        det=None,
        control_run=None,
        issues=[],
        gates_open={},
        cell_results=results,
        generated_at=datetime(2026, 11, 18, 11, 0, tzinfo=timezone.utc),
    )
    manuals = [r for r in payload.manual_rows if r.nature == "Saisie manuelle"]
    assert manuals and all(r.filled and not r.pending for r in manuals)
    wb = Workbook()
    write_a_lire_sheet(wb, payload)
    values = [str(wb[COVER_SHEET_NAME].cell(row=r, column=1).value or "") for r in range(1, 80)]
    assert any(NONE_MANUAL_MSG in v for v in values)
