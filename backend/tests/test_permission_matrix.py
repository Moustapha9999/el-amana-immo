from types import SimpleNamespace

from app.data.plateforme_catalogue import (
    is_legacy_immo_role,
    module_role_code,
    permissions_for_role,
    role_module_code,
)
from app.services.permission_service import permission_codes_from_user, user_has_permission_codes


def test_consultation_is_read_only():
    codes = set(permissions_for_role("consultation"))
    assert codes == {"immobilisations.read"}
    assert "immobilisations.create" not in codes
    assert "immobilisations.update" not in codes
    assert "immobilisations.validate" not in codes


def test_creation_includes_read():
    codes = set(permissions_for_role("creation"))
    assert codes == {"immobilisations.read", "immobilisations.create"}


def test_modification_does_not_imply_create_or_validate():
    codes = set(permissions_for_role("modification"))
    assert "immobilisations.update" in codes
    assert "immobilisations.create" not in codes
    assert "immobilisations.validate" not in codes


def test_administrateur_has_all_immo_permissions():
    codes = set(permissions_for_role("administrateur"))
    assert "immobilisations.read" in codes
    assert "immobilisations.admin" in codes
    assert "immobilisations.validate" in codes
    assert "immobilisations.delete" in codes
    assert "plateforme.users.admin" in codes
    assert "core.admin.access" not in codes


def test_immo_admin_permission_covers_module_actions():
    have = {"immobilisations.admin"}
    assert user_has_permission_codes(have, "immobilisations.read")
    assert user_has_permission_codes(have, "immobilisations.create")
    assert not user_has_permission_codes({"immobilisations.read"}, "immobilisations.create")


def test_module_admin_is_generic_not_immo_only():
    have = {"credit.admin"}
    assert user_has_permission_codes(have, "credit.read")
    assert not user_has_permission_codes(have, "immobilisations.read")


def test_superuser_exposes_wildcard():
    user = SimpleNamespace(is_superuser=True, roles=[])
    codes = permission_codes_from_user(user)
    assert "*" in codes
    assert user_has_permission_codes(codes, "immobilisations.delete")


def test_loaded_db_grants_are_source_of_truth():
    role = SimpleNamespace(code="consultation", permissions=[SimpleNamespace(code="immobilisations.create")])
    user = SimpleNamespace(is_superuser=False, roles=[role])
    codes = permission_codes_from_user(user)
    assert codes == {"immobilisations.create"}
    assert "immobilisations.read" not in codes


def test_unloaded_role_permissions_fall_back_to_catalogue():
    role = SimpleNamespace(code="consultation")
    user = SimpleNamespace(is_superuser=False, roles=[role])
    assert "immobilisations.read" in permission_codes_from_user(user)


def test_module_role_code_legacy_vs_prefixed():
    assert module_role_code("immobilisations", "comptable") == "comptable"
    assert module_role_code("credit", "admin") == "credit.admin"
    assert module_role_code("credit", "credit.lecteur") == "credit.lecteur"
    assert role_module_code("comptable") == "immobilisations"
    assert role_module_code("credit.admin") == "credit"
    assert role_module_code("custom_libre") is None
    assert is_legacy_immo_role("administrateur")
    assert not is_legacy_immo_role("credit.admin")
