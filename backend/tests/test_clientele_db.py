"""Base clientèle sur PostgreSQL : consolidation, idempotence, contraintes.

Ignoré tant que la migration ``20261008_clientele_01`` n'est pas appliquée.
Exécution : copie de la base (bea_digital_clientele_test). Chaque test est annulé à la fin.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.models import Agence, ClienteleClient, ClienteleCompte
from app.services.clientele.consolidation import consolider, lire_ligne
from app.services.clientele.persistance import ConsolidationRefusee, enregistrer
from tests.test_clientele_consolidation import brute, rib_pour

EXTRACTION = date(2026, 10, 7)
RACINES = ("000001", "000002")


@pytest.fixture
async def db():
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            pret = await conn.scalar(text("SELECT to_regclass('public.clientele_comptes') IS NOT NULL"))
    except Exception:
        pret = False
    if not pret:
        await engine.dispose()
        pytest.skip("Tables clientele_* absentes (migration 20261008_clientele_01 non appliquée)")
    session = async_sessionmaker(engine, expire_on_commit=False)()
    await session.execute(text("DELETE FROM clientele_comptes WHERE racine_client IN ('000001','000002')"))
    await session.execute(text("DELETE FROM clientele_clients WHERE racine_client IN ('000001','000002')"))
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


def _consolidation(*lignes: dict):
    return consolider(lire_ligne(b, i) for i, b in enumerate(lignes, 2))


SCENARIO = (
    brute("000001", "00000100001"),
    brute("000001", "00000100002"),
    brute("000001", "00000100003"),
    brute("000002", "00000200001"),
)


async def _compter(db) -> tuple[int, int, int]:
    clients = await db.scalar(select(func.count()).select_from(ClienteleClient)
                              .where(ClienteleClient.racine_client.in_(RACINES)))
    comptes, ribs = (await db.execute(select(func.count(), func.count(ClienteleCompte.rib.distinct()))
                                      .where(ClienteleCompte.racine_client.in_(RACINES)))).one()
    return clients, comptes, ribs


async def test_un_client_trois_comptes(db):
    bilan = await enregistrer(db, _consolidation(*SCENARIO[:3]), EXTRACTION)
    assert (bilan.clients_crees, bilan.comptes_crees) == (1, 3)
    assert await _compter(db) == (1, 3, 3)
    rib1 = await db.scalar(select(ClienteleCompte.rib).where(ClienteleCompte.compte == "00000100001"))
    assert rib1 == "00007000010000010000159"


async def test_deuxieme_client_count_clients_2_comptes_4(db):
    await enregistrer(db, _consolidation(*SCENARIO), EXTRACTION)
    assert await _compter(db) == (2, 4, 4)
    racines = (await db.execute(select(ClienteleCompte.racine_client, func.count())
                                .where(ClienteleCompte.racine_client.in_(RACINES))
                                .group_by(ClienteleCompte.racine_client))).all()
    assert dict(racines) == {"000001": 3, "000002": 1}


async def test_reimport_sans_duplication(db):
    await enregistrer(db, _consolidation(*SCENARIO), EXTRACTION)
    bilan = await enregistrer(db, _consolidation(*SCENARIO), date(2026, 10, 8))
    assert (bilan.clients_crees, bilan.clients_mis_a_jour, bilan.comptes_crees, bilan.comptes_mis_a_jour) == (0, 2, 0, 4)
    assert await _compter(db) == (2, 4, 4)
    client = await db.scalar(select(ClienteleClient).where(ClienteleClient.racine_client == "000001"))
    assert (client.premiere_extraction, client.date_extraction) == (EXTRACTION, date(2026, 10, 8))


async def test_extrait_plus_ancien_n_ecrase_pas(db):
    await enregistrer(db, _consolidation(*SCENARIO), EXTRACTION)
    ancien = brute("000001", "00000100001", ETAT_COMPTE="Fermé")
    bilan = await enregistrer(db, _consolidation(ancien), date(2026, 1, 1))
    assert (bilan.comptes_crees, bilan.comptes_mis_a_jour) == (0, 0)
    etat = await db.scalar(select(ClienteleCompte.etat_compte).where(ClienteleCompte.compte == "00000100001"))
    assert etat == "OUVERT"


async def test_compte_ne_change_pas_de_client(db):
    await enregistrer(db, _consolidation(*SCENARIO), EXTRACTION)
    with pytest.raises(ConsolidationRefusee, match="déjà rattaché au client 000001"):
        await enregistrer(db, _consolidation(brute("000002", "00000100001")), EXTRACTION)


async def test_lot_bloquant_refuse_en_entier(db):
    incoherent = _consolidation(brute("000001", "00000100001"), brute("000001", "00000100002", NATIONALITE="X"))
    with pytest.raises(ConsolidationRefusee):
        await enregistrer(db, incoherent, EXTRACTION)
    assert await _compter(db) == (0, 0, 0)


async def test_agence_inconnue_refusee(db):
    inconnue = brute("000001", "00000100001", CODE_AGENCE_COMPTE="99999", RIB=rib_pour("00000100001", "99999"))
    with pytest.raises(ConsolidationRefusee, match="agence inconnue : 99999"):
        await enregistrer(db, _consolidation(inconnue), EXTRACTION)


async def _refus(db, sql: str, params: dict) -> None:
    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(text(sql), params)


async def test_contraintes_postgresql(db):
    await enregistrer(db, _consolidation(*SCENARIO), EXTRACTION)
    agence_id = await db.scalar(select(Agence.id).where(Agence.code == "00001"))
    client_sql = ("INSERT INTO clientele_clients (id, racine_client, raison_sociale, premiere_extraction, "
                  "date_extraction) VALUES (:id, :r, 'X', :d, :d)")
    compte_sql = ("INSERT INTO clientele_comptes (id, compte, rib, racine_client, agence_id, etat_compte, devise, "
                  "premiere_extraction, date_extraction) VALUES (:id, :c, :rib, :r, :a, 'OUVERT', 'MRU', :d, :d)")
    base = {"d": EXTRACTION}

    for racine in ("00001", "0000001", "00000A"):
        await _refus(db, client_sql, {**base, "id": uuid.uuid4(), "r": racine})
    await _refus(db, client_sql, {**base, "id": uuid.uuid4(), "r": "000001"})

    nouveau = {**base, "id": uuid.uuid4(), "a": agence_id, "c": "00000300001", "rib": rib_pour("00000300001")}
    await _refus(db, compte_sql, {**nouveau, "r": "000003"})
    await _refus(db, compte_sql, {**nouveau, "r": "000001", "rib": rib_pour("00000100001")})
    await _refus(db, compte_sql, {**nouveau, "r": "000001", "rib": rib_pour("00000300002")})
    await _refus(db, compte_sql, {**nouveau, "r": "000001", "c": "00000100001"})
    await _refus(db, "DELETE FROM clientele_clients WHERE racine_client = :r", {"r": "000001"})
    await _refus(db, "UPDATE clientele_clients SET racine_client = '000009' WHERE racine_client = :r",
                 {"r": "000001"})
    assert await _compter(db) == (2, 4, 4)
