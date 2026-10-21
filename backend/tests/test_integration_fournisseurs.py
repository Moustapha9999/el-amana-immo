"""Studio d'intégration API — fournisseurs d'API externes et import OpenAPI (Phase 4).

Aucun appel réseau : les tests d'analyse bloquent toute résolution DNS ou connexion sortante. Les tests
d'accès réel créent des comptes, rôles et fiches : copie de base jetable uniquement (``base_jetable``).
"""

from __future__ import annotations

import ast
import json
import logging
import re
import socket
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import select

from app.data.plateforme_catalogue import CORE_ADMIN_PERMISSIONS, FUNCTIONAL_PERMISSIONS, ROLE_PERMISSIONS
from app.db.base import Base
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models import AuditLog
from app.schemas.integration_fournisseurs import FournisseurCreation, OperationManuelle, verifier_url_base
from app.services.integrations import catalogue as cat
from app.services.integrations import exemples_externes as ex
from app.services.integrations import fournisseurs as svc
from app.services.integrations import openapi_import as oa
from app.services.permission_service import user_has_permission_codes
from tests.test_integration_clients import (  # noqa: F401
    _Transport,
    _archiver_comptes,
    _compte,
    _entete,
    _entite_active,
    _MDP,
    _sauter_si_mfa,
    moteur_frais,
)

BASE = "/api/v1/plateforme/admin/integrations/fournisseurs"
NOUVELLES = (svc.P_VIEW, svc.P_MANAGE, svc.P_VALIDATE)
RACINE = Path(__file__).resolve().parents[1]
SECRET_EXEMPLE = "Hunter2-Exemple!"


def _spec(**extra) -> dict:
    doc = {
        "openapi": "3.0.3",
        "info": {"title": "Fournisseur démo", "version": "1.0.0"},
        "servers": [{"url": "https://api.fournisseur.example.invalid/v1"}],
        "components": {
            "securitySchemes": {
                "jeton": {"type": "http", "scheme": "bearer"},
                "cle": {"type": "apiKey", "in": "header", "name": "X-Api-Key"},
            },
            "schemas": {
                "Noeud": {"type": "object", "required": ["id"], "properties": {
                    "id": {"type": "string"}, "enfant": {"$ref": "#/components/schemas/Noeud"}}},
                "Connexion": {"type": "object", "required": ["password"], "properties": {
                    "password": {"type": "string", "example": SECRET_EXEMPLE}}},
            },
        },
        "security": [{"jeton": []}],
        "paths": {
            "/noeuds/{id}": {
                "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}],
                "get": {
                    "operationId": "lireNoeud", "summary": "Lire un nœud",
                    "parameters": [{"name": "detail", "in": "query", "required": True, "schema": {"type": "integer"}}],
                    "responses": {"200": {"description": "ok", "content": {
                        "application/json": {"schema": {"$ref": "#/components/schemas/Noeud"}}}}},
                },
                "post": {
                    "operationId": "connecter", "security": [{"cle": []}],
                    "requestBody": {"required": True, "content": {
                        "application/json": {"schema": {"$ref": "#/components/schemas/Connexion"}}}},
                    "responses": {"201": {"description": "créé"}},
                },
            },
        },
    }
    doc.update(extra)
    return doc


def _json(doc: dict) -> bytes:
    return json.dumps(doc).encode("utf-8")


@pytest.fixture
def sans_reseau(monkeypatch):
    """Toute résolution DNS ou connexion sortante fait échouer le test."""

    def interdit(*_a, **_k):
        raise AssertionError("Appel réseau interdit pendant l'analyse")

    monkeypatch.setattr(socket, "getaddrinfo", interdit)
    monkeypatch.setattr(socket, "create_connection", interdit)
    monkeypatch.setattr(socket.socket, "connect", interdit)


# --- Permissions, routes, modèle -------------------------------------------------------------


def test_permissions_declarees_sans_attribution_ni_suffixe_admin():
    core_admin = {code for code, _l, _m in CORE_ADMIN_PERMISSIONS}
    fonctionnelles = {code for code, _l, _m in FUNCTIONAL_PERMISSIONS}
    for code in NOUVELLES:
        assert code in core_admin and code in fonctionnelles
        assert not code.endswith(".admin")
        assert not any(code in perms for perms in ROLE_PERMISSIONS.values())


@pytest.mark.parametrize("have", [
    {"core.admin.access"}, {"core.admin.integrations.view"}, {"core.admin.integrations.clients.manage"},
    {"core.admin.integrations.grants.approve"}, {"core.admin.query.admin"}, {"plateforme.users.admin"},
    {svc.P_MANAGE},
])
def test_aucun_joker_ne_couvre_la_validation(have):
    assert not user_has_permission_codes(have, svc.P_VALIDATE)
    if svc.P_MANAGE not in have:
        assert not user_has_permission_codes(have, svc.P_MANAGE)


