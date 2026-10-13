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
def masse_autorisee(monkeypatch):
    """Ouvre le verrou du classement de masse pour un test (copie de base *_test uniquement)."""
    s = get_settings()
    monkeypatch.setattr(s, "clientele_classement_masse_actif", True)
    monkeypatch.setattr(s, "clientele_classement_masse_validation", "TEST-PYTEST")
    return s
