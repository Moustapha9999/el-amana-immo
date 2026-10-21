"""Studio d'intégration API — applications clientes et demandes de droits (Phase 2).

Les tests d'accès réel créent des comptes, des rôles de test et des fiches : ils ne tournent que sur
une copie de base jetable (fixture ``base_jetable``), jamais sur ``bea_digital``.
"""

from __future__ import annotations

import dataclasses
import logging
import random
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.core.security import get_password_hash
from app.data.plateforme_catalogue import CORE_ADMIN_PERMISSIONS, FUNCTIONAL_PERMISSIONS, ROLE_PERMISSIONS
from app.db.base import Base
from app.db.session import AsyncSessionLocal, engine
from app.main import app
from app.models import Departement, Permission, Role, User
from app.models.associations import role_permissions_table, user_roles_table
from app.schemas.integration_clients import IntegrationClientCreation, IntegrationGrantDecision
from app.services.integrations import catalogue as cat
from app.services.integrations import clients as svc
from app.services.permission_service import load_user_permission_codes, user_has_permission_codes

BASE = "/api/v1/plateforme/admin/integrations/clients"
NOUVELLES = (
    svc.P_CLIENTS_VIEW,
    svc.P_CLIENTS_MANAGE,
    svc.P_GRANTS_VIEW,
    svc.P_GRANTS_MANAGE,
    svc.P_GRANTS_APPROVE,
    svc.P_EXPORT,
)
_MOTS_SECRETS = re.compile(r"secret|password|mot_de_passe|token|jeton|api_key|apikey|credential|client_id", re.I)


# --- Permissions ---------------------------------------------------------------------------


def test_permissions_declarees_sans_attribution_ni_suffixe_admin():
    core_admin = {code for code, _l, _m in CORE_ADMIN_PERMISSIONS}
    fonctionnelles = {code for code, _l, _m in FUNCTIONAL_PERMISSIONS}
    for code in NOUVELLES:
        assert code in core_admin and code in fonctionnelles
        assert not code.endswith(".admin")
        assert not any(code in perms for perms in ROLE_PERMISSIONS.values())


@pytest.mark.parametrize(
    "have",
    [
        {"core.admin.access"},
        {"core.admin.integrations.view"},
        {"core.admin.query.admin"},
        {"plateforme.users.admin"},
        {"immobilisations.admin"},
        {"core.admin.integrations.grants.manage"},
    ],
)
def test_aucun_joker_ne_couvre_l_approbation(have):
    assert not user_has_permission_codes(have, svc.P_GRANTS_APPROVE)
    assert not user_has_permission_codes(have, svc.P_EXPORT)


def test_routes_login1_avec_permission_dediee_et_exclues_du_catalogue():
    _ops, index = cat.operations_de(app)
    routes = [op for op in index.values() if op.chemin.startswith(BASE)]
    assert len(routes) == 13
    for op in routes:
        assert op.authentification == cat.AUTH_LOGIN1, op.operation_id
        assert op.permissions and set(op.permissions) <= set(NOUVELLES), op.operation_id
        assert op.disponibilite == cat.DISPO_EXCLUE
    decision = next(op for op in routes if op.methode == "PATCH" and op.chemin.endswith("{grant_id}"))
    assert set(decision.permissions) == {svc.P_GRANTS_MANAGE, svc.P_GRANTS_APPROVE}


# --- Modèle et migration -------------------------------------------------------------------


def test_aucune_table_ni_colonne_d_authentification():
    tables = {t for t in Base.metadata.tables if t.startswith("integration_client")}
    assert tables == {"integration_clients", "integration_client_grants", "integration_client_grant_events"}
    for nom in tables:
        for colonne in Base.metadata.tables[nom].columns:
            assert not re.search(r"secret|password|token|jeton|api_key|credential|hash", colonne.name), colonne.name


def test_migration_additive_et_reversible():
    chemin = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "20261021_integrations_01_clients.py"
    source = chemin.read_text(encoding="utf-8")
    upgrade, downgrade = source.split("def downgrade", 1)
    assert 'down_revision: Union[str, None] = "20261020_clientele_14"' in source
    assert "drop_" not in upgrade and "alter_column" not in upgrade and "rename" not in upgrade.lower()
    for table in ("integration_clients", "integration_client_grants", "integration_client_grant_events"):
        assert f'op.drop_table("{table}")' in downgrade
    assert "integration_credentials" not in source