def test_routes_login1_avec_permission_dediee_et_exclues_du_catalogue():
    _ops, index = cat.operations_de(app)
    routes = [op for op in index.values() if op.chemin.startswith(BASE)]
    assert len(routes) == 20
    for op in routes:
        assert op.authentification == cat.AUTH_LOGIN1, op.operation_id
        assert op.permissions and set(op.permissions) <= set(NOUVELLES), op.operation_id
        assert op.disponibilite == cat.DISPO_EXCLUE
    statut = next(op for op in routes if op.chemin.endswith("/statut"))
    assert set(statut.permissions) == {svc.P_MANAGE, svc.P_VALIDATE}


def test_aucune_colonne_de_secret():
    for nom in ("integration_fournisseurs", "integration_fournisseur_specs", "integration_fournisseur_operations"):
        for colonne in Base.metadata.tables[nom].columns:
            assert not re.search(r"secret|password|token|jeton|api_key|credential|hash", colonne.name), colonne.name


def test_migration_additive_et_reversible():
    source = (RACINE / "alembic" / "versions" / "20261021_integrations_02_fournisseurs.py").read_text(encoding="utf-8")
    upgrade, downgrade = source.split("def downgrade", 1)
    assert 'down_revision: Union[str, None] = "20261021_integrations_01"' in source
    assert 'retour_arriere = "compatible"' in source
    assert "drop_" not in upgrade and "alter_column" not in upgrade and "rename" not in upgrade.lower()
    for table in ("integration_fournisseurs", "integration_fournisseur_specs", "integration_fournisseur_operations"):
        assert f'op.drop_table("{table}")' in downgrade


@pytest.mark.parametrize("module", [
    "app/services/integrations/openapi_import.py", "app/services/integrations/fournisseurs.py",
    "app/services/integrations/exemples_externes.py", "app/api/v1/endpoints/core_admin_integration_fournisseurs.py",
])
def test_aucune_bibliotheque_reseau_importee(module):
    arbre = ast.parse((RACINE / module).read_text(encoding="utf-8"))
    interdits = {"httpx", "requests", "aiohttp", "urllib.request", "http.client", "socket", "smtplib", "ftplib"}
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            noms = {a.name for a in noeud.names}
        elif isinstance(noeud, ast.ImportFrom):
            noms = {noeud.module or ""} | {f"{noeud.module}.{a.name}" for a in noeud.names}
        else:
            continue
        assert not noms & interdits, (module, noms)


# --- Analyse OpenAPI (sans base, sans réseau) ------------------------------------------------


def test_import_json_valide(sans_reseau):
    a = oa.analyser(_json(_spec()), "demo.json")
    assert a.valide and a.format == "json" and a.openapi_version == "3.0.3"
    assert [(o["methode"], o["chemin"]) for o in a.operations] == [("GET", "/noeuds/{id}"), ("POST", "/noeuds/{id}")]
    lire = a.operations[0]
    assert {p["nom"] for p in lire["parametres"]} == {"id", "detail"}
    schema = lire["reponses"][0]["contenus"][0]["schema"]
    assert schema["ref"] == "Noeud"
    enfant = next(c for c in schema["champs"] if c["nom"] == "enfant")["schema"]
    assert enfant == {"ref": "Noeud", "circulaire": True}
    assert lire["authentification"] == [{"mecanismes": ["jeton"]}]
    assert a.operations[1]["authentification"] == [{"mecanismes": ["cle"]}]
    assert {m["nom"] for m in a.securite} == {"jeton", "cle"}


def test_import_yaml_valide(sans_reseau):
    texte = (
        "openapi: 3.1.0\ninfo:\n  title: Démo YAML\n  version: 2\n"
        "paths:\n  /a:\n    get:\n      responses:\n        200:\n          description: ok\n"
    )
    a = oa.analyser(texte.encode("utf-8"), "spec.yml")
    assert a.valide and a.format == "yaml" and a.version_api == "2"
    assert a.operations[0]["reponses"][0]["code"] == "200"
    assert "INFO_VERSION" in {m.code for m in a.avertissements}


@pytest.mark.parametrize("contenu, nom, motif", [
    (b"{", "a.json", "JSON malformé"),
    (b"a: [", "a.yaml", "YAML malformé"),
    (b"", "a.json", "vide"),
    (b"{}", "a.txt", "Extension"),
    (b"\xff\xfe", "a.json", "UTF-8"),
    (b'{"openapi": NaN}', "a.json", "non finie"),
    (b'{"openapi":"3.0.0","openapi":"3.1.0"}', "a.json", "dupliquée"),
    (b"openapi: 3.0.0\nopenapi: 3.1.0\n", "a.yaml", "dupliquée"),
    (b"a: &x [1]\nb: *x\n", "a.yaml", "Ancres|Alias"),
    (b"base: &b {x: 1}\nautre:\n  <<: *b\n", "a.yaml", "Ancres|Alias|Fusion"),
    (b"!!python/object/apply:os.system ['id']", "a.yaml", "YAML malformé"),
    (b"a: !!binary aGVsbG8=\n", "a.yaml", "non pris en charge"),
    (b"[" * 3000 + b"]" * 3000, "a.json", "profonde"),
    (b"[]", "a.json", "objet OpenAPI"),
])
def test_fichiers_invalides(sans_reseau, contenu, nom, motif):
    a = oa.analyser(contenu, nom)
    assert not a.valide and re.search(motif, a.erreurs[0].message), [m.message for m in a.erreurs]


