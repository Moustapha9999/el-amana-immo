"""Vue 360° clientèle : périodes, motifs enregistrés, masquage des filtres, cohérence KPI / listes.

Les tests unitaires tournent partout. Les tests base de données ne s'exécutent que sur une copie
dont le nom se termine par ``_test`` et vérifient en plus que la lecture n'écrit rien.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.services.clientele.service import Ctx
from app.services.clientele.vue360 import (
    ANOMALIES,
    ClienteleVue360Service,
    _cumuler,
    filtres_depuis,
    motif_enregistre,
    resoudre_periode,
)

TOUT_VOIR = {"clientele.view", "clientele.filtrage.view", "clientele.classif.view"}
SANS_CLASSIF = {"clientele.view", "clientele.filtrage.view"}


def _ctx(perms: set[str]) -> Ctx:
    return Ctx(user=SimpleNamespace(is_superuser=False, id=None), permissions=perms)


# --------------------------------------------------------------------------- périodes
@pytest.mark.parametrize(("code", "debut", "fin"), [
    ("jour", date(2026, 10, 13), date(2026, 10, 13)),
    ("7j", date(2026, 10, 7), date(2026, 10, 13)),
    ("30j", date(2026, 9, 14), date(2026, 10, 13)),
    ("trimestre", date(2026, 10, 1), date(2026, 10, 13)),
    ("annee", date(2026, 1, 1), date(2026, 10, 13)),
    (None, date(2026, 9, 14), date(2026, 10, 13)),
    ("inconnu", date(2026, 9, 14), date(2026, 10, 13)),
])
def test_periode_bornes(code, debut, fin):
    p = resoudre_periode(code, aujourd_hui=date(2026, 10, 13))
    assert (p.debut, p.fin) == (debut, fin)


def test_periode_precedente_meme_duree_immediatement_anterieure():
    p = resoudre_periode("7j", aujourd_hui=date(2026, 10, 13))
    assert p.prec_fin == p.debut - timedelta(days=1)
    assert (p.prec_fin - p.prec_debut).days == (p.fin - p.debut).days


def test_periode_perso_validee():
    p = resoudre_periode("perso", date(2026, 1, 1), date(2026, 1, 31))
    assert (p.debut, p.fin, p.prec_debut, p.prec_fin) == (
        date(2026, 1, 1), date(2026, 1, 31), date(2025, 12, 1), date(2025, 12, 31))
    with pytest.raises(AppError):
        resoudre_periode("perso", date(2026, 1, 1), None)
    with pytest.raises(AppError):
        resoudre_periode("perso", date(2026, 2, 1), date(2026, 1, 1))


# --------------------------------------------------------------------------- motifs
def test_motif_enregistre_jamais_reconstitue():
    assert motif_enregistre({}) == (None, None)
    assert motif_enregistre({"motif_moteur": "", "motif_classement": "Import"}) == ("Import", "motif_classement")
    assert motif_enregistre({"motif_moteur": "Score 120000", "motif_decision_manuelle": "Revue CF"}) == (
        "Revue CF", "motif_decision_manuelle")


def test_cumuler_somme_compteurs_et_max_dates():
    t = _cumuler([
        {"profil": "PP", "clients": 3, "eleve": 1, "dernier_classement": date(2026, 1, 1)},
        {"profil": "PM", "clients": 2, "eleve": None, "dernier_classement": date(2026, 3, 1)},
    ])
    assert t["clients"] == 5 and t["eleve"] == 1
    assert t["dernier_classement"] == date(2026, 3, 1)
    assert _cumuler([])["clients"] == 0


def test_filtres_depuis_retire_vides():
    assert filtres_depuis(a=None, b="", c="X", d=0) == {"c": "X", "d": 0}


# --------------------------------------------------------------------------- filtres SQL
def test_where_valeurs_liees_jamais_interpolees():
    svc = ClienteleVue360Service(None, _ctx(TOUT_VOIR))
    where, params = svc._where({"agence": "001'; DROP TABLE x;--", "q": "abc%", "profil": "PM"})
    assert "DROP" not in where and "abc" not in where
    assert params["agence"].startswith("001'") and params["profil"] == "PM"


def test_where_valeurs_hors_liste_ignorees():
    svc = ClienteleVue360Service(None, _ctx(TOUT_VOIR))
    where, params = svc._where({"profil": "XX", "niveau": "TRES_ELEVE", "filtrage": "1=1", "anomalie": "f_x"})
    assert where == "TRUE" and params == {}


def test_where_masque_risque_sans_permission_classification():
    svc = ClienteleVue360Service(None, _ctx(SANS_CLASSIF))
    where, _ = svc._where({"niveau": "ELEVE", "profilage": "A_ARBITRER", "coherence": "A_VERIFIER",
                           "anomalie": "NIVEAU_SCORE_INCOHERENT"})
    assert where == "TRUE"
    donnees = next(a for a in ANOMALIES if a.famille == "DONNEES")
    where, _ = svc._where({"anomalie": donnees.code})
    assert donnees.colonne in where


# --------------------------------------------------------------------------- base *_test
@pytest.fixture
async def db():
    from app.db.session import AsyncSessionLocal, engine

    if not (make_url(get_settings().database_url).database or "").endswith("_test"):
        pytest.skip("Tests réservés à une copie *_test de la base (jamais la base réelle)")
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()
    await engine.dispose()


async def _empreinte(db) -> tuple:
    return tuple((await db.execute(text(
        "SELECT (SELECT md5(coalesce(string_agg(racine_client || niveau || coalesce(score_calcule::text, ''), ','"
        " ORDER BY racine_client), '')) FROM clientele_classifications),"
        " (SELECT count(*) FROM clientele_classif_historique),"
        " (SELECT count(*) FROM clientele_classif_evaluations),"
        " (SELECT count(*) FROM clientele_alertes)"))).one())


async def test_synthese_unites_sans_double_comptage(db):
    s = await ClienteleVue360Service(db, _ctx(TOUT_VOIR)).synthese({})
    c = s["clients"]
    assert c["pp"] + c["pm"] + c["non_identifies"] == c["total"]
    assert sum(s["risque"].values()) == c["total"]
    f = s["filtrage"]
    assert f["clients_avec_correspondance"] + f["clients_sans_correspondance"] == c["total"]


async def test_kpi_coherent_avec_listes(db):
    svc = ClienteleVue360Service(db, _ctx(TOUT_VOIR))
    filtres = {"niveau": "ELEVE", "profil": "PP"}
    s = await svc.synthese(filtres)
    clients = await svc.clients(filtres, 1, 1)
    assert clients["total"] == s["clients"]["total"]

    from app.services.clientele.filtrage import ClienteleFiltrageService

    alertes = await ClienteleFiltrageService(db, _ctx(TOUT_VOIR)).lister(
        groupe="OUVERTES", profil="PP", population=svc.population({"niveau": "ELEVE"}), taille=1)
    assert alertes["total"] == s["alertes"]["ouvertes"]


async def test_masquage_sans_permission_classification(db):
    s = await ClienteleVue360Service(db, _ctx(SANS_CLASSIF)).synthese({"niveau": "ELEVE"})
    assert s["risque"] is None and s["profilage"] is None
    assert all(a["famille"] == "DONNEES" for a in s["anomalies"])
    tout = await ClienteleVue360Service(db, _ctx(SANS_CLASSIF)).synthese({})
    assert s["clients"]["total"] == tout["clients"]["total"]


async def test_lecture_n_ecrit_rien(db):
    avant = await _empreinte(db)
    await db.execute(text("SET TRANSACTION READ ONLY"))
    svc = ClienteleVue360Service(db, _ctx(TOUT_VOIR))
    await svc.synthese({"profil": "PM"})
    page = await svc.clients({"profil": "PM"}, 1, 5)
    assert page["page"] == 1
    await db.rollback()
    assert await _empreinte(db) == avant


async def test_journal_reserve_supervision(db):
    from fastapi import HTTPException

    with pytest.raises((AppError, HTTPException)):
        await ClienteleVue360Service(db, _ctx(SANS_CLASSIF)).journal()


async def test_population_vide_renvoie_zero(db):
    s = await ClienteleVue360Service(db, _ctx(TOUT_VOIR)).synthese({"q": "zzz-aucun-client-zzz"})
    assert s["clients"]["total"] == 0
    assert s["alertes"]["ouvertes"] == 0
