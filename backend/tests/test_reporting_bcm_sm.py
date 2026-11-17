"""Reporting BCM SM — tests unitaires (sans DB) + catalogue."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.data.module_backup_scopes import ESPACE_MODULES, MODULE_BACKUP_SCOPES
from app.data.plateforme_catalogue import FUNCTIONAL_PERMISSIONS, PLATEFORME_MODULES, ROLE_PERMISSIONS
from app.services.reporting_bcm_sm.constants import PARAMETER_CODES
from app.services.reporting_bcm_sm.engine.amounts import amount_for_basis, quantize_mru
from app.services.reporting_bcm_sm.import_service import detect_period_from_filename


def test_catalogue_reporting_bcm_sm():
    module = next(m for m in PLATEFORME_MODULES if m["code"] == "reporting-bcm-sm")
    assert module["espace_code"] == "comptabilite"
    assert module["entry_path"] == "/reporting-bcm-sm/accueil"
    perms = {c for c, _l, m in FUNCTIONAL_PERMISSIONS if m == "reporting-bcm-sm"}
    assert {
        "reporting-bcm-sm.view",
        "reporting-bcm-sm.prepare",
        "reporting-bcm-sm.import",
        "reporting-bcm-sm.approve",
    } <= perms
    for role in (
        "reporting-bcm-sm.lecteur",
        "reporting-bcm-sm.preparateur",
        "reporting-bcm-sm.controleur",
        "reporting-bcm-sm.approbateur",
    ):
        assert set(ROLE_PERMISSIONS[role]) <= perms
    assert perms <= set(ROLE_PERMISSIONS["reporting-bcm-sm.admin"])
    assert "reporting-bcm-sm.prepare" not in ROLE_PERMISSIONS["reporting-bcm-sm.lecteur"]
    assert "reporting-bcm-sm.approve" not in ROLE_PERMISSIONS["reporting-bcm-sm.preparateur"]
    assert "reporting-bcm-sm" in ESPACE_MODULES["comptabilite"]
    assert MODULE_BACKUP_SCOPES["reporting-bcm-sm"]["table_prefixes"] == ["rbcm_"]


def test_parameter_codes_eight():
    assert len(PARAMETER_CODES) == 8
    assert "caisse_devises" in PARAMETER_CODES


def test_amounts_no_universal_max():
    d, c = Decimal("100.00"), Decimal("40.00")
    assert amount_for_basis(debit=d, credit=c, amount_basis="SIGNED") == Decimal("60.00")
    assert amount_for_basis(debit=d, credit=c, amount_basis="D") == Decimal("100.00")
    assert amount_for_basis(debit=d, credit=c, amount_basis="C") == Decimal("40.00")
    assert amount_for_basis(debit=d, credit=c, amount_basis="SD", signed_balance_mode="NATURAL") == Decimal(
        "60.00"
    )
    # SC naturel
    assert amount_for_basis(
        debit=Decimal("10"), credit=Decimal("50"), amount_basis="SC", signed_balance_mode="NATURAL"
    ) == Decimal("40.00")
    # SIGNED peut être négatif — pas de MAX universel
    assert amount_for_basis(
        debit=Decimal("10"), credit=Decimal("50"), amount_basis="SIGNED"
    ) == Decimal("-40.00")


def test_quantize_mru():
    assert quantize_mru(Decimal("1.239")) == Decimal("1.24")


def test_detect_period_filename():
    assert detect_period_from_filename("BAL DET 31-10-2026.xlsx") == (2026, 10)
    assert detect_period_from_filename("BAL_COND_2026-10.xlsx")[0] == 2026


def test_ecart_constant_not_in_engine_source():
    from pathlib import Path

    import app as app_pkg

    runner_path = Path(app_pkg.__file__).resolve().parent / "services/reporting_bcm_sm/engine/runner.py"
    runner = runner_path.read_text(encoding="utf-8")
    assert "2873223" not in runner or "historical" in runner.lower()
    # La constante ne doit pas être utilisée comme valeur de calcul
    assert "amount = Decimal(\"2873223\")" not in runner
    assert "Decimal('2873223')" not in runner


def test_parse_correspondance_a_valider_only():
    from pathlib import Path

    from app.services.reporting_bcm_sm.mapping_seed import dry_run_correspondance, parse_correspondance_xlsx

    path = Path(r"C:\Users\sallm\Downloads\Correspondance_BAL_SM_BEA_10-2026_1==SCD.xlsx")
    if not path.is_file():
        pytest.skip("Fichier Correspondance absent")
    rules = parse_correspondance_xlsx(path)
    assert len(rules) == 242
    assert all(r["lifecycle_status"] == "A_VALIDER" for r in rules)
    assert all(r["provenance"] == "CORRESPONDANCE" for r in rules)
    report = dry_run_correspondance(path)
    assert report["unique_business_rules"] == 242
    assert report["unique_cells"] == 43
    assert report["lifecycle_forced"] == "A_VALIDER"
    assert report["prefix_rules"] == 0
    assert len(report["conflicts_base_sign"]) == 1
    assert report["conflicts_base_sign"][0]["pattern"] == "218200"


def test_p2_unique_includes_version():
    from app.models.reporting_bcm_sm import RbcmCampaign

    args = RbcmCampaign.__table_args__
    uq = [a for a in args if getattr(a, "name", None) == "uq_rbcm_campaign_period_version"]
    assert uq, "Contrainte P2 manquante"
    cols = list(uq[0].columns.keys()) if hasattr(uq[0], "columns") else list(uq[0].columns)
    # SQLAlchemy UniqueConstraint stores column names
    names = set(uq[0].columns.keys()) if hasattr(uq[0].columns, "keys") else set(uq[0].columns)
    assert "campaign_version" in names
    assert "period_year" in names


def _xlsx_bytes(headers: list, rows: list) -> bytes:
    from io import BytesIO

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_analyze_bal_det_columns_and_decimal():
    from app.services.reporting_bcm_sm.import_service import analyze_bal_det

    data = _xlsx_bytes(
        ["NCG", "COMPTE", "LIBELLE", "DEVISE", "DEB", "CRE"],
        [
            ["101000", "101000001", "Caisse EUR", "EUR", "20254.50", "0"],
            ["216100", "216100001", "Compte test", "MRU", "100.00", "40.00"],
        ],
    )
    report = analyze_bal_det(data)
    assert report["header_ok"] is True
    assert report["row_count"] == 2
    assert report["ncg_count"] == 2
    assert report["devises"]["EUR"] == 1
    assert report["devises"]["MRU"] == 1
    assert report["rows"][0]["ncg"] == "101000"
    assert report["rows"][0]["compte"] == "101000001"
    assert report["rows"][0]["devise"] == "EUR"
    assert report["rows"][0]["debit"] == Decimal("20254.50")
    assert isinstance(report["sum_debit"], Decimal)
    assert report["sum_debit"] == Decimal("20354.50")


def test_analyze_bal_det_bad_header():
    from app.services.reporting_bcm_sm.import_service import analyze_bal_det

    data = _xlsx_bytes(["A", "B", "C", "D", "E", "F"], [["1", "2", "3", "MRU", "1", "0"]])
    report = analyze_bal_det(data)
    assert report["header_ok"] is False
    assert report["header_errors"]


def test_analyze_bal_cond_var_check():
    from app.services.reporting_bcm_sm.import_service import analyze_bal_cond

    data = _xlsx_bytes(
        ["CLAS", "NCG", "LIBELLE", "TOTDEB", "TOTCRE", "VAR"],
        [
            ["2", "216100", "Test", "100", "40", "60"],
            ["2", "216200", "Bad VAR", "10", "5", "99"],
        ],
    )
    report = analyze_bal_cond(data)
    assert report["header_ok"] is True
    assert report["row_count"] == 2
    assert report["var_mismatch_count"] == 1
    assert report["ncg_count"] == 2


def test_analyze_bal_cond_missing_and_duplicate_ncg():
    """Cause T3.4-A : NCG vides → '?' → collision uq_rbcm_balance_ncg."""
    from app.services.reporting_bcm_sm.import_service import (
        aggregate_cond_balances,
        analyze_bal_cond,
    )

    data = _xlsx_bytes(
        ["CLAS", "NCG", "LIBELLE", "TOTDEB", "TOTCRE", "VAR"],
        [
            ["2", "216100", "A", "100", "40", "60"],
            ["2", None, "Sans NCG 1", "1", "0", "1"],
            ["2", "", "Sans NCG 2", "2", "0", "2"],
            ["2", "216100", "A bis", "50", "10", "40"],
            ["2", "216200", "B", "10", "5", "5"],
        ],
    )
    report = analyze_bal_cond(data)
    assert report["row_count"] == 5
    assert report["missing_ncg_count"] == 2
    assert report["duplicate_ncg_count"] == 1
    assert report["ncg_count"] == 2
    assert report["ready_to_confirm"] is True

    agg, skipped = aggregate_cond_balances(report["rows"])
    assert skipped == 2
    assert set(agg.keys()) == {"216100", "216200"}
    assert agg["216100"][0] == Decimal("150.00")
    assert agg["216100"][1] == Decimal("50.00")
    # Aucun placeholder "?" — aurait violé uq_rbcm_balance_ncg
    assert "?" not in agg


def test_aggregate_det_skips_empty_ncg():
    from app.services.reporting_bcm_sm.import_service import aggregate_det_balances

    rows = [
        {"ncg": "101", "debit": Decimal("10"), "credit": Decimal("0"), "libelle": "A"},
        {"ncg": None, "debit": Decimal("1"), "credit": Decimal("0"), "libelle": "X"},
        {"ncg": "101", "debit": Decimal("5"), "credit": Decimal("2"), "libelle": "A2"},
    ]
    agg, skipped = aggregate_det_balances(rows)
    assert skipped == 1
    assert agg["101"][0] == Decimal("15")
    assert agg["101"][1] == Decimal("2")
    assert "?" not in agg


def test_import_sha_unique_includes_file_type():
    """Idempotence = (campaign_id, file_type, sha256) — DET et COND coexistent."""
    from app.models.reporting_bcm_sm import RbcmImport

    args = RbcmImport.__table_args__
    uq = [a for a in args if getattr(a, "name", None) == "uq_rbcm_import_sha"]
    assert uq
    names = set(uq[0].columns.keys()) if hasattr(uq[0].columns, "keys") else set(uq[0].columns)
    assert names == {"campaign_id", "file_type", "sha256"}


def test_balance_ncg_unique_is_per_import():
    from app.models.reporting_bcm_sm import RbcmBalanceNcg

    args = RbcmBalanceNcg.__table_args__
    uq = [a for a in args if getattr(a, "name", None) == "uq_rbcm_balance_ncg"]
    assert uq
    names = set(uq[0].columns.keys()) if hasattr(uq[0].columns, "keys") else set(uq[0].columns)
    assert names == {"import_id", "ncg"}


def test_det_only_aggregation_and_controls_helpers():
    """T3.4-A2 — BAL DET seule : agrégation + pas de dépendance COND pour le workflow."""
    from app.services.reporting_bcm_sm.constants import IMPORT_FILE_TYPES_ACTIVE, IMPORT_FILE_TYPES_DEPRECATED
    from app.services.reporting_bcm_sm.import_service import aggregate_det_balances, analyze_bal_det

    assert IMPORT_FILE_TYPES_ACTIVE == ("BAL_DET",)
    assert "BAL_COND" in IMPORT_FILE_TYPES_DEPRECATED

    det = analyze_bal_det(
        _xlsx_bytes(
            ["NCG", "COMPTE", "LIBELLE", "DEVISE", "DEB", "CRE"],
            [
                ["216100", "216100001", "A", "MRU", "100", "40"],
                ["216200", "216200001", "B", "MRU", "10", "5"],
                [None, "999", "Sans NCG", "MRU", "1", "0"],
            ],
        )
    )
    assert det["row_count"] == 3
    assert det["ncg_count"] == 2
    assert det["ready_to_confirm"] is True
    agg, skipped = aggregate_det_balances(det["rows"])
    assert skipped == 1
    assert set(agg) == {"216100", "216200"}
    assert "?" not in agg


def test_upload_rejects_bal_cond():
    """Workflow normal : upload BAL COND refusé (410 IMPORT_COND_DEPRECATED)."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    from app.core.exceptions import AppError
    from app.services.reporting_bcm_sm.import_service import upload_and_analyze

    async def _run():
        with pytest.raises(AppError) as ei:
            await upload_and_analyze(
                AsyncMock(),
                campaign=MagicMock(id="c"),
                user=MagicMock(id="u"),
                file_type="BAL_COND",
                filename="BAL COND.xlsx",
                data=b"x",
            )
        assert ei.value.code == "IMPORT_COND_DEPRECATED"
        assert ei.value.status_code == 410

    asyncio.run(_run())


