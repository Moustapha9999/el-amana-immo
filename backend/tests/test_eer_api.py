"""API EER — permissions (403), périmètre agence, workflow, révisions (409), immuabilité, OpenAPI.

Exécuté UNIQUEMENT sur une copie de base (ex. bea_digital_eer_test) : migrations eer_* appliquées,
référentiel chargé. Le test ouvre le module EER (statut actif) et crée des comptes de test
``*@eer-test.el-amana.mr`` sur cette copie ; il est ignoré sur la base réelle (tables EER absentes
ou base nommée bea_digital).
"""

from __future__ import annotations

import random
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.security import get_password_hash
from app.data.plateforme_catalogue import ACC_ESPACE_CODE, EER_MODULE_CODE
from app.db.session import get_db
from app.main import app
from app.models import Agence, PlateformeEspace, PlateformeModule, Role, User
from app.services.plateforme_access_service import PlateformeAccessService

MOT_DE_PASSE = "Eer-Test-Api-2026!"
COMPTES = {
    "charge_a": ("eer.charge", 0),
    "charge_b": ("eer.charge", 1),
    "analyste": ("eer.analyste", None),
    "superviseur": ("eer.superviseur", None),
    "sans_droit": (None, 0),
}


def _email(nom: str) -> str:
    return f"{nom}@eer-test.el-amana.mr"


@pytest.fixture
async def env():
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    async with engine.connect() as conn:
        base = await conn.scalar(text("SELECT current_database()"))
        pret = await conn.scalar(text("SELECT to_regclass('public.eer_dossiers') IS NOT NULL"))
        regles = pret and await conn.scalar(text("SELECT count(*) FROM eer_checklist_regles"))
    if not regles or base == "bea_digital":
        await engine.dispose()
        pytest.skip("API EER : copie de base avec migrations eer_* requise (jamais la base réelle)")
    fabrique = async_sessionmaker(engine, expire_on_commit=False)

    async with fabrique() as s:
        await PlateformeAccessService(s).ensure_catalogue()
        agences = list((await s.execute(select(Agence).where(Agence.is_active.is_(True))
                                        .order_by(Agence.code).limit(2))).scalars())
        if len(agences) < 2:
            await engine.dispose()
            pytest.skip("Deux agences actives nécessaires")
        module = await s.scalar(select(PlateformeModule).where(PlateformeModule.code == EER_MODULE_CODE))
        espace = await s.scalar(select(PlateformeEspace).where(PlateformeEspace.code == ACC_ESPACE_CODE))
        module.statut, module.is_active = "actif", True
        ids = {}
        for nom, (role_code, rang) in COMPTES.items():
            user = await s.scalar(select(User).where(User.email == _email(nom)))
            if user is None:
                user = User(email=_email(nom), full_name=f"Test EER {nom}", is_superuser=False, is_active=True,
                            hashed_password=get_password_hash(MOT_DE_PASSE))
                s.add(user)
                await s.flush()
            user.agence_id = agences[rang].id if rang is not None else None
            params = {"u": user.id, "e": espace.id, "m": module.id}
            await s.execute(text("INSERT INTO user_espace_acces (user_id, espace_id) VALUES (:u, :e) "
                                 "ON CONFLICT DO NOTHING"), params)
            await s.execute(text("INSERT INTO user_module_acces (user_id, module_id) VALUES (:u, :m) "
                                 "ON CONFLICT DO NOTHING"), params)
            if role_code:
                role = await s.scalar(select(Role).where(Role.code == role_code))
                await s.execute(text("INSERT INTO user_roles (user_id, role_id) VALUES (:u, :r) "
                                     "ON CONFLICT DO NOTHING"), {"u": user.id, "r": role.id})
            ids[nom] = user.id
        await s.commit()

    async def _get_db():
        async with fabrique() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _get_db
    ip = f"10.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           headers={"X-Forwarded-For": ip}) as client:
        yield {"client": client, "ids": ids, "agences": [a.id for a in agences]}
    app.dependency_overrides.pop(get_db, None)
    await engine.dispose()


