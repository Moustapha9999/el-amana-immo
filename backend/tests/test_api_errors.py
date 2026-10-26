"""Handlers d'erreur centralisés : statut HTTP réel, pas de fuite technique."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from app.core.api_errors import classify_database_error, error_body, install_error_handlers
from app.core.exceptions import AppError
from app.core.request_context import REQUEST_ID_HEADER


class _Saisie(BaseModel):
    email: EmailStr
    nom: str = Field(min_length=2)


def _app() -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/not-found")
    def not_found():
        raise HTTPException(status_code=404, detail="Not Found")

    @app.get("/forbidden")
    def forbidden():
        raise HTTPException(
            status_code=403,
            detail={"code": "PERMISSION_DENIED", "message": "Permission insuffisante pour valider."},
        )

    @app.get("/conflict")
    def conflict():
        raise AppError("Cette donnée a été modifiée par un autre utilisateur.", 409, code="CONFLIT_REVISION")

    @app.post("/saisie")
    def saisie(_body: _Saisie):
        return {"ok": True}

    @app.get("/identifiants")
    def identifiants():
        raise AppError(
            "Adresse e-mail ou mot de passe incorrect.",
            401,
            code="AUTH_INVALID_CREDENTIALS",
        )

    @app.get("/expire")
    def expire():
        raise HTTPException(
            status_code=401,
            detail={"code": "PLATFORM_SESSION_EXPIRED", "message": "Session expirée ou révoquée"},
        )

    @app.get("/sans-jeton")
    def sans_jeton():
        raise HTTPException(status_code=401, detail={"code": "UNAUTHENTICATED", "message": "Non authentifié"})

    @app.get("/compte-perdu")
    def compte_perdu():
        raise HTTPException(status_code=401, detail={"code": "USER_NOT_FOUND", "message": "Utilisateur introuvable"})

    @app.get("/boom")
    def boom():
        raise RuntimeError("secret=hunter2 traceback /var/app/secret.py SELECT * FROM users")

    @app.get("/http-500")
    def http_500():
        raise HTTPException(status_code=500, detail="psycopg2.OperationalError: password authentication failed")

    @app.get("/integrity")
    def integrity():
        orig = MagicMock()
        orig.sqlstate = "23505"
        raise IntegrityError("INSERT", {}, orig)

    @app.get("/fk")
    def fk():
        orig = MagicMock()
        orig.sqlstate = "23503"
        raise IntegrityError("INSERT", {}, orig)

    @app.get("/db-down")
    def db_down():
        orig = MagicMock()
        orig.sqlstate = "08006"
        raise OperationalError("SELECT 1", {}, orig)

    @app.get("/deadlock")
    def deadlock():
        orig = MagicMock()
        orig.sqlstate = "40P01"
        raise OperationalError("UPDATE", {}, orig)

    @app.get("/pool")
    def pool():
        raise PoolTimeoutError("QueuePool limit of size 5 overflow 10 reached")

    @app.get("/timeout-sql")
    def timeout_sql():
        orig = MagicMock()
        orig.sqlstate = "57014"
        raise OperationalError("SELECT", {}, orig)

    return app


client = TestClient(_app(), raise_server_exceptions=False)


def _assert_enveloppe(body: dict, *, status: int, code: str) -> None:
    assert body["success"] is False
    assert body["status"] == status
    assert body["code"] == code
    assert body["title"]
    assert body["message"]
    assert body["user_message"] == body["message"]
    assert body["type"] == "about:blank"
    assert isinstance(body["errors"], list)
    assert "request_id" in body


def test_404_phrase_starlette_remplacee_par_message_fr():
    r = client.get("/not-found")
    assert r.status_code == 404
    body = r.json()
    _assert_enveloppe(body, status=404, code="NOT_FOUND")
    assert "introuvable" in body["message"].lower()
    assert body["detail"] != "Not Found"
    assert "Not Found" not in r.text


def test_403_conserve_code_et_message_metier():
    r = client.get("/forbidden")
    assert r.status_code == 403
    body = r.json()
    _assert_enveloppe(body, status=403, code="PERMISSION_DENIED")
    assert "Permission insuffisante" in body["message"]
    assert body["detail"]["code"] == "PERMISSION_DENIED"


def test_409_app_error_metier():
    r = client.get("/conflict")
    assert r.status_code == 409
    body = r.json()
    _assert_enveloppe(body, status=409, code="CONFLIT_REVISION")
    assert "modifiée" in body["message"]
    assert body["title"] == "Conflit de données"


def test_422_json_malformed_sans_position():
    r = client.post("/saisie", content=b"{", headers={"content-type": "application/json"})
    assert r.status_code == 422
    body = r.json()
    _assert_enveloppe(body, status=422, code="VALIDATION_ERROR")
    assert body["errors"][0]["field"] is None
    assert "mal formé" in body["message"].lower() or "invalide" in body["errors"][0]["message"].lower()
    assert " : " not in body["message"][:4]


def test_422_validation_champs_sans_valeur_saisie():
    r = client.post("/saisie", json={"email": "pas-un-email", "nom": "A"})
    assert r.status_code == 422
    body = r.json()
    _assert_enveloppe(body, status=422, code="VALIDATION_ERROR")
    champs = {e["field"] for e in body["errors"]}
    assert "email" in champs
    assert "nom" in champs
    dumped = r.text.lower()
    assert "pas-un-email" not in dumped
    assert "input" not in dumped
    assert any("caractère" in e["message"] for e in body["errors"] if e["field"] == "nom")


def test_401_identifiants_uniforme():
    r = client.get("/identifiants")
    assert r.status_code == 401
    body = r.json()
    _assert_enveloppe(body, status=401, code="AUTH_INVALID_CREDENTIALS")
    assert "incorrect" in body["message"].lower()
    assert "existe" not in body["message"].lower()


def test_401_session_expiree_code_stable():
    r = client.get("/expire")
    assert r.status_code == 401
    body = r.json()
    _assert_enveloppe(body, status=401, code="PLATFORM_SESSION_EXPIRED")
    assert r.headers.get(REQUEST_ID_HEADER)
    assert "session" in body["message"].lower()


def test_401_phrases_techniques_remplacees_sans_enumerer_le_compte():
    r = client.get("/sans-jeton")
    assert r.status_code == 401
    body = r.json()
    _assert_enveloppe(body, status=401, code="UNAUTHENTICATED")
    assert "session" in body["message"].lower()
    assert "non authentifié" not in body["message"].lower()

    r = client.get("/compte-perdu")
    assert r.status_code == 401
    body = r.json()
    _assert_enveloppe(body, status=401, code="USER_NOT_FOUND")
    assert "introuvable" not in body["message"].lower()
    assert "existe" not in body["message"].lower()


def test_500_inattendu_sans_fuite():
    r = client.get("/boom")
    assert r.status_code == 500
    body = r.json()
    _assert_enveloppe(body, status=500, code="INTERNAL_ERROR")
    texte = r.text.lower()
    assert "hunter2" not in texte
    assert "traceback" not in texte
    assert "secret.py" not in texte
    assert "select * from" not in texte
    assert "inattendue" in body["message"].lower()


def test_http_500_detail_technique_masque():
    r = client.get("/http-500")
    assert r.status_code == 500
    body = r.json()
    _assert_enveloppe(body, status=500, code="INTERNAL_ERROR")
    assert "password" not in r.text.lower()
    assert "psycopg" not in r.text.lower()


def test_integrity_unicite_409():
    r = client.get("/integrity")
    assert r.status_code == 409
    _assert_enveloppe(r.json(), status=409, code="DUPLICATE")


def test_integrity_fk_400():
    r = client.get("/fk")
    assert r.status_code == 400
    _assert_enveloppe(r.json(), status=400, code="INVALID_VALUE")


def test_database_connexion_503():
    r = client.get("/db-down")
    assert r.status_code == 503
    body = r.json()
    _assert_enveloppe(body, status=503, code="DATABASE_ERROR")
    assert r.headers.get("Retry-After")
    assert "08006" not in r.text


def test_deadlock_409_retryable():
    r = client.get("/deadlock")
    assert r.status_code == 409
    _assert_enveloppe(r.json(), status=409, code="CONCURRENT_UPDATE")


def test_pool_timeout_503():
    r = client.get("/pool")
    assert r.status_code == 503
    body = r.json()
    _assert_enveloppe(body, status=503, code="DATABASE_BUSY")
    assert "QueuePool" not in r.text
    assert r.headers.get("Retry-After")


def test_statement_timeout_503():
    r = client.get("/timeout-sql")
    assert r.status_code == 503
    _assert_enveloppe(r.json(), status=503, code="DATABASE_TIMEOUT")


def test_classify_database_error():
    orig = MagicMock()
    orig.sqlstate = "40001"
    assert classify_database_error(OperationalError("x", {}, orig)) == (409, "CONCURRENT_UPDATE")
    orig.sqlstate = "23505"
    assert classify_database_error(IntegrityError("x", {}, orig)) == (409, "DUPLICATE")
    assert classify_database_error(ValueError("pas une erreur SQL")) is None


def test_error_body_conserve_statut():
    body = error_body(status_code=429, code="RATE_LIMITED")
    assert body["status"] == 429
    assert body["success"] is False
    assert "Patientez" in body["message"]
