# ruff: noqa: F811  (fixture ``db`` importée puis injectée par pytest)
"""Réclamations — phase 2 : référentiels, unités, enregistrement, liste, fiche, pièces.

Services appelés directement, dans la transaction annulée de ``test_reclamations_fondations`` :
aucune donnée laissée en base (les fichiers GED déposés sont supprimés en fin de test).
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy import select

from app.core.exceptions import AppError
from app.models import AuditLog, GedDocument, ReclamationParametre, ReclamationReferentiel
from app.services.ged_service import GedService, est_cloisonne
from app.services.reclamations import documents, dossiers, organisation
from app.services.reclamations.acces import ReclamationsScope, permissions_effectives
from tests.test_reclamations_fondations import _unite, _user, db  # noqa: F401  (fixture partagée)

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
POINT_RECEPTION = ("reclamations.view", "reclamations.create", "reclamations.references.view",
                   "reclamations.document.view", "reclamations.document.upload", "reclamations.document.download")


def _code(exc: BaseException) -> str | None:
    if isinstance(exc, AppError):
        return exc.code
    if isinstance(exc, HTTPException) and isinstance(exc.detail, dict):
        return exc.detail.get("code")
    return None


async def _sr(db, **extra) -> ReclamationsScope:
    return ReclamationsScope(user=await _user(db), permissions=permissions_effectives({"reclamations.admin"}),
                             membre_service_central=True, **extra)


async def _agent(db, unites=(), perms=POINT_RECEPTION) -> ReclamationsScope:
    return ReclamationsScope(user=await _user(db), permissions=frozenset(perms), unites=frozenset(unites))


async def _canal(db, code: str) -> uuid.UUID:
    return await db.scalar(select(ReclamationReferentiel.id).where(
        ReclamationReferentiel.domaine == "CANAL", ReclamationReferentiel.code == code))


async def _classement(db, s: ReclamationsScope) -> tuple[dict, dict, dict]:
    suffixe = uuid.uuid4().hex[:6]
    t = await organisation.creer_referentiel(db, s, {"domaine": "TYPE", "libelle": f"Type test {suffixe}"})
    m = await organisation.creer_referentiel(db, s, {"domaine": "MOTIF", "libelle": "Motif test",
                                                     "parent_id": uuid.UUID(t["id"])})
    sm = await organisation.creer_referentiel(db, s, {"domaine": "SOUS_MOTIF", "libelle": "Sous-motif test",
                                                      "parent_id": uuid.UUID(m["id"])})
    return t, m, sm


async def _saisie(db, unite_id, **extra) -> dict:
    return {"objet": "Prélèvement contesté", "description": "Le client conteste un prélèvement.",
            "canal_id": await _canal(db, "EMAIL"), "unite_reception_id": unite_id,
            "date_premiere_reception": datetime.now(UTC) - timedelta(days=1), "client_nom": "Client Test",
            **extra}


# ------------------------------------------------------------------ référentiels
async def test_referentiels_hierarchie_et_usage(db):
    s = await _sr(db)
    with pytest.raises(AppError) as e:
        await organisation.creer_referentiel(db, s, {"domaine": "MOTIF", "libelle": "Orphelin"})
    assert _code(e.value) == "PARENT_OBLIGATOIRE"
    t, m, _sm = await _classement(db, s)
    with pytest.raises(HTTPException) as e:
        await organisation.creer_referentiel(db, s, {"domaine": "TYPE", "libelle": t["libelle"].upper()})
    assert _code(e.value) == "REFERENTIEL_EXISTANT"
    # Même libellé sous un autre parent : autorisé.
    t2 = await organisation.creer_referentiel(db, s, {"domaine": "TYPE", "libelle": f"Autre {uuid.uuid4().hex[:6]}"})
    await organisation.creer_referentiel(db, s, {"domaine": "MOTIF", "libelle": "Motif test",
                                                 "parent_id": uuid.UUID(t2["id"])})
    # Valeur utilisée (parent d'un motif) : désactivation seulement.
    with pytest.raises(HTTPException) as e:
        await organisation.supprimer_referentiel(db, s, uuid.UUID(t["id"]))
    assert _code(e.value) == "REFERENTIEL_UTILISE"
    off = await organisation.modifier_referentiel(db, s, uuid.UUID(t["id"]), {"actif": False})
    assert off["actif"] is False
    with pytest.raises(AppError) as e:
        await organisation.modifier_referentiel(db, s, uuid.UUID(m["id"]), {"actif": True})
    lecteur = await _agent(db, perms=("reclamations.view", "reclamations.references.view"))
    with pytest.raises(HTTPException) as e:
        await organisation.creer_referentiel(db, lecteur, {"domaine": "TYPE", "libelle": "Interdit"})
    assert e.value.status_code == 403


# ---------------------------------------------------------------------- unités
async def test_unites_creation_hierarchie_membres(db):
    s = await _sr(db)
    suffixe = uuid.uuid4().hex[:6]
    dep = await organisation.creer_unite(db, s, {"type_unite": "DEPARTEMENT", "libelle": f"Département {suffixe}"})
    svc = await organisation.creer_unite(db, s, {"type_unite": "SERVICE", "libelle": f"Service {suffixe}",
                                                 "parent_id": uuid.UUID(dep["id"])})
    assert svc["parent_id"] == dep["id"] and not svc["est_service_reclamations"]
    with pytest.raises(HTTPException) as e:
        await organisation.creer_unite(db, s, {"type_unite": "SERVICE", "libelle": f"SERVICE  {suffixe}"})
    assert _code(e.value) == "UNITE_EXISTANTE"
    with pytest.raises(AppError) as e:
        await organisation.modifier_unite(db, s, uuid.UUID(dep["id"]), {"parent_id": uuid.UUID(svc["id"])})
    assert _code(e.value) == "HIERARCHIE_CIRCULAIRE"

    agent = await _user(db)
    membres = await organisation.ajouter_membre(db, s, uuid.UUID(svc["id"]),
                                                {"user_id": agent.id, "role_membre": "RESPONSABLE"})
    assert [(m["user_id"], m["role_membre"]) for m in membres] == [(str(agent.id), "RESPONSABLE")]
    with pytest.raises(HTTPException) as e:
        await organisation.ajouter_membre(db, s, uuid.UUID(svc["id"]), {"user_id": agent.id, "role_membre": "AGENT"})
    assert _code(e.value) == "MEMBRE_EXISTANT"
    membres = await organisation.modifier_membre(db, s, uuid.UUID(svc["id"]), uuid.UUID(membres[0]["id"]),
                                                 {"actif": False})
    assert membres[0]["actif"] is False
    central = next(u for u in await organisation.lister_unites(db) if u["est_service_reclamations"])
    with pytest.raises(AppError) as e:
        await organisation.modifier_unite(db, s, uuid.UUID(central["id"]), {"actif": False})
    assert _code(e.value) == "SERVICE_CENTRAL"


# ------------------------------------------------------------------ enregistrement
async def test_creation_reference_statut_chronologie(db):
    s = await _sr(db)
    unite = await _unite(db)
    t, m, sm = await _classement(db, s)
    premiere = datetime.now(UTC) - timedelta(days=2)
    d1 = await dossiers.creer(db, s, await _saisie(
        db, unite.id, sous_motif_id=uuid.UUID(sm["id"]), date_premiere_reception=premiere,
        date_reception_sr=premiere + timedelta(hours=3)))
    annee = datetime.now(UTC).year
    assert re.fullmatch(rf"REC-{annee}-\d{{6}}", d1["reference"])
    assert (d1["statut"], d1["etape"]) == ("A_QUALIFIER", "RECEPTION")
    # Type et motif déduits du sous-motif.
    assert (d1["type_ref"]["id"], d1["motif_ref"]["id"]) == (t["id"], m["id"])
    assert d1["unite_suivi_ref"] is not None and d1["echeance"] is None

    d2 = await dossiers.creer(db, s, await _saisie(db, unite.id))
    assert int(d2["reference"][-6:]) == int(d1["reference"][-6:]) + 1
    # Saisie par le Service Réclamations : la réception SR est la saisie elle-même.
    assert d2["statut"] == "A_QUALIFIER" and d2["dates"]["date_reception_sr"] is not None

    chrono = await dossiers.chronologie(db, s, uuid.UUID(d1["id"]))
    assert [c["type"] for c in chrono] == ["CREATION", "RECEPTION_SR"]
    assert chrono[0]["date_effet"] == premiere.isoformat()
    assert await db.scalar(select(AuditLog.id).where(AuditLog.entity_id == d1["id"],
                                                     AuditLog.action == "reclamations.dossier.create"))


async def test_creation_validations(db):
    s = await _sr(db)
    unite, autre = await _unite(db), await _unite(db)
    t, _m, _sm = await _classement(db, s)
    t2 = await organisation.creer_referentiel(db, s, {"domaine": "TYPE", "libelle": f"T2 {uuid.uuid4().hex[:6]}"})
    m2 = await organisation.creer_referentiel(db, s, {"domaine": "MOTIF", "libelle": "M2",
                                                      "parent_id": uuid.UUID(t2["id"])})

    async def refus(scope, attendu: str, **extra):
        with pytest.raises((AppError, HTTPException)) as e:
            await dossiers.creer(db, scope, await _saisie(db, extra.pop("unite", unite.id), **extra))
        assert _code(e.value) == attendu, e.value

    await refus(s, "DATE_FUTURE", date_premiere_reception=datetime.now(UTC) + timedelta(days=1))
    await refus(s, "DATE_INCOHERENTE", date_reception_sr=datetime.now(UTC) - timedelta(days=3))
    await refus(s, "CLASSEMENT_INCOHERENT", type_id=uuid.UUID(t["id"]), motif_id=uuid.UUID(m2["id"]))
    await refus(s, "CLIENT_NOM_OBLIGATOIRE", client_nom=" ")
    await refus(s, "RACINE_INVALIDE", client_racine="12AB")
    await refus(s, "CARTE_NON_MASQUEE", carte_masquee="4111 1111 1111 1111")
    tel = await _canal(db, "TELEPHONE")
    await refus(s, "APPEL_OBLIGATOIRE", canal_id=tel)
    appel = {"appel_le": datetime.now(UTC) - timedelta(hours=20), "numero_appelant": "+222 22 00 00 00",
             "reference_enregistrement": "ENR-1"}
    await refus(s, "ENREGISTREMENT_NON_AUTORISE", canal_id=tel, appel=appel)

    point = await _agent(db, unites={unite.id})
    await refus(point, "PERMISSION_DENIED", date_reception_sr=datetime.now(UTC) - timedelta(hours=1))
    await refus(point, "UNITE_HORS_PERIMETRE", unite=autre.id)
    await refus(await _agent(db), "AUCUNE_UNITE")

    # Autorisation bancaire de l'enregistrement : la référence devient acceptée.
    db.add(ReclamationParametre(cle="enregistrement_appels_autorise", valeur=True))
    await db.flush()
    d = await dossiers.creer(db, s, await _saisie(db, unite.id, canal_id=tel, appel=appel))
    assert d["canal_telephone"] and d["appels"][0]["reference_enregistrement"] == "ENR-1"
    assert d["appels"][0]["enregistrement_autorise"] is True
    # Point de réception mono-unité : unité déduite.
    d = await dossiers.creer(db, point, await _saisie(db, None))
    assert d["unite_reception_ref"]["id"] == str(unite.id) and d["statut"] == "A_QUALIFIER"
    assert d["dates"]["date_reception_sr"] is None


async def test_perimetre_liste_detail(db):
    sr = await _sr(db)
    agence_a, agence_b = await _unite(db), await _unite(db)
    agent_a, agent_b = await _agent(db, unites={agence_a.id}), await _agent(db, unites={agence_b.id})
    marqueur = uuid.uuid4().hex[:8]
    d = await dossiers.creer(db, agent_a, await _saisie(db, agence_a.id, objet=f"Carte avalée {marqueur}"))
    rid = uuid.UUID(d["id"])

    assert [x["id"] for x in (await dossiers.lister(db, agent_a, {"q": marqueur}))["items"]] == [d["id"]]
    assert (await dossiers.lister(db, agent_b, {"q": marqueur}))["total"] == 0
    with pytest.raises(HTTPException) as e:
        await dossiers.charger(db, agent_b, rid)
    assert e.value.status_code == 404
    with pytest.raises(HTTPException):
        await dossiers.chronologie(db, agent_b, rid)

    global_ = (await dossiers.lister(db, sr, {"q": marqueur, "groupe": ["EN_COURS"], "ouvertes": True}))
    assert global_["total"] == 1 and global_["items"][0]["statut_libelle"] == "À qualifier"
    assert (await dossiers.lister(db, sr, {"q": marqueur, "statut": ["CLOTUREE"]}))["total"] == 0
    page = await dossiers.lister(db, sr, {}, page=1, taille=1000, tri="inconnu")
    assert page["taille"] == 100


async def test_modification_revision_motif(db):
    sr = await _sr(db)
    unite = await _unite(db)
    point = await _agent(db, unites={unite.id})
    d = await dossiers.creer(db, point, await _saisie(db, unite.id, compte_reference="00012345678"))
    rid = uuid.UUID(d["id"])
    assert d["actions"]["modifier"]

    with pytest.raises(HTTPException) as e:
        await dossiers.modifier(db, point, rid, {"revision": d["revision"] + 5, "objet": "X"})
    assert _code(e.value) == "CONFLIT_REVISION"
    with pytest.raises(AppError) as e:
        await dossiers.modifier(db, point, rid, {
            "revision": d["revision"], "date_premiere_reception": datetime.now(UTC) - timedelta(days=3),
            "date_reclamation": (datetime.now(UTC) - timedelta(days=3)).date()})
    assert _code(e.value) == "MOTIF_OBLIGATOIRE"
    d = await dossiers.modifier(db, point, rid, {
        "revision": d["revision"], "objet": "Objet corrigé", "effacer": ["compte_reference"],
        "date_premiere_reception": datetime.now(UTC) - timedelta(days=3), "motif": "Date du cachet postal",
        "date_reclamation": (datetime.now(UTC) - timedelta(days=3)).date()})
    assert d["objet"] == "Objet corrigé" and d["compte_reference"] is None and d["revision"] == 2
    modif = (await dossiers.chronologie(db, sr, rid))[-1]
    assert modif["type"] == "MODIFICATION" and modif["commentaire"] == "Date du cachet postal"
    assert "Objet" in modif["donnees"]["champs"]
    # Sans changement : ni révision ni événement.
    assert (await dossiers.modifier(db, point, rid, {"revision": 2, "objet": "Objet corrigé"}))["revision"] == 2

    with pytest.raises(AppError) as e:
        await dossiers.modifier(db, point, rid, {"revision": 2, "effacer": ["objet"]})
    assert _code(e.value) == "CHAMP_INVALIDE"
    # Dossier qualifié par le SR : le point de réception ne le modifie plus.
    r = await dossiers.charger(db, sr, rid)
    r.statut = "A_AFFECTER"
    await db.flush()
    with pytest.raises(HTTPException) as e:
        await dossiers.modifier(db, point, rid, {"revision": r.revision, "objet": "Encore"})
    assert e.value.status_code == 403
    r.statut = "CLOTUREE"
    r.date_cloture = datetime.now(UTC)
    await db.flush()
    with pytest.raises(HTTPException) as e:
        await dossiers.modifier(db, sr, rid, {"revision": r.revision, "objet": "Encore"})
    assert _code(e.value) == "DOSSIER_TERMINE"


# --------------------------------------------------------------------- pièces
async def test_pieces_ged_cloisonnees(db):
    sr = await _sr(db)
    unite = await _unite(db)
    point = await _agent(db, unites={unite.id})
    d = await dossiers.creer(db, point, await _saisie(db, unite.id))
    rid = uuid.UUID(d["id"])
    chemins: list[str] = []
    try:
        with pytest.raises(AppError) as e:
            await documents.deposer(db, point, rid, UploadFile(BytesIO(PDF), filename="x.pdf"), "INCONNUE", None)
        assert _code(e.value) == "CATEGORIE_INVALIDE"
        r = await documents.deposer(db, point, rid, UploadFile(BytesIO(PDF), filename="scan réclamation.pdf"),
                                    "ORIGINAL", "Courrier reçu en agence")
        r = await documents.deposer(db, point, rid, UploadFile(BytesIO(PDF), filename="releve.pdf"),
                                    "PIECE_CLIENT", None)
        assert [x["categorie"] for x in r["items"]] == ["ORIGINAL", "PIECE_CLIENT"]
        assert not r["actions"]["retirer"]
        docs = {x["categorie"]: await db.get(GedDocument, uuid.UUID(x["id"])) for x in r["items"]}
        chemins += [doc.stored_path for doc in docs.values()]
        original = docs["ORIGINAL"]
        assert est_cloisonne(original.module_code, original.entity)
        assert original.security_level == "restricted" and original.ocr_status == "skipped"

        _doc, chemin = await documents.fichier(db, point, rid, original.id, apercu=True)
        assert chemin.read_bytes() == PDF
        autre = await _agent(db, unites={(await _unite(db)).id})
        with pytest.raises(HTTPException) as e:
            await documents.fichier(db, autre, rid, original.id)
        assert e.value.status_code == 404

        with pytest.raises(HTTPException) as e:
            await documents.retirer(db, point, rid, original.id, "erreur")
        assert e.value.status_code == 403
        responsable = ReclamationsScope(user=sr.user, permissions=frozenset(
            {"reclamations.view", "reclamations.scope.all", "reclamations.document.view",
             "reclamations.document.remove"}))
        with pytest.raises(HTTPException) as e:
            await documents.retirer(db, responsable, rid, original.id, "erreur")
        assert _code(e.value) == "ORIGINAL_PROTEGE"
        with pytest.raises(AppError):
            await documents.retirer(db, responsable, rid, docs["PIECE_CLIENT"].id, "  ")
        r = await documents.retirer(db, responsable, rid, docs["PIECE_CLIENT"].id, "Pièce d'un autre client")
        assert [x["categorie"] for x in r["items"]] == ["ORIGINAL"]
        await db.refresh(docs["PIECE_CLIENT"])
        assert docs["PIECE_CLIENT"].deleted_at is not None
        assert docs["PIECE_CLIENT"].delete_reason == "Pièce d'un autre client"

        types = [c["type"] for c in await dossiers.chronologie(db, sr, rid)]
        assert types.count("DOCUMENT_AJOUT") == 2 and types.count("DOCUMENT_RETRAIT") == 1
        actions = set((await db.scalars(select(AuditLog.action).where(AuditLog.entity_id == d["id"]))).all())
        assert {"reclamations.document.upload", "reclamations.document.preview",
                "reclamations.document.remove"} <= actions
        assert len(actions) >= 3
        assert (await dossiers.lister(db, sr, {"q": d["reference"]}))["items"][0]["nb_documents"] == 1
    finally:
        for rel in chemins:
            GedService(db).absolute_path(rel).unlink(missing_ok=True)
