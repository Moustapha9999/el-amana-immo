"""Format d'erreur API standard BEA DIGITAL (inspiré de RFC 9457, compatible historique).

Toute réponse d'erreur contient :
  type, title, status, code, message, user_message, errors[{field, code, message}],
  request_id, success=false
et conserve ``detail`` (contrat historique lu par le front existant).

Le statut HTTP réel est toujours conservé. Aucune trace, requête SQL, chemin interne
ni message brut d'exception n'est renvoyé au client : ils restent dans les journaux,
corrélés par ``request_id``. Catalogue des codes : ``app/core/error_catalog.py``.
"""

from __future__ import annotations

import logging
import socket
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, IntegrityError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.error_catalog import STATUS_CODES, default_code, spec_for, title_for
from app.core.exceptions import AppError
from app.core.request_context import REQUEST_ID_HEADER, current_request_id, new_request_id

log = logging.getLogger("bea.errors")

# Compatibilité : anciens imports de ces tables.
DEFAULT_MESSAGES: dict[str, str] = {code: spec_for(code, 0).message for code in set(STATUS_CODES.values())}

# Phrases génériques (anglais) produites par Starlette / FastAPI, remplacées par le message FR.
_GENERIC_PHRASES = frozenset(
    {
        "Not authenticated",
        "Internal Server Error",
        "Content Too Large",
        "Non authentifié",
        "Token invalide",
        "Refresh token invalide",
        "Utilisateur introuvable",
        "Session expirée ou révoquée",
        "Session BEA DIGITAL requise",
        "Session module invalide",
    }
)

_FIELD_MESSAGES: dict[str, str] = {
    "missing": "Ce champ est obligatoire.",
    "string_type": "Texte attendu.",
    "int_parsing": "Nombre entier attendu.",
    "int_type": "Nombre entier attendu.",
    "float_parsing": "Nombre attendu.",
    "float_type": "Nombre attendu.",
    "decimal_parsing": "Montant invalide.",
    "decimal_type": "Montant invalide.",
    "decimal_max_digits": "Montant trop grand.",
    "decimal_max_places": "Trop de décimales.",
    "bool_parsing": "Valeur oui / non attendue.",
    "date_from_datetime_parsing": "Date invalide.",
    "date_parsing": "Date invalide.",
    "date_type": "Date invalide.",
    "datetime_parsing": "Date et heure invalides.",
    "datetime_from_date_parsing": "Date et heure invalides.",
    "uuid_parsing": "Identifiant invalide.",
    "uuid_type": "Identifiant invalide.",
    "enum": "Valeur non autorisée.",
    "literal_error": "Valeur non autorisée.",
    "string_pattern_mismatch": "Format invalide.",
    "url_parsing": "Adresse web invalide.",
    "list_type": "Liste attendue.",
    "dict_type": "Objet attendu.",
    "model_attributes_type": "Objet attendu.",
    "extra_forbidden": "Champ non autorisé.",
    "json_invalid": "Le contenu envoyé est mal formé.",
    "value_error": "Valeur invalide.",
}

_BOUND_MESSAGES: dict[str, tuple[str, str]] = {
    "string_too_short": ("min_length", "Ce champ doit contenir au moins {} caractère(s)."),
    "string_too_long": ("max_length", "Ce champ ne doit pas dépasser {} caractères."),
    "too_short": ("min_length", "Au moins {} élément(s) attendu(s)."),
    "too_long": ("max_length", "Au plus {} élément(s) autorisé(s)."),
    "greater_than": ("gt", "La valeur doit être supérieure à {}."),
    "greater_than_equal": ("ge", "La valeur doit être supérieure ou égale à {}."),
    "less_than": ("lt", "La valeur doit être inférieure à {}."),
    "less_than_equal": ("le", "La valeur doit être inférieure ou égale à {}."),
}

# SQLSTATE PostgreSQL (préfixe) → (statut, code). Ordre significatif.
_SQLSTATE_RULES: tuple[tuple[str, int, str], ...] = (
    ("23505", 409, "DUPLICATE"),  # unique_violation (si non traduit en IntegrityError)
    ("40P01", 409, "CONCURRENT_UPDATE"),  # deadlock_detected
    ("40001", 409, "CONCURRENT_UPDATE"),  # serialization_failure
    ("55P03", 409, "RESOURCE_LOCKED"),  # lock_not_available (NOWAIT / lock_timeout)
    ("57014", 503, "DATABASE_TIMEOUT"),  # query_canceled (statement_timeout)
    ("23", 400, "INVALID_VALUE"),  # autres contraintes d'intégrité (FK, check, not null)
    ("53", 503, "DATABASE_BUSY"),  # insufficient_resources (too_many_connections…)
    ("08", 503, "DATABASE_ERROR"),  # connection_exception
    ("57P", 503, "DATABASE_ERROR"),  # admin_shutdown, cannot_connect_now…
    ("28", 503, "DATABASE_ERROR"),  # invalid_authorization (configuration)
    ("22", 400, "INVALID_VALUE"),  # data_exception (valeur hors limites, texte trop long…)
)