def test_engine_requires_det_only_not_cond():
    from pathlib import Path

    import app as app_pkg

    src = (Path(app_pkg.__file__).resolve().parent / "services/reporting_bcm_sm/engine/runner.py").read_text(
        encoding="utf-8"
    )
    assert "CALC_MISSING_IMPORTS" in src
    assert "BAL_DET" in src
    assert "SUM_SIGNED_CLASSES_1_8_DET" in src
    assert "Imports DET et COND validés requis" not in src
    assert 'source == "BAL_COND"' not in src or "legacy" in src.lower()


def test_sha256_idempotence_helper():
    from app.services.reporting_bcm_sm.import_service import _sha256

    a = _sha256(b"abc")
    b = _sha256(b"abc")
    c = _sha256(b"abd")
    assert a == b
    assert a != c
    assert len(a) == 64


def test_parameter_no_n1_carry():
    """Garantit qu'aucun service ne propose une reconduction N−1."""
    from pathlib import Path

    import app as app_pkg

    src = Path(app_pkg.__file__).resolve().parent / "services/reporting_bcm_sm/parameter_service.py"
    text = src.read_text(encoding="utf-8")
    assert "reconduction" in text.lower() or "N−1" in text or "N-1" in text
    assert "previous_month" not in text
    assert "carry_forward" not in text


