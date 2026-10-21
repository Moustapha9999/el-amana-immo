"""Phases 5 et 6 — destinations, exécution contrôlée, supervision. HTTP simulé uniquement."""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import select

from app.core.exceptions import AppError
from app.data.plateforme_catalogue import CORE_ADMIN_PERMISSIONS, FUNCTIONAL_PERMISSIONS, ROLE_PERMISSIONS
from app.db.base import Base
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models import AuditLog
from app.schemas.integration_execution import ApercuTestIn, DestinationCreation, ExecuterTestIn
from app.services.integrations import catalogue as cat
from app.services.integrations import destinations as dest
from app.services.integrations import executeur as exe
from app.services.integrations import supervision as sup
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
from tests.test_integration_fournisseurs import _creer, _manuelle

FOURN = "/api/v1/plateforme/admin/integrations/fournisseurs"
DEST = "/api/v1/plateforme/admin/integrations/destinations"
TESTS = "/api/v1/plateforme/admin/integrations/tests"
EXEC = "/api/v1/plateforme/admin/integrations/executions"
SUP = "/api/v1/plateforme/admin/integrations/supervision"
HOTE = "api.test.example"
PERMS_DEST = (dest.P_VIEW, dest.P_MANAGE, dest.P_APPROVE)
PERMS_TEST = (exe.P_VIEW, exe.P_EXECUTE)
PERMS_SUP = (sup.P_VIEW, sup.P_MANAGE, sup.P_EXPORT)
TOUTES = PERMS_DEST + PERMS_TEST + PERMS_SUP
RACINE = Path(__file__).resolve().parents[1]


# --- Permissions, routes, modèle -----------------------------------------------------------


def test_permissions_declarees_sans_attribution_ni_suffixe_admin():
    core_admin = {code for code, _l, _m in CORE_ADMIN_PERMISSIONS}
    fonctionnelles = {code for code, _l, _m in FUNCTIONAL_PERMISSIONS}
    for code in TOUTES:
        assert code in core_admin and code in fonctionnelles
        assert not code.endswith(".admin")
        assert not any(code in perms for perms in ROLE_PERMISSIONS.values())


@pytest.mark.parametrize("have", [
    {"core.admin.access"}, {"core.admin.integrations.view"},
    {"core.admin.integrations.fournisseurs.manage"}, {dest.P_MANAGE}, {exe.P_VIEW},
])
def test_aucun_joker_ne_couvre_execution_ni_approbation(have):
    assert not user_has_permission_codes(have, exe.P_EXECUTE)
    assert not user_has_permission_codes(have, dest.P_APPROVE)


def test_routes_login1_permissions_dediees():
    _ops, index = cat.operations_de(app)
    dests = [op for op in index.values() if op.chemin.startswith(DEST)]
    tests = [op for op in index.values() if op.chemin.startswith(TESTS)]
    execs = [op for op in index.values() if op.chemin.startswith(EXEC)]
    superv = [op for op in index.values() if op.chemin.startswith(SUP)]
    assert len(dests) == 9 and len(tests) == 2 and len(execs) == 2 and len(superv) == 5
    for op in dests + tests + execs + superv:
        assert op.authentification == cat.AUTH_LOGIN1, op.operation_id
        assert op.disponibilite == cat.DISPO_EXCLUE
    assert set(next(o for o in dests if o.chemin.endswith("/statut")).permissions) == {dest.P_MANAGE, dest.P_APPROVE}


def test_aucune_colonne_de_secret():
    for nom in ("integration_destinations", "integration_executions", "integration_alertes"):
        for colonne in Base.metadata.tables[nom].columns:
            assert not __import__("re").search(r"secret|password|token|jeton|api_key|credential|hash", colonne.name)


def test_migration_additive_et_reversible():
    source = (RACINE / "alembic" / "versions" / "20261021_integrations_03_execution.py").read_text(encoding="utf-8")
    upgrade, downgrade = source.split("def downgrade", 1)
    assert 'down_revision: Union[str, None] = "20261021_integrations_02"' in source
    assert 'retour_arriere = "compatible"' in source
    assert "drop_" not in upgrade and "alter_column" not in upgrade
    for table in ("integration_destinations", "integration_executions", "integration_alertes"):
        assert f'op.drop_table("{table}")' in downgrade


