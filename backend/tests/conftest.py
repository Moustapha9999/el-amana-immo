import os

# Les tests vérifient les verrous de production, même si le conteneur tourne en mode test Achats.
os.environ["ACHATS_MODE_TEST"] = "0"

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()
