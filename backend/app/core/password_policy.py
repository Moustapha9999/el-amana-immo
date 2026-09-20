"""Politique de mots de passe — validation serveur (pas de stockage en clair)."""

from __future__ import annotations

import re
from typing import Any

from app.services.security_policy_service import get_cached_security_policy

_SPECIAL = re.compile(r"[^A-Za-z0-9]")


def validate_password_policy(password: str) -> None:
    """Lève ValueError si le mot de passe ne respecte pas la politique effective."""
    pol = get_cached_security_policy()
    pwd = password or ""
    min_len = max(8, int(pol.get("password_min_length") or 8))
    if len(pwd) < min_len:
        raise ValueError(f"Le mot de passe doit contenir au moins {min_len} caractères.")
    if pol.get("password_require_uppercase") and not any(c.isupper() for c in pwd):
        raise ValueError("Le mot de passe doit contenir au moins une majuscule.")
    if pol.get("password_require_lowercase") and not any(c.islower() for c in pwd):
        raise ValueError("Le mot de passe doit contenir au moins une minuscule.")
    if pol.get("password_require_digit") and not any(c.isdigit() for c in pwd):
        raise ValueError("Le mot de passe doit contenir au moins un chiffre.")
    if pol.get("password_require_special") and not _SPECIAL.search(pwd):
        raise ValueError("Le mot de passe doit contenir au moins un caractère spécial.")


def password_policy_summary() -> dict[str, Any]:
    pol = get_cached_security_policy()
    return {
        "min_length": max(8, int(pol.get("password_min_length") or 8)),
        "require_uppercase": bool(pol.get("password_require_uppercase")),
        "require_lowercase": bool(pol.get("password_require_lowercase")),
        "require_digit": bool(pol.get("password_require_digit")),
        "require_special": bool(pol.get("password_require_special")),
        "hash_algorithm": "bcrypt",
        "history_reuse_current_forbidden": True,
    }
