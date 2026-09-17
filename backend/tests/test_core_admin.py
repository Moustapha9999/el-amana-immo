from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.data.plateforme_catalogue import (
    CORE_ADMIN_PERMISSIONS,
    CORE_PERMISSIONS,
    FUNCTIONAL_PERMISSIONS,
    permissions_for_role,
)
from app.services.core_admin_service import (
    day_bounds_nouakchott,
    platform_health,
    serialize_activity,
)
from app.services.permission_service import user_has_permission_codes


def test_core_admin_permissions_are_catalogued_not_granted_to_immo_admin():
    admin_codes = {row[0] for row in CORE_ADMIN_PERMISSIONS}
    assert "core.admin.access" in admin_codes
    assert "core.admin.users" in admin_codes
    functional = {row[0] for row in FUNCTIONAL_PERMISSIONS}
    assert admin_codes.issubset(functional)
    core = {row[0] for row in CORE_PERMISSIONS}
    assert not admin_codes.intersection(core)
    immo_admin = set(permissions_for_role("administrateur"))
    assert not admin_codes.intersection(immo_admin)
    assert "core.admin.access" not in immo_admin


def test_immo_and_plateforme_admin_do_not_cover_core_admin_access():
    assert not user_has_permission_codes({"immobilisations.admin"}, "core.admin.access")
    assert not user_has_permission_codes({"plateforme.users.admin"}, "core.admin.access")
    assert user_has_permission_codes({"core.admin.access"}, "core.admin.access")
    assert user_has_permission_codes({"*"}, "core.admin.access")
    assert user_has_permission_codes({"core.admin.users"}, "core.admin.users")
    assert not user_has_permission_codes({"core.admin.access"}, "core.admin.users")


def test_day_bounds_nouakchott_is_local_calendar_day():
    moment = datetime(2026, 9, 17, 22, 30, tzinfo=timezone.utc)
    start, end = day_bounds_nouakchott(moment)
    assert start.date().isoformat() == "2026-09-17"
    assert (end - start).total_seconds() == 24 * 3600
    assert start <= moment < end


def test_serialize_activity_and_health():
    log = SimpleNamespace(
        id=uuid4(),
        user=None,
        action="login",
        entity="auth",
        entity_id=None,
        module_code="immobilisations",
        espace_code="comptabilite",
        created_at=None,
    )
    row = serialize_activity(log)
    assert row["who"] == "Système"
    assert row["action"] == "login"
    assert row["module"] == "immobilisations"

    etat = platform_health(db_ok=True, modules_actifs=1)
    assert etat["core"]["ok"] is True
    assert etat["db"]["ok"] is True
    assert etat["modules"]["ok"] is True
    assert platform_health(db_ok=False, modules_actifs=0)["modules"]["ok"] is False
    assert platform_health(db_ok=False, modules_actifs=0)["db"]["ok"] is False
