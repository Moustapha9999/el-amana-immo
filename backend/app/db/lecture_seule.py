"""Sessions en lecture seule garantie (simulations, rapports).

Trois verrous indépendants :
- PostgreSQL : chaque connexion ouvre ses transactions en ``default_transaction_read_only = on`` — y compris
  après un commit ou un rollback, et pour tout SQL brut ; INSERT / UPDATE / DELETE / DDL sont refusés ;
- moteur : seules les requêtes SELECT / WITH / SHOW partent vers la base ; un ``SET`` qui lèverait le
  verrou PostgreSQL (``SET default_transaction_read_only = off``, ``SET TRANSACTION READ WRITE``) est refusé ;
- SQLAlchemy : tout ``flush`` ou ``commit`` lève ``EcritureInterdite`` avant d'atteindre la base, même si
  un service appelé indirectement ajoute un objet (photographie d'évaluation, audit…).
"""
from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.db.ssl_context import build_asyncpg_ssl_context


class EcritureInterdite(RuntimeError):
    pass


class _SessionLectureSeule(Session):
    pass


@event.listens_for(_SessionLectureSeule, "before_flush")
def _refuser_flush(session, _ctx, _instances) -> None:
    if session.new or session.dirty or session.deleted:
        raise EcritureInterdite("Session en lecture seule : aucune écriture n'est autorisée (simulation).")


@event.listens_for(_SessionLectureSeule, "before_commit")
def _refuser_commit(_session) -> None:
    raise EcritureInterdite("Session en lecture seule : commit interdit (simulation).")


def creer_moteur_lecture_seule(url: str | None = None) -> AsyncEngine:
    connect_args: dict = {"server_settings": {"default_transaction_read_only": "on"}}
    ssl = build_asyncpg_ssl_context()
    if ssl is not False:
        connect_args["ssl"] = ssl
    moteur = create_async_engine(url or get_settings().database_url, poolclass=NullPool, connect_args=connect_args)
    event.listen(moteur.sync_engine, "before_cursor_execute", _refuser_requete)
    return moteur


_REQUETES_LECTURE = ("SELECT", "WITH", "SHOW")


def _refuser_requete(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
    mot = statement.lstrip(" \t\r\n(").split(None, 1)[0].upper() if statement.strip() else ""
    if mot not in _REQUETES_LECTURE:
        raise EcritureInterdite(f"Session en lecture seule : requête {mot or '(vide)'} refusée (simulation).")


def fabrique_lecture_seule(moteur: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(moteur, class_=AsyncSession, sync_session_class=_SessionLectureSeule,
                              expire_on_commit=False, autoflush=False)
