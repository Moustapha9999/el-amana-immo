from app.core.error_catalog import CATALOG, STATUS_CODES, default_code, spec_for, title_for


def test_chaque_statut_transversal_a_une_entree_catalogue():
    manquants = {code for code in STATUS_CODES.values() if code not in CATALOG}
    assert manquants == set()


def test_spec_statut_inconnu():
    assert default_code(418) == "BUSINESS_RULE_ERROR"
    assert default_code(599) == "INTERNAL_ERROR"
    assert spec_for(None, 409).code == "CONFLICT"
    assert title_for("TRANSITION_INVALIDE", 400) == "Opération impossible"
    assert title_for("AUTH_INVALID_CREDENTIALS", 401) == "Connexion refusée"