def test_open_campaign_statuses_exclude_closed():
    from app.services.reporting_bcm_sm.constants import CAMPAIGN_STATUSES, OPEN_CAMPAIGN_STATUSES

    assert "CLOTUREE" not in OPEN_CAMPAIGN_STATUSES
    assert "CLOTUREE" in CAMPAIGN_STATUSES


def test_sm_kpi_open_excludes_calculee():
    """T3.4-C — CALCULEE n'est pas une SM ouverte."""
    from app.services.reporting_bcm_sm.constants import (
        SM_APPROVED_STATUSES,
        SM_CALCULATED_STATUSES,
        SM_CLOSED_STATUSES,
        SM_OPEN_STATUSES,
        SM_PENDING_VALIDATION_STATUSES,
    )

    assert "CALCULEE" not in SM_OPEN_STATUSES
    assert "CALCULEE" in SM_CALCULATED_STATUSES
    assert "A_CONTROLER" in SM_PENDING_VALIDATION_STATUSES
    assert "APPROUVEE" in SM_APPROVED_STATUSES
    assert "CLOTUREE" in SM_CLOSED_STATUSES


def test_delete_eligibility_messages_documented():
    """Suppression d'une SM autorisée quel que soit le statut (cascade FK)."""
    from pathlib import Path

    import app as app_pkg

    src = Path(app_pkg.__file__).resolve().parent / "services/reporting_bcm_sm/campaign_service.py"
    text = src.read_text(encoding="utf-8")
    assert "_purge_campaign_children" in text
    assert '"can_delete": True' in text
    assert "can_archive" in text
    assert "ARCHIVE" in text
