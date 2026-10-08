"""Phase 10 — Déclaration mensuelle BCM : moteur commun, A_CONFIGURER, snapshot figé."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.data.clientele_bcm import BCM_GRILLE_VERSION, STATUTS_FIGES, fiches
from app.data.plateforme_catalogue import FUNCTIONAL_PERMISSIONS, ROLE_PERMISSIONS
from app.models import User
from app.services.clientele.declaration import ClienteleDeclarationService
from app.services.clientele.import_service import ClienteleImportService
from app.services.clientele.periodes import fenetre_mois_bcm
from app.services.clientele.service import Ctx
from tests.test_clientele_consolidation import brute
from tests.test_clientele_import import classeur

AUJ = date(2026, 10, 8)
EXTRACTION = date(2026, 7, 15)
_IN = "('000001','000002','000003')"


@pytest.fixture
async def db():
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            pret = await conn.scalar(text(
                "SELECT to_regclass('public.clientele_declarations_bcm') IS NOT NULL"))
    except Exception:
        pret = False
    if not pret:
        await engine.dispose()
        pytest.skip("Table clientele_declarations_bcm absente (migration 20261008_clientele_04)")
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
    await session.execute(text(
        "DELETE FROM clientele_declarations_bcm WHERE annee = 2026 AND mois IN (8, 10)"))
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
    return Ctx(user=user, permissions={"clientele.admin", "clientele.bcm.view",
                                       "clientele.bcm.prepare", "clientele.bcm.valider",
                                       "clientele.bcm.cloturer", "clientele.reporting.view",
                                       "clientele.view", "clientele.export"})


async def _importer(db, ctx) -> None:
    svc = ClienteleImportService(db, ctx)
    a = await svc.analyser(classeur(
        brute("000001", "00000100001"),
        brute("000001", "00000100002"),
        brute("000001", "00000100003"),
        brute("000002", "00000200001"),
    ), "juil-bcm.xlsx")
    await svc.confirmer(uuid.UUID(a["id"]), {"date_extraction": EXTRACTION.isoformat()})


def _cell(detail: dict, tableau: str, ligne: str, col: str) -> dict:
    tab = next(t for t in detail["cellules"]["tableaux"] if t["code"] == tableau)
    lig = next(row for row in tab["lignes"] if row["code"] == ligne)
    return lig["cellules"][col]


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
async def test_declaration_aout_stock_et_a_configurer(db):
    ctx = await _ctx(db)
    await _importer(db, ctx)
    await db.execute(text("""
        INSERT INTO clientele_classif_historique
            (id, racine_client, ancienne_classe, nouvelle_classe, source, motif_classement, created_at)
        VALUES
            (gen_random_uuid(), '000001', NULL, 'FAIBLE', 'MANUEL', 'test',
             '2026-07-01 12:00:00+00'),
            (gen_random_uuid(), '000002', NULL, 'ELEVE', 'MANUEL', 'test',
             '2026-08-10 12:00:00+00')
    """))
    await db.commit()
    svc = ClienteleDeclarationService(db, ctx)
    d = await svc.creer(2026, 8, aujourdhui=AUJ)
    assert d["statut"] == "BROUILLON"
    assert d["bcm_officielle"] is True
    cal = await svc.calculer(uuid.UUID(d["id"]), aujourdhui=AUJ)
    assert cal["statut"] == "CALCULEE"
    assert cal["cellules"]["grille_version"] == BCM_GRILLE_VERSION
    assert _cell(cal, "T1A", "stock_m1", "total")["valeur"] == 2
    assert _cell(cal, "T1A", "stock_m1", "pp")["valeur"] == 2
    assert _cell(cal, "T1A", "stock_m1", "cj")["valeur"] is None
    assert _cell(cal, "T1A", "stock_m1", "cj")["statut"] == "A_CONFIGURER"
    assert _cell(cal, "T1A", "cible", "total")["valeur"] is None
    assert _cell(cal, "T1A", "cible", "total")["statut"] == "A_CONFIGURER"
    assert _cell(cal, "T1A", "maj_mois", "total")["valeur"] == 0
    assert _cell(cal, "T1A", "maj_5ans", "total")["valeur"] is None
    assert _cell(cal, "T1B", "stock_m1", "faible")["valeur"] == 1
    assert _cell(cal, "T1B", "stock_m1", "eleve")["valeur"] == 0
    assert _cell(cal, "T1B", "stock_m1", "total")["valeur"] == 2
    assert _cell(cal, "T4", "eleve", "valeur")["valeur"] == 1
    assert _cell(cal, "T4", "faible", "valeur")["valeur"] == 1
    assert _cell(cal, "T4", "total", "valeur")["valeur"] == 2
    assert _cell(cal, "T4", "total", "ratio")["valeur"] == 100.0
    assert _cell(cal, "T2", "enregistrees", "valeur")["statut"] == "A_CONFIGURER"
    assert _cell(cal, "T3", "recues", "valeur")["statut"] == "A_CONFIGURER"
    fiche = _cell(cal, "T4", "eleve", "valeur")["fiche"]
    assert fiche["libelle_officiel"]
    assert fiche["source"] == "clientele_classif_historique"
    assert fiche["historique_utilise"] is True
    assert fiche["eer_utilise"] is False
    assert cal["controles"][0]["niveau"] in ("CONFORME", "ATTENTION", "ERREUR")
    identite = next(c for c in cal["controles"] if c["code"] == "identite_t4_t1")
    assert identite["bloquant"] is False
    assert identite["attendu"] == 0
    xlsx = await svc.exporter_xlsx(uuid.UUID(d["id"]))
    assert xlsx[:2] == b"PK"
    pdf = await svc.exporter_pdf(uuid.UUID(d["id"]))
    assert pdf[:4] == b"%PDF"


@pytest.mark.asyncio
async def test_mois_non_clos_et_snapshot_fige(db):
    ctx = await _ctx(db)
    await _importer(db, ctx)
    svc = ClienteleDeclarationService(db, ctx)
    oct_ = await svc.creer(2026, 10, aujourdhui=AUJ)
    assert oct_["simulation"] is True
    cal = await svc.calculer(uuid.UUID(oct_["id"]), aujourdhui=AUJ)
    cal = await svc.controler(uuid.UUID(cal["id"]))
    with pytest.raises(AppError) as err:
        await svc.valider(uuid.UUID(cal["id"]), aujourdhui=AUJ)
    assert err.value.code == "MOIS_NON_CLOS"

    aout = await svc.creer(2026, 8, aujourdhui=AUJ)
    aout = await svc.calculer(uuid.UUID(aout["id"]), aujourdhui=AUJ)
    aout = await svc.controler(uuid.UUID(aout["id"]))
    aout = await svc.valider(uuid.UUID(aout["id"]), aujourdhui=AUJ)
    assert aout["statut"] == "VALIDEE"
    assert aout["statut"] in STATUTS_FIGES
    with pytest.raises(AppError) as err:
        await svc.calculer(uuid.UUID(aout["id"]), aujourdhui=AUJ)
    assert err.value.code == "DECLARATION_FIGEE"
    with pytest.raises(AppError) as err:
        await svc.creer(2026, 8, aujourdhui=AUJ)
    assert err.value.code == "DECLARATION_EXISTANTE"
