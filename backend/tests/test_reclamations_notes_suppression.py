# ruff: noqa: F811  (fixture ``db`` importée puis injectée par pytest)
"""Réclamations — notes et pièces jointes, suppression (corbeille) et restauration.

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
    ReclamationDocument,
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


# ----------------------------------------------------- 5. suppression autorisée
async def test_suppression_puis_restauration(db):
    unite = await _unite(db)
    point = await _agent(db, unites={unite.id})
    sup = await _supprimeur(db)
    d = await dossiers.creer(db, point, await _saisie(db, unite.id))
    rid = uuid.UUID(d["id"])
    fiche = await circuit.fiche(db, sup, await dossiers.charger(db, sup, rid))
    assert fiche["actions"]["supprimer"] and not fiche["actions"]["restaurer"]
    ligne = (await dossiers.lister(db, sup, {"q": d["reference"]}))["items"][0]
    assert ligne["suppression"]["possible"]

    base = {"revision": fiche["revision"], "motif": "Saisie en double"}
    await _refus(suppression.supprimer(db, sup, rid, {**base, "confirmation": "REC-0000-000000"}),
                 "CONFIRMATION_INVALIDE")
    await _refus(suppression.supprimer(db, sup, rid, {**base, "motif": " ", "confirmation": d["reference"]}),
                 "MOTIF_OBLIGATOIRE")
    await _refus(suppression.supprimer(db, sup, rid, {**base, "revision": 0, "confirmation": d["reference"]}),
                 "CONFLIT_REVISION")
    res = await suppression.supprimer(db, sup, rid, {**base, "confirmation": d["reference"].lower()})
    assert res["reference"] == d["reference"] and res["supprimee_le"]

    # Hors des listes, KPI et exports ordinaires ; visible dans la corbeille des profils habilités.
    assert (await dossiers.lister(db, sup, {"q": d["reference"]}))["total"] == 0
    corbeille = await dossiers.lister(db, sup, {"q": d["reference"], "corbeille": True})
    assert corbeille["total"] == 1 and corbeille["items"][0]["suppression"]["restaurable"]
    assert corbeille["items"][0]["motif_suppression"] == "Saisie en double"
    assert (await reporting.tableau_de_bord(db, sup, {"q": d["reference"]}))["total"] == 0
    with pytest.raises(HTTPException) as e:
        await dossiers.charger(db, point, rid)
    assert e.value.status_code == 404
    await _refus(dossiers.modifier(db, sup, rid, {"revision": fiche["revision"] + 1, "objet": "X"}),
                 "DOSSIER_SUPPRIME")
    await _refus(suppression.supprimer(db, sup, rid, {**base, "confirmation": d["reference"]}), "DEJA_SUPPRIME")
    vue = await circuit.fiche(db, sup, await dossiers.charger(db, sup, rid))
    assert vue["actions"]["restaurer"] and not vue["actions"]["supprimer"] and not vue["actions"]["modifier"]
    assert vue["suppression"]["motif"] == "Saisie en double" and vue["suppression"]["supprimee_par"]

    r = await suppression.restaurer(db, sup, rid, {"revision": vue["revision"], "motif": "Suppression à tort"})
    assert r.supprimee_le is None
    assert (await dossiers.lister(db, point, {"q": d["reference"]}))["total"] == 1
    types = [c["type"] for c in await dossiers.chronologie(db, sup, rid)]
    assert types[-2:] == ["SUPPRESSION", "RESTAURATION"]
    audit = set((await db.scalars(select(AuditLog.action).where(AuditLog.entity_id == str(rid)))).all())
    assert {"reclamations.suppression", "reclamations.restauration"} <= audit


# ------------------------------------------------- 6. refus sans la permission
async def test_suppression_refusee_sans_permission(db):
    unite = await _unite(db)
    point = await _agent(db, unites={unite.id})
    d = await dossiers.creer(db, point, await _saisie(db, unite.id))
    rid = uuid.UUID(d["id"])
    corps = {"revision": d["revision"], "motif": "Essai", "confirmation": d["reference"]}
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


# --------------------------------------------- 7. dossier clôturé / officiel
async def test_suppression_dossier_cloture_ou_officiel(db):
    sr = await _sr(db)
    unite = await _unite(db)
    d = await dossiers.creer(db, sr, await _saisie(db, unite.id))
    rid = uuid.UUID(d["id"])
    r = await dossiers.charger(db, sr, rid)
    r.statut, r.etape = "CLOTUREE", "CLOTURE"
    await db.flush()
    fiche = await circuit.fiche(db, sr, r)
    assert not fiche["actions"]["supprimer"]
    assert [b["code"] for b in fiche["suppression"]["blocages"]] == ["DOSSIER_CLOTURE"]
    with pytest.raises(HTTPException) as e:
        await suppression.supprimer(db, sr, rid, {"revision": r.revision, "motif": "x", "confirmation": r.reference})
    assert e.value.status_code == 409 and _code(e.value) == "DOSSIER_CLOTURE"
    r.archivee_le = r.updated_at
    await db.flush()
    assert "DOSSIER_ARCHIVE" in [b["code"] for b in (await suppression.blocages(db, [r]))[rid]]

    ouvert = await dossiers.creer(db, sr, await _saisie(db, unite.id))
    oid = uuid.UUID(ouvert["id"])
    try:
        await documents.deposer(db, sr, oid, _fichier("reponse.pdf"), "REPONSE_CLIENT", None)
        await _refus(suppression.supprimer(db, sr, oid, {"revision": ouvert["revision"], "motif": "x",
                                                         "confirmation": ouvert["reference"]}),
                     "DOCUMENTS_OFFICIELS")
    finally:
        await _nettoyer(db, oid)
    cible = await dossiers.creer(db, sr, await _saisie(db, unite.id))
    await dossiers.creer(db, sr, await _saisie(db, unite.id, reclamation_liee_id=uuid.UUID(cible["id"])))
    await _refus(suppression.supprimer(db, sr, uuid.UUID(cible["id"]), {
        "revision": cible["revision"], "motif": "x", "confirmation": cible["reference"]}), "DOSSIER_REFERENCE")


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

    await suppression.supprimer(db, sr, rid, {"revision": d["revision"], "motif": "Erreur de saisie",
                                              "confirmation": d["reference"]})
    assert await db.scalar(select(func.count()).select_from(ClienteleClient)) == clients_avant
    assert await db.scalar(select(func.count()).select_from(ReclamationOperation)) == ops_avant
    rattachees = (await db.scalars(select(ReclamationOperation.reference).where(
        ReclamationOperation.reclamation_id == rid).order_by(ReclamationOperation.ordre))).all()
    assert rattachees == ["ORION-778899", "ORION-778900"]
    assert (await dossiers.lister(db, sr, {"q": "ORION-778899"}))["items"][0]["id"] == autre["id"]
    audit = await db.scalar(select(AuditLog).where(AuditLog.entity_id == str(rid),
                                                   AuditLog.action == "reclamations.suppression"))
    assert audit.before_data["operations"] == ["ORION-778899", "ORION-778900"]

    # Aucune suppression physique possible, même en SQL : la chronologie est en ajout seul.
    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(text("DELETE FROM reclamations WHERE id = :i"), {"i": rid})
    assert await db.get(Reclamation, rid) is not None


# --------------------------------------- 9. cohérence des pièces après suppression
async def test_pieces_coherentes_apres_suppression(db):
    unite = await _unite(db)
    point = await _agent(db, unites={unite.id})
    sup = await _supprimeur(db)
    d = await dossiers.creer(db, point, await _saisie(db, unite.id))
    rid = uuid.UUID(d["id"])
    try:
        await documents.deposer(db, point, rid, _fichier("note.pdf"), "NOTE", None, titre="Note de traitement")
        await documents.deposer(db, point, rid, _fichier("piece.png", PNG), "PIECE_CLIENT", None)
        avant = await documents.lister(db, sup, rid)
        fiche = await circuit.fiche(db, sup, await dossiers.charger(db, sup, rid))
        await suppression.supprimer(db, sup, rid, {"revision": fiche["revision"], "motif": "Doublon",
                                                   "confirmation": d["reference"]})
        # Pièces conservées en GED (ni corbeille GED ni fichier effacé), consultables par le profil habilité.
        docs = (await db.scalars(select(GedDocument).where(GedDocument.entity_id == str(rid)))).all()
        assert len(docs) == 2 and all(x.deleted_at is None for x in docs)
        assert all(GedService(db).absolute_path(x.stored_path).exists() for x in docs)
        assert await db.scalar(select(func.count()).select_from(ReclamationDocument).where(
            ReclamationDocument.reclamation_id == rid)) == 2
        pendant = await documents.lister(db, sup, rid)
        assert [x["id"] for x in pendant["items"]] == [x["id"] for x in avant["items"]]
        assert not pendant["actions"]["deposer"] and not pendant["actions"]["retirer"]
        _doc, chemin = await documents.fichier(db, sup, rid, uuid.UUID(avant["items"][0]["id"]))
        assert chemin.read_bytes() == PDF
        await _refus(documents.deposer(db, sup, rid, _fichier("x.pdf"), "NOTE", None, titre="Note"),
                     "DOSSIER_SUPPRIME")
        await _refus(documents.retirer(db, await _sr(db), rid, uuid.UUID(avant["items"][1]["id"]), "x"),
                     "DOSSIER_SUPPRIME")
        with pytest.raises(HTTPException) as e:
            await documents.lister(db, point, rid)
        assert e.value.status_code == 404

        r = await suppression.restaurer(db, sup, rid, {"revision": fiche["revision"] + 1, "motif": "Pas un doublon"})
        apres = await documents.lister(db, point, rid)
        assert [x["id"] for x in apres["items"]] == [x["id"] for x in avant["items"]] and apres["actions"]["deposer"]
        assert r.revision == fiche["revision"] + 2
    finally:
        await _nettoyer(db, rid)
