"""Sessions de simulation : aucune écriture possible, même par erreur ou appel indirect.

Exécution uniquement sur une copie dont le nom se termine par ``_test``.
"""

from __future__ import annotations

from types import SimpleNamespace

import asyncpg
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.db.lecture_seule import EcritureInterdite, creer_moteur_lecture_seule, fabrique_lecture_seule
from app.models import AuditLog, ClienteleClassifEvaluation, ClienteleClassification, ClienteleClient, User
from app.services.clientele.classification import ClienteleClassificationService
from app.services.clientele.service import Ctx

PERMS = {"clientele.view", "clientele.classif.view", "clientele.classif.execute"}
INSERT_BRUT = ("INSERT INTO clientele_clients (racine_client, raison_sociale, premiere_extraction, date_extraction) "
               "VALUES ('999999', 'INTRUS', CURRENT_DATE, CURRENT_DATE)")


@pytest.fixture
async def moteur():
    url = get_settings().database_url
    if not (make_url(url).database or "").endswith("_test"):
        pytest.skip("Tests réservés à une copie *_test de la base (jamais la base réelle)")
    m = creer_moteur_lecture_seule(url)
    try:
        yield m
    finally:
        await m.dispose()


@pytest.fixture
async def session(moteur):
    async with fabrique_lecture_seule(moteur)() as s:
        yield s


async def _compteurs() -> dict:
    m = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        async with m.connect() as c:
            return {
                "clients": await c.scalar(select(func.count()).select_from(ClienteleClient)),
                "evaluations": await c.scalar(select(func.count()).select_from(ClienteleClassifEvaluation)),
                "classifications": await c.scalar(select(func.count()).select_from(ClienteleClassification)),
                "audit": await c.scalar(select(func.count()).select_from(AuditLog)),
            }
    finally:
        await m.dispose()


async def test_connexion_postgres_en_lecture_seule(moteur):
    async with moteur.connect() as c:
        assert await c.scalar(text("SHOW default_transaction_read_only")) == "on"
        assert await c.scalar(text("SHOW transaction_read_only")) == "on"


@pytest.mark.parametrize("sql", [
    INSERT_BRUT,
    "UPDATE clientele_clients SET raison_sociale = 'X'",
    "DELETE FROM clientele_classification",
    "SET default_transaction_read_only = off",
    "SET TRANSACTION READ WRITE",
    "  update clientele_clients set raison_sociale = 'X'",
])
async def test_sql_brut_refuse_avant_la_base(session, sql):
    with pytest.raises(EcritureInterdite):
        await session.execute(text(sql))


async def test_postgres_refuse_meme_sans_sqlalchemy_et_apres_rollback(moteur):
    async with moteur.connect() as c:
        brute = (await c.get_raw_connection()).driver_connection
        for _ in range(2):
            with pytest.raises(asyncpg.exceptions.ReadOnlySQLTransactionError):
                await brute.execute(INSERT_BRUT)
            await c.rollback()
            assert await c.scalar(text("SHOW transaction_read_only")) == "on"


async def test_flush_et_commit_refuses(session):
    with pytest.raises(EcritureInterdite):
        await session.commit()
    await session.rollback()
    session.add(ClienteleClient(racine_client="999999", raison_sociale="INTRUS"))
    with pytest.raises(EcritureInterdite):
        await session.flush()


async def test_appels_indirects_du_moteur_refuses(session):
    avant = await _compteurs()
    user = await session.scalar(select(User).where(User.is_superuser.is_(False)).limit(1))
    if user is None:
        pytest.skip("Aucun utilisateur non superadmin dans la copie")
    racine = await session.scalar(
        select(ClienteleClient.racine_client)
        .where(~ClienteleClient.racine_client.in_(select(ClienteleClassification.racine_client)))
        .order_by(ClienteleClient.racine_client).limit(1))
    if racine is None:
        pytest.skip("Aucun client sans classification dans la copie")
    ctx = Ctx(user=SimpleNamespace(id=user.id, is_superuser=False), permissions=set(PERMS))
    svc = ClienteleClassificationService(session, ctx)

    ev = await svc.evaluer_racine(racine, persister=False)
    await session.rollback()

    with pytest.raises(EcritureInterdite):
        await svc.evaluer_racine(racine, persister=True)
    await session.rollback()

    ev = {**ev, "statut": "EVALUE", "niveau_final": "FAIBLE"}
    with pytest.raises(EcritureInterdite):
        await svc.ecrire_resultat_moteur(racine, ev, "Tentative indirecte")
    await session.rollback()

    with pytest.raises(EcritureInterdite):
        await svc.svc.audit("clientele.test", "clientele_client", racine, after={})
        await session.flush()
    await session.rollback()

    assert await _compteurs() == avant