_RETRY_AFTER_SECONDS: dict[str, str] = {"DATABASE_BUSY": "5", "DATABASE_ERROR": "10", "DEPENDENCY_UNAVAILABLE": "10"}


def error_body(
    *,
    status_code: int,
    code: str | None = None,
    message: str | None = None,
    errors: list[dict[str, Any]] | None = None,
    detail: Any = None,
) -> dict[str, Any]:
    code = code or default_code(status_code)
    text = message or spec_for(code, status_code).message
    return {
        "type": "about:blank",
        "title": title_for(code, status_code),
        "status": status_code,
        "success": False,
        "code": code,
        "message": text,
        "user_message": text,
        "errors": errors or [],
        "request_id": current_request_id() or new_request_id(),
        "detail": detail if detail is not None else text,
    }


def _respond(request: Request, status_code: int, body: dict[str, Any], headers: dict | None = None) -> JSONResponse:
    request.state.error_code = body["code"]
    request.state.error_message = body["message"]
    merged = dict(headers or {})
    if body.get("request_id"):
        merged[REQUEST_ID_HEADER] = body["request_id"]
    if body["code"] in _RETRY_AFTER_SECONDS and "Retry-After" not in merged:
        merged["Retry-After"] = _RETRY_AFTER_SECONDS[body["code"]]
    return JSONResponse(status_code=status_code, content=body, headers=merged)


def _is_generic_phrase(text: str, status_code: int) -> bool:
    if text in _GENERIC_PHRASES:
        return True
    try:
        return text == HTTPStatus(status_code).phrase
    except ValueError:
        return False


async def _http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail
    code: str | None = None
    message: str | None = None
    if isinstance(detail, dict):
        code = detail.get("code") if isinstance(detail.get("code"), str) else None
        raw = detail.get("message") or detail.get("detail")
        message = raw if isinstance(raw, str) else None
        if message and _is_generic_phrase(message, exc.status_code):
            message = None
    elif isinstance(detail, str) and detail.strip():
        if _is_generic_phrase(detail, exc.status_code):
            detail = None
        else:
            message = detail
    if exc.status_code >= 500 and not code:
        # Un 5xx en texte libre peut contenir un message d'exception : jamais renvoyé au client.
        if message:
            log.error("http_5xx_detail_masked request_id=%s route=%s detail=%s",
                      current_request_id(), request.url.path, message[:500])
        message, detail = None, None
    body = error_body(status_code=exc.status_code, code=code, message=message, detail=detail)
    return _respond(request, exc.status_code, body, getattr(exc, "headers", None))


def _field_message(err: dict[str, Any]) -> str:
    err_type = str(err.get("type", "value_error"))
    ctx = err.get("ctx") or {}
    if err_type == "value_error":
        cause = ctx.get("error")
        # Validateurs du projet : messages français rédigés pour l'utilisateur.
        if isinstance(cause, (ValueError, AssertionError)) and str(cause).strip():
            return str(cause).strip()
        if "email" in str(err.get("msg", "")).lower():
            return "Adresse e-mail invalide."
    if err_type in _BOUND_MESSAGES:
        key, template = _BOUND_MESSAGES[err_type]
        if key in ctx:
            return template.format(ctx[key])
    return _FIELD_MESSAGES.get(err_type, "Valeur invalide.")


async def _validation_exception(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = []
    for err in exc.errors():
        loc = [
            str(p)
            for p in err.get("loc", ())
            if p not in ("body", "query", "path", "header", "cookie") and not (isinstance(p, int) or str(p).isdigit())
        ]
        errors.append(
            {
                "field": ".".join(loc) or None,
                "code": str(err.get("type", "value_error")).upper(),
                "message": _field_message(err),
            }
        )
    first = errors[0] if errors else None
    message = spec_for("VALIDATION_ERROR", 422).message
    if first and len(errors) == 1:
        message = f"{first['field']} : {first['message']}" if first["field"] else first["message"]
    body = error_body(
        status_code=422,
        code="VALIDATION_ERROR",
        message=message,
        errors=errors,
        detail=jsonable_errors(exc),
    )
    return _respond(request, 422, body)


def jsonable_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    """Erreurs Pydantic sans la valeur saisie (``input``) ni le contexte : rien de sensible."""
    out = []
    for err in exc.errors():
        out.append({k: v for k, v in err.items() if k in {"loc", "msg", "type"}})
    return out


async def _app_error(request: Request, exc: AppError) -> JSONResponse:
    body = error_body(status_code=exc.status_code, code=getattr(exc, "code", None), message=exc.message)
    return _respond(request, exc.status_code, body)


async def _integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
    log.warning("integrity_error request_id=%s: %s", current_request_id(), exc.orig)
    # Seule une violation d'unicité (SQLSTATE 23505) est un doublon ; check / not null / FK = valeur refusée.
    sqlstate = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)
    if sqlstate and sqlstate != "23505":
        body = error_body(status_code=400, code="INVALID_VALUE")
        return _respond(request, 400, body)
    body = error_body(status_code=409, code="DUPLICATE")
    return _respond(request, 409, body)