def test_fichier_trop_volumineux():
    a = oa.analyser(b" " * (oa.TAILLE_MAX + 1), "gros.json")
    assert [m.code for m in a.erreurs] == ["FICHIER_TROP_VOLUMINEUX"]


@pytest.mark.parametrize("doc, code", [
    ({"swagger": "2.0", "info": {"title": "x", "version": "1"}}, "VERSION_NON_PRISE_EN_CHARGE"),
    ({"openapi": "2.0.0", "info": {"title": "x", "version": "1"}}, "VERSION_NON_PRISE_EN_CHARGE"),
    ({"openapi": "4.0.0", "info": {"title": "x", "version": "1"}}, "VERSION_NON_PRISE_EN_CHARGE"),
    ({"openapi": 3.0, "info": {"title": "x", "version": "1"}}, "VERSION_NON_PRISE_EN_CHARGE"),
    ({"openapi": "3.0.0", "info": {"version": "1"}}, "INFO_INVALIDE"),
    ({"openapi": "3.0.0", "info": {"title": "x"}}, "INFO_INVALIDE"),
    ({"openapi": "3.0.0", "info": {"title": "x", "version": "1"}, "paths": []}, "PATHS_INVALIDE"),
])
def test_versions_et_structure(doc, code):
    a = oa.analyser(_json(doc), "s.json")
    assert code in {m.code for m in a.erreurs}


def test_references_locales_et_distantes(sans_reseau):
    doc = _spec()
    doc["paths"]["/distant"] = {"get": {"responses": {"200": {"description": "x", "content": {
        "application/json": {"schema": {"$ref": "https://attaquant.example.invalid/schema.json"}}}}}}}
    doc["paths"]["/fichier"] = {"get": {"responses": {"200": {"$ref": "autre.yaml#/components/responses/R"}}}}
    a = oa.analyser(_json(doc), "s.json")
    assert a.valide
    externes = [m for m in a.avertissements if m.code == "REFERENCE_EXTERNE"]
    assert len(externes) == 2 and all("jamais chargée" in m.message for m in externes)
    distant = next(o for o in a.operations if o["chemin"] == "/distant")
    assert distant["reponses"][0]["contenus"][0]["schema"]["non_resolue"] is True

    doc["paths"]["/casse"] = {"get": {"responses": {"200": {"$ref": "#/components/responses/Absente"}}}}
    a = oa.analyser(_json(doc), "s.json")
    assert not a.valide and "REFERENCE_INTROUVABLE" in {m.code for m in a.erreurs}


def test_reference_circulaire_entre_objets(sans_reseau):
    doc = _spec()
    doc["components"]["responses"] = {"A": {"$ref": "#/components/responses/B"},
                                      "B": {"$ref": "#/components/responses/A"}}
    doc["paths"]["/boucle"] = {"get": {"responses": {"200": {"$ref": "#/components/responses/A"}}}}
    a = oa.analyser(_json(doc), "s.json")
    assert "REFERENCE_CIRCULAIRE" in {m.code for m in a.erreurs}


def test_schemas_complexes_bornes(monkeypatch, sans_reseau):
    monkeypatch.setattr(oa, "SCHEMA_EXPANSION_MAX", 5)
    a = oa.analyser(_json(_spec()), "s.json")
    assert a.valide and "SCHEMAS_TRONQUES" in {m.code for m in a.avertissements}
    monkeypatch.setattr(oa, "NOEUDS_MAX", 20)
    assert "complexe" in oa.analyser(_json(_spec()), "s.json").erreurs[0].message
    monkeypatch.setattr(oa, "NOEUDS_MAX", 200_000)
    monkeypatch.setattr(oa, "OPERATIONS_MAX", 1)
    assert "TROP_D_OPERATIONS" in {m.code for m in oa.analyser(_json(_spec()), "s.json").erreurs}


@pytest.mark.parametrize("chemin", ["/a b", "/a/$(id)", "/a/`x`", "/../etc", "/a//b", "sans-slash", '/a"b', "/a\\b"])
def test_chemins_malformes_refuses(chemin):
    doc = _spec(paths={chemin: {"get": {"responses": {"200": {"description": "x"}}}}})
    a = oa.analyser(_json(doc), "s.json")
    assert "CHEMIN_INVALIDE" in {m.code for m in a.erreurs}


