import os

import pytest

# Les tests vérifient les verrous de production, même si le conteneur tourne en mode test Achats.
os.environ["ACHATS_MODE_TEST"] = "0"
# Idem pour le verrou du classement de masse : fermé par défaut, ouvert explicitement par test.
os.environ["CLIENTELE_CLASSEMENT_MASSE_ACTIF"] = "0"
os.environ["CLIENTELE_CLASSEMENT_MASSE_VALIDATION"] = ""

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()


@pytest.fixture
async def base_jetable():
    """Tests qui créent des comptes : copie de base uniquement, jamais la base réelle bea_digital."""
    from sqlalchemy import text

    from app.db.session import engine

    try:
        async with engine.connect() as conn:
            base = await conn.scalar(text("SELECT current_database()"))
    except Exception:
        pytest.skip("Base PostgreSQL indisponible")
    if base == "bea_digital":
        pytest.skip("Crée des comptes utilisateurs : copie de base requise (jamais bea_digital)")


@pytest.fixture
def masse_autorisee(monkeypatch):
    """Ouvre le verrou du classement de masse pour un test (copie de base *_test uniquement)."""
    s = get_settings()
    monkeypatch.setattr(s, "clientele_classement_masse_actif", True)
    monkeypatch.setattr(s, "clientele_classement_masse_validation", "TEST-PYTEST")
    return s