async def _module(client: AsyncClient, nom: str) -> dict[str, str]:
    login = await client.post("/api/v1/auth/login", json={"email": _email(nom), "password": MOT_DE_PASSE})
    assert login.status_code == 200, login.text
    plateforme = {"Authorization": f"Bearer {login.json()['access_token']}"}
    mod = await client.post(f"/api/v1/auth/modules/{EER_MODULE_CODE}/login",
                            json={"email": _email(nom), "password": MOT_DE_PASSE}, headers=plateforme)
    assert mod.status_code == 200, mod.text
    return {"Authorization": f"Bearer {mod.json()['access_token']}"}


def _nouveau(agence_id, nom: str = "Client API", **client_role) -> dict:
    return {"agence_id": str(agence_id), "type_client": "PP", "profil": "SALARIE",
            "client": {"nom": nom, "pp": {"prenom": "Test"},
                       "piece": {"type": "NNI", "numero": f"API-{uuid.uuid4().hex[:10]}",
                                 "date_expiration": "2099-01-01"}},
            "client_role": {"ppe": False, "fatca_indice": False, **client_role},
            "dossier": {"risque_lbcft": "FAIBLE", "tranche_mouvement_code": "PP_LT_50K"}}


def _valeur(chemin: str, user_id) -> object:
    feuille = chemin.rsplit(".", 1)[-1]
    if feuille in ("gestionnaire_id", "responsable_agence_id"):
        return str(user_id)
    if feuille.startswith("date"):
        return "2020-01-15"
    if feuille in ("ppe", "fatca_indice", "impact_rse"):
        return False
    return {"nombre_signataires": 1, "type_signature": "UNIQUE", "risque_lbcft": "FAIBLE",
            "tranche_mouvement": "PP_LT_50K", "salaire_net": 1000, "sexe": "M", "email": "contact@exemple.mr",
            "situation_matrimoniale": "Célibataire"}.get(feuille, "Renseigné")


# --- Permissions ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_permissions_403_et_authentification(env):
    c, agences = env["client"], env["agences"]
    sans = await _module(c, "sans_droit")
    assert (await c.get("/api/v1/eer/dossiers", headers=sans)).status_code == 403
    assert (await c.post("/api/v1/eer/dossiers", json=_nouveau(agences[0]), headers=sans)).status_code == 403

    # Session plateforme seule (pas de Login 2 module) : refusée.
    login = await c.post("/api/v1/auth/login", json={"email": _email("charge_a"), "password": MOT_DE_PASSE})
    plateforme = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert (await c.get("/api/v1/eer/dossiers", headers=plateforme)).status_code == 401

    charge = await _module(c, "charge_a")
    cree = await c.post("/api/v1/eer/dossiers", json=_nouveau(agences[0]), headers=charge)
    assert cree.status_code == 201, cree.text
    dossier = cree.json()
    did, rev = dossier["id"], dossier["revision"]
    assert "SOUMIS" in dossier["transitions_possibles"]

    for chemin, corps in (
        (f"/api/v1/eer/dossiers/{did}", {"revision": rev, "champs": [{"chemin": "dossier.origine_fonds",
                                                                      "valeur": "X"}]}),
        (f"/api/v1/eer/dossiers/{did}/submit", {"revision": rev}),
    ):
        methode = c.patch if chemin.endswith(did) else c.post
        res = await methode(chemin, json=corps, headers=sans)
        assert res.status_code == 403, res.text
    # Le chargé n'a ni eer.avis, ni eer.validate, ni eer.assign.
    for action, corps in (("avis", {"revision": rev, "favorable": True}), ("validate", {"revision": rev}),
                          ("assign", {"revision": rev, "analyste_id": str(env["ids"]["analyste"])})):
        res = await c.post(f"/api/v1/eer/dossiers/{did}/{action}", json=corps, headers=charge)
        assert res.status_code == 403, (action, res.text)
        assert res.json()["code"] == "PERMISSION_DENIED"
    perim = (await c.get("/api/v1/eer/perimetre", headers=charge)).json()
    assert perim["perimetre"] == "AGENCE" and perim["capacites"]["avis"] is False


# --- Périmètre agence ---------------------------------------------------------------------

