from unittest.mock import MagicMock

from app.data.plateforme_catalogue import CORE_PERMISSIONS, FUNCTIONAL_PERMISSIONS
from app.services.ged_service import GedService


def test_core_permissions_are_in_catalogue():
    codes = {row[0] for row in CORE_PERMISSIONS}
    assert codes == {
        "plateforme.users.read",
        "plateforme.users.admin",
        "plateforme.audit.read",
        "ged.read",
        "ged.write",
    }
    functional = {row[0] for row in FUNCTIONAL_PERMISSIONS}
    assert codes.issubset(functional)
    assert "immobilisations.read" in functional
    assert "core.admin.access" in functional


def test_ged_relative_path_is_posix_and_safe():
    svc = GedService(MagicMock())
    path = svc.relative_path(
        module_code="immobilisations",
        entity="immobilisation",
        entity_id="id with/slash",
        filename="facture.pdf",
    )
    assert path == "immobilisations/immobilisation/id-with-slash/facture.pdf"
    assert "\\" not in path


def test_ged_absolute_path_rejects_traversal(tmp_path, monkeypatch):
    from app.core import config as config_mod

    monkeypatch.setenv("GED_DIR", str(tmp_path))
    config_mod.get_settings.cache_clear()
    try:
        svc = GedService(MagicMock())
        ok = svc.absolute_path("credit/dossier/abc/file.pdf")
        assert ok.is_relative_to(tmp_path.resolve()) or str(tmp_path) in str(ok)
        try:
            svc.absolute_path("../etc/passwd")
            raise AssertionError("expected ValidationError")
        except Exception as exc:
            assert "invalide" in str(exc).lower() or "hors" in str(exc).lower()
    finally:
        config_mod.get_settings.cache_clear()
