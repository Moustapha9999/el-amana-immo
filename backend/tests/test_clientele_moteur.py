"""Moteur d'indicateurs : COUNT DISTINCT, classif à une date, A_CONFIGURER sans chiffre."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.data.plateforme_catalogue import FUNCTIONAL_PERMISSIONS, ROLE_PERMISSIONS
from app.models import User
from app.services.clientele.import_service import ClienteleImportService
from app.services.clientele.indicateurs import PAGE_MAX, ClienteleIndicateursService
from app.services.clientele.periodes import appliquer, resoudre
from app.services.clientele.service import Ctx
from tests.test_clientele_consolidation import brute
from tests.test_clientele_import import classeur

EXTRACTION = date(2026, 10, 31)
DEBUT = date(2026, 10, 1)
FIN = date(2026, 10, 31)
_IN = "('000001','000002','000003')"


@pytest.fixture
async def db():
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            pret = await conn.scalar(text(
                "SELECT to_regclass('public.clientele_classif_historique') IS NOT NULL"))
    except Exception:
        pret = False
    if not pret:
        await engine.dispose()
        pytest.skip("Tables phase 4 absentes (migration 20261008_clientele_03)")
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
    await session.execute(text(f"""
        DELETE FROM clientele_alerte_justificatifs WHERE alerte_id IN (
            SELECT id FROM clientele_alertes WHERE racine_client IN {_IN})
    """))
    await session.execute(text(f"""
        DELETE FROM clientele_alerte_evenements WHERE alerte_id IN (
            SELECT id FROM clientele_alertes WHERE racine_client IN {_IN})
    """))
    await session.execute(text(f"DELETE FROM clientele_alertes WHERE racine_client IN {_IN}"))
    await session.execute(text(
        f"DELETE FROM clientele_classif_historique WHERE racine_client IN {_IN}"))
    await session.execute(text(
        f"DELETE FROM clientele_classifications WHERE racine_client IN {_IN}"))
    await session.execute(text("DELETE FROM clientele_import_comptes"))
    await session.execute(text("DELETE FROM clientele_import_clients"))
    await session.execute(text("DELETE FROM clientele_import_anomalies"))
    await session.execute(text("DELETE FROM clientele_import_lignes"))
    await session.execute(text("DELETE FROM clientele_imports"))
    await session.execute(text(f"DELETE FROM clientele_comptes WHERE racine_client IN {_IN}"))
    await session.execute(text(f"DELETE FROM clientele_clients WHERE racine_client IN {_IN}"))


async def _ctx(db) -> Ctx:
    user = await db.scalar(select(User).limit(1))
    if not user:
        pytest.skip("aucun utilisateur en base de test")
    return Ctx(user=user, permissions={"clientele.admin", "clientele.reporting.view",
                                       "clientele.view", "clientele.export"})


async def _importer(db, ctx) -> None:
    svc = ClienteleImportService(db, ctx)
    a = await svc.analyser(classeur(
        brute("000001", "00000100001"),
        brute("000001", "00000100002"),
        brute("000001", "00000100003"),
        brute("000002", "00000200001"),
    ), "oct-moteur.xlsx")
    await svc.confirmer(uuid.UUID(a["id"]), {"date_extraction": EXTRACTION.isoformat()})


def _par(tableau: dict, code: str) -> dict:
    return next(i for i in tableau["indicateurs"] if i["code"] == code)


def test_catalogue_reporting_view():
    perms = {c for c, _l, m in FUNCTIONAL_PERMISSIONS if m == "clientele"}
    assert "clientele.reporting.view" in perms
    assert "clientele.reporting.view" in ROLE_PERMISSIONS["clientele.lecteur"]
    assert "clientele.reporting.view" in ROLE_PERMISSIONS["clientele.gestionnaire"]
    assert "clientele.bcm.view" in ROLE_PERMISSIONS["clientele.lecteur"]


def test_periodes_7j_et_mois_precedent():
    f = resoudre("7j", aujourdhui=date(2026, 10, 8))
    assert f.date_debut == date(2026, 10, 2)
    assert f.date_fin == date(2026, 10, 8)
    assert f.simulation is True
    m = resoudre("mois_precedent", aujourdhui=date(2026, 10, 8))
    assert m.date_debut == date(2026, 9, 1)
    assert m.date_fin == date(2026, 9, 30)
    assert m.bcm_officielle is True
    ytd = appliquer(m, "YTD")
    assert ytd.date_debut == date(2026, 1, 1)
    assert ytd.date_fin == date(2026, 9, 30)


def test_periode_personnalisee_refusee_si_inversee():
    with pytest.raises(ValueError):
        resoudre("personnalisee", date_debut=FIN, date_fin=DEBUT)


@pytest.mark.asyncio
async def test_un_client_trois_comptes_distinct(db):
    ctx = await _ctx(db)
    await _importer(db, ctx)
    svc = ClienteleIndicateursService(db, ctx)
    t = await svc.tableau(periode="personnalisee", date_debut=DEBUT, date_fin=FIN)
    assert _par(t, "cli.stock")["valeur"] == 2
    assert _par(t, "cli.comptes")["valeur"] == 4
    assert _par(t, "cli.pp")["valeur"] == 2
    assert _par(t, "cli.nouveaux")["valeur"] == 2
    d = await svc.detail("cli.stock", periode="personnalisee", date_debut=DEBUT, date_fin=FIN,
                         page=1, taille=1)
    assert d["total"] == 2
    assert d["taille"] == 1
    assert len(d["items"]) == 1
    trop = await svc.detail("cli.stock", periode="personnalisee", date_debut=DEBUT, date_fin=FIN,
                            page=1, taille=500)
    assert trop["taille"] == PAGE_MAX


@pytest.mark.asyncio
async def test_classif_a_une_date(db):
    ctx = await _ctx(db)
    await _importer(db, ctx)
    await db.execute(text("""
        INSERT INTO clientele_classif_historique
            (id, racine_client, ancienne_classe, nouvelle_classe, source, motif_classement, created_at)
        VALUES
            (gen_random_uuid(), '000001', NULL, 'FAIBLE', 'MANUEL', 'test',
             '2026-09-01 12:00:00+00'),
            (gen_random_uuid(), '000001', 'FAIBLE', 'ELEVE', 'MANUEL', 'test',
             '2026-10-15 12:00:00+00')
    """))
    await db.commit()
    svc = ClienteleIndicateursService(db, ctx)
    avant = await svc.tableau(periode="personnalisee",
                              date_debut=date(2026, 10, 1), date_fin=date(2026, 10, 10))
    assert _par(avant, "cli.risque.faible")["valeur"] == 1
    assert _par(avant, "cli.risque.eleve")["valeur"] == 0
    apres = await svc.tableau(periode="personnalisee", date_debut=DEBUT, date_fin=FIN)
    assert _par(apres, "cli.risque.eleve")["valeur"] == 1
    assert _par(apres, "cli.risque.faible")["valeur"] == 0
    assert _par(apres, "cli.reclass.faible_eleve")["valeur"] == 1
    assert _par(apres, "cli.reclass.vers_eleve")["valeur"] == 1


@pytest.mark.asyncio
async def test_a_configurer_sans_valeur_numerique(db):
    ctx = await _ctx(db)
    await _importer(db, ctx)
    svc = ClienteleIndicateursService(db, ctx)
    t = await svc.tableau(periode="personnalisee", date_debut=DEBUT, date_fin=FIN)
    for code in ("cli.actifs", "cli.inactifs", "cli.construction_juridique",
                 "bcm.t2.enregistrees", "bcm.t2.umef_mois", "bcm.t3.suspectes_personnel"):
        i = _par(t, code)
        assert i["statut"] == "A_CONFIGURER"
        assert i["valeur"] is None
    d = await svc.detail("cli.actifs", periode="personnalisee", date_debut=DEBUT, date_fin=FIN)
    assert d["calcule"] is False
    assert d["items"] == []
    with pytest.raises(AppError) as err:
        await svc.exporter_lignes("cli.actifs", periode="personnalisee",
                                  date_debut=DEBUT, date_fin=FIN)
    assert err.value.code == "INDICATEUR_A_CONFIGURER"


@pytest.mark.asyncio
async def test_alertes_intervalle(db):
    ctx = await _ctx(db)
    await _importer(db, ctx)
    await db.execute(text("""
        INSERT INTO clientele_alertes
            (id, racine_client, statut, motif, empreinte, score, correspondance, created_at)
        VALUES
            (gen_random_uuid(), '000001', 'NOUVELLE', 'TEST', 'moteur-1', 80, '{}',
             '2026-10-20 12:00:00+00'),
            (gen_random_uuid(), '000002', 'FAUX_POSITIF', 'TEST', 'moteur-2', 40, '{}',
             '2026-10-21 12:00:00+00')
    """))
    await db.commit()
    svc = ClienteleIndicateursService(db, ctx)
    t = await svc.tableau(periode="personnalisee", date_debut=DEBUT, date_fin=FIN)
    assert _par(t, "alerte.stock")["valeur"] == 2
    assert _par(t, "alerte.faux_positifs")["valeur"] == 1
    assert _par(t, "bcm.t2.suivi")["valeur"] == 1
    assert _par(t, "bcm.t2.extraites")["statut"] == "PRET_SOUS_RESERVE"
