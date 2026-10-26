"""SECRET_KEY faible : démarrage refusé hors développement (forge de JWT sinon)."""

import pytest
from pydantic import ValidationError

from app.core.config import DEFAULT_SECRET_KEY, Settings

CLE_FORTE = "k" * 48


def _settings(monkeypatch, **valeurs) -> Settings:
    for nom in ("APP_ENV", "SECRET_KEY"):
        monkeypatch.delenv(nom, raising=False)
    return Settings(_env_file=None, **valeurs)


@pytest.mark.parametrize("env", ["production", "staging", "test-banque"])
@pytest.mark.parametrize("cle", [DEFAULT_SECRET_KEY, "", "trop-courte", "x" * 31, f"  {DEFAULT_SECRET_KEY}  "])
def test_cle_faible_refusee_hors_dev(monkeypatch, env, cle):
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        _settings(monkeypatch, APP_ENV=env, SECRET_KEY=cle)


def test_cle_absente_refusee_en_production(monkeypatch):
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        _settings(monkeypatch, APP_ENV="production")


def test_cle_forte_acceptee_en_production(monkeypatch):
    assert _settings(monkeypatch, APP_ENV="production", SECRET_KEY=CLE_FORTE).secret_key == CLE_FORTE


@pytest.mark.parametrize("env", ["development", "test"])
def test_cle_par_defaut_toleree_en_dev(monkeypatch, env):
    assert _settings(monkeypatch, APP_ENV=env).secret_key == DEFAULT_SECRET_KEY