def test_schemas_refusent_url_arbitraire_et_secrets():
    fid = uuid4()
    with pytest.raises(ValidationError):
        ExecuterTestIn(
            fournisseur_id=fid, operation_id=fid, destination_id=fid, confirmation=True,
            url="https://evil.example/x",
        )
    with pytest.raises(ValidationError):
        DestinationCreation(nom="X", fournisseur_id=fid, hotes=["127.0.0.1"])
    with pytest.raises(ValidationError):
        ApercuTestIn(
            fournisseur_id=fid, operation_id=fid, destination_id=fid,
            parametres_requete={"q": "Bearer abcdefghijklmnop"},
        )


# --- Accès réel (copie jetable + HTTP simulé) ----------------------------------------------


@pytest.fixture
async def client(moteur_frais, base_jetable):  # noqa: F811
    exe.brancher_test(transport=None, getaddrinfo=None, quota=None)
    async with AsyncClient(transport=_Transport(app=app), base_url="http://test") as ac:
        yield ac
    exe.brancher_test()
    await _archiver_comptes()


async def _profils(client: AsyncClient) -> dict:
    return {
        "gestion": await _entete(client, await _compte(dest.P_VIEW, dest.P_MANAGE, dest.P_APPROVE,
                                                       exe.P_VIEW, exe.P_EXECUTE, sup.P_VIEW, sup.P_MANAGE, sup.P_EXPORT,
                                                       "core.admin.integrations.fournisseurs.view",
                                                       "core.admin.integrations.fournisseurs.manage",
                                                       "core.admin.integrations.fournisseurs.validate")),
        "lecteur": await _entete(client, await _compte(dest.P_VIEW, exe.P_VIEW, sup.P_VIEW,
                                                       "core.admin.integrations.fournisseurs.view")),
        "executeur": await _entete(client, await _compte(exe.P_VIEW, exe.P_EXECUTE,
                                                         dest.P_VIEW,
                                                         "core.admin.integrations.fournisseurs.view")),
    }


async def _fournisseur_valide(client, h) -> dict:
    f = await _creer(client, h, environnement="TEST", url_base="https://api.test.example")
    fid = f["id"]
    entite = await _entite_active()
    await client.patch(f"{FOURN}/{fid}", headers=h, json={"revision": f["revision"], "org_entite_id": entite})
    op = await client.post(f"{FOURN}/{fid}/operations", headers=h, json=_manuelle(
        chemin="/v1/status", parametres=[], mecanisme_auth="aucun", nom="Statut",
    ))
    assert op.status_code == 201, op.text
    f = (await client.get(f"{FOURN}/{fid}", headers=h)).json()
    assert (await client.post(f"{FOURN}/{fid}/statut", headers=h, json={"revision": f["revision"], "statut": "a_valider"})).status_code == 200
    f = (await client.get(f"{FOURN}/{fid}", headers=h)).json()
    res = await client.post(f"{FOURN}/{fid}/statut", headers=h, json={"revision": f["revision"], "statut": "valide"})
    assert res.status_code == 200, res.text
    return {"fournisseur": res.json(), "operation": op.json()}


async def _destination_active(client, h, fid, **champs) -> dict:
    corps = {"nom": f"Dest {uuid4().hex[:6]}", "fournisseur_id": fid, "hotes": [HOTE], **champs}
    res = await client.post(DEST, headers=h, json=corps)
    _sauter_si_mfa(res)
    assert res.status_code == 201, res.text
    d = res.json()
    res = await client.post(f"{DEST}/{d['id']}/statut", headers=h, json={"revision": d["revision"], "statut": "a_valider"})
    assert res.status_code == 200, res.text
    d = res.json()
    res = await client.post(f"{DEST}/{d['id']}/statut", headers=h, json={"revision": d["revision"], "statut": "active"})
    assert res.status_code == 200, res.text
    return res.json()


