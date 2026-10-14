# ruff: noqa: F811  (fixture ``db`` importée puis injectée par pytest)
"""Réclamations — notes et pièces jointes, suppression définitive, restauration de la corbeille.

Services appelés directement, dans la transaction annulée de ``test_reclamations_fondations`` ;
les fichiers GED déposés sont supprimés en fin de test.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.core.exceptions import AppError
from app.data.plateforme_catalogue import ROLE_PERMISSIONS
from app.models import (
    AuditLog,
    ClienteleClient,
    GedDocument,
    Reclamation,
    ReclamationOperation,
)
from app.services.ged_service import GedService
from app.services.reclamations import circuit, documents, dossiers, reporting, suppression
from app.services.reclamations.acces import ReclamationsScope
from tests.test_reclamations_dossiers import PDF, _agent, _code, _saisie, _sr
from tests.test_reclamations_fondations import _unite, _user, db  # noqa: F401

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
DOCX_FAUX = b"PK\x03\x04" + b"\x00" * 32
DOCS = ("reclamations.document.view", "reclamations.document.upload", "reclamations.document.download")


def _fichier(nom: str, contenu: bytes = PDF) -> UploadFile:
    return UploadFile(BytesIO(contenu), filename=nom)


async def _supprimeur(db) -> ReclamationsScope:
    """Agent explicitement habilité à supprimer (sans être administrateur du module)."""
    return ReclamationsScope(user=await _user(db), permissions=frozenset(
        {"reclamations.view", "reclamations.scope.all", "reclamations.delete", *DOCS}))


async def _nettoyer(db, rid: uuid.UUID) -> None:
    for rel in (await db.scalars(select(GedDocument.stored_path).where(GedDocument.entity_id == str(rid)))).all():
        GedService(db).absolute_path(rel).unlink(missing_ok=True)


async def _refus(coro, attendu: str) -> None:
    with pytest.raises((AppError, HTTPException)) as e:
        await coro
    assert _code(e.value) == attendu


# ----------------------------------------------------- 1 & 3. notes multiples
async def test_notes_scannees_multiples_sans_ecrasement(db):
    unite = await _unite(db)
    point = await _agent(db, unites={unite.id})
    rid = uuid.UUID((await dossiers.creer(db, point, await _saisie(db, unite.id)))["id"])
    try:
        hier = date.today() - timedelta(days=1)
        r = await documents.deposer(db, point, rid, _fichier("note.pdf"), "NOTE", "Signée par le chef d'agence",
                                    titre="Note interne — analyse du prélèvement", date_document=hier)
        r = await documents.deposer(db, point, rid, _fichier("note-scan.png", PNG), "NOTE", None,
                                    titre="Note complémentaire")
        # Même nom de fichier : un nouveau document, l'ancien n'est pas écrasé.
        r = await documents.deposer(db, point, rid, _fichier("note.pdf"), "NOTE", None, titre="Note — version 2")
        r = await documents.deposer(db, point, rid, _fichier("courrier.pdf"), "COURRIER", "Courrier du client")
        items = r["items"]
        assert sorted(x["categorie"] for x in items) == ["COURRIER", "NOTE", "NOTE", "NOTE"]
        assert len({x["id"] for x in items}) == 4
        par_titre = {x["titre"]: x for x in items}
        premiere = par_titre["Note interne — analyse du prélèvement"]
        assert premiere["date_document"] == hier.isoformat()
        assert premiere["commentaire"] == "Signée par le chef d'agence"
        assert premiere["depose_par"] == "Agent test" and premiere["created_at"]
        assert premiere["filename"] == "note.pdf" and premiere["categorie_libelle"]
        scan = par_titre["Note complémentaire"]
        assert scan["nature"] == "image" and scan["date_document"] == date.today().isoformat()
        assert par_titre["Note — version 2"]["filename"] == "note.pdf"
        assert any(t.startswith("Courrier — ") for t in par_titre)
        chemins = (await db.scalars(select(GedDocument.stored_path).where(
            GedDocument.entity_id == str(rid), GedDocument.filename == "note.pdf"))).all()
        assert len(set(chemins)) == 2
        assert all(GedService(db).absolute_path(c).read_bytes() == PDF for c in chemins)

        await _refus(documents.deposer(db, point, rid, _fichier("n.pdf"), "NOTE", None, titre="  "),
                     "TITRE_OBLIGATOIRE")
        await _refus(documents.deposer(db, point, rid, _fichier("n.docx", DOCX_FAUX), "NOTE", None, titre="Note"),
                     "FORMAT_NOTE")
        await _refus(documents.deposer(db, point, rid, _fichier("n.pdf"), "NOTE", None, titre="Note",
                                       date_document=date.today() + timedelta(days=1)), "DATE_FUTURE")
        with pytest.raises(AppError):
            await documents.deposer(db, point, rid, _fichier("n.exe", b"MZ"), "AUTRE", None)
        assert len((await documents.lister(db, point, rid))["items"]) == 4
        chrono = [c for c in await dossiers.chronologie(db, point, rid) if c["type"] == "DOCUMENT_AJOUT"]
        assert len(chrono) == 4 and "Note interne — analyse du prélèvement" in [c["donnees"].get("titre")
                                                                                 for c in chrono]
    finally:
        await _nettoyer(db, rid)


# ---------------------------------------- 2 & 4. consultation selon permissions
async def test_notes_consultation_et_restrictions(db):
    unite = await _unite(db)
    point = await _agent(db, unites={unite.id})
    rid = uuid.UUID((await dossiers.creer(db, point, await _saisie(db, unite.id)))["id"])
    try:
        r = await documents.deposer(db, point, rid, _fichier("note.pdf"), "NOTE", None, titre="Note signée")
        did = uuid.UUID(r["items"][0]["id"])
        doc, chemin = await documents.fichier(db, point, rid, did)
        assert doc.filename == "note.pdf" and chemin.read_bytes() == PDF

        lecteur_sans_pieces = await _agent(db, unites={unite.id}, perms=("reclamations.view",))
        with pytest.raises(HTTPException) as e:
            await documents.lister(db, lecteur_sans_pieces, rid)
        assert e.value.status_code == 403
        consultant = await _agent(db, unites={unite.id}, perms=("reclamations.view", "reclamations.document.view"))
        vue = await documents.lister(db, consultant, rid)
        assert len(vue["items"]) == 1 and not vue["actions"]["telecharger"] and not vue["actions"]["deposer"]
        with pytest.raises(HTTPException) as e:
            await documents.fichier(db, consultant, rid, did)
        assert e.value.status_code == 403
        with pytest.raises(HTTPException) as e:
            await documents.deposer(db, consultant, rid, _fichier("x.pdf"), "NOTE", None, titre="Note")
        assert e.value.status_code == 403
        hors_perimetre = await _agent(db, unites={(await _unite(db)).id})
        for coro in (documents.lister(db, hors_perimetre, rid), documents.fichier(db, hors_perimetre, rid, did)):
            with pytest.raises(HTTPException) as e:
                await coro
            assert e.value.status_code == 404
        # Document d'un autre dossier : jamais servi via ce dossier.
        rid2 = uuid.UUID((await dossiers.creer(db, point, await _saisie(db, unite.id)))["id"])
        with pytest.raises(AppError) as e:
            await documents.fichier(db, point, rid2, did)
        assert _code(e.value) == "NOT_FOUND"
        audit = set((await db.scalars(select(AuditLog.action).where(AuditLog.entity_id == str(rid)))).all())
        assert "reclamations.document.download" in audit
    finally:
        await _nettoyer(db, rid)


# ----------------------------------------------- 5. suppression définitive
async def _compte(db, table: str, rid: uuid.UUID) -> int:
    return await db.scalar(text(f"SELECT count(*) FROM {table} WHERE reclamation_id = :i"), {"i": rid})


async def test_suppression_definitive_en_base(db):
    unite = await _unite(db)
    point = await _agent(db, unites={unite.id})
    sup = await _supprimeur(db)
    ops = [{"reference": "ORION-1", "montant": Decimal("1500")}]
    d = await dossiers.creer(db, point, await _saisie(db, unite.id, operations=ops))
    rid = uuid.UUID(d["id"])
    await documents.deposer(db, point, rid, _fichier("note.pdf"), "NOTE", None, titre="Note")
    chemins = [GedService(db).absolute_path(p) for p in (await db.scalars(
        select(GedDocument.stored_path).where(GedDocument.entity_id == str(rid)))).all()]
    assert chemins and all(c.exists() for c in chemins)
    fiche = await circuit.fiche(db, sup, await dossiers.charger(db, sup, rid))
    assert fiche["actions"]["supprimer"]
    assert (await dossiers.lister(db, sup, {"q": d["reference"]}))["items"][0]["suppression"]["possible"]

    await _refus(suppression.supprimer(db, sup, rid, {"revision": 0}), "CONFLIT_REVISION")
    res, fichiers = await suppression.supprimer(db, sup, rid, {"revision": fiche["revision"]})
    assert res == {"id": str(rid), "reference": d["reference"], "operations_supprimees": 1,
                   "documents_supprimes": 1}
    assert await db.get(Reclamation, rid) is None
    for table in ("reclamation_operations", "reclamation_evenements", "reclamation_documents"):
        assert await _compte(db, table, rid) == 0, table
    assert await db.scalar(select(func.count()).select_from(GedDocument).where(
        GedDocument.entity_id == str(rid))) == 0
    assert (await dossiers.lister(db, sup, {"q": d["reference"]}))["total"] == 0
    assert (await dossiers.lister(db, sup, {"q": d["reference"], "corbeille": True}))["total"] == 0
    assert (await reporting.tableau_de_bord(db, sup, {"q": d["reference"]}))["total"] == 0
    with pytest.raises(HTTPException) as e:
        await dossiers.charger(db, sup, rid)
    assert e.value.status_code == 404

    audit = await db.scalar(select(AuditLog).where(AuditLog.entity_id == str(rid),
                                                   AuditLog.action == "reclamations.suppression_definitive"))
    assert audit.before_data["reference"] == d["reference"]
    assert audit.before_data["operations"] == [{"reference": "ORION-1", "montant": "1500.00"}]
    suppression.effacer_fichiers(fichiers)
    assert not any(c.exists() for c in chemins)


# ------------------------------------------------- 6. refus sans la permission
async def test_suppression_refusee_sans_permission(db):
    unite = await _unite(db)
    point = await _agent(db, unites={unite.id})
    d = await dossiers.creer(db, point, await _saisie(db, unite.id))
    rid = uuid.UUID(d["id"])
    corps = {"revision": d["revision"]}
    responsable_sr = ReclamationsScope(user=await _user(db), permissions=frozenset(
        ROLE_PERMISSIONS["reclamations.responsable_sr"]))
    for s in (point, responsable_sr):
        with pytest.raises(HTTPException) as e:
            await suppression.supprimer(db, s, rid, corps)
        assert e.value.status_code == 403
        with pytest.raises(HTTPException) as e:
            await dossiers.lister(db, s, {"corbeille": True})
        assert e.value.status_code == 403
        fiche = await circuit.fiche(db, s, await dossiers.charger(db, s, rid))
        assert not fiche["actions"]["supprimer"] and "suppression" not in \
            (await dossiers.lister(db, s, {"q": d["reference"]}))["items"][0]
    # Réservée à l'administrateur du module et aux habilitations explicites.
    assert [r for r, perms in ROLE_PERMISSIONS.items() if "reclamations.delete" in perms] == ["reclamations.admin"]
    assert (await db.get(Reclamation, rid)).supprimee_le is None


# ------------------------------- 7. quel que soit le statut (clôturé, archivé…)
async def test_suppression_quel_que_soit_le_statut(db):
    sr = await _sr(db)
    unite = await _unite(db)
    d = await dossiers.creer(db, sr, await _saisie(db, unite.id))
    rid = uuid.UUID(d["id"])
    r = await dossiers.charger(db, sr, rid)
    r.statut, r.etape, r.date_cloture, r.resultat = "CLOTUREE", "CLOTURE", r.updated_at, "FAVORABLE"
    await db.flush()
    await circuit.archiver(db, sr, rid, {"revision": r.revision})
    assert (await circuit.fiche(db, sr, await dossiers.charger(db, sr, rid)))["actions"]["supprimer"]
    await suppression.supprimer(db, sr, rid, {})
    assert await db.get(Reclamation, rid) is None

    # Réponse au client et pièce officielle : supprimées avec le dossier.
    ouvert = await dossiers.creer(db, sr, await _saisie(db, unite.id))
    oid = uuid.UUID(ouvert["id"])
    await documents.deposer(db, sr, oid, _fichier("reponse.pdf"), "REPONSE_CLIENT", None)
    _res, fichiers = await suppression.supprimer(db, sr, oid, {})
    suppression.effacer_fichiers(fichiers)
    assert await db.get(Reclamation, oid) is None

    # Dossier cité par un autre : seul le lien de l'autre dossier tombe.
    cible = await dossiers.creer(db, sr, await _saisie(db, unite.id))
    lie = await dossiers.creer(db, sr, await _saisie(db, unite.id, reclamation_liee_id=uuid.UUID(cible["id"])))
    await suppression.supprimer(db, sr, uuid.UUID(cible["id"]), {})
    autre = await db.get(Reclamation, uuid.UUID(lie["id"]))
    await db.refresh(autre)
    assert autre.reclamation_liee_id is None


# ------------------------------------- 8. opérations et données externes intactes
async def test_operations_bancaires_jamais_supprimees(db):
    sr = await _sr(db)
    unite = await _unite(db)
    ops = [{"reference": "ORION-778899", "montant": Decimal("1500")}, {"reference": "ORION-778900", "montant": Decimal("20")}]
    d = await dossiers.creer(db, sr, await _saisie(db, unite.id, operations=ops))
    autre = await dossiers.creer(db, sr, await _saisie(db, unite.id, operations=ops[:1]))
    rid = uuid.UUID(d["id"])
    clients_avant = await db.scalar(select(func.count()).select_from(ClienteleClient))
    ops_avant = await db.scalar(select(func.count()).select_from(ReclamationOperation))

    # La chronologie d'un dossier existant reste en ajout seul.
    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(text("DELETE FROM reclamation_evenements WHERE reclamation_id = :i"), {"i": rid})

    await suppression.supprimer(db, sr, rid, {"revision": d["revision"], "motif": "Erreur de saisie"})
    # Seules les références du dossier supprimé disparaissent : clients et autre dossier intacts.
    assert await db.scalar(select(func.count()).select_from(ClienteleClient)) == clients_avant
    assert await db.scalar(select(func.count()).select_from(ReclamationOperation)) == ops_avant - 2
    assert (await dossiers.lister(db, sr, {"q": "ORION-778899"}))["items"][0]["id"] == autre["id"]
    audit = await db.scalar(select(AuditLog).where(AuditLog.entity_id == str(rid),
                                                   AuditLog.action == "reclamations.suppression_definitive"))
    assert [o["reference"] for o in audit.before_data["operations"]] == ["ORION-778899", "ORION-778900"]
    assert audit.after_data["motif"] == "Erreur de saisie"


# ------------------------- 9. dossier déjà à la corbeille (ancienne suppression logique)
async def test_corbeille_restauree_ou_supprimee(db):
    unite = await _unite(db)
    point = await _agent(db, unites={unite.id})
    sup = await _supprimeur(db)
    for restaure in (True, False):
        d = await dossiers.creer(db, point, await _saisie(db, unite.id))
        rid = uuid.UUID(d["id"])
        r = await db.get(Reclamation, rid)
        r.supprimee_le, r.supprimee_par_id, r.motif_suppression = r.updated_at, sup.user_id, "Doublon"
        await db.flush()
        ligne = (await dossiers.lister(db, sup, {"q": d["reference"], "corbeille": True}))["items"][0]
        assert ligne["suppression"] == {"possible": True, "restaurable": True}
        if restaure:
            r = await suppression.restaurer(db, sup, rid, {"revision": r.revision, "motif": "Pas un doublon"})
            assert r.supprimee_le is None
            assert (await dossiers.lister(db, point, {"q": d["reference"]}))["total"] == 1
        else:
            await suppression.supprimer(db, sup, rid, {"revision": r.revision})
            assert await db.get(Reclamation, rid) is None
