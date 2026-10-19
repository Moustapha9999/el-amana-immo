"""Déclaration mensuelle BCM : calcul sur données réelles, règles enregistrées, snapshot reproductible.

Les tests base de données n'ajoutent et ne suppriment que les racines 998001 à 998004 (et leurs règles de test) :
ils s'exécutent sur une base peuplée sans en altérer le contenu. Les comptages globaux ne sont jamais supposés ;
on vérifie l'appartenance des clients de test aux populations et les identités de contrôle.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from io import BytesIO

import pytest
from openpyxl import load_workbook
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.data.clientele_bcm import BCM_GRILLE_VERSION, STATUTS_FIGES, fiches
from app.data.plateforme_catalogue import FUNCTIONAL_PERMISSIONS, ROLE_PERMISSIONS
from app.models import Agence, User
from app.services.clientele.bcm_regles import ClienteleBcmReglesService
from app.services.clientele.declaration import ClienteleDeclarationService
from app.services.clientele.periodes import fenetre_mois_bcm
from app.services.clientele.service import Ctx

AUJ = date(2026, 10, 8)
_IN = "('998001','998002','998003','998004')"
MOTIF_TEST = "test-bcm-declaration"


@pytest.fixture
async def db():
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            pret = await conn.scalar(text(
                "SELECT to_regclass('public.clientele_declarations_bcm') IS NOT NULL "
                "AND to_regclass('public.clientele_bcm_regles') IS NOT NULL"))
    except Exception:
        pret = False
    if not pret:
        await engine.dispose()
        pytest.skip("Tables BCM absentes (migrations 20261008_clientele_04 et 20261019_clientele_12)")
    session = async_sessionmaker(engine, expire_on_commit=False)()
    await _nettoyer(session)
    await session.commit()
    try:
        yield session
    finally:
        await session.rollback()
        await _nettoyer(session)
        await session.commit()
        await session.close()
        await engine.dispose()


async def _nettoyer(session) -> None:
    await session.execute(text("DELETE FROM clientele_declarations_bcm WHERE annee = 2026 AND mois IN (8, 10)"))
    await session.execute(text("SET LOCAL session_replication_role = replica"))
    await session.execute(text(f"DELETE FROM clientele_classif_historique WHERE racine_client IN {_IN}"))
    await session.execute(text("DELETE FROM clientele_bcm_regles WHERE motif LIKE :m"), {"m": f"{MOTIF_TEST}%"})
    await session.execute(text("SET LOCAL session_replication_role = origin"))
    await session.execute(text(f"DELETE FROM clientele_kyc WHERE racine_client IN {_IN}"))
    await session.execute(text(f"DELETE FROM clientele_comptes WHERE racine_client IN {_IN}"))
    await session.execute(text(f"DELETE FROM clientele_clients WHERE racine_client IN {_IN}"))


async def _ctx(db) -> Ctx:
    user = await db.scalar(select(User).limit(1))
    if not user:
        pytest.skip("aucun utilisateur en base de test")
    return Ctx(user=user, permissions={"clientele.admin", "clientele.bcm.view",
                                       "clientele.bcm.prepare", "clientele.bcm.valider",
                                       "clientele.bcm.cloturer", "clientele.reporting.view",
                                       "clientele.view", "clientele.export"})


async def _client(db, racine: str, ouverture: date, *, categorie: str | None, etat: str = "OUVERT",
                  gel: str | None = None) -> None:
    agence = await db.scalar(select(Agence.id).limit(1))
    if not agence:
        pytest.skip("aucune agence en base de test")
    await db.execute(text("""
        INSERT INTO clientele_clients (id, racine_client, raison_sociale, categorie_juridique, premiere_extraction,
                                       date_extraction, created_at, updated_at)
        VALUES (gen_random_uuid(), :r, 'CLIENT TEST BCM', :cat, '2026-10-01', '2026-10-01', now(), now())
    """), {"r": racine, "cat": categorie})
    compte = f"{racine}00001"
    await db.execute(text("""
        INSERT INTO clientele_comptes (id, compte, rib, racine_client, agence_id, etat_compte, date_ouverture, devise,
                                       premiere_extraction, date_extraction, created_at, updated_at)
        VALUES (gen_random_uuid(), :c, :rib, :r, :a, :e, :d, 'MRU', '2026-10-01', '2026-10-01', now(), now())
    """), {"c": compte, "rib": f"0000000000{compte}00", "r": racine, "a": agence, "e": etat, "d": ouverture})
    if gel:
        await db.execute(text(
            "INSERT INTO clientele_kyc (racine_client, statut_gel, source) VALUES (:r, :g, 'TEST')"),
            {"r": racine, "g": gel})


async def _historique(db, racine: str, niveau: str, le: str) -> None:
    await db.execute(text("""
        INSERT INTO clientele_classif_historique
            (id, racine_client, ancienne_classe, nouvelle_classe, source, motif_classement, created_at)
        VALUES (gen_random_uuid(), :r, NULL, :n, 'MANUEL', 'test-bcm', :le)
    """), {"r": racine, "n": niveau, "le": datetime.fromisoformat(le)})


async def _jeu(db) -> None:
    """998001 PP entré en juillet (FAIBLE puis ELEVE en août), 998002 PM entré en août (INTERDIT),
    998003 sans catégorie juridique entré en août, sans classement."""
    await _client(db, "998001", date(2026, 7, 10), categorie="PERSONNE PHYSIQUE", gel="Actif")
    await _client(db, "998002", date(2026, 8, 12), categorie="SOCIETE COMMERCIALE", gel="Inactif")
    await _client(db, "998003", date(2026, 8, 20), categorie=None)
    await _historique(db, "998001", "FAIBLE", "2026-07-01 12:00:00+00")
    await _historique(db, "998001", "ELEVE", "2026-08-10 12:00:00+00")
    await _historique(db, "998002", "INTERDIT", "2026-08-15 12:00:00+00")
    await db.commit()


def _cell(detail: dict, tableau: str, ligne: str, col: str) -> dict:
    tab = next(t for t in detail["cellules"]["tableaux"] if t["code"] == tableau)
    lig = next(row for row in tab["lignes"] if row["code"] == ligne)
    return lig["cellules"][col]


def _ctrl(detail: dict, code: str) -> dict:
    return next(c for c in detail["controles"] if c["code"] == code)


async def _racines(svc, did, code: str) -> set[str]:
    """Clients de test (998xxx) présents dans la population de la cellule."""
    dd = await svc.drilldown(did, code, taille=50, racine="998")
    return {i["racine_client"] for i in dd["items"]}


def test_catalogue_bcm():
    perms = {c for c, _l, m in FUNCTIONAL_PERMISSIONS if m == "clientele"}
    assert {"clientele.bcm.view", "clientele.bcm.prepare",
            "clientele.bcm.valider", "clientele.bcm.cloturer"} <= perms
    assert "clientele.bcm.view" in ROLE_PERMISSIONS["clientele.lecteur"]
    assert "clientele.bcm.prepare" in ROLE_PERMISSIONS["clientele.gestionnaire"]
    assert "clientele.bcm.valider" not in ROLE_PERMISSIONS["clientele.gestionnaire"]
    assert "clientele.bcm.valider" in ROLE_PERMISSIONS["clientele.admin"]
    champs = fiches()
    assert champs
    for f in champs:
        assert f["libelle_officiel"]
        assert f["tableau"] in ("T1A", "T1B", "T2", "T3", "T4")
        assert f["validation_metier"] in ("PRET", "PRET_SOUS_RESERVE", "A_CONFIGURER")
        if f["validation_metier"] == "A_CONFIGURER":
            assert not (f["formule"] or "").upper().startswith("COUNT")
            assert f["source"] == "ABSENT"
        else:
            assert f["source"] and f["formule"]


def test_fenetre_mois_bcm_officielle():
    f = fenetre_mois_bcm(2026, 8, aujourdhui=AUJ)
    assert f.date_debut == date(2026, 8, 1)
    assert f.date_fin == date(2026, 8, 31)
    assert f.bcm_officielle is True
    assert f.simulation is False
    courant = fenetre_mois_bcm(2026, 10, aujourdhui=AUJ)
    assert courant.bcm_officielle is False
    assert courant.simulation is True


@pytest.mark.asyncio
async def test_calcul_aout_populations_et_export(db):
    ctx = await _ctx(db)
    await _jeu(db)
    svc = ClienteleDeclarationService(db, ctx)
    d = await svc.creer(2026, 8, aujourdhui=AUJ)
    did = uuid.UUID(d["id"])
    cal = await svc.calculer(did, aujourdhui=AUJ)
    assert cal["statut"] == "CALCULEE"
    assert cal["cellules"]["grille_version"] == BCM_GRILLE_VERSION
    assert {r["code"] for r in cal["cellules"]["regles"]} >= {"stock.date_entree", "interdit.rattachement"}

    assert "998001" in await _racines(svc, did, "bcm.t1a.stock_m1.pp")
    assert not {"998002", "998003"} & await _racines(svc, did, "bcm.t1a.stock_m1.total")
    assert {"998002", "998003"} <= await _racines(svc, did, "bcm.t1a.maj_mois.total")
    assert "998002" in await _racines(svc, did, "bcm.t1a.maj_mois.pm")
    assert "998003" in await _racines(svc, did, "bcm.exc.forme_EXC_FORME_VIDE")
    assert "998001" in await _racines(svc, did, "bcm.t1b.stock_m1.faible")
    assert "998001" in await _racines(svc, did, "bcm.t4.eleve")
    assert "998002" in await _racines(svc, did, "bcm.exc.t4_INTERDIT")
    assert "998003" in await _racines(svc, did, "bcm.exc.t4_NON_CLASSE")
    assert "998001" in await _racines(svc, did, "bcm.t1a.cible.total")
    assert "998002" not in await _racines(svc, did, "bcm.t1a.cible.total")

    t4 = _cell(cal, "T4", "total", "valeur")["valeur"]
    assert t4 == _cell(cal, "T1A", "stock_m1", "total")["valeur"] + _cell(cal, "T1A", "maj_mois", "total")["valeur"]
    assert _ctrl(cal, "t4.identite")["ok"] is True
    assert _ctrl(cal, "unicite.clients")["ok"] is True
    assert _ctrl(cal, "classif.historique_m1")["ok"] is True
    interdit = _ctrl(cal, "interdit.rattachement")
    assert interdit["ok"] is False and interdit["bloquant"] is True
    assert _cell(cal, "T2", "extraites", "valeur")["statut"] == "A_CONFIGURER"
    assert _cell(cal, "T2", "extraites", "valeur")["fiabilite"] == "SOURCE_ABSENTE"
    assert _ctrl(cal, "t2.source")["etat"] == "SOURCE_ABSENTE"

    xlsx = await svc.exporter_xlsx(did)
    wb = load_workbook(BytesIO(xlsx))
    ws = wb["Déclaration mensuelle"]
    assert ws["E5"].value == _cell(cal, "T1A", "stock_m1", "total")["valeur"]
    assert ws["B44"].value == t4 and ws["C44"].value == 100.0
    assert ws["B21"].value == "Source absente" and ws["B31"].value == "Source absente"
    textes = [c.value for row in wb["Contrôle"].iter_rows() for c in row if c.value is not None]
    assert "interdit.rattachement" in textes
    exports = await db.scalar(text(
        "SELECT count(*) FROM audit_logs WHERE action = 'bcm.exporter' AND entity_id = :i"), {"i": d["id"]})
    assert exports == 1
    assert (await svc.exporter_pdf(did))[:4] == b"%PDF"


@pytest.mark.asyncio
async def test_interdit_bloque_puis_regle_confirmee_et_snapshot_reproductible(db):
    ctx = await _ctx(db)
    await _jeu(db)
    svc = ClienteleDeclarationService(db, ctx)
    did = uuid.UUID((await svc.creer(2026, 8, aujourdhui=AUJ))["id"])
    await svc.calculer(did, aujourdhui=AUJ)
    await svc.controler(did)
    with pytest.raises(AppError) as err:
        await svc.valider(did, aujourdhui=AUJ)
    assert err.value.code == "CONTROLES_BLOQUANTS"
    assert "interdit.rattachement" in err.value.message

    regles = ClienteleBcmReglesService(db, ctx)
    with pytest.raises(AppError) as err:
        await regles.decider("interdit.rattachement", {"valeur": "ELEVE", "statut": "CONFIRMEE", "motif": " "})
    assert err.value.code == "MOTIF_OBLIGATOIRE"
    out = await regles.decider("interdit.rattachement", {
        "valeur": "HORS_COLONNES", "statut": "CONFIRMEE", "motif": f"{MOTIF_TEST} : décision Conformité"})
    regle = next(r for r in out["regles"] if r["code"] == "interdit.rattachement")
    assert regle["statut"] == "CONFIRMEE" and regle["decidee"] is True
    async with db.bind.connect() as conn:
        with pytest.raises(DBAPIError):
            await conn.execute(text("UPDATE clientele_bcm_regles SET motif = 'x' WHERE motif LIKE :m"),
                               {"m": f"{MOTIF_TEST}%"})

    cal = await svc.calculer(did, aujourdhui=AUJ)
    assert _ctrl(cal, "interdit.rattachement")["ok"] is True
    snap = next(r for r in cal["cellules"]["regles"] if r["code"] == "interdit.rattachement")
    assert snap["statut"] == "CONFIRMEE"
    await svc.controler(did)
    val = await svc.valider(did, aujourdhui=AUJ)
    assert val["statut"] == "VALIDEE" and val["statut"] in STATUTS_FIGES

    avant = await svc.drilldown(did, "bcm.t1a.maj_mois.total", taille=1)
    await _client(db, "998004", date(2026, 8, 5), categorie="PERSONNE PHYSIQUE")
    await db.commit()
    apres = await svc.drilldown(did, "bcm.t1a.maj_mois.total", taille=1)
    assert apres["total"] == avant["total"] and apres["figee"] is True
    with pytest.raises(AppError) as err:
        await svc.calculer(did, aujourdhui=AUJ)
    assert err.value.code == "DECLARATION_FIGEE"
    with pytest.raises(AppError) as err:
        await svc.creer(2026, 8, aujourdhui=AUJ)
    assert err.value.code == "DECLARATION_EXISTANTE"


@pytest.mark.asyncio
async def test_mois_non_clos(db):
    ctx = await _ctx(db)
    await _jeu(db)
    svc = ClienteleDeclarationService(db, ctx)
    oct_ = await svc.creer(2026, 10, aujourdhui=AUJ)
    assert oct_["simulation"] is True
    await svc.calculer(uuid.UUID(oct_["id"]), aujourdhui=AUJ)
    await svc.controler(uuid.UUID(oct_["id"]))
    with pytest.raises(AppError) as err:
        await svc.valider(uuid.UUID(oct_["id"]), aujourdhui=AUJ)
    assert err.value.code == "MOIS_NON_CLOS"


@pytest.mark.asyncio
async def test_desactiver_reactiver_supprimer(db):
    ctx = await _ctx(db)
    svc = ClienteleDeclarationService(db, ctx)
    d = await svc.creer(2026, 8, aujourdhui=AUJ)
    did = uuid.UUID(d["id"])
    assert d["actions"]["desactiver"] and d["actions"]["supprimer"]
    assert d["journal"][0]["etape"] == "Créée"
    cal = await svc.calculer(did, aujourdhui=AUJ)
    assert cal["synthese"]["cellules"] > 0

    with pytest.raises(AppError):
        await svc.desactiver(did, motif="  ")
    off = await svc.desactiver(did, motif="Doublon de préparation")
    assert off["statut"] == "DESACTIVEE"
    assert off["motif_desactivation"] == "Doublon de préparation"
    assert off["actions"]["reactiver"] is True
    assert off["actions"]["desactiver"] is False
    assert off["actions"]["calculer"] is False
    with pytest.raises(AppError) as err:
        await svc.calculer(did, aujourdhui=AUJ)
    assert err.value.code == "DECLARATION_DESACTIVEE"

    on = await svc.reactiver(did)
    assert on["statut"] == "CALCULEE"
    assert on["motif_desactivation"] is None

    with pytest.raises(AppError):
        await svc.supprimer(did)
    await svc.supprimer(did, motif="Recréation demandée par la Conformité")
    assert (await db.scalar(text(
        "SELECT count(*) FROM clientele_declarations_bcm WHERE annee = 2026 AND mois = 8"))) == 0


@pytest.mark.asyncio
async def test_historique_absent_bloque_la_validation(db):
    """Sans historique de classification couvrant le mois, le risque n'est pas calculé et la validation est
    bloquée. Ne s'applique que si la base n'a aucun historique antérieur au 31/07/2026."""
    ctx = await _ctx(db)
    h_min = await db.scalar(text("SELECT min(created_at) FROM clientele_classif_historique"))
    if h_min and h_min.date() <= date(2026, 7, 31):
        pytest.skip("la base contient un historique de classification antérieur à août 2026")
    svc = ClienteleDeclarationService(db, ctx)
    did = uuid.UUID((await svc.creer(2026, 8, aujourdhui=AUJ))["id"])
    cal = await svc.calculer(did, aujourdhui=AUJ)
    assert _cell(cal, "T1B", "stock_m1", "eleve")["valeur"] is None
    assert _cell(cal, "T1B", "stock_m1", "eleve")["statut"] == "NON_CALCULABLE"
    assert _cell(cal, "T1B", "stock_m1", "eleve")["fiabilite"] == "HISTORIQUE_INDISPONIBLE"
    assert _cell(cal, "T4", "faible", "ratio")["valeur"] is None
    hist = _ctrl(cal, "classif.historique_m1")
    assert hist["bloquant"] is True and hist["etat"] == "HISTORIQUE_INDISPONIBLE"
    await svc.controler(did)
    with pytest.raises(AppError) as err:
        await svc.valider(did, aujourdhui=AUJ)
    assert err.value.code == "CONTROLES_BLOQUANTS"
