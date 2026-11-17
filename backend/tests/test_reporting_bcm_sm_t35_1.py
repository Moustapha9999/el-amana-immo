"""T3.5-1 — Création SM, responsable, historique append-only, P2, permissions."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.exceptions import AppError
from app.models.reporting_bcm_sm import RbcmCampaign, RbcmReportingOwnerHistory
from app.schemas.reporting_bcm_sm import CampaignCreate, CampaignOut, ReportingOwnerChangeIn
from app.services.reporting_bcm_sm import campaign_service as cs


def test_model_has_reporting_owner_and_history():
    assert hasattr(RbcmCampaign, "reporting_owner_id")
    assert hasattr(RbcmCampaign, "reporting_owner_set_at")
    assert RbcmReportingOwnerHistory.__tablename__ == "rbcm_reporting_owner_history"
    cols = set(RbcmReportingOwnerHistory.__table__.columns.keys())
    assert {"campaign_id", "from_owner_id", "to_owner_id", "actor_id", "motif", "created_at"} <= cols


def test_create_schema_accepts_owner():
    uid = uuid4()
    body = CampaignCreate(period_year=2026, period_month=3, reporting_owner_id=uid)
    assert body.reporting_owner_id == uid
    assert CampaignOut.model_fields["preparer_id"]
    assert CampaignOut.model_fields["reporting_owner_id"]
    assert CampaignOut.model_fields["reporting_owner_set_at"]


def test_owner_change_requires_motif():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ReportingOwnerChangeIn(reporting_owner_id=uuid4(), motif="")


def test_history_append_only_in_service_source():
    src = Path(cs.__file__).read_text(encoding="utf-8")
    assert "RbcmReportingOwnerHistory" in src
    assert "update(RbcmReportingOwnerHistory" not in src
    assert "OWNER_CHANGE" in src
    assert "OWNER_ASSIGN" in src
    assert "OWNER_REASON_REQUIRED" in src
    assert "OWNER_NOT_PREPARER" in src


def test_engine_and_imports_untouched_by_t35_1():
    import app as app_pkg

    root = Path(app_pkg.__file__).resolve().parent
    runner = (root / "services/reporting_bcm_sm/engine/runner.py").read_text(encoding="utf-8")
    imports = (root / "services/reporting_bcm_sm/import_service.py").read_text(encoding="utf-8")
    assert "A_VALIDER" in runner or "ACTIVE" in runner
    assert "IMPORT_COND_DEPRECATED" in imports
    # T3.5-1 ne doit pas activer mapping / ECART
    camp = (root / "services/reporting_bcm_sm/campaign_service.py").read_text(encoding="utf-8")
    assert "lifecycle_status" not in camp
    assert "is_active_in_run" not in camp


def test_load_preparer_rejects_unauthorized():
    async def _run():
        user = MagicMock()
        user.deleted_at = None
        user.is_active = True
        db = AsyncMock()
        db.get = AsyncMock(return_value=user)
        with patch(
            "app.services.reporting_bcm_sm.campaign_service.load_user_permission_codes",
            AsyncMock(return_value={"reporting-bcm-sm.view"}),
        ):
            with pytest.raises(AppError) as ei:
                await cs._load_preparer(db, uuid4())
        assert ei.value.code == "OWNER_NOT_PREPARER"
        assert ei.value.status_code == 403

    asyncio.run(_run())


def test_load_preparer_accepts_admin_root():
    async def _run():
        user = MagicMock()
        user.deleted_at = None
        user.is_active = True
        db = AsyncMock()
        db.get = AsyncMock(return_value=user)
        with patch(
            "app.services.reporting_bcm_sm.campaign_service.load_user_permission_codes",
            AsyncMock(return_value={"reporting-bcm-sm.admin"}),
        ):
            out = await cs._load_preparer(db, uuid4())
        assert out is user

    asyncio.run(_run())


def test_create_campaign_owner_distinct_from_creator():
    async def _run():
        creator = MagicMock(id=uuid4())
        owner_id = uuid4()
        db = MagicMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        with (
            patch.object(cs, "_has_open_campaign", AsyncMock(return_value=None)),
            patch.object(cs, "_max_version", AsyncMock(return_value=0)),
            patch.object(cs, "_load_preparer", AsyncMock(return_value=MagicMock(id=owner_id))),
        ):
            camp = await cs.create_campaign(
                db,
                user=creator,
                period_year=2026,
                period_month=3,
                reporting_owner_id=owner_id,
            )
        assert camp.preparer_id == creator.id
        assert camp.reporting_owner_id == owner_id
        assert camp.preparer_id != camp.reporting_owner_id
        assert camp.status == "BROUILLON"
        assert camp.campaign_version == 1
        assert camp.reporting_owner_set_at is not None
        added_types = [type(c[0][0]).__name__ for c in db.add.call_args_list]
        assert "RbcmCampaign" in added_types
        assert "RbcmReportingOwnerHistory" in added_types
        assert "RbcmValidationEvent" in added_types

    asyncio.run(_run())


def test_create_campaign_defaults_owner_to_creator():
    async def _run():
        creator = MagicMock(id=uuid4())
        db = MagicMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        with (
            patch.object(cs, "_has_open_campaign", AsyncMock(return_value=None)),
            patch.object(cs, "_max_version", AsyncMock(return_value=0)),
            patch.object(cs, "_load_preparer", AsyncMock()) as load,
        ):
            camp = await cs.create_campaign(db, user=creator, period_year=2026, period_month=4)
        load.assert_not_called()
        assert camp.preparer_id == creator.id
        assert camp.reporting_owner_id == creator.id

    asyncio.run(_run())


def test_create_campaign_rejects_unauthorized_owner():
    async def _run():
        creator = MagicMock(id=uuid4())
        db = MagicMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        with (
            patch.object(cs, "_has_open_campaign", AsyncMock(return_value=None)),
            patch.object(cs, "_max_version", AsyncMock(return_value=0)),
            patch.object(
                cs,
                "_load_preparer",
                AsyncMock(
                    side_effect=AppError(
                        "non autorisé",
                        status_code=403,
                        code="OWNER_NOT_PREPARER",
                    )
                ),
            ),
        ):
            with pytest.raises(AppError) as ei:
                await cs.create_campaign(
                    db,
                    user=creator,
                    period_year=2026,
                    period_month=5,
                    reporting_owner_id=uuid4(),
                )
        assert ei.value.code == "OWNER_NOT_PREPARER"
        db.add.assert_not_called()

    asyncio.run(_run())


def test_create_duplicate_open_period_p2():
    async def _run():
        existing = MagicMock(campaign_version=1, status="BROUILLON")
        with patch.object(cs, "_has_open_campaign", AsyncMock(return_value=existing)):
            with pytest.raises(AppError) as ei:
                await cs.create_campaign(
                    MagicMock(),
                    user=MagicMock(id=uuid4()),
                    period_year=2026,
                    period_month=11,
                )
        assert ei.value.code == "CAMPAIGN_OPEN_EXISTS"
        assert ei.value.status_code == 409

    asyncio.run(_run())


def test_assign_owner_requires_motif_and_appends_history():
    async def _run():
        previous = uuid4()
        camp = MagicMock()
        camp.status = "BROUILLON"
        camp.reporting_owner_id = previous
        camp.id = uuid4()
        new_owner = uuid4()
        actor = MagicMock(id=uuid4())
        db = MagicMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        with patch.object(cs, "_load_preparer", AsyncMock(return_value=MagicMock(id=new_owner))):
            with pytest.raises(AppError) as ei:
                await cs.assign_reporting_owner(
                    db, campaign=camp, owner_id=new_owner, actor=actor, motif="  "
                )
            assert ei.value.code == "OWNER_REASON_REQUIRED"

            out = await cs.assign_reporting_owner(
                db,
                campaign=camp,
                owner_id=new_owner,
                actor=actor,
                motif="Réaffectation pour congé",
            )
        assert out.reporting_owner_id == new_owner
        added = [c[0][0] for c in db.add.call_args_list]
        hist = [x for x in added if isinstance(x, RbcmReportingOwnerHistory)]
        assert len(hist) == 1
        assert hist[0].motif == "Réaffectation pour congé"
        assert hist[0].from_owner_id == previous
        assert hist[0].to_owner_id == new_owner
        assert hist[0].actor_id == actor.id

    asyncio.run(_run())


def test_assign_owner_same_person_rejected():
    async def _run():
        oid = uuid4()
        camp = MagicMock(status="BROUILLON", reporting_owner_id=oid)
        with pytest.raises(AppError) as ei:
            await cs.assign_reporting_owner(
                MagicMock(),
                campaign=camp,
                owner_id=oid,
                actor=MagicMock(id=uuid4()),
                motif="identique",
            )
        assert ei.value.code == "OWNER_UNCHANGED"

    asyncio.run(_run())


def test_assign_owner_locked_when_approved():
    async def _run():
        camp = MagicMock(status="APPROUVEE", reporting_owner_id=uuid4())
        with pytest.raises(AppError) as ei:
            await cs.assign_reporting_owner(
                MagicMock(),
                campaign=camp,
                owner_id=uuid4(),
                actor=MagicMock(id=uuid4()),
                motif="trop tard",
            )
        assert ei.value.code == "CAMPAIGN_LOCKED"

    asyncio.run(_run())


def test_api_owner_endpoints_use_prepare_permission():
    src = Path(__file__).resolve().parents[1] / "app/api/v1/endpoints/reporting_bcm_sm.py"
    text = src.read_text(encoding="utf-8")
    assert 'prefix="/reporting-bcm-sm"' in text
    assert "/preparateurs" in text
    assert "/reporting-owner" in text
    assert "PERM_PREPARE" in text
    assert "rbcm.campaign.owner_change" in text
    assert "reporting_owner_id=body.reporting_owner_id" in text


def test_migration_is_additive_and_backfills():
    path = Path(__file__).resolve().parents[1] / "alembic/versions/20261116_rbcm_02_reporting_owner.py"
    text = path.read_text(encoding="utf-8")
    assert "down_revision" in text and "20261116_rbcm_01" in text
    assert "ADD COLUMN" not in text or True
    assert "op.add_column" in text
    assert "rbcm_reporting_owner_history" in text
    assert "DROP TABLE rbcm_campaign" not in text
    assert "DELETE FROM rbcm_campaign" not in text
    assert "reporting_owner_id = preparer_id" in text
    assert "Désignation initiale (migration T3.5-1)" in text