def classify_database_error(exc: BaseException) -> tuple[int, str] | None:
    """(statut, code) d'une erreur PostgreSQL connue ; None = erreur de programmation (500)."""
    orig = getattr(exc, "orig", None) or exc
    sqlstate = str(getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None) or "")
    if sqlstate:
        for prefix, status_code, code in _SQLSTATE_RULES:
            if sqlstate.startswith(prefix):
                return status_code, code
    if isinstance(exc, (OperationalError, InterfaceError)) or getattr(exc, "connection_invalidated", False):
        return 503, "DATABASE_ERROR"
    return None


async def _database_error(request: Request, exc: DBAPIError) -> JSONResponse:
    request.state.exception_type = type(getattr(exc, "orig", None) or exc).__name__
    sqlstate = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)
    known = classify_database_error(exc)
    if known is None:
        log.exception("database_programming_error request_id=%s route=%s sqlstate=%s",
                      current_request_id(), request.url.path, sqlstate)
        return _respond(request, 500, error_body(status_code=500, code="INTERNAL_ERROR"))
    status_code, code = known
    level = logging.WARNING if status_code < 500 else logging.ERROR
    log.log(level, "database_error request_id=%s route=%s sqlstate=%s code=%s type=%s",
            current_request_id(), request.url.path, sqlstate, code, request.state.exception_type)
    return _respond(request, status_code, error_body(status_code=status_code, code=code))


async def _pool_timeout(request: Request, exc: PoolTimeoutError) -> JSONResponse:
    """Pool SQLAlchemy saturé : aucune connexion libre dans le délai ``pool_timeout``."""
    request.state.exception_type = "PoolTimeoutError"
    pool_status = ""
    try:
        from app.db.session import engine

        pool_status = engine.pool.status()
    except Exception:  # pragma: no cover - diagnostic seulement
        pass
    log.error("database_pool_exhausted request_id=%s route=%s pool=%s",
              current_request_id(), request.url.path, pool_status)
    return _respond(request, 503, error_body(status_code=503, code="DATABASE_BUSY"))


async def _dependency_unreachable(request: Request, exc: Exception) -> JSONResponse:
    """Connexion impossible à une dépendance (PostgreSQL à la connexion, Redis, service externe)."""
    request.state.exception_type = type(exc).__name__
    known = classify_database_error(exc)
    code = known[1] if known and known[0] >= 500 else "DEPENDENCY_UNAVAILABLE"
    log.error("dependency_unreachable request_id=%s route=%s type=%s code=%s",
              current_request_id(), request.url.path, type(exc).__name__, code, exc_info=exc)
    return _respond(request, 503, error_body(status_code=503, code=code))


async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled_error request_id=%s route=%s", current_request_id(), request.url.path)
    request.state.exception_type = type(exc).__name__
    body = error_body(status_code=500, code="INTERNAL_ERROR")
    return _respond(request, 500, body)


async def unhandled_response(request: Request, exc: Exception) -> JSONResponse:
    """Réponse 500 standard construite dans le contexte request_id (avant ServerErrorMiddleware)."""
    if isinstance(exc, PoolTimeoutError):
        return await _pool_timeout(request, exc)
    if isinstance(exc, _UNREACHABLE):
        return await _dependency_unreachable(request, exc)
    return await _unhandled(request, exc)


def _unreachable_types() -> tuple[type[BaseException], ...]:
    types: list[type[BaseException]] = [ConnectionError, socket.gaierror, TimeoutError]
    try:
        import asyncpg.exceptions as _pg

        # Uniquement les pannes de connexion : une UniqueViolation (PostgresError)
        # ne doit jamais devenir un 503 « service indisponible ».
        for name in (
            "PostgresConnectionError",
            "ConnectionDoesNotExistError",
            "ConnectionFailureError",
            "CannotConnectNowError",
            "TooManyConnectionsError",
        ):
            cls = getattr(_pg, name, None)
            if isinstance(cls, type):
                types.append(cls)
    except ImportError:  # pragma: no cover
        pass
    return tuple(types)


_UNREACHABLE = _unreachable_types()


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_exception)
    app.add_exception_handler(RequestValidationError, _validation_exception)
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(IntegrityError, _integrity_error)
    app.add_exception_handler(DBAPIError, _database_error)
    app.add_exception_handler(PoolTimeoutError, _pool_timeout)
    for exc_type in _UNREACHABLE:
        app.add_exception_handler(exc_type, _dependency_unreachable)
    app.add_exception_handler(Exception, _unhandled)


def success_body(*, code: str, message: str, data: Any = None) -> dict[str, Any]:
    """Enveloppe succès standard pour les nouveaux endpoints."""
    return {
        "success": True,
        "code": code,
        "message": message,
        "data": data,
        "request_id": current_request_id(),
    }


__all__ = [
    "classify_database_error",
    "error_body",
    "install_error_handlers",
    "status",
    "success_body",
    "unhandled_response",
]
