# ruff: noqa: F811
"""Réclamations — circuit : qualification → affectation → retour → réponse → clôture."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy import select

from app.core.exceptions import AppError
from app.models import ReclamationReferentiel, ReclamationUnite
from app.services.reclamations import circuit, delais, documents, dossiers, reponses
from app.services.reclamations.acces import ReclamationsScope, permissions_effectives
from tests.test_reclamations_dossiers import PDF, _canal, _classement, _code, _saisie, _sr
from tests.test_reclamations_fondations import _unite, _user, db  # noqa: F401


async def _agent_service(db, unite_id) -> ReclamationsScope:
    return ReclamationsScope(
        user=await _user(db),
        permissions=permissions_effectives({
            "reclamations.view", "reclamations.treat", "reclamations.document.view",
            "reclamations.document.upload",
        }),
        unites=frozenset({unite_id}),
    )


async def _sr_unite(db) -> ReclamationUnite:
    u = await db.scalar(select(ReclamationUnite).where(ReclamationUnite.est_service_reclamations.is_(True)))
    return u or await _unite(db)


async def test_circuit_complet_jusqua_cloture(db):
    sr = await _sr(db)
    unite_sr = await _sr_unite(db)
    service = await _unite(db)
    t, m, _sm = await _classement(db, sr)
    d = await dossiers.creer(db, sr, await _saisie(
        db, unite_sr.id, date_reception_sr=datetime.now(UTC) - timedelta(hours=1),
        type_id=uuid.UUID(t["id"]), motif_id=uuid.UUID(m["id"])))
    rid = uuid.UUID(d["id"])
    assert d["statut"] == "RECUE_SR"

    q = await circuit.qualifier(db, sr, rid, {
        "revision": d["revision"], "type_id": uuid.UUID(t["id"]), "motif_id": uuid.UUID(m["id"])})
    assert q["statut"] == "A_QUALIFIER" and q["actions"]["affecter"]

    a = await circuit.affecter(db, sr, rid, {
        "revision": q["revision"], "unite_id": service.id, "instructions": "Vérifier le GAB"})
    assert a["statut"] == "AFFECTEE"

    agent = await _agent_service(db, service.id)
    p = await circuit.prendre(db, agent, rid, {"revision": a["revision"]})
    assert p["statut"] == "EN_TRAITEMENT"

    ret = await circuit.retourner(db, agent, rid, {
        "revision": p["revision"], "analyse": "Transaction non aboutie côté GAB.",
        "conclusion": "Remboursement recommandé.", "decision_proposee": "FAVORABLE"})
    assert ret["statut"] == "RETOUR_RECU"

    ev = await circuit.evaluer(db, sr, rid, {"revision": ret["revision"], "evaluation": "SUFFISANT"})
    assert ev["statut"] == "REPONSE_A_PREPARER"

    brouillon = await reponses.enregistrer(db, sr, rid, {
        "revision": ev["revision"], "contenu": "Nous procédons au remboursement.", "resultat": "FAVORABLE"})
    soumis = await reponses.soumettre(db, sr, rid, {"revision": brouillon["revision"]})
    valide = await reponses.valider(db, sr, rid, {"revision": soumis["revision"]})
    canal = await db.scalar(select(ReclamationReferentiel.id).where(
        ReclamationReferentiel.domaine == "CANAL_REPONSE"))
    env = await reponses.envoyer(db, sr, rid, {
        "revision": valide["revision"], "canal_envoi_id": canal, "destinataire": "Client Test"})
    assert env["statut"] == "REPONSE_ENVOYEE"

    with pytest.raises((AppError, HTTPException)) as e:
        await circuit.cloturer(db, sr, rid, {"revision": env["revision"], "resultat": "FAVORABLE"})
    assert _code(e.value) == "PREUVE_ENVOI_MANQUANTE"

    await documents.deposer(db, sr, rid, UploadFile(BytesIO(PDF), filename="preuve.pdf"), "PREUVE_ENVOI", None)
    clot = await circuit.cloturer(db, sr, rid, {
        "revision": env["revision"], "resultat": "FAVORABLE", "motif_resolution": "Remboursé"})
    assert clot["statut"] == "CLOTUREE" and clot["actions"]["rouvrir"]


async def test_renvoi_si_retour_insuffisant(db):
    sr = await _sr(db)
    unite_sr = await _sr_unite(db)
    service = await _unite(db)
    t, _m, _ = await _classement(db, sr)
    d = await dossiers.creer(db, sr, await _saisie(
        db, unite_sr.id, date_reception_sr=datetime.now(UTC) - timedelta(hours=2),
        type_id=uuid.UUID(t["id"])))
    rid = uuid.UUID(d["id"])
    d = await circuit.qualifier(db, sr, rid, {"revision": d["revision"], "type_id": uuid.UUID(t["id"])})
    d = await circuit.affecter(db, sr, rid, {"revision": d["revision"], "unite_id": service.id})
    agent = await _agent_service(db, service.id)
    d = await circuit.prendre(db, agent, rid, {"revision": d["revision"]})
    d = await circuit.retourner(db, agent, rid, {
        "revision": d["revision"], "analyse": "Incomplet", "conclusion": "Manque le ticket"})
    d = await circuit.evaluer(db, sr, rid, {
        "revision": d["revision"], "evaluation": "INSUFFISANT", "motif": "Joindre le ticket GAB"})
    assert d["statut"] == "AFFECTEE" and d["nb_renvois"] == 1 and len(d["affectations"]) == 2


async def test_regle_delai_calcule_echeance(db):
    sr = await _sr(db)
    unite_sr = await _sr_unite(db)
    t, _m, _ = await _classement(db, sr)
    regle = await delais.creer_regle(db, sr, {
        "libelle": "Délai test 10 j", "type_id": uuid.UUID(t["id"]), "duree": 10,
        "unite_duree": "JOURS_CALENDAIRES", "point_depart": "PREMIERE_RECEPTION",
        "date_effet": date(2020, 1, 1),
    })
    assert regle["statut_validation"] == "A_VALIDER"
    d = await dossiers.creer(db, sr, await _saisie(
        db, unite_sr.id, type_id=uuid.UUID(t["id"]),
        date_premiere_reception=datetime.now(UTC) - timedelta(days=1)))
    assert d["echeance"] is not None
