"""Classement par liste : contrôle niveau du fichier / niveau enregistré par le moteur SCORE.

Tests unitaires partout. Tests base de données uniquement sur une copie ``*_test`` : chaque test
travaille dans une transaction annulée et vérifie que le moteur SCORE n'est jamais relancé.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.services.clientele.lots import comparer_niveaux, niveau_officiel


def _classif(niveau_propose: str | None, niveau: str | None = None, score: int | None = 400):
    return SimpleNamespace(niveau_propose=niveau_propose, niveau=niveau or niveau_propose, score_calcule=score,
                           version_regles="CDC-1.0", mode_decision="MOTEUR")


# --------------------------------------------------------------------------- unitaires
@pytest.mark.parametrize(("brut", "attendu"), [
    ("FAIBLE", "FAIBLE"), ("faible", "FAIBLE"), ("Risque élevé", "ELEVE"), ("ÉLEVÉ", "ELEVE"),
    ("  Moyen ", "MOYEN"), ("INTERDIT", "INTERDIT"),
    ("HAUT", None), ("FORT", None), ("BAS", None), ("Elev", None), ("Moy.", None), ("3", None), ("", None),
])
def test_niveau_officiel_sans_correspondance_inventee(brut, attendu):
    assert niveau_officiel(brut) == attendu


def test_identiques_conforme_sans_decision():
    r = comparer_niveaux("Faible", _classif("FAIBLE"))
    assert r["statut"] == "CONFORME"
    assert r["message"] == "Le niveau du fichier correspond au niveau du moteur SCORE. Aucune décision requise."
    assert (r["niveau_fichier"], r["niveau_moteur"]) == ("FAIBLE", "FAIBLE")


def test_libelle_officiel_ecrit_autrement_conforme():
    assert comparer_niveaux("Risque ÉLEVÉ", _classif("ELEVE"))["statut"] == "CONFORME"


def test_differents_ecart():
    r = comparer_niveaux("ELEVE", _classif("FAIBLE"))
    assert r["statut"] == "ECART"
    assert (r["niveau_fichier"], r["niveau_moteur"]) == ("ELEVE", "FAIBLE")


@pytest.mark.parametrize(("brut", "classif", "manque"), [
    (None, _classif("FAIBLE"), "fichier"),
    ("   ", _classif("FAIBLE"), "fichier"),
    ("MOYEN", None, "moteur SCORE"),
    ("MOYEN", _classif(None, niveau="MOYEN"), "moteur SCORE"),
    (None, None, "fichier et moteur SCORE"),
])
def test_donnee_manquante(brut, classif, manque):
    r = comparer_niveaux(brut, classif)
    assert r["statut"] == "DONNEE_MANQUANTE"
    assert r["message"].startswith("Comparaison impossible — donnée manquante")
    assert manque in r["message"]


@pytest.mark.parametrize(("brut", "moteur"), [("HAUT", "ELEVE"), ("Risque 2", "MOYEN"), ("FAIBLE", "INCONNU")])
def test_non_comparable(brut, moteur):
    r = comparer_niveaux(brut, _classif(moteur))
    assert r["statut"] == "NON_COMPARABLE"
    assert "vérification requise" in r["message"]


# --------------------------------------------------------------------------- base *_test
@pytest.fixture
async def db(monkeypatch):
    from app.db.session import AsyncSessionLocal, engine
    from app.services.clientele.classification import ClienteleClassificationService

    if not (make_url(get_settings().database_url).database or "").endswith("_test"):
        pytest.skip("Tests réservés à une copie *_test de la base (jamais la base réelle)")

    async def interdit(*_a, **_k):
        raise AssertionError("Le moteur SCORE ne doit pas être relancé pendant le contrôle")

    monkeypatch.setattr(ClienteleClassificationService, "evaluer_racine", interdit)
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()
    await engine.dispose()


async def _contexte(db, niveau_moteur: str = "FAIBLE", brut_fichier: str = "ELEVE"):
    from app.models import ClienteleClassification, ClienteleClassifLot, ClienteleClassifLotLigne, User
    from app.services.clientele.service import Ctx

    user = await db.scalar(select(User).where(User.is_superuser.is_(True)).limit(1))
    c = await db.scalar(select(ClienteleClassification).where(
        ClienteleClassification.niveau_propose == niveau_moteur,
        ClienteleClassification.niveau == niveau_moteur).limit(1))
    if not user or not c:
        pytest.skip("Copie sans administrateur ou sans classification adaptée")
    lot = ClienteleClassifLot(id=uuid.uuid4(), fichier_nom="test.xlsx", type="LISTE", statut="ANALYSE",
                              created_by_id=user.id)
    db.add(lot)
    await db.flush()
    x = ClienteleClassifLotLigne(lot_id=lot.id, ligne=2, racine_client=c.racine_client, statut="OK",
                                 classe_source_brut=brut_fichier, classe_source=niveau_officiel(brut_fichier),
                                 decision_detail={"controle": comparer_niveaux(brut_fichier, c)})
    db.add(x)
    await db.flush()
    perms = {"clientele.view", "clientele.classif.view", "clientele.classif.execute"}
    return Ctx(user=user, permissions=perms), lot, x, c


async def _historique(db, racine: str) -> int:
    from app.models import ClienteleClassifHistorique

    return await db.scalar(select(func.count()).select_from(ClienteleClassifHistorique)
                           .where(ClienteleClassifHistorique.racine_client == racine)) or 0


async def test_conserver_moteur_ne_modifie_rien(db):
    from app.services.clientele.lots import ClienteleLotService

    ctx, lot, x, c = await _contexte(db)
    avant = (c.niveau, c.source, c.mode_decision, await _historique(db, c.racine_client))
    r = await ClienteleLotService(db, ctx).decider_controle(lot.id, {"ligne": x.ligne, "choix": "MOTEUR"})
    assert r["decision"] == "CONSERVE_MOTEUR"
    d = r["decision_controle"]
    assert d["effet"] == "AUCUNE_MODIFICATION" and d["par_nom"] and d["le"]
    assert (c.niveau, c.source, c.mode_decision, await _historique(db, c.racine_client)) == avant


async def test_retenir_fichier_exige_justification(db):
    from app.services.clientele.lots import ClienteleLotService

    ctx, lot, x, _ = await _contexte(db)
    with pytest.raises(AppError):
        await ClienteleLotService(db, ctx).decider_controle(lot.id, {"ligne": x.ligne, "choix": "FICHIER"})


async def test_retenir_fichier_decision_manuelle_tracee(db):
    from app.services.clientele.lots import ClienteleLotService

    ctx, lot, x, c = await _contexte(db)
    nb = await _historique(db, c.racine_client)
    r = await ClienteleLotService(db, ctx).decider_controle(
        lot.id, {"ligne": x.ligne, "choix": "FICHIER", "justification": "Revue KYC : activité à risque"})
    assert r["decision"] == "RETENU_FICHIER"
    assert r["decision_controle"]["effet"] == "CLASSIFICATION_MODIFIEE"
    assert c.niveau == "ELEVE" and c.mode_decision == "MANUEL"
    assert c.niveau_propose == "FAIBLE"
    assert await _historique(db, c.racine_client) == nb + 1
    with pytest.raises(AppError):
        await ClienteleLotService(db, ctx).decider_controle(
            lot.id, {"ligne": x.ligne, "choix": "MOTEUR"})


async def test_conforme_aucune_decision_possible(db):
    from app.services.clientele.lots import ClienteleLotService

    ctx, lot, x, _ = await _contexte(db, brut_fichier="Faible")
    with pytest.raises(AppError):
        await ClienteleLotService(db, ctx).decider_controle(lot.id, {"ligne": x.ligne, "choix": "MOTEUR"})


async def test_non_comparable_aucune_decision_possible(db):
    from app.services.clientele.lots import ClienteleLotService

    ctx, lot, x, _ = await _contexte(db, brut_fichier="HAUT")
    with pytest.raises(AppError):
        await ClienteleLotService(db, ctx).decider_controle(lot.id, {"ligne": x.ligne, "choix": "MOTEUR"})


async def test_moteur_interdit_abaisse_exige_forcage(db):
    from app.services.clientele.lots import ClienteleLotService

    ctx, lot, x, _ = await _contexte(db, niveau_moteur="INTERDIT", brut_fichier="MOYEN")
    with pytest.raises(AppError):
        await ClienteleLotService(db, ctx).decider_controle(
            lot.id, {"ligne": x.ligne, "choix": "FICHIER", "justification": "Revue"})


async def test_permission_classif_execute_requise(db):
    from app.services.clientele.lots import ClienteleLotService
    from app.services.clientele.service import Ctx

    ctx, lot, x, _ = await _contexte(db)
    lecteur = Ctx(user=SimpleNamespace(is_superuser=False, id=ctx.user.id), permissions={"clientele.classif.view"})
    with pytest.raises((AppError, HTTPException)):
        await ClienteleLotService(db, lecteur).decider_controle(lot.id, {"ligne": x.ligne, "choix": "MOTEUR"})