@pytest.mark.asyncio
async def test_perimetre_agence_a_ne_voit_pas_b(env):
    c, (agence_a, agence_b) = env["client"], env["agences"]
    charge_a, charge_b = await _module(c, "charge_a"), await _module(c, "charge_b")
    analyste = await _module(c, "analyste")
    da = (await c.post("/api/v1/eer/dossiers", json=_nouveau(agence_a, "Client agence A"), headers=charge_a)).json()
    db_ = (await c.post("/api/v1/eer/dossiers", json=_nouveau(agence_b, "Client agence B"), headers=charge_b)).json()

    liste_a = (await c.get("/api/v1/eer/dossiers?size=100", headers=charge_a)).json()
    ids_a = {d["id"] for d in liste_a["items"]}
    assert da["id"] in ids_a and db_["id"] not in ids_a
    assert all(d["agence_id"] == str(agence_a) for d in liste_a["items"])
    # Même en filtrant explicitement sur l'agence B, le chargé A ne voit rien.
    forcee = (await c.get(f"/api/v1/eer/dossiers?agence_id={agence_b}", headers=charge_a)).json()
    assert forcee["total"] == 0

    assert (await c.get(f"/api/v1/eer/dossiers/{db_['id']}", headers=charge_a)).status_code == 404
    for suffixe in ("checklist", "versions", "history", "anomalies", "fiches"):
        assert (await c.get(f"/api/v1/eer/dossiers/{db_['id']}/{suffixe}", headers=charge_a)).status_code == 404
    patch = await c.patch(f"/api/v1/eer/dossiers/{db_['id']}", headers=charge_a, json={
        "revision": db_["revision"], "champs": [{"chemin": "dossier.origine_fonds", "valeur": "Pirate"}]})
    assert patch.status_code == 404
    soumis = await c.post(f"/api/v1/eer/dossiers/{db_['id']}/submit", headers=charge_a,
                          json={"revision": db_["revision"]})
    assert soumis.status_code == 404
    hors = await c.post("/api/v1/eer/dossiers", json=_nouveau(agence_b), headers=charge_a)
    assert hors.status_code == 403 and hors.json()["code"] == "EER_ACCES_REFUSE"

    tous = {d["id"] for d in (await c.get("/api/v1/eer/dossiers?size=100", headers=analyste)).json()["items"]}
    assert {da["id"], db_["id"]} <= tous
    tdb = (await c.get("/api/v1/eer/dashboard", headers=charge_a)).json()
    assert [a["code"] for a in tdb["par_agence"]] == [liste_a["items"][0]["agence_code"]]
    assert tdb["total"] == liste_a["total"]

    assert [a["id"] for a in (await c.get("/api/v1/eer/agences", headers=charge_a)).json()] == [str(agence_a)]
    assert len((await c.get("/api/v1/eer/agences", headers=analyste)).json()) >= 2
    profils = (await c.get("/api/v1/eer/referentiels?domaine=PROFIL", headers=charge_a)).json()
    assert next(p for p in profils if p["code"] == "SALARIE")["parent_code"] == "PP"


# --- Workflow complet par l'API -------------------------------------------------------------

async def _completer_fiches(c, headers, did, rev, user_id) -> int:
    for _ in range(5):
        fiches = (await c.get(f"/api/v1/eer/dossiers/{did}/fiches", headers=headers)).json()
        champs = [{"chemin": ch["chemin"], "valeur": _valeur(ch["chemin"], user_id),
                   "dossier_partie_id": cle.split(":", 1)[1] if ":" in cle else None}
                  for cle, liste in fiches.items() for ch in liste if ch["bloquant"]]
        if not champs:
            return rev
        res = await c.patch(f"/api/v1/eer/dossiers/{did}", headers=headers, json={"revision": rev, "champs": champs})
        assert res.status_code == 200, res.text
        rev = res.json()["revision"]
    raise AssertionError("Fiches incomplètes")


