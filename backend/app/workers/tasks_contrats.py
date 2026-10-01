"""Celery — rappels quotidiens Contrats & échéances (notification in-app + e-mail si SMTP)."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _run() -> dict:
    from app.services.mg_contrats_service import MgContratsService

    from app.db.ssl_context import build_asyncpg_ssl_context

    ssl = build_asyncpg_ssl_context()
    engine = create_async_engine(
        get_settings().database_url,
        poolclass=NullPool,
        connect_args={"ssl": ssl} if ssl is not False else {},
    )
    try:
        async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
            return await MgContratsService(session).envoyer_rappels()
    finally:
        await engine.dispose()


@celery_app.task(name="app.workers.tasks_contrats.rappels_contrats")
def rappels_contrats() -> dict:
    result = asyncio.run(_run())
    logger.info("rappels contrats : %s", result)
    return result