# --- Règles (sans base) --------------------------------------------------------------------


def _admissible_brute():
    ops, _index = cat.operations_de(app)
    for op in ops:
        etats = {op.module_code: "actif"} if op.module_code else {}
        if svc.admissibilite(op, etats)[0]:
            return op
    pytest.fail("Aucune opération admissible dans le catalogue")


def test_admissibilite_exige_une_documentation_sans_reserve():
    ops, index = cat.operations_de(app)
    assert svc.admissibilite(None, {}) == (False, "Opération absente du catalogue actuel.")
    for op in ops:
        if op.disponibilite != cat.DISPO_DOCUMENTEE:
            assert not svc.admissibilite(op, {op.module_code: "actif"})[0], op.operation_id
    assert not svc.admissibilite(index["get.ged.download_document"], {"ged": "actif"})[0]
    assert not svc.admissibilite(index["get.core_admin_users.list_admin_users"], {})[0]


@pytest.mark.parametrize(
    "modif, etat, attendu",
    [
        ({"methode": "DELETE"}, "actif", "Suppression"),
        ({"chemin": "/api/v1/x/export"}, "actif", "sensible"),
        ({"chemin": "/api/v1/x/import-fichier"}, "actif", "sensible"),
        ({"permissions": ["core.admin.users"]}, "actif", "absente du référentiel|administration"),
        ({"permissions": ["immobilisations.admin"]}, "actif", "administration"),
        ({"permissions": ["code.invente"]}, "actif", "référentiel"),
        ({"permissions": []}, "actif", "non identifiée"),
        ({"permission_statut": cat.PERM_NON_DETERMINEE}, "actif", "non identifiée"),
        ({"authentification": cat.AUTH_INDETERMINEE}, "actif", "Authentification"),
        ({"disponibilite": cat.DISPO_RESTREINTE}, "actif", "non documentée"),
        ({"module_code": "immobilisations"}, "bientot", "non actif"),
        ({"module_code": "immobilisations"}, "desactive", "non actif"),
    ],
)
def test_admissibilite_refuse_les_cas_incertains_ou_sensibles(modif, etat, attendu):
    op = dataclasses.replace(_admissible_brute(), **modif)
    ok, motif = svc.admissibilite(op, {op.module_code: etat} if op.module_code else {})
    assert not ok and re.search(attendu, motif), motif


def test_transitions_des_droits():
    vers_approuvee = {k: v for k, v in svc.TRANSITIONS_GRANT.items() if k[1] == "approuvee"}
    assert vers_approuvee == {("en_attente", "approuvee"): svc.P_GRANTS_APPROVE}
    for (ancien, nouveau), perm in svc.TRANSITIONS_GRANT.items():
        if nouveau in ("approuvee", "refusee", "revoquee"):
            assert perm == svc.P_GRANTS_APPROVE
        else:
            assert perm == svc.P_GRANTS_MANAGE
    assert svc.MOTIF_OBLIGATOIRE == {"refusee", "revoquee"}
    assert svc.TRANSITIONS_CLIENT["archivee"] == frozenset()
    assert all("archivee" not in v for v in svc.TRANSITIONS_CLIENT.values())