def test_secrets_bloques_ou_masques(sans_reseau):
    a = oa.analyser(_json(_spec()), "s.json")
    connexion = a.document["components"]["schemas"]["Connexion"]["properties"]["password"]
    assert connexion["example"] == oa.MASQUE
    assert SECRET_EXEMPLE not in json.dumps(a.document) + json.dumps(a.operations)

    doc = _spec(servers=[{"url": "https://admin:motdepasse@api.example.invalid"}])
    a = oa.analyser(_json(doc), "s.json")
    assert a.serveurs == [{"url": "https://api.example.invalid", "description": None}]
    assert "motdepasse" not in json.dumps(a.document)
    assert "URL_IDENTIFIANTS_RETIRES" in {m.code for m in a.avertissements}

    for valeur in ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3OCJ9.c2lnbmF0dXJl",
                   "-----BEGIN RSA PRIVATE KEY-----", "Bearer abcdefghijklmnopqrstuvwxyz123456"):
        doc = _spec(info={"title": "x", "version": "1", "description": f"exemple {valeur}"})
        a = oa.analyser(_json(doc), "s.json")
        assert not a.valide and a.erreurs[0].code == "SECRET_SUSPECT"
        assert valeur not in json.dumps([m.dict() for m in a.erreurs])


def test_callbacks_webhooks_et_serveurs_jamais_invoques(sans_reseau):
    doc = _spec(webhooks={"evt": {"post": {"responses": {"200": {"description": "x"}}}}})
    doc["paths"]["/noeuds/{id}"]["get"]["callbacks"] = {
        "cb": {"https://rappel.example.invalid": {"post": {"responses": {"200": {"description": "x"}}}}}}
    a = oa.analyser(_json(doc), "s.json")
    codes = {m.code for m in a.avertissements}
    assert {"NON_IMPORTE", "SERVEURS_DECLARES"} <= codes
    assert all(o["chemin"].startswith("/noeuds") for o in a.operations)


# --- Exemples générés -------------------------------------------------------------------------


def test_exemples_espaces_reserves_non_testes_et_python_valide():
    a = oa.analyser(_json(_spec()), "s.json")
    for op in a.operations:
        doc = ex.generer(op, a.securite, "openapi", "https://api.fournisseur.example.invalid/v1")
        assert doc["elements_verifies"] == []
        assert any("non vérifiée" in d for d in doc["elements_declares"])
        assert "NON testé" in doc["avertissements"][0]
        for exemple in doc["exemples"]:
            code = exemple["code"]
            assert "EXTERNAL_API_BASE_URL" in code and "NON testé" in code
            assert SECRET_EXEMPLE not in code and "api.fournisseur.example.invalid" not in code
            if exemple["langage"] == "python":
                compile(code, "exemple.py", "exec")
        assert "EXTERNAL_API_TOKEN" in doc["exemples"][0]["code"]


def test_exemples_echappent_les_chaines_non_fiables():
    op = {"methode": "GET", "chemin": "/a", "authentification": [{"mecanismes": ["k"]}],
          "parametres": [{"nom": "x' ; rm -rf / ; '", "emplacement": "query", "requis": True, "schema": {"type": "string"}}]}
    mecanismes = [{"nom": "k", "type": "apiKey", "emplacement": "header", "nom_parametre": "X-K'ey"}]
    doc = ex.generer(op, mecanismes, "openapi", "https://x.example.invalid\nrm -rf /")
    curl = doc["exemples"][0]["code"]
    assert "rm -rf / ;" not in curl and "x%27%20%3B%20rm" in curl
    assert "-H 'X-K'\"'\"'ey: '" in curl
    compile(doc["exemples"][1]["code"], "exemple.py", "exec")
    assert all("\nrm -rf /" not in d for d in doc["elements_declares"])


# --- Schémas de saisie ------------------------------------------------------------------------


@pytest.mark.parametrize("url", [
    "ftp://x.example", "https://user:pw@x.example", "https://x.example/?token=1", "https://x.example/#f",
    "x.example", "https://x .example", "https://",
])
def test_url_de_base_refusee(url):
    with pytest.raises(ValueError):
        verifier_url_base(url)


def test_url_de_base_acceptee_sans_resolution(sans_reseau):
    assert verifier_url_base("https://api.example.invalid:8443/v1/") == "https://api.example.invalid:8443/v1"
    with pytest.raises(ValidationError):
        FournisseurCreation(nom="X", environnement="DEV", notes="password=Azerty123")
    with pytest.raises(ValidationError):
        FournisseurCreation(nom="X", environnement="PROD")
    with pytest.raises(ValidationError):
        FournisseurCreation(nom="X", environnement="DEV", statut="valide")


def _manuelle(**champs) -> dict:
    return {"nom": "Lire", "methode": "GET", "chemin": "/v1/comptes/{id}",
            "parametres": [{"nom": "id", "emplacement": "path", "requis": True}], **champs}