@pytest.mark.asyncio
async def test_workflow_complet_api_complement_avis_et_conflit(env):
    c, ids = env["client"], env["ids"]
    charge, analyste, sup = (await _module(c, "charge_a"), await _module(c, "analyste"),
                             await _module(c, "superviseur"))
    url = "/api/v1/eer/dossiers"
    d = (await c.post(url, json=_nouveau(env["agences"][0], "Client cycle API", ppe=True,
                                         ppe_motif="Fonction publique"), headers=charge)).json()
    did, rev = d["id"], d["revision"]
    assert d["avis_requis"] is True

    async def post(chemin, headers, **corps):
        nonlocal rev
        res = await c.post(f"{url}/{did}/{chemin}", headers=headers, json={"revision": rev, **corps})
        if res.status_code == 200:
            rev = res.json()["revision"]
        return res

    # Transition interdite (validation d'un brouillon) → 400, rien ne change.
    assert (await post("validate", sup)).status_code == 400
    # Concurrence : deux soumissions depuis la même révision → la seconde reçoit 409.
    rev0 = rev
    assert (await post("submit", charge)).status_code == 200
    conflit = await c.post(f"{url}/{did}/submit", headers=charge, json={"revision": rev0})
    assert conflit.status_code == 409 and conflit.json()["code"] == "EER_CONFLIT_REVISION"

    assert (await c.get(f"{url}/{did}/analystes", headers=charge)).status_code == 403
    eligibles = {a["id"] for a in (await c.get(f"{url}/{did}/analystes", headers=sup)).json()}
    assert str(ids["analyste"]) in eligibles and str(ids["charge_a"]) not in eligibles
    assert (await post("assign", sup, analyste_id=str(ids["charge_a"]))).status_code in (400, 403)
    assert (await post("assign", sup, analyste_id=str(ids["analyste"]))).status_code == 200
    assert (await post("start-control", analyste)).status_code == 200

    checklist = (await c.get(f"{url}/{did}/checklist", headers=analyste)).json()
    assert checklist["non_pointes"] > 0
    connue = {i["regle_code"]: i["donnee_connue"] for i in checklist["items"]}
    assert connue["PIECE_IDENTITE"] is True and connue["PPE_MOTIF"] is True
    assert connue["ORIGINE_FONDS"] is False and connue.get("VISAS_BANQUE") is None
    assert (await post("checklist/validate", analyste)).status_code == 400
    for item in checklist["items"]:
        if item["statut"] == "NON_APPLICABLE":
            continue
        presence = "ABSENT" if item["regle_code"] == "PIECE_IDENTITE" else "PRESENT"
        res = await c.patch(f"{url}/{did}/checklist/items/{item['id']}", headers=analyste,
                            json={"revision": rev, "presence": presence})
        assert res.status_code == 200, res.text
        rev = res.json()["revision"]
    assert (await post("checklist/validate", analyste)).status_code == 200
    rev = await _completer_fiches(c, analyste, did, rev, ids["analyste"])
    assert (await post("fiches/complete", analyste)).status_code == 200

    auto = await post("controls", analyste)
    assert auto.status_code == 200
    rev = auto.json()["revision"]
    assert any(k["code"] == "PIECE_IDENTITE" and k["resultat"] == "MANQUANT" for k in auto.json()["constats"])

    async def tout_controler():
        nonlocal rev
        for item in (await c.get(f"{url}/{did}/checklist", headers=analyste)).json()["items"]:
            if item["statut"] == "NON_CONTROLE":
                res = await c.patch(f"{url}/{did}/controls/{item['id']}", headers=analyste,
                                    json={"revision": rev, "conforme": True})
                assert res.status_code == 200, res.text
                rev = res.json()["revision"]

    await tout_controler()
    assert (await post("decision", analyste, resultat="CONFORME")).status_code == 400
    assert (await post("anomalies/open", analyste)).status_code == 200
    assert (await post("decision", analyste, resultat="NON_CONFORME")).status_code == 200
    anomalies = (await c.get(f"{url}/{did}/anomalies", headers=analyste)).json()
    assert [a["gravite"] for a in anomalies] == ["BLOQUANTE"]

    assert (await post("complement", analyste, consigne="Pièce d'identité absente",
                       cibles={"anomalie_ids": [anomalies[0]["id"]]})).status_code == 200
    hors_cible = await c.patch(f"{url}/{did}", headers=analyste, json={
        "revision": rev, "champs": [{"chemin": "client.adresse", "valeur": "Ailleurs"}]})
    assert hors_cible.status_code == 400
    assert (await post("resubmit", analyste)).status_code == 400
    piece = next(i for i in (await c.get(f"{url}/{did}/checklist", headers=analyste)).json()["items"]
                 if i["regle_code"] == "PIECE_IDENTITE")
    assert (await post("complements/fourni", analyste, item_id=piece["id"])).status_code == 200
    res = await post("resubmit", analyste)
    assert res.status_code == 200 and res.json()["version_courante"] == 2

    assert (await post("start-control", analyste)).status_code == 200
    res = await c.patch(f"{url}/{did}/checklist/items/{piece['id']}", headers=analyste,
                        json={"revision": rev, "presence": "PRESENT"})
    rev = res.json()["revision"]
    assert (await post("checklist/validate", analyste)).status_code == 200
    assert (await post("fiches/complete", analyste)).status_code == 200
    await tout_controler()
    assert (await post("decision", analyste, resultat="CONFORME")).status_code == 200

    # Avis KYC : le contrôleur ne peut pas émettre l'avis (permission) ; validation directe interdite.
    assert (await post("validate", sup)).status_code == 400
    assert (await post("request-avis", analyste)).status_code == 200
    assert (await post("avis", analyste, favorable=True)).status_code == 403
    res = await post("avis", sup, favorable=True, commentaire="RAS")
    assert res.status_code == 200 and res.json()["statut"] == "VALIDE"

    visas = (await c.get(f"{url}/{did}/avis", headers=analyste)).json()
    assert [(v["avis"], v["user_id"], v["version"]) for v in visas] == [("FAVORABLE", str(ids["superviseur"]), 2)]
    versions = (await c.get(f"{url}/{did}/versions", headers=analyste)).json()
    assert [v["evenement"] for v in versions][-1] == "VALIDE"
    detail = (await c.get(f"{url}/{did}/versions/{versions[0]['id']}", headers=analyste)).json()
    assert detail["empreinte_verifiee"] is True and detail["numero"] == 1
    historique = (await c.get(f"{url}/{did}/history", headers=analyste)).json()
    assert {"CREATION", "CONTROLES_AUTO", "COMPLEMENT_RECU", "TRANSITION"} <= {h["action"] for h in historique}
    audit = await c.get(f"{url}/{did}/audit", headers=sup)
    assert audit.status_code == 200 and "Client cycle API" not in audit.text
    assert (await c.get(f"{url}/{did}/audit", headers=analyste)).status_code == 403

    assert (await post("close", sup)).status_code == 200
    assert (await post("archive", sup)).status_code == 200
    final = (await c.get(f"{url}/{did}", headers=sup)).json()
    assert final["statut"] == "ARCHIVE" and final["transitions_possibles"] == []


