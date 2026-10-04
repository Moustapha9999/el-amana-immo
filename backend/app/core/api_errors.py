"""Format d'erreur API standard BEA DIGITAL.

Toute réponse d'erreur contient :
  success=false, code, message, user_message, errors[], request_id
et conserve ``detail`` (contrat historique lu par le front existant).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppError
from app.core.request_context import REQUEST_ID_HEADER, current_request_id

log = logging.getLogger("bea.errors")

STATUS_CODES: dict[int, str] = {
    400: "BUSINESS_RULE_ERROR",
    401: "AUTH_REQUIRED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    503: "SERVICE_UNAVAILABLE",
}

DEFAULT_MESSAGES: dict[str, str] = {
    "BUSINESS_RULE_ERROR": "L’opération n’a pas pu être effectuée.",
    "AUTH_REQUIRED": "Votre session a expiré. Veuillez vous reconnecter.",
    "FORBIDDEN": "Vous n’avez pas les autorisations nécessaires pour effectuer cette action.",
    "NOT_FOUND": "L’élément demandé est introuvable.",
    "METHOD_NOT_ALLOWED": "Opération non autorisée.",
    "CONFLICT": "Cette donnée a été modifiée entre-temps ou entre en conflit avec une donnée existante.",
    "DUPLICATE": "Cette donnée existe déjà.",
    "INVALID_VALUE": "Une valeur saisie n’est pas autorisée. Vérifiez les champs à liste de choix.",
    "PAYLOAD_TOO_LARGE": "Le fichier ou la requête est trop volumineux.",
    "UNSUPPORTED_MEDIA_TYPE": "Type de fichier non pris en charge.",
    "VALIDATION_ERROR": "Certains champs sont invalides. Veuillez les corriger.",
    "RATE_LIMITED": "Trop de tentatives. Patientez quelques instants puis réessayez.",
    "DATABASE_ERROR": "La base de données est momentanément indisponible. Réessayez dans quelques instants.",
    "SERVICE_UNAVAILABLE": "Le service est momentanément indisponible.",
    "INTERNAL_ERROR": "Une erreur interne est survenue.",
}

# Phrases HTTP génériques (anglais) produites par Starlette : remplacées par le message FR du code.
_STARLETTE_PHRASES = frozenset(
    {"Not Found", "Method Not Allowed", "Unauthorized", "Forbidden", "Not authenticated", "Internal Server Error"}
)

_FIELD_MESSAGES: dict[str, str] = {
    "missing": "Ce champ est obligatoire.",
    "string_too_short": "Ce champ est trop court.",
    "string_too_long": "Ce champ est trop long.",
    "string_type": "Texte attendu.",
    "int_parsing": "Nombre entier attendu.",
    "float_parsing": "Nombre attendu.",
    "decimal_parsing": "Montant invalide.",
    "date_from_datetime_parsing": "Date invalide.",
    "date_parsing": "Date invalide.",
    "uuid_parsing": "Identifiant invalide.",
    "enum": "Valeur non autorisée.",
    "literal_error": "Valeur non autorisée.",
    "greater_than_equal": "Valeur trop petite.",
    "less_than_equal": "Valeur trop grande.",
    "value_error": "Valeur invalide.",
}


def error_body(
    *,
    status_code: int,
    code: str | None = None,
    message: str | None = None,
    errors: list[dict[str, Any]] | None = None,
    detail: Any = None,
) -> dict[str, Any]:
    code = code or STATUS_CODES.get(status_code) or ("INTERNAL_ERROR" if status_code >= 500 else "ERROR")
    text = message or DEFAULT_MESSAGES.get(code) or DEFAULT_MESSAGES["BUSINESS_RULE_ERROR"]
    return {
        "success": False,
        "code": code,
        "message": text,
        "user_message": text,
        "errors": errors or [],
        "request_id": current_request_id(),
        "detail": detail if detail is not None else text,
    }


def _respond(request: Request, status_code: int, body: dict[str, Any], headers: dict | None = None) -> JSONResponse:
    request.state.error_code = body["code"]
    request.state.error_message = body["message"]
    merged = dict(headers or {})
    if body.get("request_id"):
        merged[REQUEST_ID_HEADER] = body["request_id"]
    return JSONResponse(status_code=status_code, content=body, headers=merged)


async def _http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail
    code: str | None = None
    message: str | None = None
    if isinstance(detail, dict):
        code = detail.get("code") if isinstance(detail.get("code"), str) else None
        raw = detail.get("message") or detail.get("detail")
        message = raw if isinstance(raw, str) else None
    elif isinstance(detail, str) and detail.strip() and detail not in _STARLETTE_PHRASES:
        message = detail
    if isinstance(detail, str) and detail in _STARLETTE_PHRASES:
        detail = None
    body = error_body(status_code=exc.status_code, code=code, message=message, detail=detail)
    return _respond(request, exc.status_code, body, getattr(exc, "headers", None))


async def _validation_exception(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = []
    for err in exc.errors():
        loc = [str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path")]
        err_type = str(err.get("type", "value_error"))
        errors.append(
            {
                "field": ".".join(loc) or None,
                "code": err_type.upper(),
                "message": _FIELD_MESSAGES.get(err_type, err.get("msg") or "Valeur invalide."),
            }
        )
    first = errors[0] if errors else None
    message = DEFAULT_MESSAGES["VALIDATION_ERROR"]
    if first and first["field"] and len(errors) == 1:
        message = f"{first['field']} : {first['message']}"
    body = error_body(
        status_code=422,
        code="VALIDATION_ERROR",
        message=message,
        errors=errors,
        detail=jsonable_errors(exc),
    )
    return _respond(request, 422, body)


def jsonable_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
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


async def _database_error(request: Request, exc: OperationalError) -> JSONResponse:
    log.error("database_error request_id=%s: %s", current_request_id(), exc.orig)
    request.state.exception_type = type(exc).__name__
    body = error_body(status_code=503, code="DATABASE_ERROR")
    return _respond(request, 503, body)


async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled_error request_id=%s route=%s", current_request_id(), request.url.path)
    request.state.exception_type = type(exc).__name__
    body = error_body(status_code=500, code="INTERNAL_ERROR")
    return _respond(request, 500, body)


async def unhandled_response(request: Request, exc: Exception) -> JSONResponse:
    """Réponse 500 standard construite dans le contexte request_id (avant ServerErrorMiddleware)."""
    return await _unhandled(request, exc)


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_exception)
    app.add_exception_handler(RequestValidationError, _validation_exception)
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(IntegrityError, _integrity_error)
    app.add_exception_handler(OperationalError, _database_error)
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


__all__ = ["error_body", "install_error_handlers", "success_body", "status", "unhandled_response"]
