"""Studio d'intégration API (CORE ADMIN) — catalogue, exemples et console en lecture seule."""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import re
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.responses import PlainTextResponse
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, ValidationError
from sqlalchemy import select, text

from app.api.deps import get_current_user, require_module_access, require_platform_permission
from app.core.config import get_settings
from app.core.security import get_password_hash
from app.data.plateforme_catalogue import CORE_ADMIN_PERMISSIONS, FUNCTIONAL_PERMISSIONS, ROLE_PERMISSIONS
from app.db.session import AsyncSessionLocal, engine
from app.main import app
from app.middleware.request_context import RequestContextMiddleware
from app.models import User
from app.schemas.integrations import IntegrationConsoleRequete
from app.services.integrations import catalogue as cat
from app.services.integrations import console
from app.services.integrations.exemples import generer
from app.services.permission_service import user_has_permission_codes

PERM = "core.admin.integrations.view"
BASE = "/api/v1/plateforme/admin/integrations"


@pytest.fixture(scope="module")
def operations():
    ops, index = cat.operations_de(app)
    return ops, index


def _op(index, operation_id):
    assert operation_id in index, operation_id
    return index[operation_id]


# --- Permission ----------------------------------------------------------------------------


def test_permission_declaree_dans_le_catalogue_core_admin_sans_attribution():
    assert PERM in {code for code, _l, _m in CORE_ADMIN_PERMISSIONS}
    assert PERM in {code for code, _l, _m in FUNCTIONAL_PERMISSIONS}
    assert not PERM.endswith(".admin")
    assert not any(PERM in perms for perms in ROLE_PERMISSIONS.values())


def test_permission_non_couverte_par_acces_core_admin_ni_par_un_code_admin():
    assert user_has_permission_codes({PERM}, PERM)
    assert user_has_permission_codes({"*"}, PERM)
    for have in ({"core.admin.access"}, {"core.admin.query.admin"}, {"plateforme.users.admin"}, {"core.admin.users"}):
        assert not user_has_permission_codes(have, PERM)


# --- Catalogue -----------------------------------------------------------------------------


def test_routes_du_studio_protegees_par_login1_et_permission_dediee(operations):
    _ops, index = operations
    studio = [
        op for op in index.values()
        if op.chemin.startswith(BASE)
        and not op.chemin.startswith((
            f"{BASE}/clients", f"{BASE}/fournisseurs", f"{BASE}/destinations",
            f"{BASE}/tests", f"{BASE}/executions", f"{BASE}/supervision",
        ))
    ]
    assert len(studio) == 5
    for op in studio:
        assert op.authentification == cat.AUTH_LOGIN1
        assert op.permissions == [PERM]
        assert op.permission_statut == cat.PERM_IDENTIFIEE


def test_identifiants_uniques_et_stables():
    premiers = [op.operation_id for op in cat.construire_operations(app)]
    seconds = [op.operation_id for op in cat.construire_operations(app)]
    assert premiers == seconds
    assert len(premiers) == len(set(premiers))
    for op_id in premiers:
        assert re.fullmatch(r"[a-z]+\.[A-Za-z0-9_]+\.[A-Za-z0-9_]+(\.[0-9a-f]{8})?", op_id), op_id


def test_meme_fonction_sur_deux_chemins_donne_deux_identifiants(operations):
    ops, _index = operations
    agence = [op for op in ops if op.operation_id.startswith("get.reporting.get_amortissements_agence")]
    assert len(agence) == 2
    assert len({op.operation_id for op in agence}) == 2
    assert len({op.chemin for op in agence}) == 2


@pytest.mark.parametrize(
    "operation_id",
    [
        "get.mg_requests.me_get",
        "get.mg_achats.dossier_facture",
        "post.documents.upload_document",
        "post.core_admin_rbac.create_role",
    ],
)
def test_controle_dans_le_traitement_jamais_presente_comme_certain(operations, operation_id):
    _ops, index = operations
    op = _op(index, operation_id)
    assert op.permission_statut == cat.PERM_NON_DETERMINEE
    assert any(d.startswith("corps de l'endpoint") for d in op.dependances_non_analysees)
    if op.disponibilite != cat.DISPO_EXCLUE:
        assert any("traitement" in m for m in op.motifs)
        assert not op.exemples_disponibles


def test_permission_identifiee_sans_controle_cache(operations):
    ops, _index = operations
    for op in ops:
        if op.permission_statut == cat.PERM_IDENTIFIEE:
            assert op.permissions and op.exigences
            assert cat._controles_corps(op.route.endpoint) == [], op.operation_id


