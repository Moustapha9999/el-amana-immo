"""Rate limiting défensif par IP + catégorie.

Compteurs dans Redis, partagés par tous les processus uvicorn (WEB_CONCURRENCY > 1) ;
Redis indisponible → fenêtre en mémoire du processus (dégradation journalisée, jamais de blocage).
"""

from __future__ import annotations

import logging
import math
import os
import threading
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.api_errors import error_body
from app.core.request_client import get_client_ip
from app.services.security_policy_service import get_cached_security_policy

log = logging.getLogger("bea.rate_limit")

_MESSAGES = {
    "login_platform": "Trop de tentatives de connexion. Patientez une minute avant de réessayer.",
    "login_module": "Trop de tentatives de connexion. Patientez une minute avant de réessayer.",
    "password_reset": "Trop de demandes de réinitialisation. Patientez une minute avant de réessayer.",
    "sensitive": "Trop d’opérations sensibles en peu de temps. Patientez quelques instants avant de réessayer.",
    "api": "Trop de requêtes en peu de temps. Patientez quelques instants avant de réessayer.",
}

class _SlidingWindow:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def hit(self, key: str, *, limit: int, window_seconds: float = 60.0) -> tuple[bool, int, int]:
        """(autorisé, restant, secondes avant qu'une place se libère)."""
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            cutoff = now - window_seconds
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= limit:
                return False, 0, max(1, math.ceil(q[0] + window_seconds - now))
            q.append(now)
            return True, max(0, limit - len(q)), 0


_BUCKET = _SlidingWindow()

# Fenêtre glissante atomique : ZSET des horodatages de la clé, purgé à chaque appel.
_LUA_FENETRE = """
local key, now, win, limit, membre = KEYS[1], tonumber(ARGV[1]), tonumber(ARGV[2]), tonumber(ARGV[3]), ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - win)
local n = redis.call('ZCARD', key)
if n >= limit then
  local premier = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  return {0, 0, tostring(premier[2])}
end
redis.call('ZADD', key, now, membre)
redis.call('PEXPIRE', key, math.ceil(win * 1000))
return {1, limit - n - 1, '0'}
"""
# Après un échec Redis, repli mémoire sans réessayer pendant ce délai (évite d'attendre le
# timeout de connexion à chaque requête).
_REDIS_PAUSE_SECONDS = 30.0
_redis_ko_jusqua = 0.0


async def _hit_partage(key: str, *, limit: int, window_seconds: float = 60.0) -> tuple[bool, int, int]:
    global _redis_ko_jusqua
    from app.middleware.idempotency import _redis

    now = time.time()
    if now < _redis_ko_jusqua:
        return _BUCKET.hit(key, limit=limit, window_seconds=window_seconds)
    try:
        ok, remaining, premier = await _redis().eval(
            _LUA_FENETRE, 1, f"bea:rl:{key}", now, window_seconds, limit, f"{now}:{os.urandom(6).hex()}"
        )
    except Exception as exc:
        _redis_ko_jusqua = now + _REDIS_PAUSE_SECONDS
        log.warning("rate_limit_redis_indisponible (repli mémoire par processus %ss) : %s", _REDIS_PAUSE_SECONDS, exc)
        return _BUCKET.hit(key, limit=limit, window_seconds=window_seconds)
    if int(ok):
        return True, int(remaining), 0
    return False, 0, max(1, math.ceil(float(premier) + window_seconds - now))


def _client_ip(request: Request) -> str:
    return get_client_ip(request) or "unknown"


def _category(path: str) -> str | None:
    p = path.lower()
    if not p.startswith("/api/"):
        return None
    if p.endswith("/auth/login") or p.rstrip("/").endswith("/auth/login"):
        return "login_platform"
    if "/auth/modules/" in p and p.rstrip("/").endswith("/login"):
        return "login_module"
    if "/auth/forgot-password" in p or "/auth/reset-password" in p:
        return "password_reset"
    if "/plateforme/admin/" in p or "/auth/2fa/" in p:
        return "sensitive"
    return "api"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method == "OPTIONS":
            return await call_next(request)

        pol = get_cached_security_policy()
        if not pol.get("rate_limit_enabled", True):
            return await call_next(request)

        cat = _category(request.url.path)
        if cat is None:
            return await call_next(request)

        limits = {
            "login_platform": int(pol.get("rate_limit_login_per_minute") or 20),
            "login_module": int(pol.get("rate_limit_login_per_minute") or 20),
            "password_reset": int(pol.get("rate_limit_password_reset_per_minute") or 10),
            "sensitive": int(pol.get("rate_limit_sensitive_per_minute") or 60),
            "api": int(pol.get("rate_limit_api_per_minute") or 300),
        }
        limit = int(limits.get(cat, 60) or 60)
        ip = _client_ip(request)
        ok, remaining, retry_after = await _hit_partage(f"{cat}:{ip}", limit=limit)
        if not ok:
            message = _MESSAGES.get(cat, _MESSAGES["api"])
            request.state.error_code = "RATE_LIMITED"
            request.state.error_message = f"{message} (catégorie {cat}, limite {limit}/min)"
            log.warning("rate_limited category=%s limit=%s ip=%s route=%s", cat, limit, ip, request.url.path)
            return JSONResponse(
                status_code=429,
                content=error_body(
                    status_code=429,
                    code="RATE_LIMITED",
                    message=message,
                    detail={"code": "RATE_LIMITED", "message": message, "category": cat},
                ),
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Category": cat,
                },
            )
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Category"] = cat
        return response
