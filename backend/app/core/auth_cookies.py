"""Refresh tokens en cookie HttpOnly pour le front (jamais lisibles par JavaScript).

Mode activé par l'en-tête ``X-BEA-Auth: cookie`` : un formulaire ou un lien d'un autre site ne peut
pas l'envoyer (CSRF), et sans lui le cookie est ignoré. Sans cet en-tête, le refresh token reste
échangé dans le corps JSON (tests, Locust, clients techniques).
"""

from __future__ import annotations

import re

from fastapi import HTTPException, Request, Response, status

from app.core.config import get_settings
from app.schemas.auth import TokenPair

AUTH_MODE_HEADER = "x-bea-auth"
PLATFORM_REFRESH_COOKIE = "bea_rt"
MODULE_REFRESH_COOKIE_PREFIX = "bea_mrt_"
_MODULE_CODE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


def cookie_mode(request: Request) -> bool:
    return request.headers.get(AUTH_MODE_HEADER, "").strip().lower() == "cookie"


def cookie_path() -> str:
    return f"{get_settings().api_v1_prefix.rstrip('/')}/auth"


def module_cookie_name(module_code: str | None) -> str:
    code = (module_code or "").strip().lower()
    if not _MODULE_CODE.match(code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Code module invalide")
    return MODULE_REFRESH_COOKIE_PREFIX + code.replace("-", "_")


def read_refresh(request: Request, cookie_name: str, body_token: str | None) -> str | None:
    """Cookie en priorité (mode cookie) ; corps accepté pour migrer une session localStorage."""
    if cookie_mode(request):
        return request.cookies.get(cookie_name) or body_token or None
    return body_token or None


def respond(
    request: Request, response: Response, pair: TokenPair, cookie_name: str, max_age: int
) -> TokenPair:
    if not cookie_mode(request):
        return pair
    response.set_cookie(
        cookie_name,
        pair.refresh_token,
        max_age=max_age,
        path=cookie_path(),
        httponly=True,
        secure=get_settings().auth_cookie_secure,
        samesite="strict",
    )
    return TokenPair(access_token=pair.access_token, refresh_token="", token_type=pair.token_type)


def clear(response: Response, cookie_name: str) -> None:
    response.delete_cookie(
        cookie_name,
        path=cookie_path(),
        httponly=True,
        secure=get_settings().auth_cookie_secure,
        samesite="strict",
    )


def module_cookie_names(request: Request) -> list[str]:
    return [name for name in request.cookies if name.startswith(MODULE_REFRESH_COOKIE_PREFIX)]
