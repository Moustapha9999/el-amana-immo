"""Contexte de requête transversal : identifiant de corrélation (request_id)."""

from __future__ import annotations

import re
import secrets
from contextvars import ContextVar
from datetime import datetime, timezone

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_INCOMING = re.compile(r"^[A-Za-z0-9._-]{8,64}$")

_request_id: ContextVar[str | None] = ContextVar("bea_request_id", default=None)


def new_request_id() -> str:
    """Format lisible support : REQ-2026-09-29-8F72A1."""
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"REQ-{day}-{secrets.token_hex(3).upper()}"


def accept_or_create(incoming: str | None) -> str:
    if incoming and _VALID_INCOMING.match(incoming):
        return incoming
    return new_request_id()


def set_request_id(value: str | None):
    return _request_id.set(value)


def reset_request_id(token) -> None:
    _request_id.reset(token)


def current_request_id() -> str | None:
    return _request_id.get()
