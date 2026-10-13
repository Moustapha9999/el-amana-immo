"""Utilitaires partagés du module Réclamations (texte, dates, erreurs, audit)."""

from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import User
from app.services.audit_service import AuditService
from app.services.reclamations.acces import ReclamationsScope
from app.services.reclamations.constantes import ESPACE_CODE, MODULE_CODE


def maintenant() -> datetime:
    return datetime.now(UTC)


def propre(texte: str | None) -> str:
    return re.sub(r"\s+", " ", (texte or "").strip())


def texte_long(texte: str | None) -> str | None:
    """Texte multi-lignes : espaces de bord retirés, retours à la ligne conservés."""
    t = (texte or "").strip()
    return t or None


def cle(texte: str | None) -> str:
    """Clé de comparaison : minuscules, sans accents ni ponctuation, espaces réduits."""
    s = unicodedata.normalize("NFKD", texte or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def code_propre(code: str | None) -> str | None:
    c = re.sub(r"[^A-Z0-9_]+", "_", propre(code).upper()).strip("_")
    return c or None


def erreur(message: str, code: str, status_code: int = 422) -> AppError:
    return AppError(message, status_code, code=code)


def conflit(message: str, code: str, **extra: Any) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, detail={"code": code, "message": message, **extra})


def iso(v: datetime | date | None) -> str | None:
    return v.isoformat() if v else None


def serialisable(v: Any) -> Any:
    if isinstance(v, datetime | date):
        return v.isoformat()
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, Decimal):
        return str(v)
    return v


async def noms_utilisateurs(db: AsyncSession, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    rows = (await db.execute(select(User.id, User.full_name, User.email).where(User.id.in_(ids)))).all()
    return {i: (n or e) for i, n, e in rows}


async def auditer(db: AsyncSession, s: ReclamationsScope, action: str, entity: str, entity_id: Any, *,
                  before: dict | None = None, after: dict | None = None) -> None:
    await AuditService(db).log(
        user=s.user, action=action, entity=entity, entity_id=str(entity_id) if entity_id else None,
        before=before, after=after, ip_address=s.ip_address, espace_code=ESPACE_CODE,
        module_code=MODULE_CODE, session_id=s.session_id,
    )
