"""Isolation modules — permissions + garde Login 2 (unitaires, sans DB)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api.deps import require_module_access
from app.data.module_backup_scopes import (
    SHARED_CORE_TABLES,
    known_module_codes,
    make_module_scope,
    merge_scopes,
    register_module_scope,
    scope_for_module,
)
from app.data.notification_taxonomy import (
    categorie_from_type,
    coerce_type_notification,
)
from app.models.enums import TypeNotification
from app.services.permission_service import user_has_permission_codes


def test_credit_admin_does_not_cover_immobilisations():
    have = {"credit.admin"}
    assert user_has_permission_codes(have, "credit.read")
    assert not user_has_permission_codes(have, "immobilisations.read")
    assert not user_has_permission_codes(have, "immobilisations.update")


def test_immo_admin_does_not_cover_credit():
    have = {"immobilisations.admin"}
    assert user_has_permission_codes(have, "immobilisations.delete")
    assert not user_has_permission_codes(have, "credit.read")


def test_require_permission_is_or_not_and():
    """Un seul code parmi la liste suffit (mapping admin|comptable → update|create)."""
    have = {"immobilisations.create"}
    assert user_has_permission_codes(have, "immobilisations.update", "immobilisations.create")
    assert not user_has_permission_codes(have, "immobilisations.validate", "immobilisations.delete")


@pytest.mark.asyncio
async def test_require_module_access_rejects_wrong_module():
    checker = require_module_access("immobilisations")
    # Simule une session module credit présentée à une route immo.
    user = SimpleNamespace(id="u1", is_superuser=False, roles=[])
    session = SimpleNamespace(
        kind="module",
        module_code="credit",
        parent_session_id=None,
        id="s1",
    )

    async def fake_load(credentials, db):
        return user, session, None

    import app.api.deps as deps

    original = deps._load_user_and_session
    deps._load_user_and_session = fake_load  # type: ignore[assignment]
    try:
        with pytest.raises(HTTPException) as exc:
            await checker(
                request=MagicMock(state=SimpleNamespace()),
                credentials=MagicMock(),
                db=MagicMock(),
            )
        assert exc.value.status_code == 401
        detail = exc.value.detail
        if isinstance(detail, dict):
            assert detail.get("code") == "MODULE_AUTH_REQUIRED"
    finally:
        deps._load_user_and_session = original  # type: ignore[assignment]


def test_backup_scope_factory_keeps_core_out_of_exclusive():
    scope = make_module_scope(
        label="Crédit",
        exclusive_tables=["credit_dossiers"],
        uploads_subdir="credit",
    )
    assert "users" not in scope["exclusive_tables"]
    assert "users" in scope["shared_dependencies"]
    assert set(SHARED_CORE_TABLES).issubset(set(scope["shared_dependencies"]))
    register_module_scope("credit_test", scope)
    assert scope_for_module("credit_test") is not None
    assert "immobilisations" in known_module_codes()
    merged = merge_scopes(["immobilisations", "credit_test"])
    assert merged is not None
    assert "credit_dossiers" in merged["exclusive_tables"]
    assert "immobilisations" in merged["exclusive_tables"] or "amortissements" in merged["exclusive_tables"]


def test_notification_open_types_via_event_and_module():
    assert categorie_from_type("credit.dossier_ouvert", module_code="credit") == "credit"
    assert categorie_from_type("fin_amortissement") == "amortissements"
    assert coerce_type_notification("credit.dossier_ouvert") is TypeNotification.SYSTEME
    assert coerce_type_notification("inventaire") is TypeNotification.INVENTAIRE