def test_exigence_restitue_la_logique_au_moins_une(operations):
    _ops, index = operations
    batch = next(op for op in index.values() if "mg.batch.admin" in op.permissions)
    assert cat.exigence_texte(batch.exigences) == "au moins une de (mg.batch.admin, mg.batch.update)"
    assert cat.exigence_texte([["a"], ["b", "c"]]) == "a ET au moins une de (b, c)"
    assert cat.exigence_texte([]) is None


def test_aucune_permission_inventee(operations):
    """Chaque code vient du code source ; un code absent du référentiel est signalé, jamais masqué."""
    ops, _index = operations
    connues = {code for code, _l, _m in FUNCTIONAL_PERMISSIONS}
    for op in ops:
        for code in op.permissions:
            if code not in connues and op.disponibilite != cat.DISPO_EXCLUE:
                assert any(code in m and "absente" in m for m in op.motifs), (op.operation_id, code)
    absentes = {code for op in ops for code in op.permissions} - connues
    assert absentes == {"mg.batch.admin"}


def test_aucun_schema_invente(operations):
    ops, _index = operations
    composants = set((app.openapi().get("components") or {}).get("schemas") or {})
    for op in ops:
        noms = [r["schema_nom"] for r in op.reponses] + [op.corps["schema_nom"] if op.corps else None]
        for nom in filter(None, noms):
            assert nom.removeprefix("liste de ") in composants, (op.operation_id, nom)


def test_permission_identifiee_seulement_si_tout_est_analyse(operations):
    ops, _index = operations
    for op in ops:
        if op.permission_statut == cat.PERM_IDENTIFIEE:
            assert op.permissions and not op.dependances_non_analysees
        if op.authentification in (cat.AUTH_AUCUNE, cat.AUTH_INDETERMINEE):
            assert op.permission_statut == cat.PERM_NON_VERIFIEE


def test_route_sans_schema_de_reponse_est_restreinte_et_sans_exemple(operations):
    _ops, index = operations
    op = _op(index, "get.ged.download_document")
    assert op.schema_reponse_statut == cat.SCHEMA_ABSENT
    assert op.disponibilite == cat.DISPO_RESTREINTE
    assert any("response_model" in m for m in op.motifs)
    assert all(not r["champs"] for r in op.reponses if r["code"].startswith("2"))
    exemples = generer(op)
    assert exemples["disponible"] is False and exemples["exemples"] == []


def test_route_a_schema_generique_est_signalee(operations):
    _ops, index = operations
    op = _op(index, "get.org_referentiel.agences")
    assert op.schema_reponse_statut == cat.SCHEMA_GENERIQUE
    assert op.disponibilite == cat.DISPO_RESTREINTE
    assert op.authentification == cat.AUTH_SESSION
    assert op.permission_statut == cat.PERM_NON_DETERMINEE


def test_routes_sensibles_exclues_sans_metadonnees(operations):
    ops, index = operations
    assert _op(index, "post.auth.login").categorie_exclusion == cat.EXCLUSION_AUTH
    assert _op(index, "get.main.health").categorie_exclusion == cat.EXCLUSION_INFRA
    assert _op(index, "get.core_admin_users.list_admin_users").categorie_exclusion == cat.EXCLUSION_ADMIN
    for op in ops:
        if op.disponibilite == cat.DISPO_EXCLUE:
            expose = cat.detail_expose(op)
            assert expose["parametres"] == [] and expose["corps"] is None and expose["description"] is None
            assert not op.exemples_disponibles
            assert generer(op)["exemples"] == []


def test_get_n_est_pas_suffisant_pour_etre_documente(operations):
    ops, _index = operations
    assert any(op.methode == "GET" and op.disponibilite != cat.DISPO_DOCUMENTEE for op in ops)


def test_module_login2_identifie(operations):
    ops, _index = operations
    modules = {op.module_code for op in ops if op.authentification == cat.AUTH_LOGIN2}
    assert {"immobilisations", "clientele", "formation", "reclamations"} <= modules
    for op in ops:
        if op.module_code:
            assert op.authentification == cat.AUTH_LOGIN2 and op.module == op.module_code


