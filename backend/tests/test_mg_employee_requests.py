"""Demandes employés — transitions et isolation (sans DB)."""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.schemas.mg_requests import RequestCreate, RequestItemIn
from app.services.mg_requests_service import EDITABLE, GROUPABLE, MgRequestsService


def _user(*, superuser=False):
    u = MagicMock()
    u.id = uuid4()
    u.full_name = "Moustapha Test"
    u.agence_id = uuid4()
    u.is_superuser = superuser
    return u


def _request(*, statut="BROUILLON", requester=None):
    uid = requester or uuid4()
    return SimpleNamespace(
        id=uuid4(),
        request_number="DEM-MG-2026-000001",
        requester_id=uid,
        status=statut,
        items=[SimpleNamespace(id=uuid4(), description="Ramette", quantity=Decimal("2"))],
        complement_comment=None,
        submitted_at=None,
        received_at=None,
        validated_at=None,
        rejected_at=None,
        closed_at=None,
        validated_by=None,
        rejected_by=None,
        rejection_reason=None,
        validation_comment=None,
        batch_id=None,
        achat_demande_id=None,
        title="Papier",
        priority="NORMALE",
        source_espace_code="credit",
        target_espace_code="moyens-generaux",
    )


@pytest.mark.asyncio
async def test_submit_sets_soumise_and_notifies():
    db = MagicMock()
    db.commit = AsyncMock()
    svc = MgRequestsService(db)
    user = _user()
    row = _request(requester=user.id)
    svc._load = AsyncMock(return_value=row)
    svc._approve = AsyncMock()
    with (
        patch("app.services.mg_requests_service.audit_request", AsyncMock()),
        patch("app.services.mg_requests_service.notify_requester", AsyncMock()) as n1,
        patch("app.services.mg_requests_service.notify_mg_roles", AsyncMock()) as n2,
    ):
        out = await svc.submit(row.id, user)
    assert out.status == "SOUMISE"
    assert out.submitted_at is not None
    n1.assert_awaited()
    n2.assert_awaited()


@pytest.mark.asyncio
async def test_employee_cannot_see_other_request_on_update():
    db = MagicMock()
    svc = MgRequestsService(db)
    owner = _user()
    other = _user()
    row = _request(requester=owner.id)
    svc._load = AsyncMock(return_value=row)
    with pytest.raises(HTTPException) as exc:
        await svc.update_request(row.id, MagicMock(), other, owner_only=True)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_validate_moves_to_regrouper():
    db = MagicMock()
    db.commit = AsyncMock()
    svc = MgRequestsService(db)
    user = _user()
    row = _request(statut="RECUE")
    svc._load = AsyncMock(return_value=row)
    svc._approve = AsyncMock()
    with (
        patch("app.services.mg_requests_service.audit_request", AsyncMock()),
        patch("app.services.mg_requests_service.notify_requester", AsyncMock()),
    ):
        out = await svc.validate(row.id, user, "OK")
    assert out.status == "A_REGROUPER"
    assert out.status in GROUPABLE


@pytest.mark.asyncio
async def test_reject_requires_comment():
    db = MagicMock()
    svc = MgRequestsService(db)
    row = _request(statut="RECUE")
    svc._load = AsyncMock(return_value=row)
    with pytest.raises(HTTPException) as exc:
        await svc.reject(row.id, _user(), None)
    assert exc.value.status_code == 400


def test_editable_and_groupable_sets():
    assert "BROUILLON" in EDITABLE
    assert "A_COMPLETER" in EDITABLE
    assert "A_REGROUPER" in GROUPABLE


@pytest.mark.asyncio
async def test_create_request_requires_items():
    db = MagicMock()
    svc = MgRequestsService(db)
    svc.ensure_categories = AsyncMock()
    cat = SimpleNamespace(id=uuid4(), active=True, name="Fournitures")
    db.get = AsyncMock(return_value=cat)
    svc._agence = AsyncMock()
    data = RequestCreate(category_id=cat.id, agency_id=uuid4(), items=[])
    with pytest.raises(HTTPException) as exc:
        await svc.create_request(data, _user())
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_create_request_ok():
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    svc = MgRequestsService(db)
    user = _user()
    cat = SimpleNamespace(id=uuid4(), active=True, name="Fournitures")
    svc.ensure_categories = AsyncMock()
    svc._agence = AsyncMock()
    svc._next_number = AsyncMock(return_value="DEM-MG-2026-000002")
    svc._approve = AsyncMock()
    loaded = _request(requester=user.id)
    svc._load = AsyncMock(return_value=loaded)
    db.get = AsyncMock(return_value=cat)
    data = RequestCreate(
        category_id=cat.id,
        agency_id=user.agence_id,
        items=[RequestItemIn(description="Ramette A4", quantity=Decimal("2"))],
    )
    with patch("app.services.mg_requests_service.audit_request", AsyncMock()):
        out = await svc.create_request(data, user, source_espace_code="credit")
    assert out.request_number
    db.add.assert_called()