# --- Immuabilité / OpenAPI ----------------------------------------------------------------

def test_aucune_route_ne_modifie_versions_historique_avis_decisions():
    for route in app.routes:
        chemin = getattr(route, "path", "")
        if not chemin.startswith("/api/v1/eer"):
            continue
        methodes = getattr(route, "methods", set()) or set()
        if any(seg in chemin for seg in ("/versions", "/history", "/audit")):
            assert methodes <= {"GET", "HEAD"}, (chemin, methodes)
        if chemin.endswith("/avis"):
            assert "PATCH" not in methodes and "PUT" not in methodes and "DELETE" not in methodes
        assert "DELETE" not in methodes, chemin
        assert "PUT" not in methodes, chemin


def test_openapi_schemas_pydantic():
    spec = app.openapi()
    chemins = {p: v for p, v in spec["paths"].items() if p.startswith("/api/v1/eer")}
    assert len(chemins) >= 35
    for chemin, operations in chemins.items():
        for methode, op in operations.items():
            reponse = op["responses"].get("200") or op["responses"].get("201")
            assert reponse and "content" in reponse, (methode, chemin)
            assert reponse["content"]["application/json"]["schema"], (methode, chemin)
    composants = spec["components"]["schemas"]
    assert {"EerDossierOut", "EerChecklistOut", "EerMutationOut", "EerVersionOut"} <= set(composants)
