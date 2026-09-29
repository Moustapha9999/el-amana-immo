"""Protection contre les doubles soumissions (en-tête ``Idempotency-Key``).

Actif uniquement si le client envoie l'en-tête. Même clé + même utilisateur + même route :
- requête identique en cours  → 409 DUPLICATE_REQUEST ;
- requête déjà terminée (< 5xx) → réponse rejouée (``Idempotent-Replayed: true``).
Redis indisponible → pas de blocage (dégradation silencieuse, journalisée).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.api_errors import error_body
from app.core.config import get_settings

log = logging.getLogger("bea.idempotency")

HEADER = "Idempotency-Key"
_VALID_KEY = re.compile(r"^[A-Za-z0-9._:-]{8,100}$")
_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_LOCK_TTL = 120
_RESULT_TTL = 600
_MAX_STORED_BYTES = 512 * 1024

_client = None


def _redis():
    global _client
    if _client is None:
        from redis import asyncio as aioredis

        _client = aioredis.from_url(get_settings().redis_url, socket_timeout=1.5, socket_connect_timeout=1.5)
    return _client


def _scope_key(request: Request, key: str) -> str:
    principal = request.headers.get("authorization") or (request.client.host if request.client else "anon")
    raw = f"{principal}|{request.method}|{request.url.path}|{key}"
    return "bea:idem:" + hashlib.sha256(raw.encode()).hexdigest()


class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        key = request.headers.get(HEADER)
        if request.method not in _METHODS or not key:
            return await call_next(request)
        if not _VALID_KEY.match(key):
            return await call_next(request)

        base = _scope_key(request, key)
        try:
            client = _redis()
            stored = await client.get(base + ":res")
            if stored:
                data = json.loads(stored)
                return Response(
                    content=data["body"].encode("utf-8"),
                    status_code=data["status"],
                    media_type=data.get("media_type") or "application/json",
                    headers={"Idempotent-Replayed": "true"},
                )
            acquired = await client.set(base + ":lock", "1", nx=True, ex=_LOCK_TTL)
        except Exception as exc:  # Redis KO : on ne bloque pas le métier
            log.warning("idempotency_unavailable: %s", exc)
            return await call_next(request)

        if not acquired:
            body = error_body(
                status_code=409,
                code="DUPLICATE_REQUEST",
                message="Cette opération est déjà en cours de traitement. Patientez quelques instants.",
            )
            request.state.error_code = "DUPLICATE_REQUEST"
            return JSONResponse(status_code=409, content=body)

        response = await call_next(request)
        chunks: list[bytes] = []
        async for chunk in response.body_iterator:
            chunks.append(chunk if isinstance(chunk, bytes) else chunk.encode())
        payload = b"".join(chunks)
        replay = Response(
            content=payload,
            status_code=response.status_code,
            headers={k: v for k, v in response.headers.items() if k.lower() != "content-length"},
            media_type=response.media_type,
        )
        try:
            media = response.headers.get("content-type", "")
            if response.status_code < 500 and len(payload) <= _MAX_STORED_BYTES and "json" in media:
                await client.set(
                    base + ":res",
                    json.dumps({"status": response.status_code, "body": payload.decode("utf-8"), "media_type": media}),
                    ex=_RESULT_TTL,
                )
            await client.delete(base + ":lock")
        except Exception as exc:
            log.warning("idempotency_store_failed: %s", exc)
        return replay