@pytest.mark.asyncio
async def test_processor_cannot_open_other_target():
    db = MagicMock()
    svc = MgRequestsService(db)
    user = _user()
    row = _request(statut="RECUE")
    row.target_espace_code = "rh"
    svc._load = AsyncMock(return_value=row)
    with pytest.raises(HTTPException) as exc:
        await svc.get_mg(row.id, user, target_espace="moyens-generaux")
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_list_categories_filters_source_espace():
    db = MagicMock()
    svc = MgRequestsService(db)
    svc.ensure_categories = AsyncMock()
    mg = SimpleNamespace(source_espaces=["*"], active=True)
    rh_only = SimpleNamespace(source_espaces=["rh"], active=True)
    result = MagicMock()
    result.scalars.return_value.all.return_value = [mg, rh_only]
    db.execute = AsyncMock(return_value=result)
    rows = await svc.list_categories(source_espace="credit")
    assert rows == [mg]


@pytest.mark.asyncio
async def test_delete_draft_only_owner_brouillon():
    db = MagicMock()
    db.commit = AsyncMock()
    db.delete = AsyncMock()
    svc = MgRequestsService(db)
    owner = _user()
    other = _user()
    row = _request(statut="BROUILLON", requester=owner.id)
    svc._load = AsyncMock(return_value=row)
    with pytest.raises(HTTPException) as exc:
        await svc.delete_draft(row.id, other)
    assert exc.value.status_code == 403

    row.status = "SERVIE"
    row.batch_id = None
    row.achat_demande_id = None
    with pytest.raises(HTTPException) as exc:
        await svc.delete_draft(row.id, owner)
    assert exc.value.status_code == 400

    row.status = "BROUILLON"
    with patch("app.services.mg_requests_service.audit_request", AsyncMock()):
        await svc.delete_draft(row.id, owner)
    db.delete.assert_awaited()

    row.status = "SOUMISE"
    db.delete.reset_mock()
    with patch("app.services.mg_requests_service.audit_request", AsyncMock()):
        await svc.delete_draft(row.id, owner)
    db.delete.assert_awaited()


@pytest.mark.asyncio
async def test_mine_dashboard_counts_from_real_statuses():
    db = MagicMock()
    svc = MgRequestsService(db)
    statuses = [("BROUILLON", 2), ("SOUMISE", 1), ("A_COMPLETER", 1)]
    status_result = MagicMock()
    status_result.all.return_value = statuses
    urgentes_count = 0
    unread_count = 3
    cat_result = MagicMock()
    cat_result.all.return_value = [("FOURNITURES", "Fournitures", 4)]

    async def _execute(stmt):
        sql = str(stmt)
        if "mg_request_categories" in sql:
            return cat_result
        return status_result

    db.execute = AsyncMock(side_effect=_execute)
    db.scalar = AsyncMock(side_effect=[urgentes_count, unread_count])
    svc.list_requests = AsyncMock(return_value=([], 0))
    out = await svc.mine_dashboard(_user().id)
    assert out["total"] == 4
    assert out["brouillons"] == 2
    assert out["a_completer"] == 1
    assert out["soumises"] == 1
    assert out["notifications_non_lues"] == 3
    assert any(i["statut"] == "A_COMPLETER" for i in out["insights"])


def test_demandes_engine_covers_departments():
    from app.data.demandes_engine import DEMANDES_MODULE_CODES, DEMANDES_MODULES, PROCESSOR_MODULE_CODES

    assert set(DEMANDES_MODULES) >= {"comptabilite", "credit", "rh", "informatique", "moyens-generaux"}
    assert "demandes-mg" in DEMANDES_MODULE_CODES
    assert PROCESSOR_MODULE_CODES == frozenset({"demandes-mg"})
    assert "demandes-employes" not in DEMANDES_MODULE_CODES
