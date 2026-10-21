"""Studio d'intégration API — suppression sûre, transitions d'alertes, tris et séries de supervision.

Aucun appel réseau. Les tests d'accès réel utilisent une copie jetable (``base_jetable``).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.main import app
from app.models import AuditLog
from app.services.integrations import catalogue as cat
from app.services.integrations import clients as cli
from app.services.integrations import supervision as sup
from tests.test_integration_clients import (  # noqa: F401
    _Transport,
    _archiver_comptes,
    _compte,
    _entete,
    _entite_active,
    _sauter_si_mfa,
    moteur_frais,
)
from tests.test_integration_execution import DEST, EXEC, FOURN, HOTE, SUP, _destination_active, _fournisseur_valide
from tests.test_integration_execution import _profils as _profils_exec
from tests.test_integration_fournisseurs import _creer, _manuelle

CLIENTS = "/api/v1/plateforme/admin/integrations/clients"


def test_suppressions_exigent_la_permission_de_gestion():
    _ops, index = cat.operations_de(app)
    attendues = {
        f"{CLIENTS}/{{client_id}}": "core.admin.integrations.clients.manage",
        f"{FOURN}/{{fournisseur_id}}": "core.admin.integrations.fournisseurs.manage",
        f"{FOURN}/{{fournisseur_id}}/operations/{{operation_id}}": "core.admin.integrations.fournisseurs.manage",
        f"{DEST}/{{destination_id}}": "core.admin.integrations.destinations.manage",
    }
    suppressions = {op.chemin: op for op in index.values() if op.methode == "DELETE" and "/integrations/" in op.chemin}
    assert set(suppressions) == set(attendues)
    for chemin, permission in attendues.items():
        assert suppressions[chemin].permissions == [permission]
        assert suppressions[chemin].authentification == cat.AUTH_LOGIN1
    assert not any(op.methode == "DELETE" and ("/executions" in op.chemin or "/alertes" in op.chemin)
                   for op in index.values())


@pytest.fixture
async def client(moteur_frais, base_jetable):  # noqa: F811
    async with AsyncClient(transport=_Transport(app=app), base_url="http://test") as ac:
        yield ac
    await _archiver_comptes()


async def _audit(action: str, entity_id: str) -> AuditLog | None:
    async with AsyncSessionLocal() as s:
        return await s.scalar(select(AuditLog).where(AuditLog.action == action, AuditLog.entity_id == entity_id))


@pytest.mark.asyncio
async def test_fournisseur_vide_supprime_et_journalise(client: AsyncClient):
    p = await _profils_exec(client)
    f = await _creer(client, p["gestion"])
    bilan = (await client.get(f"{FOURN}/{f['id']}/dependances", headers=p["gestion"])).json()
    assert bilan["supprimable"] is True and bilan["dependances"] == [] and bilan["conditions"] == []
    assert (await client.delete(f"{FOURN}/{f['id']}", headers=p["lecteur"],
                                params={"revision": f["revision"]})).status_code == 403
    assert (await client.delete(f"{FOURN}/{f['id']}", headers=p["gestion"],
                                params={"revision": f["revision"] + 5})).status_code == 409
    res = await client.delete(f"{FOURN}/{f['id']}", headers=p["gestion"], params={"revision": f["revision"]})
    assert res.status_code == 204, res.text
    assert (await client.get(f"{FOURN}/{f['id']}", headers=p["gestion"])).status_code == 404
    trace = await _audit("integration_fournisseur_delete", f["id"])
    assert trace is not None and trace.before_data["nom"] == f["nom"]


@pytest.mark.asyncio
async def test_fournisseur_avec_dependances_bloque_sans_cascade(client: AsyncClient):
    p = await _profils_exec(client)
    ctx = await _fournisseur_valide(client, p["gestion"])
    f = ctx["fournisseur"]
    bilan = (await client.get(f"{FOURN}/{f['id']}/dependances", headers=p["gestion"])).json()
    assert bilan["supprimable"] is False
    assert any("statut" in c for c in bilan["conditions"])
    assert {d["code"] for d in bilan["dependances"]} >= {"operations"}
    assert "Archiver" in bilan["alternative"]
    res = await client.delete(f"{FOURN}/{f['id']}", headers=p["gestion"], params={"revision": f["revision"]})
    assert res.status_code == 409 and res.json()["code"] == "SUPPRESSION_BLOQUEE"
    assert (await client.get(f"{FOURN}/{f['id']}", headers=p["gestion"])).status_code == 200
    ops = (await client.get(f"{FOURN}/{f['id']}/operations", headers=p["gestion"])).json()
    assert ops["total"] >= 1


@pytest.mark.asyncio
async def test_destination_brouillon_supprimable_active_bloquee(client: AsyncClient):
    p = await _profils_exec(client)
    ctx = await _fournisseur_valide(client, p["gestion"])
    fid = ctx["fournisseur"]["id"]
    res = await client.post(DEST, headers=p["gestion"], json={"nom": f"Brouillon {uuid4().hex[:6]}",
                                                             "fournisseur_id": fid, "hotes": [HOTE]})
    _sauter_si_mfa(res)
    brouillon = res.json()
    assert (await client.get(f"{DEST}/{brouillon['id']}/dependances", headers=p["gestion"])).json()["supprimable"]
    res = await client.delete(f"{DEST}/{brouillon['id']}", headers=p["gestion"],
                              params={"revision": brouillon["revision"]})
    assert res.status_code == 204, res.text
    assert await _audit("integration_destination_delete", brouillon["id"]) is not None

    active = await _destination_active(client, p["gestion"], fid)
    bilan = (await client.get(f"{DEST}/{active['id']}/dependances", headers=p["gestion"])).json()
    assert bilan["supprimable"] is False and bilan["conditions"]
    res = await client.delete(f"{DEST}/{active['id']}", headers=p["gestion"], params={"revision": active["revision"]})
    assert res.status_code == 409
    assert (await client.get(f"{DEST}/{active['id']}", headers=p["gestion"])).json()["statut"] == "active"


@pytest.mark.asyncio
async def test_operation_manuelle_referencee_bloquee_libre_supprimee(client: AsyncClient):
    p = await _profils_exec(client)
    f = await _creer(client, p["gestion"], environnement="TEST", url_base="https://api.test.example")
    h = p["gestion"]
    ref = (await client.post(f"{FOURN}/{f['id']}/operations", headers=h,
                             json=_manuelle(chemin="/v1/a", parametres=[], mecanisme_auth="aucun"))).json()
    libre = (await client.post(f"{FOURN}/{f['id']}/operations", headers=h,
                               json=_manuelle(chemin="/v1/b", parametres=[], mecanisme_auth="aucun"))).json()
    res = await client.post(DEST, headers=h, json={"nom": f"D {uuid4().hex[:6]}", "fournisseur_id": f["id"],
                                                   "hotes": [HOTE], "operations": [ref["id"]]})
    _sauter_si_mfa(res)
    assert res.status_code == 201, res.text
    bilan = (await client.get(f"{FOURN}/{f['id']}/operations/{ref['id']}/dependances", headers=h)).json()
    assert bilan["supprimable"] is False and bilan["dependances"][0]["code"] == "destinations"
    res = await client.delete(f"{FOURN}/{f['id']}/operations/{ref['id']}", headers=h,
                              params={"revision": ref["revision"]})
    assert res.status_code == 409
    res = await client.delete(f"{FOURN}/{f['id']}/operations/{libre['id']}", headers=h,
                              params={"revision": libre["revision"]})
    assert res.status_code == 204, res.text
    assert (await client.get(f"{FOURN}/{f['id']}/operations/{libre['id']}", headers=h)).status_code == 404
    histo = (await client.get(f"{FOURN}/{f['id']}/historique", headers=h)).json()
    assert any(i["action"] == "integration_fournisseur_operation_delete" for i in histo["items"])


@pytest.mark.asyncio
async def test_client_brouillon_supprimable_engage_bloque(client: AsyncClient):
    h = await _entete(client, await _compte(cli.P_CLIENTS_VIEW, cli.P_CLIENTS_MANAGE))
    lecteur = await _entete(client, await _compte(cli.P_CLIENTS_VIEW))
    res = await client.post(CLIENTS, headers=h, json={"nom": f"Appli {uuid4().hex[:6]}", "environnement": "DEV"})
    _sauter_si_mfa(res)
    brouillon = res.json()
    assert (await client.delete(f"{CLIENTS}/{brouillon['id']}", headers=lecteur,
                                params={"revision": brouillon["revision"]})).status_code == 403
    res = await client.delete(f"{CLIENTS}/{brouillon['id']}", headers=h, params={"revision": brouillon["revision"]})
    assert res.status_code == 204, res.text
    assert await _audit("integration_client_delete", brouillon["id"]) is not None

    res = await client.post(CLIENTS, headers=h, json={"nom": f"Appli {uuid4().hex[:6]}", "environnement": "DEV"})
    c = res.json()
    c = (await client.patch(f"{CLIENTS}/{c['id']}", headers=h,
                            json={"revision": c["revision"], "statut": "en_preparation"})).json()
    bilan = (await client.get(f"{CLIENTS}/{c['id']}/dependances", headers=h)).json()
    assert bilan["supprimable"] is False and "brouillon" in bilan["conditions"][0]
    res = await client.delete(f"{CLIENTS}/{c['id']}", headers=h, params={"revision": c["revision"]})
    assert res.status_code == 409


@pytest.mark.asyncio
async def test_alertes_transitions_reouverture_historique_et_compteurs(client: AsyncClient):
    p = await _profils_exec(client)
    cle = f"test:{uuid4().hex}"
    async with AsyncSessionLocal() as s:
        a = await sup.ouvrir_alerte(s, "latence", cle, None, None, None, "Latence test", {"duree_ms": 9000})
        await s.commit()
        aid = str(a.id)
    liste = (await client.get(f"{SUP}/alertes", headers=p["gestion"], params={"q": "Latence test"})).json()
    assert liste["compteurs"]["nouvelle"] >= 1
    item = next(x for x in liste["items"] if x["id"] == aid)
    assert item["transitions"] == ["en_cours", "ignoree", "resolue"]
    assert (await client.patch(f"{SUP}/alertes/{aid}", headers=p["lecteur"],
                               json={"statut": "en_cours"})).status_code == 403
    assert (await client.patch(f"{SUP}/alertes/{aid}", headers=p["gestion"],
                               json={"statut": "nouvelle"})).status_code == 409
    assert (await client.patch(f"{SUP}/alertes/{aid}", headers=p["gestion"],
                               json={"statut": "resolue"})).json()["transitions"] == ["nouvelle"]
    res = await client.patch(f"{SUP}/alertes/{aid}", headers=p["gestion"], json={"statut": "en_cours"})
    assert res.status_code == 409 and res.json()["code"] == "TRANSITION_INTERDITE"

    async with AsyncSessionLocal() as s:
        await sup.ouvrir_alerte(s, "latence", cle, None, None, None, "Latence test 2", {})
        await s.commit()
    res = await client.patch(f"{SUP}/alertes/{aid}", headers=p["gestion"], json={"statut": "nouvelle"})
    assert res.status_code == 409 and res.json()["code"] == "ALERTE_DEJA_OUVERTE"

    histo = (await client.get(f"{SUP}/alertes/{aid}/historique", headers=p["lecteur"])).json()
    assert [i["apres"] for i in histo["items"]] == ["Résolue"]


@pytest.mark.asyncio
async def test_tris_recherche_et_series(client: AsyncClient):
    p = await _profils_exec(client)
    h = p["lecteur"]
    for params in ({"tri": "duree_ms", "ordre": "asc"}, {"q": "aucune-correspondance-xyz"}):
        res = await client.get(EXEC, headers=h, params=params)
        _sauter_si_mfa(res)
        assert res.status_code == 200, res.text
    assert (await client.get(EXEC, headers=h, params={"q": "aucune-correspondance-xyz"})).json()["total"] == 0
    assert (await client.get(EXEC, headers=h, params={"tri": "hote"})).status_code == 422
    dests = await client.get(DEST, headers=h, params={"tri": "nom", "ordre": "asc"})
    assert dests.status_code == 200
    for d in dests.json()["items"]:
        assert "fournisseur_nom" in d and "nb_operations" in d
    tableau = (await client.get(SUP, headers=h)).json()
    assert isinstance(tableau["series"], list) and isinstance(tableau["par_fournisseur"], list)
    assert sum(s["total"] for s in tableau["series"]) == tableau["total"]
