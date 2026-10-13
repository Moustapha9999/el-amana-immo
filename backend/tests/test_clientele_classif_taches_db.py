"""Tâche de classement de masse SCORE (progression serveur, filtres PP/PM, reprise) sur PostgreSQL.

Exécution uniquement sur une copie jetable dont le nom se termine par ``_test``, migration
``20261013_clientele_10`` appliquée : la tâche de fond valide réellement ses paquets (commits).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.db.session import AsyncSessionLocal, engine
from app.models import ClienteleClassifTache, ClienteleClient, ClienteleSituation, User
from app.services.clientele import taches
from app.services.clientele.service import Ctx, maintenant
from app.services.clientele.taches import ClienteleTacheService

pytestmark = pytest.mark.usefixtures("masse_autorisee")

PERMS = {"clientele.view", "clientele.classif.view", "clientele.classif.execute"}


@pytest.fixture
async def db():
    if not (make_url(get_settings().database_url).database or "").endswith("_test"):
        pytest.skip("Tests réservés à une copie *_test de la base (jamais la base réelle)")
    async with AsyncSessionLocal() as session:
        if not await session.scalar(text("SELECT to_regclass('public.clientele_classif_taches') IS NOT NULL")):
            pytest.skip("Migration 20261013_clientele_10 non appliquée")
        await session.execute(text("DELETE FROM clientele_classif_taches"))
        await session.commit()
        yield session
    await engine.dispose()


async def _ctx(db) -> Ctx:
    user = await db.scalar(select(User).where(User.is_superuser.is_(True)).limit(1))
    if not user:
        pytest.skip("Aucun utilisateur administrateur dans la copie")
    return Ctx(user=user, permissions=PERMS)


async def _petite_agence(db, profil: str) -> tuple[str, int]:
    row = (await db.execute(
        select(ClienteleSituation.code_agence, func.count())
        .join(ClienteleClient, ClienteleClient.racine_client == ClienteleSituation.racine_client)
        .where(ClienteleSituation.profil_derive == profil, ClienteleSituation.code_agence.is_not(None))
        .group_by(ClienteleSituation.code_agence).having(func.count() >= 3)
        .order_by(func.count()).limit(1))).first()
    if not row:
        pytest.skip(f"Aucune agence avec des clients {profil}")
    return row[0], int(row[1])


async def _attendre(tid: str) -> dict:
    tache = taches._EN_COURS.get(uuid.UUID(tid))
    if tache:
        await asyncio.wait_for(tache, timeout=600)
    async with AsyncSessionLocal() as s:
        return taches.tache_dict(await s.get(ClienteleClassifTache, uuid.UUID(tid)))


async def test_perimetre_compte_pp_pm(db):
    p = await ClienteleTacheService(db, await _ctx(db)).perimetre()
    total = await db.scalar(select(func.count()).select_from(ClienteleClient))
    assert p["TOUS"] == total == p["PP"] + p["PM"] + p["NON_IDENTIFIE"]


@pytest.mark.parametrize("profil", ["PP", "PM"])
async def test_tache_filtre_profil_et_progression_reelle(db, profil):
    agence, attendu = await _petite_agence(db, profil)
    svc = ClienteleTacheService(db, await _ctx(db))
    lancee = await svc.lancer({"motif": "Test tâche", "population": profil, "code_agence": agence})
    assert lancee["total"] == attendu and lancee["population"] == profil
    fin = await _attendre(lancee["id"])
    assert fin["statut"] in ("TERMINE", "TERMINE_ERREURS")
    assert fin["traites"] == fin["total"] == attendu and fin["pourcentage"] == 100.0
    assert sum(fin["bilan"].values()) == attendu
    r = fin["resume"]
    assert r["classes"] + r["preserves"] + r["non_classes"] + r["erreurs"] == attendu


async def test_une_seule_tache_active_et_reprise_apres_interruption(db):
    agence, attendu = await _petite_agence(db, "PM")
    ctx = await _ctx(db)
    premiere = (await db.scalars(
        select(ClienteleClient.racine_client).join(
            ClienteleSituation, ClienteleSituation.racine_client == ClienteleClient.racine_client)
        .where(ClienteleSituation.profil_derive == "PM", ClienteleSituation.code_agence == agence)
        .order_by(ClienteleClient.racine_client).limit(1))).one()
    vieille = maintenant() - timedelta(minutes=10)
    t = ClienteleClassifTache(statut="EN_COURS", profil="PM", code_agence=agence, motif="Test reprise",
                              total=attendu, traites=1, bilan={"INCHANGE": 1}, erreurs=[], curseur=premiere,
                              created_by_id=ctx.user.id, created_at=vieille, debut=vieille, maj_le=vieille)
    db.add(t)
    await db.commit()

    svc = ClienteleTacheService(db, ctx)
    courante = await svc.courante()
    assert courante["id"] == str(t.id) and courante["statut"] == "INTERROMPU" and courante["reprenable"]
    await db.commit()

    repris = await svc.reprendre(t.id)
    fin = await _attendre(repris["id"])
    assert fin["statut"] in ("TERMINE", "TERMINE_ERREURS")
    assert fin["traites"] == attendu and sum(fin["bilan"].values()) == attendu


async def test_lancement_refuse_si_tache_active(db):
    ctx = await _ctx(db)
    db.add(ClienteleClassifTache(statut="EN_COURS", motif="En cours", total=10, traites=2, bilan={}, erreurs=[],
                                 created_by_id=ctx.user.id, created_at=maintenant(), maj_le=maintenant()))
    await db.commit()
    with pytest.raises(AppError) as err:
        await ClienteleTacheService(db, ctx).lancer({"motif": "Doublon", "population": "PP"})
    assert err.value.status_code == 409 and err.value.code == "TACHE_EN_COURS"
    await db.rollback()
    await db.execute(text("DELETE FROM clientele_classif_taches"))
    await db.commit()


async def test_population_invalide_refusee(db):
    with pytest.raises(AppError) as err:
        await ClienteleTacheService(db, await _ctx(db)).lancer({"motif": "x", "population": "NON_IDENTIFIE"})
    assert err.value.status_code == 422