def _pub_dns(host, *a, **k):
    if host in {HOTE, "api.test.example"}:
        return [(2, 1, 6, "", ("8.8.8.8", 0))]
    raise AssertionError(f"DNS inattendu: {host}")


def _transport(handler):
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_sans_authentification_et_login2_refuses(client: AsyncClient):
    did, eid, aid = uuid4(), uuid4(), uuid4()
    for methode, url in [
        ("GET", DEST), ("POST", DEST), ("GET", f"{DEST}/{did}"),
        ("POST", f"{TESTS}/apercu"), ("POST", f"{TESTS}/executer"),
        ("GET", EXEC), ("GET", f"{EXEC}/{eid}"),
        ("GET", SUP), ("GET", f"{SUP}/alertes"), ("GET", f"{SUP}/export"),
        ("PATCH", f"{SUP}/alertes/{aid}"),
    ]:
        assert (await client.request(methode, url)).status_code == 401, (methode, url)
    admin = await _compte(superuser=True)
    plateforme = await _entete(client, admin)
    module = await client.post("/api/v1/auth/modules/immobilisations/login",
                               json={"email": admin, "password": _MDP}, headers=plateforme)
    if module.status_code != 200:
        pytest.skip("Login module indisponible")
    login2 = {"Authorization": f"Bearer {module.json()['access_token']}"}
    assert (await client.get(DEST, headers=login2)).status_code == 401
    assert (await client.post(f"{TESTS}/executer", headers=login2, json={
        "fournisseur_id": str(did), "operation_id": str(did), "destination_id": str(did), "confirmation": True,
    })).status_code == 401


@pytest.mark.asyncio
async def test_permissions_insuffisantes(client: AsyncClient):
    p = await _profils(client)
    autres = await _entete(client, await _compte("core.admin.access", "core.admin.integrations.view"))
    res = await client.get(DEST, headers=autres)
    _sauter_si_mfa(res)
    assert res.status_code == 403
    assert (await client.post(f"{TESTS}/executer", headers=p["lecteur"], json={
        "fournisseur_id": str(uuid4()), "operation_id": str(uuid4()),
        "destination_id": str(uuid4()), "confirmation": True,
    })).status_code == 403
    assert (await client.get(SUP, headers=p["executeur"])).status_code == 403


@pytest.mark.asyncio
async def test_sauvegarde_et_apercu_sans_appel(client: AsyncClient):
    appels = []

    def handler(request: httpx.Request) -> httpx.Response:
        appels.append(str(request.url))
        return httpx.Response(200, json={"ok": True})

    exe.brancher_test(transport=_transport(handler), getaddrinfo=_pub_dns, quota=lambda *_: None)
    p = await _profils(client)
    ctx = await _fournisseur_valide(client, p["gestion"])
    d = await _destination_active(client, p["gestion"], ctx["fournisseur"]["id"])
    apercu = await client.post(f"{TESTS}/apercu", headers=p["executeur"], json={
        "fournisseur_id": ctx["fournisseur"]["id"], "operation_id": ctx["operation"]["id"],
        "destination_id": d["id"],
    })
    assert apercu.status_code == 200, apercu.text
    body = apercu.json()
    assert body["url"].startswith("https://api.test.example/v1/status")
    assert appels == []
    assert "Aucun secret" in body["avertissement"]


