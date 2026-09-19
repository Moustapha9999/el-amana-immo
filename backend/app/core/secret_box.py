"""Chiffrement at-rest pour secrets MFA (Fernet dérivé de SECRET_KEY)."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

_PREFIX = "enc:v1:"


def _fernet() -> Fernet:
    digest = hashlib.sha256(get_settings().secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def seal(plaintext: str | None) -> str | None:
    if not plaintext:
        return plaintext
    if plaintext.startswith(_PREFIX):
        return plaintext
    token = _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")
    return f"{_PREFIX}{token}"


def open_secret(stored: str | None) -> str | None:
    """Déchiffre si préfixe enc:v1:, sinon retourne tel quel (migration douce)."""
    if not stored:
        return stored
    if not stored.startswith(_PREFIX):
        return stored
    raw = stored[len(_PREFIX) :]
    try:
        return _fernet().decrypt(raw.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None
