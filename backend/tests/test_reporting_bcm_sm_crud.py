"""CRUD SM — suppression d'analyses non confirmées, garde-fous imports validés."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import AppError
from app.services.reporting_bcm_sm import import_service as ims
from app.services.reporting_bcm_sm.constants import (
    IMPORT_STATUSES_CONFIRMED,
    IMPORT_STATUSES_UNCONFIRMED,
)


def test_unconfirmed_vs_confirmed_status_sets():
    assert set(IMPORT_STATUSES_UNCONFIRMED) == {"UPLOADED", "ANALYZED", "REJECTED"}
    assert set(IMPORT_STATUSES_CONFIRMED) == {"VALIDATED", "SUPERSEDED"}
    assert not (set(IMPORT_STATUSES_UNCONFIRMED) & set(IMPORT_STATUSES_CONFIRMED))


def test_discard_and_delete_routes_in_source():
    import app as app_pkg

    root = Path(app_pkg.__file__).resolve().parent
    api = (root / "api/v1/endpoints/reporting_bcm_sm.py").read_text(encoding="utf-8")
    imports = (root / "services/reporting_bcm_sm/import_service.py").read_text(encoding="utf-8")
    camp = (root / "services/reporting_bcm_sm/campaign_service.py").read_text(encoding="utf-8")
    assert 'discard_unconfirmed_import' in api
    assert "/campaigns/{campaign_id}/imports/{import_id}" in api
    assert "IMPORT_DELETE_FORBIDDEN" in imports
    assert "_purge_campaign_children" in camp
    assert "imports_confirmed" in camp
    assert "quel que soit son statut" in camp


def test_discard_rejects_validated_import():
    async def _run():
        campaign = MagicMock()
        campaign.id = uuid4()
        campaign.status = "IMPORTS"
        imp = MagicMock()
        imp.status = "VALIDATED"
        imp.campaign_id = campaign.id
        db = AsyncMock()
        db.scalar = AsyncMock(return_value=imp)
        with pytest.raises(AppError) as ei:
            await ims.discard_unconfirmed_import(db, campaign=campaign, import_id=uuid4())
        assert ei.value.code == "IMPORT_DELETE_FORBIDDEN"
        assert ei.value.status_code == 409

    asyncio.run(_run())


def test_discard_rejects_superseded_import():
    async def _run():
        campaign = MagicMock()
        campaign.id = uuid4()
        campaign.status = "CALCULEE"
        imp = MagicMock()
        imp.status = "SUPERSEDED"
        imp.campaign_id = campaign.id
        db = AsyncMock()
        db.scalar = AsyncMock(return_value=imp)
        with pytest.raises(AppError) as ei:
            await ims.discard_unconfirmed_import(db, campaign=campaign, import_id=uuid4())
        assert ei.value.code == "IMPORT_DELETE_FORBIDDEN"

    asyncio.run(_run())


def test_discard_not_found():
    async def _run():
        campaign = MagicMock()
        campaign.id = uuid4()
        campaign.status = "BROUILLON"
        db = AsyncMock()
        db.scalar = AsyncMock(return_value=None)
        with pytest.raises(AppError) as ei:
            await ims.discard_unconfirmed_import(db, campaign=campaign, import_id=uuid4())
        assert ei.value.code == "IMPORT_NOT_FOUND"
        assert ei.value.status_code == 404

    asyncio.run(_run())


def test_discard_locked_campaign():
    async def _run():
        campaign = MagicMock()
        campaign.id = uuid4()
        campaign.status = "CLOTUREE"
        db = AsyncMock()
        with pytest.raises(AppError) as ei:
            await ims.discard_unconfirmed_import(db, campaign=campaign, import_id=uuid4())
        assert ei.value.code == "CAMPAIGN_LOCKED"
        db.scalar.assert_not_called()

    asyncio.run(_run())


def test_unlink_refuses_path_outside_upload_root(tmp_path, monkeypatch):
    outside = tmp_path / "outside.xlsx"
    outside.write_bytes(b"x")
    root = tmp_path / "uploads"
    root.mkdir()
    monkeypatch.setattr(ims, "upload_root", lambda: root)
    ims._unlink_stored_import(str(outside))
    assert outside.exists()


def test_unlink_removes_file_under_upload_root(tmp_path, monkeypatch):
    root = tmp_path / "uploads"
    dest = root / "reporting-bcm-sm" / "camp"
    dest.mkdir(parents=True)
    f = dest / "BAL_DET_abc.xlsx"
    f.write_bytes(b"x")
    monkeypatch.setattr(ims, "upload_root", lambda: root)
    ims._unlink_stored_import(str(f))
    assert not f.exists()


def test_delete_eligibility_allows_any_status():
    async def _run():
        from app.services.reporting_bcm_sm.campaign_service import delete_eligibility

        campaign = MagicMock()
        campaign.id = uuid4()
        campaign.status = "CALCULEE"
        db = AsyncMock()
        db.scalar = AsyncMock(side_effect=[2, 1, 3, 4])
        el = await delete_eligibility(db, campaign)
        assert el["can_delete"] is True
        assert el["dependencies"]["imports"] == 2
        assert el["dependencies"]["imports_confirmed"] == 1
        assert el["dependencies"]["parameters"] == 3
        assert el["dependencies"]["status"] == "CALCULEE"
        assert any("import" in r for r in el["reasons"])

    asyncio.run(_run())


def test_engine_untouched_by_crud_phase():
    import app as app_pkg

    root = Path(app_pkg.__file__).resolve().parent
    runner = (root / "services/reporting_bcm_sm/engine/runner.py").read_text(encoding="utf-8")
    mapping = (root / "services/reporting_bcm_sm/campaign_service.py").read_text(encoding="utf-8")
    assert "lifecycle_status" not in mapping
    assert "ENGINE_VERSION" in runner or "0.2.0-sm" in runner
