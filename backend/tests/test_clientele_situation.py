"""Vues Situation PP / PM : COUNT DISTINCT racine, pas de copie, profil dérivé documenté."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.models import ClienteleSituation, User
from app.services.clientele.consolidation import lire_ligne
from app.services.clientele.persistance import enregistrer
from app.services.clientele.service import Ctx
from app.services.clientele.situation import ClienteleSituationService
from tests.test_clientele_consolidation import brute

EXTRACTION = date(2026, 10, 8)
RACINES = ("000001", "000002", "000003")


@pytest.fixture
async def db():
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            pret = await conn.scalar(text("SELECT to_regclass('public.clientele_situation') IS NOT NULL"))
    except Exception:
        pret = False
    if not pret:
        await engine.dispose()
        pytest.skip("Vue clientele_situation absente (migration 20261008_clientele_02)")
    session = async_sessionmaker(engine, expire_on_commit=False)()
    await session.execute(text("DELETE FROM clientele_comptes WHERE racine_client IN ('000001','000002','000003')"))
    await session.execute(text("DELETE FROM clientele_clients WHERE racine_client IN ('000001','000002','000003')"))
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


def _cons(*lignes: dict):
    from app.services.clientele.consolidation import consolider
    return consolider(lire_ligne(b, i) for i, b in enumerate(lignes, 2))


@pytest.mark.asyncio
async def test_situation_count_distinct_et_profil(db):
    await enregistrer(db, _cons(
        brute("000001", "00000100001"),
        brute("000001", "00000100002"),
        brute("000002", "00000200001", AGENT_ECONOMIQUE="AUTRES SOCIETES",
              CATEGORIE_JURIDIQUE="SOCIETE COMMERCIALE", TYPE_IDENTIFIANT="NIF",
              IDENTIFIANT_LISTE="123456"),
        brute("000003", "00000300001", ETAT_COMPTE="Fermé"),
    ), EXTRACTION)
    await db.flush()

    n = await db.scalar(select(func.count()).select_from(ClienteleSituation)
                        .where(ClienteleSituation.racine_client.in_(RACINES)))
    assert n == 3
    pp = await db.scalar(select(ClienteleSituation.profil_derive)
                         .where(ClienteleSituation.racine_client == "000001"))
    pm = await db.scalar(select(ClienteleSituation.profil_derive)
                         .where(ClienteleSituation.racine_client == "000002"))
    assert pp == "PP"
    assert pm == "PM"
    etat = await db.scalar(select(ClienteleSituation.etat_client)
                           .where(ClienteleSituation.racine_client == "000003"))
    assert etat == "CLOTURE"
    comptes = await db.scalar(select(ClienteleSituation.nb_comptes)
                              .where(ClienteleSituation.racine_client == "000001"))
    assert comptes == 2

    user = await db.scalar(select(User).limit(1))
    if not user:
        pytest.skip("aucun utilisateur")
    svc = ClienteleSituationService(db, Ctx(user=user, permissions={"clientele.view"}))
    pp = await svc.lister(profil="PP", racine="000001")
    assert pp["total"] == 1 and pp["items"][0]["profil_derive"] == "PP"
    pm = await svc.lister(profil="PM", racine="000002")
    assert pm["total"] == 1 and pm["items"][0]["profil_derive"] == "PM"
    cloture = await svc.lister(etat="CLOTURE", racine="000003")
    assert cloture["items"][0]["etat_client"] == "CLOTURE"
    fiche = await svc.fiche("000001")
    assert len(fiche["comptes"]) == 2
    assert fiche["situation"]["nb_comptes"] == 2
