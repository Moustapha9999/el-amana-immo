from sqlalchemy.engine import make_url

from app.core.config import Settings


def _url(raw: str):
    return make_url(Settings(DATABASE_URL=raw).database_url)


def test_mot_de_passe_brut_avec_arobase_est_encode():
    url = _url("postgresql+asyncpg://admin:Exemple@Mdp1@postgres:5432/bea_digital")
    assert (url.username, url.password, url.host, url.database) == ("admin", "Exemple@Mdp1", "postgres", "bea_digital")


def test_mot_de_passe_deja_encode_reste_identique():
    raw = "postgresql+asyncpg://admin:Exemple%40Mdp1@postgres:5432/bea_digital"
    assert Settings(DATABASE_URL=raw).database_url == raw


def test_url_simple_inchangee():
    raw = "postgresql+asyncpg://user:secret@localhost:5432/db"
    assert Settings(DATABASE_URL=raw).database_url == raw