@pytest.mark.parametrize("champs", [
    {"chemin": "/v1/comptes"},
    {"parametres": []},
    {"chemin": "v1/comptes/{id}"},
    {"chemin": "/v1/../comptes/{id}"},
    {"chemin": "/v1/comptes/{id}?x=1"},
    {"entetes": [{"nom": "Authorization"}]},
    {"entetes": [{"nom": "X A"}]},
    {"corps_schema": {"type": "object"}},
    {"methode": "POST", "corps_schema": {"$ref": "#/x"}},
    {"methode": "POST", "corps_schema": {"type": "object", "properties": {"password": {"example": "Azerty123!"}}}},
    {"reponse_schema": {"type": "string", "example": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3OCJ9.c2ln"}},
    {"mecanisme_auth": "api_key_header"},
    {"mecanisme_auth": "http_bearer", "nom_cle_api": "X-Key"},
    {"codes_reponse": [99]},
    {"notes": "token=abc"},
    {"inconnu": True},
])
def test_operation_manuelle_refusee(champs):
    with pytest.raises(ValidationError):
        OperationManuelle(**_manuelle(**champs))


def test_operation_manuelle_valide():
    op = OperationManuelle(**_manuelle(mecanisme_auth="api_key_header", nom_cle_api="X-Api-Key",
                                       codes_reponse=[404, 200, 200]))
    assert op.codes_reponse == [200, 404]


# --- Accès réel (copie de base jetable uniquement) -------------------------------------------


@pytest.fixture
async def client(moteur_frais, base_jetable, monkeypatch):  # noqa: F811
    hotes: set[str] = set()
    origine = socket.getaddrinfo

    def surveille(host, *a, **k):
        hotes.add(str(host))
        return origine(host, *a, **k)

    def interdit(*_a, **_k):
        raise AssertionError("Appel HTTP sortant interdit")

    monkeypatch.setattr(socket, "getaddrinfo", surveille)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", interdit)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", interdit)
    async with AsyncClient(transport=_Transport(app=app), base_url="http://test") as ac:
        yield ac
    await _archiver_comptes()
    assert hotes <= {"postgres", "redis", "localhost", "127.0.0.1"}, hotes


async def _profils(client: AsyncClient) -> dict:
    return {
        "gestion": await _entete(client, await _compte(svc.P_VIEW, svc.P_MANAGE)),
        "validateur": await _entete(client, await _compte(svc.P_VIEW, svc.P_VALIDATE)),
        "lecteur": await _entete(client, await _compte(svc.P_VIEW)),
    }


async def _creer(client, h, **champs) -> dict:
    corps = {"nom": f"Fournisseur test {uuid4().hex[:8]}", "environnement": "DEV", **champs}
    res = await client.post(BASE, headers=h, json=corps)
    _sauter_si_mfa(res)
    assert res.status_code == 201, res.text
    return res.json()


async def _analyser(client, h, fid, contenu: bytes, nom="spec.json"):
    return await client.post(f"{BASE}/{fid}/specs/analyse", headers=h, files={"file": (nom, contenu)})


async def _importer(client, h, fid, contenu: bytes, analyse: dict, nom="spec.json", **form):
    data = {"empreinte": analyse["empreinte"], **form}
    if analyse.get("version_courante"):
        data.setdefault("version_courante", str(analyse["version_courante"]))
    return await client.post(f"{BASE}/{fid}/specs", headers=h, files={"file": (nom, contenu)}, data=data)


@pytest.mark.asyncio
async def test_sans_authentification_et_login2_refuses(client: AsyncClient):
    fid, oid, sid = uuid4(), uuid4(), uuid4()
    appels = [
        ("GET", BASE), ("POST", BASE), ("GET", f"{BASE}/{fid}"), ("PATCH", f"{BASE}/{fid}"),
        ("POST", f"{BASE}/{fid}/statut"), ("POST", f"{BASE}/{fid}/archive"), ("GET", f"{BASE}/{fid}/historique"),
        ("POST", f"{BASE}/{fid}/specs/analyse"), ("POST", f"{BASE}/{fid}/specs"), ("GET", f"{BASE}/{fid}/specs"),
        ("GET", f"{BASE}/{fid}/specs/{sid}"), ("GET", f"{BASE}/{fid}/operations"),
        ("POST", f"{BASE}/{fid}/operations"), ("GET", f"{BASE}/{fid}/operations/{oid}"),
        ("PATCH", f"{BASE}/{fid}/operations/{oid}"), ("POST", f"{BASE}/{fid}/operations/{oid}/archive"),
    ]
    for methode, url in appels:
        assert (await client.request(methode, url)).status_code == 401, (methode, url)

    admin = await _compte(superuser=True)
    plateforme = await _entete(client, admin)
    module = await client.post("/api/v1/auth/modules/immobilisations/login",
                               json={"email": admin, "password": _MDP}, headers=plateforme)
    if module.status_code != 200:
        pytest.skip("Login module indisponible pour ce compte de test")
    login2 = {"Authorization": f"Bearer {module.json()['access_token']}"}
    assert (await client.get(BASE, headers=login2)).status_code == 401
    assert (await client.post(BASE, headers=login2, json={"nom": "L2", "environnement": "DEV"})).status_code == 401


@pytest.mark.asyncio
async def test_permissions_insuffisantes(client: AsyncClient):
    p = await _profils(client)
    autres = await _entete(client, await _compte("core.admin.access", "core.admin.integrations.view",
                                                  "core.admin.integrations.clients.manage"))
    res = await client.get(BASE, headers=autres)
    _sauter_si_mfa(res)
    assert res.status_code == 403 and res.json()["request_id"]
    f = await _creer(client, p["gestion"])
    fid = f["id"]
    assert (await client.get(f"{BASE}/{fid}", headers=p["lecteur"])).status_code == 200
    for methode, url, kwargs in [
        ("POST", BASE, {"json": {"nom": "Lecteur", "environnement": "DEV"}}),
        ("PATCH", f"{BASE}/{fid}", {"json": {"revision": 1, "nom": "Lecteur"}}),
        ("POST", f"{BASE}/{fid}/archive", {"json": {"revision": 1, "motif": "lecteur"}}),
        ("POST", f"{BASE}/{fid}/specs/analyse", {"files": {"file": ("s.json", _json(_spec()))}}),
        ("POST", f"{BASE}/{fid}/operations", {"json": _manuelle()}),
        ("POST", f"{BASE}/{fid}/statut", {"json": {"revision": 1, "statut": "a_valider"}}),
    ]:
        res = await client.request(methode, url, headers=p["lecteur"], **kwargs)
        assert res.status_code == 403, (methode, url, res.text)
    assert (await client.post(BASE, headers=p["validateur"],
                              json={"nom": "Validateur", "environnement": "DEV"})).status_code == 403
    soumis = await client.post(f"{BASE}/{fid}/statut", headers=p["validateur"],
                               json={"revision": f["revision"], "statut": "a_valider"})
    assert soumis.status_code == 403 and soumis.json()["code"] == "PERMISSION_INSUFFISANTE"


@pytest.mark.asyncio
async def test_parcours_import_versions_conflits_et_manuel(client: AsyncClient, caplog):
    caplog.set_level(logging.DEBUG)
    p = await _profils(client)
    h = p["gestion"]
    f = await _creer(client, h, url_base="http://api.dev.example.invalid", description="Démo")
    fid = f["id"]
    assert re.fullmatch(r"EXT-[0-9A-Z]{8}", f["code"]) and f["statut"] == "brouillon" and f["modifiable"]

    v1 = _json(_spec())
    res = await _analyser(client, h, fid, v1)
    assert res.status_code == 200, res.text
    analyse = res.json()
    assert analyse["valide"] and analyse["nb_operations"] == 2 and analyse["version_courante"] is None
    assert analyse["diff"] is None and "EXEMPLE_MASQUE" in {m["code"] for m in analyse["avertissements"]}
    assert (await client.get(f"{BASE}/{fid}/specs", headers=h)).json()["items"] == []

    perime = await _importer(client, h, fid, _json(_spec(info={"title": "Autre", "version": "9"})), analyse)
    assert perime.status_code == 409 and perime.json()["code"] == "ANALYSE_PERIMEE"
    res = await _importer(client, h, fid, v1, analyse)
    assert res.status_code == 201, res.text
    spec1 = res.json()
    assert spec1["numero"] == 1 and spec1["courante"] and spec1["nb_operations"] == 2
    assert "aucun appel externe" in spec1["avertissement"]

    deja = (await _analyser(client, h, fid, v1)).json()
    assert deja["deja_importee"] == 1 and deja["diff"]["inchangees"] == 2
    res = await _importer(client, h, fid, v1, deja)
    assert res.status_code == 409 and res.json()["code"] == "SPEC_DEJA_IMPORTEE"

    ops = (await client.get(f"{BASE}/{fid}/operations", headers=h)).json()
    assert ops["version_courante"] == 1 and ops["total"] == 2
    lire = next(o for o in ops["items"] if o["methode"] == "GET")
    detail = (await client.get(f"{BASE}/{fid}/operations/{lire['id']}", headers=h)).json()
    assert detail["origine"] == "openapi" and "non vérifiée" in detail["source"]
    assert detail["elements_verifies"] == [] and len(detail["exemples"]) == 3
    assert all("EXTERNAL_API_BASE_URL" in e["code"] for e in detail["exemples"])

    doublon = await client.post(f"{BASE}/{fid}/operations", headers=h, json=_manuelle(chemin="/noeuds/{id}"))
    assert doublon.status_code == 409 and doublon.json()["code"] == "OPERATION_DEJA_IMPORTEE"
    manuelle = await client.post(f"{BASE}/{fid}/operations", headers=h, json=_manuelle(
        chemin="/comptes/{id}", mecanisme_auth="http_bearer", reponse_schema={"type": "object"}))
    assert manuelle.status_code == 201, manuelle.text
    m = manuelle.json()
    assert m["origine"] == "manuelle" and "Configuration manuelle" in m["source"] and m["revision"] == 1
    assert (await client.post(f"{BASE}/{fid}/operations", headers=h,
                              json=_manuelle(chemin="/comptes/{id}"))).json()["code"] == "OPERATION_DOUBLON"
    modif = await client.patch(f"{BASE}/{fid}/operations/{m['id']}", headers=h,
                               json={**_manuelle(chemin="/comptes/{id}", nom="Lire un compte"), "revision": 1})
    assert modif.status_code == 200 and modif.json()["revision"] == 2 and modif.json()["nom"] == "Lire un compte"
    perimee = await client.patch(f"{BASE}/{fid}/operations/{m['id']}", headers=h,
                                 json={**_manuelle(chemin="/comptes/{id}"), "revision": 1})
    assert perimee.json()["code"] == "CONFLIT_REVISION"
    importee = await client.patch(f"{BASE}/{fid}/operations/{lire['id']}", headers=h,
                                  json={**_manuelle(chemin="/noeuds/{id}"), "revision": 1})
    assert importee.json()["code"] == "OPERATION_IMPORTEE"

    doc2 = _spec(info={"title": "Fournisseur démo", "version": "2.0.0"})
    doc2["paths"]["/comptes/{id}"] = {"get": {"parameters": [{"name": "id", "in": "path", "required": True}],
                                              "responses": {"200": {"description": "ok"}}}}
    del doc2["paths"]["/noeuds/{id}"]["post"]
    v2 = yaml_dump(doc2)
    analyse2 = (await _analyser(client, h, fid, v2, "spec.yaml")).json()
    assert analyse2["valide"] and analyse2["version_courante"] == 1 and analyse2["conflits"] == ["GET /comptes/{id}"]
    assert analyse2["diff"]["ajoutees"] == ["GET /comptes/{id}"]
    assert analyse2["diff"]["supprimees"] == ["POST /noeuds/{id}"]
    refus = await _importer(client, h, fid, v2, analyse2, "spec.yaml")
    assert refus.status_code == 409 and refus.json()["code"] == "CONFLITS_NON_ACCEPTES"
    perime = await _importer(client, h, fid, v2, {**analyse2, "version_courante": None}, "spec.yaml")
    assert perime.json()["code"] == "CONFLIT_VERSION"
    res = await _importer(client, h, fid, v2, analyse2, "spec.yaml", accepter_conflits="true")
    assert res.status_code == 201, res.text
    assert res.json()["numero"] == 2 and res.json()["format"] == "yaml"

    ops = (await client.get(f"{BASE}/{fid}/operations", headers=h)).json()
    assert ops["version_courante"] == 2
    assert {(o["methode"], o["chemin"], o["origine"]) for o in ops["items"]} == {
        ("GET", "/noeuds/{id}", "openapi"), ("GET", "/comptes/{id}", "openapi"), ("GET", "/comptes/{id}", "manuelle")}
    assert all(o["conflit"] == (o["chemin"] == "/comptes/{id}") for o in ops["items"])
    versions = (await client.get(f"{BASE}/{fid}/specs", headers=h)).json()["items"]
    assert [(v["numero"], v["courante"]) for v in versions] == [(2, True), (1, False)]
    ancienne = (await client.get(f"{BASE}/{fid}/operations/{lire['id']}", headers=h)).json()
    assert "version antérieure" in ancienne["source"]

    archive = await client.post(f"{BASE}/{fid}/operations/{m['id']}/archive", headers=h, json={"revision": 2})
    assert archive.status_code == 200 and archive.json()["statut"] == "archivee"

    hist = (await client.get(f"{BASE}/{fid}/historique", headers=h, params={"size": 100})).json()
    actions = {e["action"] for e in hist["items"]}
    assert {"integration_fournisseur_create", "integration_fournisseur_spec_analyse",
            "integration_fournisseur_spec_import", "integration_fournisseur_operation_create",
            "integration_fournisseur_operation_update", "integration_fournisseur_operation_archive"} <= actions
    async with AsyncSessionLocal() as s:
        audits = (await s.scalars(select(AuditLog).where(AuditLog.entity_id == fid))).all()
    rendu = json.dumps([a.after_data for a in audits] + [a.before_data for a in audits], default=str)
    assert SECRET_EXEMPLE not in rendu and '"openapi"' not in rendu
    assert SECRET_EXEMPLE not in json.dumps(hist) + caplog.text
    assert "Bearer ey" not in caplog.text


def yaml_dump(doc: dict) -> bytes:
    import yaml

    return yaml.safe_dump(doc, allow_unicode=True, sort_keys=False).encode("utf-8")


@pytest.mark.asyncio
async def test_transitions_validation_et_verrouillage(client: AsyncClient):
    p = await _profils(client)
    h, v = p["gestion"], p["validateur"]
    f = await _creer(client, h)
    fid = f["id"]

    async def statut(hh, cible, revision, motif=None):
        return await client.post(f"{BASE}/{fid}/statut", headers=hh,
                                 json={"revision": revision, "statut": cible, "motif": motif})

    assert (await statut(v, "valide", 1)).json()["code"] == "TRANSITION_INTERDITE"
    res = await statut(h, "a_valider", 1)
    assert res.status_code == 200 and res.json()["statut"] == "a_valider"
    assert (await statut(h, "valide", 2)).json()["code"] == "PERMISSION_INSUFFISANTE"
    incomplet = await statut(v, "valide", 2)
    assert incomplet.status_code == 422 and incomplet.json()["code"] == "VALIDATION_INCOMPLETE"

    entite = await _entite_active()
    res = await client.patch(f"{BASE}/{fid}", headers=h, json={"revision": 2, "org_entite_id": entite,
                                                                "url_base": "https://api.example.invalid"})
    assert res.status_code == 200 and res.json()["revision"] == 3
    assert (await client.post(f"{BASE}/{fid}/operations", headers=h, json=_manuelle())).status_code == 201
    revision = (await client.get(f"{BASE}/{fid}", headers=h)).json()["revision"]
    valide = await statut(v, "valide", revision)
    assert valide.status_code == 200, valide.text
    fiche = valide.json()
    assert fiche["statut"] == "valide" and fiche["valide_par"] and not fiche["modifiable"]

    for res in (
        await client.patch(f"{BASE}/{fid}", headers=h, json={"revision": fiche["revision"], "nom": "Autre"}),
        await client.post(f"{BASE}/{fid}/operations", headers=h, json=_manuelle(chemin="/x/{id}")),
        await _importer(client, h, fid, _json(_spec()), {"empreinte": "0" * 64}),
    ):
        assert res.status_code == 409 and res.json()["code"] == "FOURNISSEUR_VERROUILLE", res.text

    assert (await statut(v, "suspendu", fiche["revision"])).json()["code"] == "MOTIF_OBLIGATOIRE"
    suspendu = await statut(v, "suspendu", fiche["revision"], "Revue sécurité")
    assert suspendu.json()["statut"] == "suspendu" and suspendu.json()["motif_statut"] == "Revue sécurité"
    rev = suspendu.json()["revision"]
    assert (await statut(h, "valide", rev)).json()["code"] == "TRANSITION_INTERDITE"
    archive = await client.post(f"{BASE}/{fid}/archive", headers=h, json={"revision": rev, "motif": "Fin de test"})
    assert archive.status_code == 200 and archive.json()["statut"] == "archive" and archive.json()["transitions"] == []
    assert (await statut(h, "a_valider", rev + 1)).json()["code"] == "FOURNISSEUR_ARCHIVE"
    actions = [e["action"] for e in (await client.get(f"{BASE}/{fid}/historique", headers=v)).json()["items"]]
    assert actions.count("integration_fournisseur_statut") == 3 and "integration_fournisseur_archive" in actions


@pytest.mark.asyncio
async def test_isolation_fournisseurs_et_environnements(client: AsyncClient):
    p = await _profils(client)
    h = p["gestion"]
    nom = f"Isolation {uuid4().hex[:8]}"
    a = await _creer(client, h, nom=nom, environnement="DEV")
    b = await _creer(client, h, nom=nom, environnement="TEST")
    assert (await client.post(BASE, headers=h, json={"nom": nom, "environnement": "DEV"})).json()["code"] == \
        "FOURNISSEUR_DOUBLON"
    https = await client.post(BASE, headers=h, json={"nom": f"{nom} http", "environnement": "TEST",
                                                     "url_base": "http://api.example.invalid"})
    assert https.status_code == 422 and https.json()["code"] == "URL_HTTPS_REQUISE"

    contenu = _json(_spec())
    analyse = (await _analyser(client, h, a["id"], contenu)).json()
    spec = (await _importer(client, h, a["id"], contenu, analyse)).json()
    op = (await client.get(f"{BASE}/{a['id']}/operations", headers=h)).json()["items"][0]
    assert (await client.get(f"{BASE}/{b['id']}/operations/{op['id']}", headers=h)).status_code == 404
    assert (await client.get(f"{BASE}/{b['id']}/specs/{spec['id']}", headers=h)).status_code == 404
    assert (await client.get(f"{BASE}/{b['id']}/operations", headers=h)).json()["total"] == 0
    assert (await client.post(f"{BASE}/{b['id']}/operations/{op['id']}/archive", headers=h,
                              json={"revision": 1})).status_code == 404

    analyse_b = (await _analyser(client, h, b["id"], contenu)).json()
    assert analyse_b["deja_importee"] is None and analyse_b["version_courante"] is None

    verrou = await client.patch(f"{BASE}/{a['id']}", headers=h, json={"revision": 2, "environnement": "TEST"})
    assert verrou.status_code == 409 and verrou.json()["code"] in ("ENVIRONNEMENT_VERROUILLE", "FOURNISSEUR_DOUBLON")
    liste = (await client.get(BASE, headers=h, params={"q": nom, "environnement": "TEST"})).json()
    assert [x["id"] for x in liste["items"]] == [b["id"]]


@pytest.mark.asyncio
async def test_fichier_trop_volumineux_refuse_par_l_api(client: AsyncClient, monkeypatch):
    p = await _profils(client)
    f = await _creer(client, p["gestion"])
    from app.api.v1.endpoints import core_admin_integration_fournisseurs as ep

    monkeypatch.setattr(ep, "TAILLE_MAX", 1024)
    res = await _analyser(client, p["gestion"], f["id"], b"{" + b" " * 2048 + b"}")
    assert res.status_code == 413 and res.json()["code"] == "FICHIER_TROP_VOLUMINEUX"
    invalide = (await _analyser(client, p["gestion"], f["id"], b'{"swagger": "2.0"}')).json()
    assert not invalide["valide"] and invalide["erreurs"][0]["code"] == "VERSION_NON_PRISE_EN_CHARGE"
