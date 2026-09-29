"""Enregistre les erreurs API vues par les utilisateurs (supervision CORE ADMIN).

Jamais de corps de requête, mot de passe, token ni secret : uniquement le
message utilisateur standard, le code, la route et le request_id.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.db.session import AsyncSessionLocal
from app.models.supervision import ApiErrorEvent

log = logging.getLogger(__name__)

# 401 (session expirée) et 404 sont trop bruyants pour la supervision.
RECORDED_STATUSES = frozenset({403, 409, 422, 429})

_pending: set[asyncio.Task] = set()


def should_record(path: str, status_code: int) -> bool:
    return path.startswith("/api/") and (status_code >= 500 or status_code in RECORDED_STATUSES)


async def _write(fields: dict[str, Any]) -> None:
    try:
        async with AsyncSessionLocal() as db:
            db.add(ApiErrorEvent(**fields))
            await db.commit()
    except Exception:  # la supervision ne doit jamais casser une requête
        log.warning("api_error_event non enregistré request_id=%s", fields.get("request_id"), exc_info=True)


def record_api_error(**fields: Any) -> None:
    """Écriture en tâche de fond, hors transaction métier."""
    for key, limit in (("route", 255), ("message", 500), ("code", 60), ("exception_type", 120)):
        value = fields.get(key)
        if isinstance(value, str) and len(value) > limit:
            fields[key] = value[:limit]
    task = asyncio.create_task(_write(fields))
    _pending.add(task)
    task.add_done_callback(_pending.discard)