@pytest.mark.parametrize(
    "champ, valeur",
    [
        ("notes", "password=Azerty123"),
        ("notes", "Authorization: Bearer abcdefghijklmnop1234"),
        ("description", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig"),
        ("finalite", "api_key: 12345"),
        ("contact_technique", "Jean\nDupont"),
        ("nom", "a\x00b"),
    ],
)
def test_textes_refusent_secrets_et_controles(champ, valeur):
    data = {"nom": "Application", "environnement": "DEV", champ: valeur}
    with pytest.raises(ValidationError):
        IntegrationClientCreation(**data)


def test_schemas_refusent_champs_inconnus():
    for extra in ({"client_secret": "x"}, {"code": "INT-X"}, {"statut": "active"}, {"created_by_id": str(uuid4())}):
        with pytest.raises(ValidationError):
            IntegrationClientCreation(nom="A", environnement="DEV", **extra)
    with pytest.raises(ValidationError):
        IntegrationClientCreation(nom="   ", environnement="DEV")
    with pytest.raises(ValidationError):
        IntegrationClientCreation(nom="A", environnement="PROD")
    with pytest.raises(ValidationError):
        IntegrationGrantDecision(statut="approuvee", permissions=["*"])


def test_identifiant_interne_et_normalisation():
    codes = {svc._nouveau_code() for _ in range(200)}
    assert len(codes) == 200
    assert all(re.fullmatch(r"INT-[0-9A-HJKMNP-TV-Z]{8}", c) for c in codes)
    assert svc.normaliser_nom("  Démo   Portail ") == svc.normaliser_nom("demo portail")


# --- Accès réel (copie de base jetable uniquement) -----------------------------------------


class _Transport(ASGITransport):
    """Une adresse source par requête : le limiteur « sensible » (60/min) ne fausse pas les parcours."""

    async def handle_async_request(self, request):
        self.client = (f"10.78.{random.randint(0, 250)}.{random.randint(1, 250)}", 50000)
        return await super().handle_async_request(request)


@pytest.fixture
async def moteur_frais():
    try:
        await engine.dispose()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("Base PostgreSQL indisponible")


_MDP = "StudioClients@2026"
_COMPTES: list[str] = []


@pytest.fixture
async def client(moteur_frais, base_jetable):
    async with AsyncClient(transport=_Transport(app=app), base_url="http://test") as ac:
        yield ac
    await _archiver_comptes()


async def _compte(*codes: str, superuser: bool = False) -> str:
    email = f"studio-clients-{uuid4().hex[:8]}@el-amana.mr"
    async with AsyncSessionLocal() as s:
        user = User(email=email, full_name=f"Test {email[:22]}", hashed_password=get_password_hash(_MDP),
                    is_superuser=superuser)
        s.add(user)
        await s.flush()
        if codes:
            role = Role(code=f"test-studio-{uuid4().hex[:10]}", label="Rôle de test Studio (jetable)")
            s.add(role)
            await s.flush()
            for code in codes:
                perm = await s.scalar(select(Permission).where(Permission.code == code))
                if perm is None:
                    perm = Permission(code=code, label=code, module="core")
                    s.add(perm)
                    await s.flush()
                await s.execute(role_permissions_table.insert().values(role_id=role.id, permission_id=perm.id))
            await s.execute(user_roles_table.insert().values(user_id=user.id, role_id=role.id))
        await s.commit()
    _COMPTES.append(email)
    return email


async def _archiver_comptes() -> None:
    if not _COMPTES:
        return
    async with AsyncSessionLocal() as s:
        for row in (await s.scalars(select(User).where(User.email.in_(_COMPTES)))).all():
            row.is_active = False
            row.deleted_at = datetime.now(timezone.utc)
        await s.commit()
    _COMPTES.clear()


async def _entete(client: AsyncClient, email: str) -> dict:
    res = await client.post("/api/v1/auth/login", json={"email": email, "password": _MDP})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _sauter_si_mfa(res) -> None:
    if res.status_code == 403 and "MFA" in res.text:
        pytest.skip("Politique MFA CORE ADMIN active sur cette copie")


async def _entite_active() -> str:
    async with AsyncSessionLocal() as s:
        e = await s.scalar(select(Departement.id).where(Departement.is_active.is_(True),
                                                        Departement.deleted_at.is_(None)).limit(1))
    if e is None:
        pytest.skip("Aucune entité active dans l'organigramme de la copie")
    return str(e)


async def _profils(client: AsyncClient) -> dict[str, dict]:
    gestion = await _compte(svc.P_CLIENTS_VIEW, svc.P_CLIENTS_MANAGE, svc.P_GRANTS_VIEW, svc.P_GRANTS_MANAGE)
    approbateur = await _compte(svc.P_CLIENTS_VIEW, svc.P_GRANTS_VIEW, svc.P_GRANTS_APPROVE)
    lecteur = await _compte(svc.P_CLIENTS_VIEW)
    export = await _compte(svc.P_EXPORT)
    return {
        "gestion": await _entete(client, gestion),
        "approbateur": await _entete(client, approbateur),
        "lecteur": await _entete(client, lecteur),
        "export": await _entete(client, export),
        "_emails": {"gestion": gestion, "approbateur": approbateur},
    }


def _sans_secret(payload) -> None:
    def parcourir(v, chemin=""):
        if isinstance(v, dict):
            for k, x in v.items():
                assert not _MOTS_SECRETS.search(str(k)), f"{chemin}.{k}"
                parcourir(x, f"{chemin}.{k}")
        elif isinstance(v, list):
            for x in v:
                parcourir(x, chemin)
    parcourir(payload)
    rendu = str(payload)
    assert not re.search(r"eyJ[A-Za-z0-9_\-]{10,}\.", rendu)
    secret_key = get_settings().secret_key
    if secret_key:
        assert secret_key not in rendu


async def _creer(client, h, **champs) -> dict:
    corps = {"nom": f"Portail test {uuid4().hex[:6]}", "environnement": "DEV", **champs}
    res = await client.post(BASE, headers=h, json=corps)
    _sauter_si_mfa(res)
    assert res.status_code == 201, res.text
    return res.json()


async def _admissibles(client, h, client_id: str, n: int = 2) -> list[str]:
    res = await client.get(f"{BASE}/{client_id}/operations-admissibles", headers=h, params={"size": 100})
    assert res.status_code == 200, res.text
    items = [i for i in res.json()["items"] if i["admissible"] and not i["deja_demandee"]]
    if len(items) < n:
        pytest.skip("Pas assez d'opérations admissibles sur cette copie (modules actifs)")
    return [i["operation_id"] for i in items[:n]]


@pytest.mark.asyncio
async def test_sans_authentification_tout_est_refuse(client: AsyncClient):
    cid = uuid4()
    gid = uuid4()
    appels = [
        ("GET", BASE, None), ("POST", BASE, {"nom": "x", "environnement": "DEV"}),
        ("GET", f"{BASE}/{cid}", None), ("PATCH", f"{BASE}/{cid}", {"revision": 1}),
        ("POST", f"{BASE}/{cid}/archive", {"revision": 1, "motif": "test"}),
        ("GET", f"{BASE}/{cid}/grants", None), ("POST", f"{BASE}/{cid}/grants", {"operation_ids": ["x"]}),
        ("PATCH", f"{BASE}/{cid}/grants/{gid}", {"statut": "approuvee"}),
        ("GET", f"{BASE}/{cid}/historique", None), ("GET", f"{BASE}/{cid}/operations-admissibles", None),
        ("GET", f"{BASE}/{cid}/documentation", None),
    ]
    for methode, url, corps in appels:
        res = await client.request(methode, url, json=corps)
        assert res.status_code == 401, (methode, url, res.status_code)


@pytest.mark.asyncio
async def test_jeton_login2_refuse(client: AsyncClient):
    admin = await _compte(superuser=True)
    plateforme = await _entete(client, admin)
    module = await client.post("/api/v1/auth/modules/immobilisations/login",
                               json={"email": admin, "password": _MDP}, headers=plateforme)
    if module.status_code != 200:
        pytest.skip("Login module indisponible pour ce compte de test")
    login2 = {"Authorization": f"Bearer {module.json()['access_token']}"}
    assert (await client.get(BASE, headers=login2)).status_code == 401
    res = await client.post(BASE, headers=login2, json={"nom": "Login2", "environnement": "DEV"})
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_permissions_manquantes(client: AsyncClient):
    p = await _profils(client)
    phase1 = await _entete(client, await _compte("core.admin.access", "core.admin.integrations.view"))
    res = await client.get(BASE, headers=phase1)
    _sauter_si_mfa(res)
    assert res.status_code == 403
    assert res.json()["code"] == "PERMISSION_DENIED" and res.json()["request_id"]

    fiche = await _creer(client, p["gestion"])
    cid = fiche["id"]
    assert (await client.get(BASE, headers=p["lecteur"])).status_code == 200
    assert (await client.get(f"{BASE}/{cid}", headers=p["lecteur"])).status_code == 200
    interdits = [
        ("POST", BASE, {"nom": "Lecteur", "environnement": "DEV"}),
        ("PATCH", f"{BASE}/{cid}", {"revision": 1, "nom": "Lecteur"}),
        ("POST", f"{BASE}/{cid}/archive", {"revision": 1, "motif": "lecteur"}),
        ("GET", f"{BASE}/{cid}/grants", None),
        ("POST", f"{BASE}/{cid}/grants", {"operation_ids": ["x"]}),
        ("GET", f"{BASE}/{cid}/operations-admissibles", None),
        ("GET", f"{BASE}/{cid}/documentation", None),
    ]
    for methode, url, corps in interdits:
        res = await client.request(methode, url, headers=p["lecteur"], json=corps)
        assert res.status_code == 403, (methode, url, res.text)
    assert (await client.get(BASE, headers=p["export"])).status_code == 403
    assert (await client.post(f"{BASE}/{cid}/archive", headers=p["approbateur"],
                              json={"revision": 1, "motif": "approbateur"})).status_code == 403
    assert (await client.post(f"{BASE}/{cid}/grants", headers=p["approbateur"],
                              json={"operation_ids": ["x"]})).status_code == 403
    assert (await client.get(f"{BASE}/{cid}/documentation", headers=p["export"])).status_code == 200


@pytest.mark.asyncio
async def test_creation_validation_doublons_et_modification(client: AsyncClient, caplog):
    caplog.set_level(logging.DEBUG)
    p = await _profils(client)
    h = p["gestion"]
    nom = f"Démo Portail {uuid4().hex[:6]}"
    fiche = await _creer(client, h, nom=nom, description="Portail de test", contact_technique="Équipe SI",
                         finalite=None, notes="Note interne")
    _sans_secret(fiche)
    assert re.fullmatch(r"INT-[0-9A-Z]{8}", fiche["code"])
    assert fiche["statut"] == "brouillon" and fiche["revision"] == 1 and fiche["nb_operations"] == 0
    assert fiche["cree_par"]["nom"] and "authentifier" in fiche["avertissement"]

    for corps in (
        {"nom": "", "environnement": "DEV"},
        {"nom": "X", "environnement": "PROD"},
        {"nom": "X", "environnement": "DEV", "client_secret": "s"},
        {"nom": "X", "environnement": "DEV", "notes": "token=abc123"},
        {"nom": "X" * 121, "environnement": "DEV"},
        {"nom": "X", "environnement": "DEV", "statut": "active"},
        {"nom": "X", "environnement": "DEV", "org_entite_id": "pas-un-uuid"},
    ):
        res = await client.post(BASE, headers=h, json=corps)
        assert res.status_code == 422, (corps, res.text)
        assert res.json()["request_id"]
    res = await client.post(BASE, headers=h, json={"nom": "X", "environnement": "DEV", "org_entite_id": str(uuid4())})
    assert res.status_code == 422 and res.json()["code"] == "ENTITE_INVALIDE"

    doublon = await client.post(BASE, headers=h, json={"nom": nom.upper().replace("É", "E"), "environnement": "DEV"})
    assert doublon.status_code == 409 and doublon.json()["code"] == "CLIENT_DOUBLON"
    autre_env = await client.post(BASE, headers=h, json={"nom": nom, "environnement": "TEST"})
    assert autre_env.status_code == 201

    cid = fiche["id"]
    modif = await client.patch(f"{BASE}/{cid}", headers=h, json={"revision": 1, "description": "Nouvelle",
                                                                 "statut": "en_preparation"})
    assert modif.status_code == 200, modif.text
    assert modif.json()["revision"] == 2 and modif.json()["statut"] == "en_preparation"
    perime = await client.patch(f"{BASE}/{cid}", headers=h, json={"revision": 1, "description": "Ancienne"})
    assert perime.status_code == 409 and perime.json()["code"] == "CONFLIT_REVISION"
    vide = await client.patch(f"{BASE}/{cid}", headers=h, json={"revision": 2, "nom": None})
    assert vide.status_code == 422
    incomplet = await client.patch(f"{BASE}/{cid}", headers=h, json={"revision": 2, "statut": "active"})
    assert incomplet.status_code == 422 and incomplet.json()["code"] == "ACTIVATION_INCOMPLETE"
    archive_direct = await client.patch(f"{BASE}/{cid}", headers=h, json={"revision": 2, "statut": "archivee"})
    assert archive_direct.status_code == 422

    liste = await client.get(BASE, headers=h, params={"q": nom, "environnement": "DEV", "tri": "nom",
                                                      "ordre": "asc"})
    assert liste.status_code == 200
    assert [i["id"] for i in liste.json()["items"]] == [cid]
    assert (await client.get(BASE, headers=h, params={"q": "%_"})).status_code == 200
    assert (await client.get(BASE, headers=h, params={"tri": "secret"})).status_code == 422
    assert (await client.get(f"{BASE}/{uuid4()}", headers=h)).status_code == 404
    assert "Note interne" not in caplog.text and _MDP not in caplog.text


@pytest.mark.asyncio
async def test_cycle_des_droits_sans_escalade(client: AsyncClient):
    p = await _profils(client)
    g, a = p["gestion"], p["approbateur"]
    entite = await _entite_active()
    fiche = await _creer(client, g, finalite="Consultation des référentiels", org_entite_id=entite,
                         statut="en_preparation")
    cid = fiche["id"]

    async with AsyncSessionLocal() as s:
        avant = {}
        for cle in ("gestion", "approbateur"):
            u = await s.scalar(select(User).where(User.email == p["_emails"][cle]))
            avant[cle] = await load_user_permission_codes(s, u)
        liens_avant = await s.scalar(select(func.count()).select_from(role_permissions_table))

    inconnue = await client.post(f"{BASE}/{cid}/grants", headers=g, json={"operation_ids": ["inconnue.x.y"]})
    assert inconnue.status_code == 422 and inconnue.json()["code"] == "OPERATION_INCONNUE"
    for op_id in ("get.ged.download_document", "get.core_admin_users.list_admin_users", "post.auth.login"):
        res = await client.post(f"{BASE}/{cid}/grants", headers=g, json={"operation_ids": [op_id]})
        assert res.status_code == 422 and res.json()["code"] == "OPERATION_INADMISSIBLE", (op_id, res.text)
    ops = await _admissibles(client, g, cid, 3)
    melange = await client.post(f"{BASE}/{cid}/grants", headers=g,
                                json={"operation_ids": [ops[0], "get.ged.download_document"]})
    assert melange.status_code == 422
    assert (await client.get(f"{BASE}/{cid}/grants", headers=g)).json()["items"] == []

    demande = await client.post(f"{BASE}/{cid}/grants", headers=g,
                                json={"operation_ids": ops, "justification": "Besoin de consultation"})
    assert demande.status_code == 201, demande.text
    grants = {x["operation_id"]: x for x in demande.json()["items"]}
    assert {x["statut"] for x in grants.values()} == {"demandee"}
    assert all(x["admissible"] and x["permissions"] for x in grants.values())
    assert (await client.post(f"{BASE}/{cid}/grants", headers=g, json={"operation_ids": [ops[0]]})).status_code == 409
    g1, g2, g3 = (grants[o]["id"] for o in ops)

    def url(gid):
        return f"{BASE}/{cid}/grants/{gid}"

    sans_attente = await client.patch(url(g1), headers=a, json={"statut": "approuvee"})
    assert sans_attente.status_code == 409 and sans_attente.json()["code"] == "TRANSITION_INTERDITE"
    for gid in (g1, g2, g3):
        assert (await client.patch(url(gid), headers=g, json={"statut": "en_attente"})).status_code == 200
    auto = await client.patch(url(g1), headers=g, json={"statut": "approuvee"})
    assert auto.status_code == 403 and auto.json()["code"] == "PERMISSION_DENIED"
    lecteur = await client.patch(url(g1), headers=p["lecteur"], json={"statut": "approuvee"})
    assert lecteur.status_code == 403

    ok = await client.patch(url(g1), headers=a, json={"statut": "approuvee"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["statut"] == "approuvee" and ok.json()["decide_par"]["nom"] and ok.json()["decide_le"]
    assert (await client.patch(url(g2), headers=a, json={"statut": "refusee"})).status_code == 422
    refus = await client.patch(url(g2), headers=a, json={"statut": "refusee", "motif": "Hors finalité"})
    assert refus.status_code == 200 and refus.json()["motif"] == "Hors finalité"
    assert (await client.patch(url(g1), headers=a, json={"statut": "revoquee"})).status_code == 422
    revoc = await client.patch(url(g1), headers=a, json={"statut": "revoquee", "motif": "Fin du besoin"})
    assert revoc.status_code == 200 and revoc.json()["statut"] == "revoquee"
    assert (await client.patch(url(g1), headers=a, json={"statut": "approuvee"})).status_code == 409
    redemande = await client.patch(url(g1), headers=g, json={"statut": "demandee"})
    assert redemande.status_code == 200 and redemande.json()["decide_par"] is None
    assert (await client.patch(url(g3), headers=a, json={"statut": "approuvee"})).status_code == 200
    autre = await client.patch(f"{BASE}/{uuid4()}/grants/{g3}", headers=a, json={"statut": "revoquee", "motif": "x"})
    assert autre.status_code == 404

    async with AsyncSessionLocal() as s:
        for cle in ("gestion", "approbateur"):
            u = await s.scalar(select(User).where(User.email == p["_emails"][cle]))
            assert await load_user_permission_codes(s, u) == avant[cle]
        assert await s.scalar(select(func.count()).select_from(role_permissions_table)) == liens_avant

    hist = await client.get(f"{BASE}/{cid}/historique", headers=a)
    assert hist.status_code == 200
    evts = [(e["operation_id"], e["ancien_statut"], e["nouveau_statut"], e["motif"]) for e in hist.json()["items"]]
    assert (ops[0], "approuvee", "revoquee", "Fin du besoin") in evts
    assert (ops[1], "en_attente", "refusee", "Hors finalité") in evts
    assert (ops[0], None, "demandee", "Besoin de consultation") in evts
    assert all(e["acteur"] and e["acteur"]["nom"] for e in hist.json()["items"])
    assert hist.json()["total"] == 11

    async with AsyncSessionLocal() as s:
        actions = set((await s.scalars(text(
            "SELECT action FROM audit_logs WHERE entity IN ('integration_client', 'integration_client_grant') "
            "AND (entity_id = :cid OR after_data->>'client_id' = :cid)"
        ).bindparams(cid=cid))).all())
    assert {"integration_client_create", "integration_grant_request", "integration_grant_approuvee",
            "integration_grant_refusee", "integration_grant_revoquee"} <= actions

    doc = await client.get(f"{BASE}/{cid}/documentation", headers=p["export"])
    assert doc.status_code == 200, doc.text
    corps = doc.json()
    assert [o["operation_id"] for o in corps["operations"]] == [ops[2]]
    assert corps["en_attente"] == 1
    assert any("machine-à-machine" in x for x in corps["avertissements"])
    assert "BEA_ACCESS_TOKEN" in corps["markdown"] and fiche["code"] in corps["markdown"]
    _sans_secret({k: v for k, v in corps.items() if k != "markdown"})
    assert not re.search(r"eyJ[A-Za-z0-9_\-]{10,}\.", corps["markdown"])

    verrou = await client.patch(f"{BASE}/{cid}", headers=g, json={"revision": fiche["revision"],
                                                                  "environnement": "TEST"})
    assert verrou.status_code == 409 and verrou.json()["code"] == "ENVIRONNEMENT_VERROUILLE"


@pytest.mark.asyncio
async def test_archivage_conserve_la_tracabilite(client: AsyncClient):
    p = await _profils(client)
    g, a = p["gestion"], p["approbateur"]
    entite = await _entite_active()
    nom = f"Archivage {uuid4().hex[:6]}"
    fiche = await _creer(client, g, nom=nom, finalite="Test d'archivage", org_entite_id=entite,
                         statut="en_preparation")
    cid = fiche["id"]
    ops = await _admissibles(client, g, cid, 2)
    items = (await client.post(f"{BASE}/{cid}/grants", headers=g, json={"operation_ids": ops})).json()["items"]
    gid = {x["operation_id"]: x["id"] for x in items}
    await client.patch(f"{BASE}/{cid}/grants/{gid[ops[0]]}", headers=g, json={"statut": "en_attente"})
    assert (await client.patch(f"{BASE}/{cid}/grants/{gid[ops[0]]}", headers=a,
                               json={"statut": "approuvee"})).status_code == 200

    sans_motif = await client.post(f"{BASE}/{cid}/archive", headers=g, json={"revision": 1})
    assert sans_motif.status_code == 422
    perime = await client.post(f"{BASE}/{cid}/archive", headers=g, json={"revision": 99, "motif": "Fin du projet"})
    assert perime.status_code == 409
    arch = await client.post(f"{BASE}/{cid}/archive", headers=g, json={"revision": 1, "motif": "Fin du projet"})
    assert arch.status_code == 200, arch.text
    assert arch.json()["statut"] == "archivee" and arch.json()["archive_par"]["nom"]
    assert arch.json()["motif_archivage"] == "Fin du projet" and arch.json()["transitions"] == []

    grants = (await client.get(f"{BASE}/{cid}/grants", headers=g)).json()
    statuts = {x["operation_id"]: x["statut"] for x in grants["items"]}
    assert statuts == {ops[0]: "revoquee", ops[1]: "retiree"}
    assert (await client.patch(f"{BASE}/{cid}", headers=g, json={"revision": 2, "nom": "Autre"})).status_code == 409
    assert (await client.post(f"{BASE}/{cid}/archive", headers=g,
                              json={"revision": 2, "motif": "Encore"})).status_code == 409
    assert (await client.post(f"{BASE}/{cid}/grants", headers=g, json={"operation_ids": ops})).status_code == 409
    assert (await client.patch(f"{BASE}/{cid}/grants/{gid[ops[1]]}", headers=g,
                               json={"statut": "demandee"})).status_code == 409
    hist = (await client.get(f"{BASE}/{cid}/historique", headers=g)).json()["items"]
    assert any(e["nouveau_statut"] == "revoquee" and "Archivage" in (e["motif"] or "") for e in hist)

    par_defaut = (await client.get(BASE, headers=g, params={"q": nom})).json()
    assert par_defaut["total"] == 0
    tout = (await client.get(BASE, headers=g, params={"q": nom, "inclure_archivees": True})).json()
    assert [i["id"] for i in tout["items"]] == [cid]
    reutilise = await client.post(BASE, headers=g, json={"nom": nom, "environnement": "DEV"})
    assert reutilise.status_code == 201
    assert reutilise.json()["code"] != fiche["code"]

    async with AsyncSessionLocal() as s:
        assert await s.scalar(text("SELECT count(*) FROM integration_clients WHERE id = CAST(:i AS uuid)").bindparams(i=cid)) == 1


@pytest.mark.asyncio
async def test_isolation_des_environnements_et_transitions_client(client: AsyncClient):
    p = await _profils(client)
    g = p["gestion"]
    marque = uuid4().hex[:6]
    dev = await _creer(client, g, nom=f"Iso {marque} A", environnement="DEV")
    test = await _creer(client, g, nom=f"Iso {marque} B", environnement="TEST")
    seul_dev = (await client.get(BASE, headers=g, params={"q": f"Iso {marque}", "environnement": "DEV"})).json()
    assert [i["id"] for i in seul_dev["items"]] == [dev["id"]]
    seul_test = (await client.get(BASE, headers=g, params={"q": f"Iso {marque}", "environnement": "TEST"})).json()
    assert [i["id"] for i in seul_test["items"]] == [test["id"]]

    bascule = await client.patch(f"{BASE}/{dev['id']}", headers=g, json={"revision": 1, "environnement": "TEST",
                                                                          "nom": f"Iso {marque} B"})
    assert bascule.status_code == 409 and bascule.json()["code"] == "CLIENT_DOUBLON"
    for statut in ("active", "suspendue"):
        res = await client.patch(f"{BASE}/{dev['id']}", headers=g, json={"revision": 1, "statut": statut})
        assert res.status_code == 409 and res.json()["code"] == "TRANSITION_INTERDITE", statut

    ops = await _admissibles(client, g, dev["id"], 1)
    items = (await client.post(f"{BASE}/{dev['id']}/grants", headers=g, json={"operation_ids": ops})).json()["items"]
    gid = items[0]["id"]
    await client.patch(f"{BASE}/{dev['id']}/grants/{gid}", headers=g, json={"statut": "en_attente"})
    brouillon = await client.patch(f"{BASE}/{dev['id']}/grants/{gid}", headers=p["approbateur"],
                                   json={"statut": "approuvee"})
    assert brouillon.status_code == 409 and brouillon.json()["code"] == "CLIENT_NON_APPROUVABLE"
    croise = await client.patch(f"{BASE}/{test['id']}/grants/{gid}", headers=p["approbateur"],
                                json={"statut": "approuvee"})
    assert croise.status_code == 404
