"""Règle `.admin` : seule une racine `{module}.admin` (deux segments) couvre `{module}.*`."""

import pytest

from app.data.plateforme_catalogue import FUNCTIONAL_PERMISSIONS, ROLE_PERMISSIONS
from app.services.permission_service import admin_root_module, user_has_permission_codes

CATALOGUE = {code: module for code, _label, module in FUNCTIONAL_PERMISSIONS}


def _ancienne_regle(have: set[str], *needed: str) -> bool:
    """Comportement d'avant la Phase 0 (premier segment), pour mesurer l'écart."""
    if "*" in have or have.intersection(needed):
        return True
    prefixes = {c.split(".", 1)[0] for c in have if c.endswith(".admin") and "." in c}
    return any("." in c and c.split(".", 1)[0] in prefixes for c in needed)


@pytest.mark.parametrize(
    ("have", "needed"),
    [
        ("core.admin.query.admin", "core.admin.users"),
        ("core.admin.query.admin", "core.admin.recovery.execute"),
        ("core.admin.query.admin", "core.admin.access"),
        ("mg.request.admin", "mg.purchase.pay"),
        ("mg.request.admin", "mg.stock.period.reopen"),
        ("mg.batch.admin", "mg.factures.payment.create"),
        ("clientele.classif.admin", "clientele.export"),
        ("clientele.classif.admin", "clientele.bcm.valider"),
        ("plateforme.users.admin", "plateforme.audit.read"),
    ],
)
def test_admin_profond_n_accorde_pas_le_premier_segment(have, needed):
    assert _ancienne_regle({have}, needed), "cas censé illustrer l'ancienne élévation"
    assert not user_has_permission_codes({have}, needed)


@pytest.mark.parametrize(
    ("have", "needed"),
    [
        ("immobilisations.admin", "mg.stock.view"),
        ("immobilisations.admin", "core.admin.users"),
        ("eer.admin", "clientele.view"),
        ("clientele.admin", "reclamations.view"),
        ("reclamations.admin", "formation.view"),
        ("formation.admin", "immobilisations.read"),
        ("credit.admin", "immobilisations.read"),
    ],
)
def test_admin_racine_ne_deborde_pas_sur_un_autre_module(have, needed):
    assert not user_has_permission_codes({have}, needed)


@pytest.mark.parametrize(
    "code",
    [code for code in CATALOGUE if code.endswith(".admin")] + ["mg.batch.admin"],
)
def test_toute_permission_admin_reste_valable_exactement(code):
    assert user_has_permission_codes({code}, code)


@pytest.mark.parametrize(
    ("have", "needed"),
    [
        ("immobilisations.admin", "immobilisations.delete"),
        ("immobilisations.admin", "immobilisations.validate"),
        ("eer.admin", "eer.validate"),
        ("eer.admin", "eer.document.download"),
        ("formation.admin", "formation.import.execute"),
        ("clientele.admin", "clientele.classif.force"),
        ("clientele.admin", "clientele.classif.admin"),
        ("reclamations.admin", "reclamations.delete"),
        ("credit.admin", "credit.read"),
    ],
)
def test_racine_module_admin_couvre_son_module(have, needed):
    assert user_has_permission_codes({have}, needed)


@pytest.mark.parametrize(
    ("have", "needed"),
    [
        ("core.admin.query.admin", "core.admin.query.sql"),
        ("core.admin.query.admin", "core.admin.query.execute"),
        ("clientele.classif.admin", "clientele.classif.view"),
        ("mg.request.admin", "mg.request.validate"),
        ("mg.request.admin", "mg.request.mine.create"),
        ("plateforme.users.admin", "plateforme.users.read"),
    ],
)
def test_admin_a_plusieurs_niveaux_est_une_permission_exacte(have, needed):
    assert not user_has_permission_codes({have}, needed)


@pytest.mark.parametrize(
    ("have", "needed"),
    [
        ("core.admin", "core.admin.users"),
        ("core.admin", "core.admin.recovery.execute"),
        ("plateforme.admin", "plateforme.users.admin"),
        ("ged.admin", "ged.write"),
        ("org.admin", "org.scope.all"),
    ],
)
def test_espaces_transverses_sans_racine_admin(have, needed):
    assert admin_root_module(have) is None
    assert not user_has_permission_codes({have}, needed)


def test_admin_root_module():
    assert admin_root_module("immobilisations.admin") == "immobilisations"
    assert admin_root_module("credit.admin") == "credit"
    assert admin_root_module("mg.admin") == "mg"
    assert admin_root_module("core.admin.query.admin") is None
    assert admin_root_module("mg.request.admin") is None
    assert admin_root_module("admin") is None
    assert admin_root_module(".admin") is None
    assert admin_root_module("immobilisations.read") is None


def test_permissions_sans_rapport_et_cas_limites():
    assert not user_has_permission_codes({"immobilisations.read"}, "immobilisations.create")
    assert not user_has_permission_codes({"mg.stock.view"}, "mg.purchase.view")
    assert not user_has_permission_codes(set(), "immobilisations.read")
    assert not user_has_permission_codes({"immobilisations.admin"}, "admin")
    assert user_has_permission_codes({"*"}, "core.admin.recovery.execute")
    assert user_has_permission_codes(set())


def test_mode_ou_conserve():
    have = {"mg.request.admin"}
    assert user_has_permission_codes(have, "mg.request.validate", "mg.request.admin")
    assert user_has_permission_codes({"mg.batch.update"}, "mg.batch.update", "mg.batch.admin")


@pytest.mark.parametrize("role", sorted(ROLE_PERMISSIONS))
def test_roles_semes_conservent_leurs_permissions(role):
    have = set(ROLE_PERMISSIONS[role])
    for code in have:
        assert user_has_permission_codes(have, code), (role, code)


@pytest.mark.parametrize("role", sorted(ROLE_PERMISSIONS))
def test_roles_semes_ne_perdent_rien_dans_leurs_modules(role):
    """Seules disparaissent des permissions de modules dont le rôle ne détient aucun droit."""
    have = set(ROLE_PERMISSIONS[role])
    modules_du_role = {CATALOGUE[c] for c in have if c in CATALOGUE}
    for code, module in CATALOGUE.items():
        avant = _ancienne_regle(have, code)
        apres = user_has_permission_codes(have, code)
        assert not (apres and not avant), (role, code)
        if avant and not apres:
            assert module not in modules_du_role, (role, code)
