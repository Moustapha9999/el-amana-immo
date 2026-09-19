"""Génération de mots de passe temporaires conformes à la politique."""

from __future__ import annotations

import secrets
import string

from app.core.password_policy import validate_password_policy


def generate_temporary_password(length: int = 16) -> str:
    """Produit un mot de passe aléatoire valide (politique serveur)."""
    length = max(12, min(64, int(length)))
    alphabet = string.ascii_letters + string.digits + "!@#$%&*-_=+"
    for _ in range(40):
        chars = [
            secrets.choice(string.ascii_uppercase),
            secrets.choice(string.ascii_lowercase),
            secrets.choice(string.digits),
            secrets.choice("!@#$%&*-_=+"),
        ]
        chars += [secrets.choice(alphabet) for _ in range(length - 4)]
        secrets.SystemRandom().shuffle(chars)
        candidate = "".join(chars)
        try:
            validate_password_policy(candidate)
            return candidate
        except ValueError:
            continue
    # Dernier recours déterministe (toujours conforme à la politique par défaut)
    return "Tmp#" + secrets.token_hex(6) + "Aa1!"
