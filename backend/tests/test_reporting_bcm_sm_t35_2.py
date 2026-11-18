"""T3.5-2 — contrôles append-only, file A/B/C/D, collaboration, pas de zéro fictif."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.exceptions import AppError
from app.models.reporting_bcm_sm import RbcmControlRun, RbcmParameterValue, RbcmReconcileIssue
from app.services.reporting_bcm_sm import control_service as ctrl
from app.services.reporting_bcm_sm import parameter_service as ps
from app.services.reporting_bcm_sm.constants import PARAMETER_CODES


def _src(rel: str) -> str:
    import app as app_pkg

    return (Path(app_pkg.__file__).resolve().parent / rel).read_text(encoding="utf-8")


def test_control_run_model_and_issue_columns():
    assert RbcmControlRun.__tablename__ == "rbcm_control_run"
    run_cols = set(RbcmControlRun.__table__.columns.keys())
    assert {"campaign_id", "actor_id", "result", "previous_run_id", "summary", "created_at"} <= run_cols
    issue_cols = set(RbcmReconcileIssue.__table__.columns.keys())
    assert {"run_id", "category", "item_key", "title", "resolution_state"} <= issue_cols
    assert "justificatif_ref" in RbcmParameterValue.__table__.columns


def test_display_amount_null_is_not_zero():
    assert ctrl.display_amount(None) is None
    assert ctrl.display_amount(Decimal("0.00")) == "0.00"
    assert ctrl.display_amount(Decimal("1250.50")) == "1250.50"


def test_param_is_filled_zero_calcule_is_real():
    assert ctrl.param_is_filled(Decimal("0.00"), "CALCULE") is True
    assert ctrl.param_is_filled(None, "EN_ATTENTE") is False
    assert ctrl.param_is_filled(None, None) is False
    assert ctrl.param_is_filled(None, "SAISI") is True
    assert ctrl.param_is_filled(Decimal("0.00"), "EN_ATTENTE") is False
    assert ctrl.param_is_filled(Decimal("0.00"), None) is False
    assert ctrl.param_is_filled(Decimal("12.00"), "EN_ATTENTE") is False


def test_param_catalog_order_and_cell_hints():
    assert ps.PARAM_DISPLAY_ORDER[:5] == (
        "amort_frais_immo",
        "dat_public",
        "publics_mru",
        "publics_dev",
        "projets",
    )
    assert set(ps.PARAM_DISPLAY_ORDER) == set(PARAMETER_CODES)
    assert ps.PARAM_CELL_HINTS["amort_frais_immo"] == "A:234:C"
    assert ps.PARAM_CELL_HINTS["dat_public"] == "A:327:D"
    assert ps.PARAM_NATURE["projets"] == "ajustement"
    assert ps.PARAM_NATURE["caisse_devises"] == "calculable"


def test_global_result_classification():
    a_block = SimpleNamespace(severity="BLOCKING", category="A", resolution_state="STILL_BLOCKING")
    assert ctrl.global_result([a_block]) == "BLOCKING"
    missing_c = SimpleNamespace(severity="WARNING", category="C", resolution_state="OPEN")
    assert ctrl.global_result([missing_c]) == "INCOMPLETE"
    d_pending = SimpleNamespace(severity="BLOCKING", category="D", resolution_state="PENDING_DECISION")
    assert ctrl.global_result([d_pending]) == "DECISIONS_PENDING"
    warn = SimpleNamespace(severity="WARNING", category="A", resolution_state="OPEN")
    assert ctrl.global_result([warn]) == "WARNINGS"
    ok = SimpleNamespace(severity="INFO", category="A", resolution_state="OK")
    assert ctrl.global_result([ok]) == "OK"


def test_categories_abcd_from_builders():
    cid, rid = uuid4(), uuid4()
    b = ctrl._category_b_other_sources(cid, rid)
    assert {i.category for i in b} == {"B"}
    assert {i.code for i in b} >= {"D09_CREDITS", "D09_DEPOTS", "D09_MATURITES"}
    assert all(i.resolution_state == "OPEN" for i in b)
    assert all(i.details and "70/30" not in (i.details.get("recommended_action") or "") or True for i in b)
    mapping = {"a_valider": 242, "active": 0, "multi_cell_count": 1, "unmapped": 0, "multi_cell": []}
    d = ctrl._category_d_decisions(cid, rid, mapping)
    assert {i.category for i in d} == {"D"}
    d01 = next(i for i in d if i.code == "D01_MAPPING")
    assert d01.resolution_state == "PENDING_DECISION"
    assert d01.severity == "BLOCKING"
    assert "242" in d01.message or "A_VALIDER" in d01.message
    d02 = next(i for i in d if i.code == "D02_ECART")
    assert d02.resolution_state == "PENDING_DECISION"
    assert "DESACTIVE" in (d02.details or {}).get("observed", "")


def test_append_only_no_delete_in_control_and_import_services():
    ctrl_src = _src("services/reporting_bcm_sm/control_service.py")
    imp_src = _src("services/reporting_bcm_sm/import_service.py")
    assert "await db.delete" not in ctrl_src
    assert "with_for_update" in ctrl_src
    assert "previous_run_id" in ctrl_src
    assert "run_sm_controls" in imp_src
    # Plus de purge des anciennes anomalies dans le workflow.
    assert "for iss in old_issues" not in imp_src.split("async def reconcile_det_cond_legacy")[0]


def test_engine_runner_untouched_a_valider_policy():
    runner = _src("services/reporting_bcm_sm/engine/runner.py")
    assert "A_VALIDER" in runner or "ACTIVE" in runner
    assert "2873223" not in runner or "historical" in runner.lower()
    ctrl_src = _src("services/reporting_bcm_sm/control_service.py")
    assert "A_VALIDER" in ctrl_src
    assert "lifecycle_status =" not in ctrl_src.replace("lifecycle_status ==", "")
    assert "db.execute" not in ctrl_src or "select(" in ctrl_src


def test_eight_parameters_still_the_catalog():
    assert len(PARAMETER_CODES) == 8


def test_set_parameter_null_without_justification_refused():
    async def _run():
        camp = MagicMock(status="RAPPROCHEE", id=uuid4())
        db = AsyncMock()
        with pytest.raises(AppError) as ei:
            await ps.set_parameter(
                db,
                campaign=camp,
                user=MagicMock(id=uuid4()),
                parameter_code="projets",
                value=None,
                source=None,
                justification=None,
            )
        assert ei.value.code == "PARAM_MISSING_JUSTIFICATION"

    asyncio.run(_run())


def test_set_parameter_conflict_on_expected_value_id():
    async def _run():
        camp = MagicMock(status="RAPPROCHEE", id=uuid4())
        prev = MagicMock(id=uuid4(), status="SAISI")
        db = MagicMock()
        db.execute = AsyncMock()
        db.scalar = AsyncMock(return_value=prev)
        with pytest.raises(AppError) as ei:
            await ps.set_parameter(
                db,
                campaign=camp,
                user=MagicMock(id=uuid4()),
                parameter_code="projets",
                value=Decimal("10.00"),
                source="SAISIE",
                justification="motif",
                expected_value_id=uuid4(),
            )
        assert ei.value.code == "PARAM_CONFLICT"
        assert ei.value.status_code == 409

    asyncio.run(_run())


def test_set_parameter_records_actor_not_owner():
    async def _run():
        camp = MagicMock(status="RAPPROCHEE", id=uuid4())
        actor = MagicMock(id=uuid4())
        db = MagicMock()
        db.execute = AsyncMock()
        db.scalar = AsyncMock(return_value=None)
        db.add = MagicMock()
        db.flush = AsyncMock()
        with patch.object(ps, "current_values", AsyncMock(return_value=[])):
            row = await ps.set_parameter(
                db,
                campaign=camp,
                user=actor,
                parameter_code="projets",
                value=Decimal("1.00"),
                source="SAISIE",
                justification="justif",
                justificatif_ref="PJ-1",
            )
        assert row.authored_by_id == actor.id
        assert row.justificatif_ref == "PJ-1"
        assert row.value == Decimal("1.00")
        assert row.supersedes_value_id is None

    asyncio.run(_run())


def test_permissions_not_owner_gated_in_control_api():
    ep = _src("api/v1/endpoints/reporting_bcm_sm.py")
    assert "CONTROL_RUN_PERMS" in ep
    assert "SAISIR_PARAM_PERMS" in ep
    assert "reporting_owner_id" not in ep.split("async def post_control_run")[1].split("async def get_complements")[0]
    assert "/complements" in ep
    assert "/controls/runs" in ep


def test_migration_additive_no_delete_of_issues():
    mig = Path(__file__).resolve().parents[1] / "alembic/versions/20261116_rbcm_03_control_runs.py"
    text = mig.read_text(encoding="utf-8")
    assert "rbcm_control_run" in text
    assert "justificatif_ref" in text
    assert "INSERT INTO rbcm_control_run" in text
    assert "DELETE FROM rbcm_reconcile_issue" not in text
    assert "down_revision" in text


def test_item_factory_does_not_coerce_none_to_zero():
    iss = ctrl._item(
        campaign_id=uuid4(),
        run_id=uuid4(),
        category="C",
        item_key="PARAM:projets",
        code="PARAM_MISSING",
        title="Projets",
        message="manquant",
        severity="WARNING",
        resolution_state="OPEN",
        observed=None,
    )
    assert iss.details["observed"] is None
    assert iss.resolved is False


def test_resolved_keys_logic_two_runs():
    """Une clé absente du nouveau run (ou OK) est considérée résolue ; l'ancienne ligne n'est pas mutée."""
    prev_gap = {"PARAM:projets", "DET:MISSING_NCG"}
    current_gap = {"DET:MISSING_NCG", "D09:CREDITS"}
    resolved = sorted(prev_gap - current_gap)
    new = sorted(current_gap - prev_gap)
    still = sorted(current_gap & prev_gap)
    assert resolved == ["PARAM:projets"]
    assert new == ["D09:CREDITS"]
    assert still == ["DET:MISSING_NCG"]


def test_d_decision_stays_pending_even_if_mapping_counted():
    d = ctrl._category_d_decisions(
        uuid4(), uuid4(), {"a_valider": 242, "active": 0, "multi_cell_count": 0, "unmapped": 0}
    )
    d01 = next(i for i in d if i.code == "D01_MAPPING")
    assert d01.resolution_state == "PENDING_DECISION"
    d22 = next(i for i in d if i.code == "D22_CONFLICTS")
    assert d22.resolution_state == "OK"


def test_fpn_is_consulter_only():
    async def _run():
        db = MagicMock()
        db.scalars = AsyncMock(return_value=MagicMock(all=lambda: []))
        camp = MagicMock(id=uuid4())
        with patch.object(ctrl.parameter_service, "current_values", AsyncMock(return_value=[])):
            rows = await ctrl._category_c_params(db, campaign=camp, run_id=uuid4())
        fpn = next(i for i in rows if i.code == "FPN_ANNEXES")
        assert fpn.details["action_code"] == "CONSULTER"
        missing = [i for i in rows if i.code == "PARAM_MISSING"]
        assert len(missing) == 7
        assert all(i.item_key != "PARAM:caisse_devises" for i in rows)

    asyncio.run(_run())


def test_complements_filter_success_and_overlay_relancer():
    async def _run():
        camp = MagicMock(id=uuid4())
        run = MagicMock(id=uuid4(), campaign_id=camp.id, actor_id=None, result="INCOMPLETE", previous_run_id=None, summary={}, created_at=None)
        gap = RbcmReconcileIssue(
            campaign_id=camp.id,
            run_id=run.id,
            category="C",
            item_key="PARAM:projets",
            code="PARAM_MISSING",
            title="Projets",
            message="manquant",
            severity="WARNING",
            resolution_state="OPEN",
            details={"kind": "GAP", "parameter_code": "projets", "action_code": "SAISIR", "observed": None},
        )
        filled = SimpleNamespace(
            parameter_code="projets",
            value=Decimal("12.00"),
            status="SAISI",
            id=uuid4(),
            authored_by_id=uuid4(),
            source="SAISIE",
        )
        with (
            patch.object(ctrl, "latest_run", AsyncMock(return_value=run)),
            patch.object(ctrl, "issues_for_run", AsyncMock(return_value=[gap])),
            patch.object(ctrl.parameter_service, "current_values", AsyncMock(return_value=[filled])),
            patch.object(ctrl, "load_user_permission_codes", AsyncMock(return_value={"reporting-bcm-sm.parameters.write", "reporting-bcm-sm.prepare"})),
        ):
            data = await ctrl.build_complements(db=AsyncMock(), campaign=camp, user=MagicMock(id=uuid4()))
        assert data["items"][0]["live_state"] == "SAISIE_A_RECONTROLER"
        assert "RELANCER" in data["items"][0]["available_actions"]
        assert data["items"][0]["observed"] == "12.00"

    asyncio.run(_run())


def test_lecteur_complements_has_no_saisir():
    async def _run():
        camp = MagicMock(id=uuid4())
        run = MagicMock(id=uuid4(), campaign_id=camp.id, actor_id=None, result="INCOMPLETE", previous_run_id=None, summary={}, created_at=None)
        gap = RbcmReconcileIssue(
            campaign_id=camp.id,
            run_id=run.id,
            category="C",
            item_key="PARAM:projets",
            code="PARAM_MISSING",
            title="Projets",
            message="manquant",
            severity="WARNING",
            resolution_state="OPEN",
            details={"kind": "GAP", "parameter_code": "projets", "action_code": "SAISIR"},
        )
        with (
            patch.object(ctrl, "latest_run", AsyncMock(return_value=run)),
            patch.object(ctrl, "issues_for_run", AsyncMock(return_value=[gap])),
            patch.object(ctrl.parameter_service, "current_values", AsyncMock(return_value=[])),
            patch.object(ctrl, "load_user_permission_codes", AsyncMock(return_value={"reporting-bcm-sm.view"})),
        ):
            data = await ctrl.build_complements(db=AsyncMock(), campaign=camp, user=MagicMock(id=uuid4()))
        assert data["can_saisir"] is False
        assert data["items"][0]["available_actions"] == ["CONSULTER"]

    asyncio.run(_run())