@pytest.mark.asyncio
async def test_execution_succes_simule_et_supervision(client: AsyncClient, caplog):
    caplog.set_level(logging.DEBUG)
    vus = []

    def handler(request: httpx.Request) -> httpx.Response:
        vus.append({
            "host": request.url.host, "path": request.url.path,
            "auth": request.headers.get("authorization"),
            "cookie": request.headers.get("cookie"),
        })
        return httpx.Response(200, headers={"Content-Type": "application/json", "Set-Cookie": "sid=abc"},
                              content=b'{"ok":true,"token":"Bearer eyJhbGciOiJIUzI1NiJ9.aaa.bbb"}')

    exe.brancher_test(transport=_transport(handler), getaddrinfo=_pub_dns, quota=lambda *_: None)
    p = await _profils(client)
    ctx = await _fournisseur_valide(client, p["gestion"])
    d = await _destination_active(client, p["gestion"], ctx["fournisseur"]["id"])
    corps = {
        "fournisseur_id": ctx["fournisseur"]["id"], "operation_id": ctx["operation"]["id"],
        "destination_id": d["id"], "confirmation": True,
    }
    res = await client.post(f"{TESTS}/executer", headers=p["executeur"], json=corps)
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["statut"] == "succes" and out["http_status"] == 200 and out["correlation_id"]
    assert out["reponse"]["extrait"] and "<masqué>" in out["reponse"]["extrait"]
    assert all(e["nom"].lower() != "set-cookie" for e in out["reponse"]["entetes"])
    assert vus and vus[0]["auth"] is None and vus[0]["cookie"] is None
    assert vus[0]["host"] == "8.8.8.8" and vus[0]["path"] == "/v1/status"

    hist = (await client.get(EXEC, headers=p["lecteur"], params={"destination_id": d["id"]})).json()
    assert hist["total"] == 1 and hist["items"][0]["id"] == out["id"]
    ligne = hist["items"][0]
    assert ligne["fournisseur_nom"] == ctx["fournisseur"]["nom"] and ligne["destination_nom"] == d["nom"]
    assert ligne["environnement"] == "TEST" and "operation_nom" in ligne
    filtre = (await client.get(EXEC, headers=p["lecteur"], params={
        "destination_id": d["id"], "operation_id": ctx["operation"]["id"], "statut": "timeout",
    })).json()
    assert filtre["total"] == 0
    dash = (await client.get(SUP, headers=p["gestion"], params={"destination_id": d["id"]})).json()
    assert dash["total"] == 1 and dash["taux_succes"] == 1 and dash["sondes_automatiques"] is False
    assert "Aucune donnée" not in dash["taux_libelle"]
    vide = (await client.get(SUP, headers=p["gestion"], params={
        "depuis": "2000-01-01T00:00:00Z", "jusqua": "2000-01-02T00:00:00Z",
    })).json()
    assert vide["total"] == 0 and vide["taux_succes"] is None and vide["taux_libelle"] == "Aucune donnée"

    export = await client.get(f"{SUP}/export", headers=p["gestion"], params={"destination_id": d["id"]})
    assert export.status_code == 200 and "correlation" in export.text
    assert "fournisseur" in export.text.splitlines()[0] and ctx["fournisseur"]["nom"] in export.text
    export_filtre = await client.get(f"{SUP}/export", headers=p["gestion"], params={
        "destination_id": d["id"], "statut": "timeout", "operation_id": ctx["operation"]["id"],
    })
    assert export_filtre.status_code == 200 and len(export_filtre.text.strip().splitlines()) == 1
    assert (await client.get(f"{SUP}/export", headers=p["lecteur"])).status_code == 403
    assert "Bearer eyJ" not in export.text + caplog.text + str(out)
    async with AsyncSessionLocal() as s:
        audits = (await s.scalars(select(AuditLog).where(AuditLog.action == "integration_test_execute"))).all()
    assert any(a.after_data and a.after_data.get("correlation_id") == out["correlation_id"] for a in audits)


@pytest.mark.asyncio
async def test_refus_destination_operation_methode_secret(client: AsyncClient):
    exe.brancher_test(transport=_transport(lambda r: httpx.Response(200)), getaddrinfo=_pub_dns, quota=lambda *_: None)
    p = await _profils(client)
    ctx = await _fournisseur_valide(client, p["gestion"])
    brouillon = (await client.post(DEST, headers=p["gestion"], json={
        "nom": "Brouillon", "fournisseur_id": ctx["fournisseur"]["id"], "hotes": [HOTE],
    })).json()
    payload = {
        "fournisseur_id": ctx["fournisseur"]["id"], "operation_id": ctx["operation"]["id"],
        "destination_id": brouillon["id"], "confirmation": True,
    }
    res = await client.post(f"{TESTS}/executer", headers=p["executeur"], json=payload)
    assert res.status_code == 422 and res.json()["code"] == "DESTINATION_INACTIVE"

    secret = await client.post(f"{FOURN}/{ctx['fournisseur']['id']}/operations", headers=p["gestion"], json=_manuelle(
        chemin="/v1/secret", parametres=[], mecanisme_auth="http_bearer", nom="Secret",
    ))
    # fournisseur validé = verrouillé → opération refusée
    assert secret.status_code == 409

    autre = await _creer(client, p["gestion"], environnement="TEST", nom=f"Autre {uuid4().hex[:6]}")
    d = await _destination_active(client, p["gestion"], ctx["fournisseur"]["id"])
    res = await client.post(f"{TESTS}/executer", headers=p["executeur"], json={
        "fournisseur_id": autre["id"], "operation_id": ctx["operation"]["id"],
        "destination_id": d["id"], "confirmation": True,
    })
    assert res.status_code in (404, 422)


