"""Session SQLAlchemy synchrone — workers Celery (OCR, etc.)."""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def _sync_database_url(async_url: str) -> str:
    url = async_url.strip()
    if "+asyncpg" in url:
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)
    if url.startswith("postgresql+psycopg2://"):
        return url
    return url


@lru_cache
def _sync_engine():
    settings = get_settings()
    return create_engine(
        _sync_database_url(settings.database_url),
        pool_pre_ping=True,
        future=True,
    )


@lru_cache
def _sync_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=_sync_engine(), autoflush=False, autocommit=False, future=True)


def sync_session() -> Session:
    return _sync_session_factory()()
