"""Rate limiting défensif en mémoire (par IP + catégorie)."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.services.security_policy_service import get_cached_security_policy


class _SlidingWindow:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def hit(self, key: str, *, limit: int, window_seconds: float = 60.0) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            cutoff = now - window_seconds
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= limit:
                return False, 0
            q.append(now)
            return True, max(0, limit - len(q))


_BUCKET = _SlidingWindow()


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


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
        ok, remaining = _BUCKET.hit(f"{cat}:{ip}", limit=limit)
        if not ok:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": {
                        "code": "RATE_LIMITED",
                        "message": "Trop de requêtes — réessayez dans une minute.",
                        "category": cat,
                    }
                },
                headers={"Retry-After": "60", "X-RateLimit-Limit": str(limit)},
            )
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Category"] = cat
        return response