@pytest.mark.asyncio
async def test_ssrf_prive_redirection_timeout_volume_quota(client: AsyncClient):
    p = await _profils(client)
    ctx = await _fournisseur_valide(client, p["gestion"])
    d = await _destination_active(client, p["gestion"], ctx["fournisseur"]["id"])
    base = {
        "fournisseur_id": ctx["fournisseur"]["id"], "operation_id": ctx["operation"]["id"],
        "destination_id": d["id"], "confirmation": True,
    }

    def prive(host, *a, **k):
        return [(2, 1, 6, "", ("169.254.169.254", 0))]

    exe.brancher_test(transport=_transport(lambda r: httpx.Response(200)), getaddrinfo=prive, quota=lambda *_: None)
    res = await client.post(f"{TESTS}/executer", headers=p["executeur"], json=base)
    assert res.status_code == 200 and res.json()["statut"] == "refuse_securite"

    def mixte(host, *a, **k):
        return [(2, 1, 6, "", ("8.8.8.8", 0)), (2, 1, 6, "", ("10.0.0.1", 0))]

    exe.brancher_test(transport=_transport(lambda r: httpx.Response(200)), getaddrinfo=mixte, quota=lambda *_: None)
    res = await client.post(f"{TESTS}/executer", headers=p["executeur"], json=base)
    assert res.json()["statut"] == "refuse_securite"

    cibles = []

    def redir(request: httpx.Request) -> httpx.Response:
        cibles.append(str(request.url))
        return httpx.Response(302, headers={"Location": "https://169.254.169.254/meta"})

    exe.brancher_test(transport=_transport(redir), getaddrinfo=_pub_dns, quota=lambda *_: None)
    res = await client.post(f"{TESTS}/executer", headers=p["executeur"], json=base)
    assert res.json()["statut"] == "redirection_refusee"
    assert len(cibles) == 1 and "169.254" not in cibles[0]

    class TimeoutT(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            raise httpx.ReadTimeout("slow")

    exe.brancher_test(transport=TimeoutT(), getaddrinfo=_pub_dns, quota=lambda *_: None)
    res = await client.post(f"{TESTS}/executer", headers=p["executeur"], json=base)
    assert res.json()["statut"] == "timeout"

    class TlsT(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            raise httpx.ConnectError("certificate verify failed")

    exe.brancher_test(transport=TlsT(), getaddrinfo=_pub_dns, quota=lambda *_: None)
    res = await client.post(f"{TESTS}/executer", headers=p["executeur"], json=base)
    assert res.json()["statut"] == "tls"

    class ProtoT(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            raise httpx.RemoteProtocolError("malformed")

    exe.brancher_test(transport=ProtoT(), getaddrinfo=_pub_dns, quota=lambda *_: None)
    res = await client.post(f"{TESTS}/executer", headers=p["executeur"], json=base)
    assert res.json()["statut"] == "reponse_invalide"

    exe.brancher_test(
        transport=_transport(lambda r: httpx.Response(200, content=b"x" * (70 * 1024))),
        getaddrinfo=_pub_dns, quota=lambda *_: None,
    )
    res = await client.post(f"{TESTS}/executer", headers=p["executeur"], json=base)
    assert res.json()["statut"] == "trop_volumineux"

    def trop(*_a):
        raise AppError("Quota de tests dépassé", 429, code="QUOTA")

    exe.brancher_test(transport=_transport(lambda r: httpx.Response(200)), getaddrinfo=_pub_dns, quota=trop)
    res = await client.post(f"{TESTS}/executer", headers=p["executeur"], json=base)
    assert res.json()["statut"] == "quota"


@pytest.mark.asyncio
async def test_alertes_dedup_et_transitions(client: AsyncClient):
    def ko(_r):
        return httpx.Response(503, text="down")

    exe.brancher_test(transport=_transport(ko), getaddrinfo=_pub_dns, quota=lambda *_: None)
    p = await _profils(client)
    ctx = await _fournisseur_valide(client, p["gestion"])
    d = await _destination_active(client, p["gestion"], ctx["fournisseur"]["id"])
    corps = {
        "fournisseur_id": ctx["fournisseur"]["id"], "operation_id": ctx["operation"]["id"],
        "destination_id": d["id"], "confirmation": True,
    }
    for _ in range(3):
        assert (await client.post(f"{TESTS}/executer", headers=p["executeur"], json=corps)).json()["statut"] == "http_erreur"
    alertes = (await client.get(f"{SUP}/alertes", headers=p["gestion"], params={"type": "echecs_consecutifs"})).json()
    assert alertes["total"] >= 1
    a = alertes["items"][0]
    assert a["occurences"] >= 1
    assert a["niveau"] == "elevee" and "échec" in (a["regle"] or "")
    par_niveau = (await client.get(f"{SUP}/alertes", headers=p["gestion"], params={"niveau": "elevee"})).json()
    assert any(x["id"] == a["id"] for x in par_niveau["items"])
    assert all(x["niveau"] == "elevee" for x in par_niveau["items"])
    info = (await client.get(f"{SUP}/alertes", headers=p["gestion"], params={"niveau": "info", "type": "echecs_consecutifs"})).json()
    assert info["total"] == 0
    passe = (await client.get(f"{SUP}/alertes", headers=p["gestion"], params={
        "type": "echecs_consecutifs", "jusqua": "2000-01-01T00:00:00Z",
    })).json()
    assert passe["total"] == 0
    res = await client.patch(f"{SUP}/alertes/{a['id']}", headers=p["gestion"], json={"statut": "en_cours"})
    assert res.json()["statut"] == "en_cours"
    res = await client.patch(f"{SUP}/alertes/{a['id']}", headers=p["gestion"], json={"statut": "resolue"})
    assert res.json()["statut"] == "resolue"
    exe.brancher_test(transport=_transport(ko), getaddrinfo=_pub_dns, quota=lambda *_: None)
    await client.post(f"{TESTS}/executer", headers=p["executeur"], json=corps)
    encore = (await client.get(f"{SUP}/alertes", headers=p["gestion"], params={"type": "echecs_consecutifs"})).json()
    ouvertes = [x for x in encore["items"] if x["statut"] in ("nouvelle", "en_cours") and x.get("destination_id") == d["id"]]
    assert len(ouvertes) == 1

    suspendue = await client.post(f"{DEST}/{d['id']}/statut", headers=p["gestion"],
                                  json={"revision": d["revision"], "statut": "suspendue", "motif": "Revue"})
    assert suspendue.status_code == 200
    dest_al = (await client.get(f"{SUP}/alertes", headers=p["gestion"], params={"type": "destination_suspendue"})).json()
    assert dest_al["total"] >= 1


@pytest.mark.asyncio
async def test_hote_refuse_a_la_creation(client: AsyncClient):
    p = await _profils(client)
    ctx = await _fournisseur_valide(client, p["gestion"])
    for hote in ("localhost", "127.0.0.1", "10.0.0.1", "metadata.google.internal"):
        res = await client.post(DEST, headers=p["gestion"], json={
            "nom": f"X {hote}", "fournisseur_id": ctx["fournisseur"]["id"], "hotes": [hote],
        })
        assert res.status_code == 422, hote
    res = await client.post(DEST, headers=p["gestion"], json={
        "nom": "Port", "fournisseur_id": ctx["fournisseur"]["id"], "hotes": [HOTE], "ports": [8080],
    })
    assert res.status_code == 422
