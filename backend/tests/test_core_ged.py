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
