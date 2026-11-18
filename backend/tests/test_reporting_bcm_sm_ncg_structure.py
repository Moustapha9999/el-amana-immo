"""Structure NCG — comparaison BAL DET par période (sans DB)."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from app.services.reporting_bcm_sm.engine.det_basis import canonical_ncg
from app.services.reporting_bcm_sm.ncg_structure_service import (
    PeriodNcgRow,
    PeriodSnapshot,
    STATUS_ABSENT_MAPPE,
    STATUS_CONNU_NON_ORIENTE,
    STATUS_DEJA_MAPPE,
    STATUS_NOUVEAU,
    build_structure_report,
    catalog_exact_ncg_index,
    structure_summary,
)


def _row(ncg: str, deb: str = "0", cre: str = "0", lib: str | None = None) -> PeriodNcgRow:
    return PeriodNcgRow(
        ncg=ncg,
        libelle=lib or ncg,
        tot_debit=Decimal(deb),
        tot_credit=Decimal(cre),
    )


def _snap(year: int, month: int, rows: dict[str, PeriodNcgRow]) -> PeriodSnapshot:
    return PeriodSnapshot(
        period_year=year,
        period_month=month,
        campaign_id=uuid4(),
        import_id=uuid4(),
        rows=rows,
    )


def test_canonical_formats_are_same_ncg():
    assert canonical_ncg("210 000") == "210000"
    assert canonical_ncg("210000.0") == "210000"
    assert canonical_ncg("210000") == "210000"


def test_catalog_index_includes_exact_mapped_ncgs():
    index = catalog_exact_ncg_index()
    assert "210000" in index
    assert any(c["cell_ref"] == "A:131:D" for c in index["210000"])
    assert "315100" in index
    assert any(c["cell_ref"] == "A:402:D" and c["basis"] == "CREDIT" for c in index["315100"])
    assert "322000" in index
    assert any(c["cell_ref"] == "A:206:D" and c["basis"] == "DEBIT" for c in index["322000"])


def test_new_known_mapped_absent_zero_and_reappeared():
    mapped = {
        "210000": [{"cell_ref": "A:131:D", "basis": "DEBIT", "sign": 1}],
        "999001": [{"cell_ref": "A:999:D", "basis": "DEBIT", "sign": 1}],
    }
    aout = _snap(
        2026,
        8,
        {
            "210000": _row("210000", "100", "0"),
            "500001": _row("500001", "10", "0"),  # connu plus tard, non mappé
            "500002": _row("500002", "1", "0"),  # disparaît en sept, revient en oct
        },
    )
    sept = _snap(
        2026,
        9,
        {
            "210000": _row("210000", "110", "0"),
            "500001": _row("500001", "0", "0"),  # présent solde nul
        },
    )
    octo = _snap(
        2026,
        10,
        {
            "210000": _row("210000", "120", "0"),  # déjà mappé
            "500001": _row("500001", "5", "0"),  # connu non orienté
            "500002": _row("500002", "2", "0"),  # réapparu
            "700099": _row("700099", "9", "0"),  # nouveau (classe 7 informatif)
            "888888": _row("888888", "0", "0"),  # nouveau + solde nul
        },
    )
    report = build_structure_report(
        current=octo,
        history=[aout, sept],
        mapped_index=mapped,
        class_prefixes=frozenset({"6", "7", "8"}),
    )
    by = {i["ncg"]: i for i in report["items"]}
    assert by["210000"]["status"] == STATUS_DEJA_MAPPE
    assert by["500001"]["status"] == STATUS_CONNU_NON_ORIENTE
    assert by["500002"]["status"] == STATUS_CONNU_NON_ORIENTE
    assert by["500002"]["reapparu"] is True
    assert by["500002"]["last_seen_period"] == "08/2026"
    assert by["700099"]["status"] == STATUS_NOUVEAU
    assert by["700099"]["covered_by_class"] is True
    assert by["888888"]["status"] == STATUS_NOUVEAU
    assert by["888888"]["present_zero"] is True
    assert report["counts"]["nouveau"] == 2
    assert report["counts"]["reapparu"] == 1
    assert report["counts"]["present_zero"] == 1
    absent = {a["ncg"]: a for a in report["absents"]}
    assert absent["999001"]["status"] == STATUS_ABSENT_MAPPE
    assert report["orientation_auto"] is False
    summary = structure_summary(report)
    assert "700099" in summary["nouveaux"]
    assert "500002" in summary["reapparus"]
    assert "999001" in summary["absents_mappe"]


def test_late_import_of_older_period_does_not_make_current_ncgs_new():
    """Août importé après octobre : les NCG d'octobre déjà vus en août ne sont pas nouveaux."""
    mapped = {"210000": [{"cell_ref": "A:131:D", "basis": "DEBIT", "sign": 1}]}
    # Historique métier : août puis septembre, même si août a été confirmé plus tard.
    aout = _snap(2026, 8, {"210000": _row("210000", "1"), "311115": _row("311115", "2")})
    sept = _snap(2026, 9, {"210000": _row("210000", "3")})
    octo = _snap(
        2026,
        10,
        {
            "210000": _row("210000", "4"),
            "311115": _row("311115", "5"),
            "900001": _row("900001", "6"),
        },
    )
    report = build_structure_report(
        current=octo,
        history=[sept, aout],  # ordre d'import inversé volontairement
        mapped_index=mapped,
        class_prefixes=frozenset(),
    )
    by = {i["ncg"]: i for i in report["items"]}
    assert by["210000"]["status"] == STATUS_DEJA_MAPPE
    assert by["311115"]["status"] == STATUS_CONNU_NON_ORIENTE
    assert by["311115"]["reapparu"] is True  # absent en sept, présent en août
    assert by["900001"]["status"] == STATUS_NOUVEAU
    assert report["history_period_count"] == 2
    assert [p["label"] for p in report["available_periods"]] == ["08/2026", "09/2026", "10/2026"]


def test_no_validated_det_report():
    report = build_structure_report(current=None, history=[], mapped_index={}, class_prefixes=frozenset())
    assert report["has_validated_det"] is False
    assert report["items"] == []
    assert report["counts"]["nouveau"] == 0