def test_filtres_et_kpis(operations):
    ops, index = operations
    ids = console.ids_console(index)
    gets = cat.filtrer(ops, methode="get")
    assert gets and all(op.methode == "GET" for op in gets)
    assert all(op.module == "core-admin" for op in cat.filtrer(ops, module="core-admin"))
    assert {op.operation_id for op in cat.filtrer(ops, console_ids=ids, console=True)} == ids
    recherche = cat.filtrer(ops, recherche="integrations/console")
    assert {op.operation_id for op in recherche} == {
        "get.core_admin_integrations.operations_console",
        "post.core_admin_integrations.executer_console",
    }
    k = cat.kpis(ops, ids)
    assert k["total"] == len(ops) == k["documentees"] + k["restreintes"] + k["exclues"]
    assert k["console"] == len(ids)
    for statut, nombre in k["par_schema_reponse"].items():
        assert len(cat.filtrer(ops, schema_reponse=statut)) == nombre


def test_recherche_ignore_le_resume_des_routes_exclues(operations):
    ops, _index = operations
    exclue = next(op for op in ops if op.disponibilite == cat.DISPO_EXCLUE)
    restreinte = next(op for op in ops if op.disponibilite == cat.DISPO_RESTREINTE)
    marque = "resume-interne-zq81"
    copies = [dataclasses.replace(exclue, resume=marque), dataclasses.replace(restreinte, resume=marque)]
    assert [op.operation_id for op in cat.filtrer(copies, recherche=marque)] == [restreinte.operation_id]


# --- Exemples ------------------------------------------------------------------------------


def test_exemples_sans_secret_et_avec_espaces_reserves(operations):
    ops, _index = operations
    settings = get_settings()
    secrets = [s for s in (settings.secret_key, "Admin@2026") if s]
    documentees = [op for op in ops if op.exemples_disponibles]
    assert documentees
    for op in documentees:
        rendu = generer(op)
        assert rendu["disponible"] is True
        assert {e["langage"] for e in rendu["exemples"]} == {"curl", "python", "typescript"}
        for exemple in rendu["exemples"]:
            code = exemple["code"]
            assert "BEA_ACCESS_TOKEN" in code and "BEA_BASE_URL" in code
            assert "droits autorisés" in code
            assert not re.search(r"eyJ[A-Za-z0-9_\-]{10,}", code)
            for secret in secrets:
                assert secret not in code
        assert any("Permission" in p for p in rendu["prerequis"]) == bool(op.permissions)


def test_exemple_login2_montre_le_login_module(operations):
    _ops, index = operations
    op = next(
        o for o in index.values()
        if o.exemples_disponibles and o.authentification == cat.AUTH_LOGIN2 and o.module_code == "immobilisations"
    )
    code = generer(op)["exemples"][0]["code"]
    assert "/api/v1/auth/modules/immobilisations/login" in code


# --- Console : règles ----------------------------------------------------------------------


def test_liste_console_revue_et_eligible(operations):
    _ops, index = operations
    assert console.ids_console(index) == set(console.CONSOLE_OPERATIONS)
    for op_id in console.CONSOLE_OPERATIONS:
        op = index[op_id]
        assert op.methode == "GET" and op.authentification == cat.AUTH_LOGIN1


def test_operation_hors_liste_refusee(operations):
    _ops, index = operations
    op = _op(index, "get.core_admin_users.list_admin_users")
    assert console.eligibilite(op) == (False, "Hors liste d'autorisation revue de la console.")


def test_methode_non_get_refusee_meme_si_inscrite(operations, monkeypatch):
    _ops, index = operations
    op = _op(index, "post.core_admin_integrations.executer_console")
    monkeypatch.setitem(console.CONSOLE_OPERATIONS, op.operation_id, "test")
    ok, motif = console.eligibilite(op)
    assert not ok and "GET" in motif


def test_operation_login2_refusee_meme_si_inscrite(operations, monkeypatch):
    _ops, index = operations
    op = next(o for o in index.values() if o.methode == "GET" and o.authentification == cat.AUTH_LOGIN2)
    monkeypatch.setitem(console.CONSOLE_OPERATIONS, op.operation_id, "test")
    ok, motif = console.eligibilite(op)
    assert not ok and "Login 1" in motif


@pytest.mark.parametrize(
    "valeur",
    ["../users", "a/b", "http://exemple.invalid", "%2e%2e", "a b", "", "x" * 200, "a?b=1", "a#b"],
)
def test_chemin_arbitraire_refuse(operations, valeur):
    _ops, index = operations
    op = _op(index, "get.core_admin_integrations.fiche_operation")
    with pytest.raises(console.ConsoleRefus) as err:
        console.construire_chemin(op, {"operation_id": valeur})
    assert err.value.status_code == 400


