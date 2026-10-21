"""Phase 3 — préparation de l'authentification machine-à-machine (non activée, sans base).

Vérifie les règles de décision préparatoires et l'absence de tout mécanisme actif : aucune route
d'émission de jeton, aucune table d'identifiants, aucun jeton utilisateur réutilisable comme jeton client.
"""

from __future__ import annotations

import dataclasses

import pytest
from fastapi.routing import APIRoute

from app.core.security import create_access_token
from app.db.base import Base
from app.main import app
from app.services.integrations import catalogue as cat
from app.services.integrations import clients as svc
from app.services.integrations import m2m_preparation as m2m


def _op_admissible() -> cat.Operation:
    ops, _index = cat.operations_de(app)
    for op in ops:
        if svc.admissibilite(op, {op.module_code: "actif"} if op.module_code else {})[0]:
            return op
    pytest.fail("Aucune opération admissible dans le catalogue")


def _droit(op: cat.Operation, **modif) -> m2m.DroitApprouve:
    base = m2m.DroitApprouve(op.operation_id, op.methode, op.chemin, tuple(op.permissions))
    return dataclasses.replace(base, **modif)


def _etats(op: cat.Operation) -> dict[str, str]:
    return {op.module_code: "actif"} if op.module_code else {}


# --- Aucun mécanisme actif -------------------------------------------------------------------


def test_aucune_route_d_emission_ni_de_validation_de_jeton_client():
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        chemin = route.path.lower()
        assert "oauth" not in chemin and "client_credentials" not in chemin, route.path
        if "/integrations" in chemin:
            assert "token" not in chemin and "jeton" not in chemin and "credential" not in chemin, route.path


def test_aucune_table_d_identifiants_clients():
    assert "integration_credentials" not in Base.metadata.tables
    for nom, table in Base.metadata.tables.items():
        if nom.startswith("integration_client"):
            for colonne in table.columns:
                assert "secret" not in colonne.name and "credential" not in colonne.name, (nom, colonne.name)


def test_le_module_preparatoire_n_est_branche_sur_aucune_route():
    for route in app.routes:
        if isinstance(route, APIRoute):
            assert route.endpoint.__module__ != m2m.__name__


def test_jeton_utilisateur_sans_audience_ni_emetteur():
    """Un futur validateur de jeton client exigera iss/aud dédiés : un jeton utilisateur ne les porte pas."""
    from jose import jwt

    jeton = create_access_token("00000000-0000-0000-0000-000000000001", sid="00000000-0000-0000-0000-000000000002")
    claims = jwt.get_unverified_claims(jeton)
    assert "aud" not in claims and "iss" not in claims
    assert claims["type"] == "access" and claims["sid"]


# --- Éligibilité à l'émission ----------------------------------------------------------------


@pytest.mark.parametrize(
    "statut, env_client, env_cible, nb, code",
    [
        (None, None, "DEV", 0, "CLIENT_INCONNU"),
        ("brouillon", "DEV", "DEV", 3, "CLIENT_NON_ACTIF"),
        ("en_preparation", "DEV", "DEV", 3, "CLIENT_NON_ACTIF"),
        ("suspendue", "DEV", "DEV", 3, "CLIENT_NON_ACTIF"),
        ("archivee", "DEV", "DEV", 3, "CLIENT_NON_ACTIF"),
        ("active", "DEV", "TEST", 3, "ENVIRONNEMENT_DIFFERENT"),
        ("active", "TEST", "DEV", 3, "ENVIRONNEMENT_DIFFERENT"),
        ("active", "DEV", "PROD", 3, "ENVIRONNEMENT_FERME"),
        ("active", "DEV", "DEV", 0, "AUCUNE_OPERATION_APPROUVEE"),
    ],
)
def test_emission_refusee(statut, env_client, env_cible, nb, code):
    d = m2m.eligibilite_emission(statut, env_client, env_cible, nb)
    assert not d.autorise and d.code == code


def test_emission_eligible_seulement_si_tout_est_etabli():
    assert m2m.eligibilite_emission("active", "TEST", "TEST", 1).autorise


# --- Décision par appel ----------------------------------------------------------------------


def test_operation_approuvee_autorisee():
    op = _op_admissible()
    d = m2m.decision_appel(op, op.methode, op.chemin, {op.operation_id: _droit(op)}, _etats(op))
    assert d.autorise and d.code == "APPROUVEE"


def test_operation_non_approuvee_ou_droit_revoque():
    op = _op_admissible()
    assert m2m.decision_appel(op, op.methode, op.chemin, {}, _etats(op)).code == "OPERATION_NON_APPROUVEE"


def test_operation_inconnue_ou_autre_route():
    op = _op_admissible()
    droits = {op.operation_id: _droit(op)}
    assert m2m.decision_appel(None, "GET", "/x", droits, {}).code == "OPERATION_INCONNUE"
    assert m2m.decision_appel(op, "DELETE", op.chemin, droits, _etats(op)).code == "OPERATION_INCONNUE"
    assert m2m.decision_appel(op, op.methode, op.chemin + "/autre", droits, _etats(op)).code == "OPERATION_INCONNUE"


def test_permissions_ou_route_modifiees_depuis_l_approbation():
    op = _op_admissible()
    ajout = {op.operation_id: _droit(op, permissions=tuple(op.permissions) + ("autre.permission",))}
    assert m2m.decision_appel(op, op.methode, op.chemin, ajout, _etats(op)).code == "PERMISSIONS_MODIFIEES"
    deplacee = {op.operation_id: _droit(op, chemin="/ancien/chemin")}
    assert m2m.decision_appel(op, op.methode, op.chemin, deplacee, _etats(op)).code == "OPERATION_MODIFIEE"


@pytest.mark.parametrize(
    "modif",
    [
        {"permission_statut": cat.PERM_NON_DETERMINEE},
        {"authentification": cat.AUTH_INDETERMINEE},
        {"disponibilite": cat.DISPO_RESTREINTE},
    ],
)
def test_route_sans_controle_fiable_refusee_meme_si_approuvee(modif):
    op = dataclasses.replace(_op_admissible(), **modif)
    d = m2m.decision_appel(op, op.methode, op.chemin, {op.operation_id: _droit(op)}, _etats(op))
    assert not d.autorise and d.code == "OPERATION_NON_FIABLE"


def test_module_desactive_refuse():
    op = dataclasses.replace(_op_admissible(), module_code="clientele")
    d = m2m.decision_appel(op, op.methode, op.chemin, {op.operation_id: _droit(op)}, {op.module_code: "desactive"})
    assert d.code == "OPERATION_NON_FIABLE"


def test_pas_d_elevation_par_permission_admin():
    op = dataclasses.replace(_op_admissible(), permissions=["immobilisations.admin"])
    d = m2m.decision_appel(op, op.methode, op.chemin, {op.operation_id: _droit(op)}, _etats(op))
    assert not d.autorise
