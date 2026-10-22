"""Celery — contrôle quotidien des seuils de stock (rattrapage, idempotent)."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _run() -> dict:
    from app.db.ssl_context import build_asyncpg_ssl_context
    from app.services.mg_stock_alertes import MgStockAlerteService

    ssl = build_asyncpg_ssl_context()
    engine = create_async_engine(
        get_settings().database_url,
        poolclass=NullPool,
        connect_args={"ssl": ssl} if ssl is not False else {},
    )
    try:
        async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
            resultat = await MgStockAlerteService(session).controle()
            await session.commit()
            return {k: str(v) for k, v in resultat.items()}
    finally:
        await engine.dispose()


@celery_app.task(name="app.workers.tasks_stock.controle_seuils")
def controle_seuils() -> dict:
    result = asyncio.run(_run())
    logger.info("contrôle seuils stock : %s", result)
    return result