def test_parametres_de_chemin_inattendus_refuses(operations):
    _ops, index = operations
    op = _op(index, "get.core_admin_integrations.fiche_operation")
    with pytest.raises(console.ConsoleRefus):
        console.construire_chemin(op, {"operation_id": "x", "url": "http://exemple.invalid"})
    with pytest.raises(console.ConsoleRefus):
        console.construire_chemin(op, {})
    assert console.construire_chemin(op, {"operation_id": "get.main.health"}).endswith(
        "/integrations/catalogue/get.main.health"
    )


def test_parametres_de_requete_controles(operations):
    _ops, index = operations
    op = _op(index, "get.core_admin_catalogue.list_modules")
    assert console.construire_requete(op, {"page": 1, "size": 5, "search": ""}) == [("page", "1"), ("size", "5")]
    for mauvais in ({"url": "http://x"}, {"search": "a\nb"}, {"search": "x" * 201}, {"search": {"a": 1}}):
        with pytest.raises(console.ConsoleRefus):
            console.construire_requete(op, mauvais)
    with pytest.raises(console.ConsoleRefus):
        console.construire_requete(op, {"search": ["a"] * 21})


def test_requete_console_refuse_url_methode_et_entetes():
    for champ in ({"url": "http://exemple.invalid"}, {"methode": "DELETE"}, {"headers": {"X": "1"}}, {"chemin": "/x"}):
        with pytest.raises(ValidationError):
            IntegrationConsoleRequete(operation_id="get.main.health", **champ)


def test_masquage_recursif():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl"
    valeur, n = console.masquer(
        {
            "items": [{"email": "a@b.c", "code": "immo", "access_token": "abc", "nested": {"mot_de_passe": "x"}}],
            "ip_address": "10.0.0.1",
            "libre": jwt,
            "vide": None,
            "password": "",
        }
    )
    assert valeur["items"][0]["email"] == console.MASQUE
    assert valeur["items"][0]["access_token"] == console.MASQUE
    assert valeur["items"][0]["nested"]["mot_de_passe"] == console.MASQUE
    assert valeur["items"][0]["code"] == "immo"
    assert valeur["ip_address"] == console.MASQUE
    assert valeur["libre"] == console.MASQUE
    assert n == 5


# --- Console : exécution sur une application de test (sans base) ---------------------------


class _Petit(BaseModel):
    code: str
    email: str | None = None
    password: str | None = None


class _Liste(BaseModel):
    items: list[str]


_PERM_TEST = require_platform_permission("core.admin.integrations.view")
_PERM_REFUSEE = require_platform_permission("core.admin.modules")


def _refuser():
    from fastapi import HTTPException

    raise HTTPException(status_code=403, detail="Permission refusée")


def _mini_app() -> FastAPI:
    mini = FastAPI()
    mini.add_middleware(RequestContextMiddleware)

    @mini.get("/api/v1/test/petit", response_model=_Petit)
    async def petit(filtre: str | None = None, _u=Depends(_PERM_TEST)):
        return {"code": "ok", "email": "agent@exemple.invalid", "password": "S3cret-Console!"}

    @mini.get("/api/v1/test/gros", response_model=_Liste)
    async def gros(_u=Depends(_PERM_TEST)):
        return {"items": ["x" * 1000] * 400}

    @mini.get("/api/v1/test/lent", response_model=_Petit)
    async def lent(_u=Depends(_PERM_TEST)):
        await asyncio.sleep(1.0)
        return {"code": "tard"}

    @mini.get("/api/v1/test/refus", response_model=_Petit)
    async def refus(_u=Depends(_PERM_REFUSEE)):
        return {"code": "jamais"}

    @mini.get("/api/v1/test/texte", response_model=_Petit)
    async def texte(_u=Depends(_PERM_TEST)):
        return PlainTextResponse("pas du json")

    @mini.get("/api/v1/test/session", response_model=_Petit)
    async def session(_u=Depends(get_current_user)):
        return {"code": "ok"}

    @mini.get("/api/v1/test/module", response_model=_Petit, dependencies=[Depends(require_module_access("immobilisations"))])
    async def module():
        return {"code": "ok"}

    mini.dependency_overrides[_PERM_TEST] = lambda: object()
    mini.dependency_overrides[_PERM_REFUSEE] = _refuser
    return mini


