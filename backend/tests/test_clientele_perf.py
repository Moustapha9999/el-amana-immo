"""Performance : 40 000 clients simulés via staging SQL (skip sans CLIENTELE_PERF=1)."""

from __future__ import annotations

import os
import time
import uuid
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.models import ClienteleImport, ClienteleImportLigne
from app.services.clientele.consolidation import cle_rib
from app.services.clientele.persistance import enregistrer_depuis_staging

N = 40_000
EXTRACTION = date(2026, 10, 8)


def _rib(compte: str) -> str:
    return f"0000700001{compte}{cle_rib('00007', '00001', compte):02d}"


@pytest.mark.asyncio
@pytest.mark.skipif(not os.environ.get("CLIENTELE_PERF"), reason="CLIENTELE_PERF=1 pour lancer le test 40k")
async def test_upsert_sql_40000_clients():
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            pret = await conn.scalar(text("SELECT to_regclass('public.clientele_imports') IS NOT NULL"))
    except Exception:
        pret = False
    if not pret:
        await engine.dispose()
        pytest.skip("migration clientele_02 absente")
    session = async_sessionmaker(engine, expire_on_commit=False)()
    iid = uuid.uuid4()
    try:
        session.add(ClienteleImport(id=iid, fichier_nom="perf.xlsx", fichier_sha256="0" * 64,
                                    statut="ANALYSE", nb_lignes=N))
        await session.flush()
        lot: list[dict] = []
        for i in range(N):
            racine = f"{900000 + i:06d}"
            compte = f"{racine}00001"
            lot.append({
                "id": uuid.uuid4(), "import_id": iid, "numero_ligne": i + 2, "statut_ligne": "VALIDE",
                "racine_client": racine, "raison_sociale": f"CLIENT {racine}",
                "compte": compte, "rib": _rib(compte), "code_agence": "00001",
                "etat_compte": "OUVERT", "devise": "MRU",
            })
            if len(lot) == 2000:
                await session.execute(pg_insert(ClienteleImportLigne.__table__), lot)
                lot = []
        if lot:
            await session.execute(pg_insert(ClienteleImportLigne.__table__), lot)
        t0 = time.perf_counter()
        bilan = await enregistrer_depuis_staging(session, iid, EXTRACTION)
        elapsed = time.perf_counter() - t0
        assert (bilan.clients_crees, bilan.comptes_crees) == (N, N)
        assert elapsed < 60, f"upsert 40k trop lent : {elapsed:.1f}s"
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()