@pytest.fixture
def mini(monkeypatch):
    monkeypatch.setattr("app.middleware.request_context.record_api_error", lambda **_k: None)
    application = _mini_app()
    _ops, index = cat.operations_de(application)
    for op_id in index:
        monkeypatch.setitem(console.CONSOLE_OPERATIONS, op_id, "test")
    yield application, index
    cat.vider_cache()


def _mini_op(index, nom):
    return next(op for op in index.values() if op.nom == nom)


async def _executer(application, op, **kwargs):
    return await console.executer(
        application,
        op,
        parametres_chemin=kwargs.get("chemin", {}),
        parametres_requete=kwargs.get("requete", {}),
        authorization=kwargs.get("authorization", "Bearer jeton-de-test"),
        client_ip="10.9.8.7",
    )


@pytest.mark.asyncio
async def test_console_masque_et_ne_journalise_aucun_secret(mini, caplog):
    application, index = mini
    caplog.set_level(logging.DEBUG)
    jeton = "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.c2VjcmV0LWNvbnNvbGU"
    res = await _executer(application, _mini_op(index, "petit"), authorization=jeton, requete={"filtre": "SondeJournal-42"})
    assert res["statut_http"] == 200
    assert res["corps"]["code"] == "ok"
    assert res["corps"]["email"] == console.MASQUE and res["corps"]["password"] == console.MASQUE
    assert res["champs_masques"] == 2
    assert res["request_id"]
    journal = caplog.text
    assert "S3cret-Console!" not in journal
    assert "agent@exemple.invalid" not in journal
    assert "eyJhbGciOiJIUzI1NiJ9" not in journal
    assert "SondeJournal-42" not in journal
    assert console.HOTE_INTERNE not in journal


@pytest.mark.asyncio
async def test_console_limite_la_taille(mini):
    application, index = mini
    res = await _executer(application, _mini_op(index, "gros"))
    assert res["tronquee"] is True and res["corps"] is None
    assert res["taille_octets"] > console.TAILLE_MAX_OCTETS


@pytest.mark.asyncio
async def test_console_delai_maximal(mini, monkeypatch):
    application, index = mini
    monkeypatch.setattr(console, "DELAI_MAX_SECONDES", 0.05)
    with pytest.raises(console.ConsoleRefus) as err:
        await _executer(application, _mini_op(index, "lent"))
    assert err.value.status_code == 504


@pytest.mark.asyncio
async def test_console_restitue_le_refus_de_l_endpoint_cible(mini):
    application, index = mini
    res = await _executer(application, _mini_op(index, "refus"))
    assert res["statut_http"] == 403


@pytest.mark.asyncio
async def test_console_ne_montre_pas_une_reponse_non_json(mini):
    application, index = mini
    res = await _executer(application, _mini_op(index, "texte"))
    assert res["corps"] is None and "non JSON" in res["message"]


@pytest.mark.asyncio
async def test_console_refuse_sans_jeton_et_hors_login1(mini):
    application, index = mini
    with pytest.raises(console.ConsoleRefus) as err:
        await _executer(application, _mini_op(index, "petit"), authorization=None)
    assert err.value.status_code == 401
    for nom in ("session", "module"):
        with pytest.raises(console.ConsoleRefus) as err:
            await _executer(application, _mini_op(index, nom))
        assert err.value.status_code == 403


# --- Accès réel (copie de base jetable uniquement) -----------------------------------------


@pytest.fixture
async def moteur_frais():
    """Les connexions du pool restent liées à la boucle d'un test précédent : on repart d'un pool vide."""
    try:
        await engine.dispose()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("Base PostgreSQL indisponible")


@pytest.fixture
async def client(moteur_frais, base_jetable):
    transport = ASGITransport(app=app, client=(f"10.77.{uuid4().int % 250}.{uuid4().int % 250}", 50000))
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _creer_compte(superuser: bool) -> tuple[str, str]:
    email = f"studio-api-{uuid4().hex[:8]}@el-amana.mr"
    password = "StudioApi@2026"
    async with AsyncSessionLocal() as session:
        session.add(
            User(
                email=email,
                full_name="Test Studio API",
                hashed_password=get_password_hash(password),
                is_superuser=superuser,
            )
        )
        await session.commit()
    return email, password


async def _archiver(email: str) -> None:
    async with AsyncSessionLocal() as session:
        row = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if row is not None:
            row.is_active = False
            row.deleted_at = datetime.now(timezone.utc)
            await session.commit()


async def _jeton(client: AsyncClient, email: str, password: str) -> str:
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


ROUTES_GET = (
    f"{BASE}/catalogue",
    f"{BASE}/catalogue/get.main.health",
    f"{BASE}/catalogue/get.main.health/exemples",
    f"{BASE}/console/operations",
)


@pytest.mark.asyncio
async def test_acces_studio_login1_permission_et_refus(client: AsyncClient):
    for route in ROUTES_GET:
        assert (await client.get(route)).status_code == 401
    assert (await client.post(f"{BASE}/console/executer", json={"operation_id": "x"})).status_code == 401

    sans_droit, mdp = await _creer_compte(superuser=False)
    admin, mdp_admin = await _creer_compte(superuser=True)
    try:
        refuse = {"Authorization": f"Bearer {await _jeton(client, sans_droit, mdp)}"}
        for route in ROUTES_GET:
            res = await client.get(route, headers=refuse)
            assert res.status_code == 403, (route, res.text)
        res = await client.post(f"{BASE}/console/executer", headers=refuse, json={"operation_id": "x"})
        assert res.status_code == 403

        ok = {"Authorization": f"Bearer {await _jeton(client, admin, mdp_admin)}"}
        page = await client.get(f"{BASE}/catalogue", headers=ok, params={"size": 5, "methode": "GET"})
        if page.status_code == 403 and "MFA" in page.text:
            pytest.skip("Politique MFA CORE ADMIN active sur cette copie")
        assert page.status_code == 200, page.text
        body = page.json()
        assert body["total"] > 0 and len(body["items"]) <= 5
        assert all(item["methode"] == "GET" for item in body["items"])
        assert "autorisation" in body["avertissement"]

        fiche = await client.get(f"{BASE}/catalogue/get.core_admin_integrations.lister_catalogue", headers=ok)
        assert fiche.status_code == 200 and fiche.json()["permissions"] == [PERM]
        assert (await client.get(f"{BASE}/catalogue/inconnue.x.y", headers=ok)).status_code == 404
        exclue = await client.get(f"{BASE}/catalogue/get.main.health/exemples", headers=ok)
        assert exclue.status_code == 200 and exclue.json()["disponible"] is False

        ops = await client.get(f"{BASE}/console/operations", headers=ok)
        assert ops.status_code == 200
        assert {o["operation_id"] for o in ops.json()["items"]} == set(console.CONSOLE_OPERATIONS)

        execution = await client.post(
            f"{BASE}/console/executer",
            headers=ok,
            json={"operation_id": "get.core_admin_catalogue.list_modules", "parametres_requete": {"size": 2}},
        )
        assert execution.status_code == 200, execution.text
        resultat = execution.json()
        assert resultat["statut_http"] == 200 and resultat["methode"] == "GET"
        assert len(resultat["corps"]["items"]) <= 2

        hors_liste = await client.post(
            f"{BASE}/console/executer", headers=ok, json={"operation_id": "get.core_admin_users.list_admin_users"}
        )
        assert hors_liste.status_code == 403
        forge = await client.post(f"{BASE}/console/executer", headers=ok, json={"operation_id": "x" * 160})
        assert forge.status_code == 403, forge.text
        url = await client.post(
            f"{BASE}/console/executer",
            headers=ok,
            json={"operation_id": "get.core_admin_catalogue.list_modules", "url": "http://exemple.invalid"},
        )
        assert url.status_code == 422
        for methode in ("get", "put", "delete"):
            assert (await client.request(methode.upper(), f"{BASE}/console/executer", headers=ok)).status_code == 405
    finally:
        await _archiver(sans_droit)
        await _archiver(admin)


@pytest.mark.asyncio
async def test_jeton_login2_refuse(client: AsyncClient):
    admin, mdp = await _creer_compte(superuser=True)
    try:
        plateforme = await _jeton(client, admin, mdp)
        module = await client.post(
            "/api/v1/auth/modules/immobilisations/login",
            json={"email": admin, "password": mdp},
            headers={"Authorization": f"Bearer {plateforme}"},
        )
        if module.status_code != 200:
            pytest.skip("Login module indisponible pour ce compte de test")
        login2 = {"Authorization": f"Bearer {module.json()['access_token']}"}
        for route in ROUTES_GET:
            assert (await client.get(route, headers=login2)).status_code == 401
        res = await client.post(
            f"{BASE}/console/executer", headers=login2, json={"operation_id": "get.core_admin_catalogue.list_modules"}
        )
        assert res.status_code == 401
    finally:
        await _archiver(admin)
