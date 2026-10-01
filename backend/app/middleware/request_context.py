"""Corrélation request_id + journal d'accès structuré (JSON, sans secrets)."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.api_errors import unhandled_response
from app.core.request_client import get_client_ip
from app.core.request_context import (
    REQUEST_ID_HEADER,
    accept_or_create,
    reset_request_id,
    set_request_id,
)
from app.services.api_error_recorder import record_api_error, should_record

access_log = logging.getLogger("bea.access")
_QUIET_PATHS = {"/health", "/version"}


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = accept_or_create(request.headers.get(REQUEST_ID_HEADER))
        request.state.request_id = request_id
        token = set_request_id(request_id)
        started = time.perf_counter()
        status_code = 500
        try:
            try:
                response = await call_next(request)
            except Exception as exc:
                response = await unhandled_response(request, exc)
            status_code = response.status_code
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            path = request.url.path
            state = request.state
            if path not in _QUIET_PATHS:
                level = logging.ERROR if status_code >= 500 else logging.WARNING if status_code >= 400 else logging.INFO
                access_log.log(
                    level,
                    json.dumps(
                        {
                            "ts": datetime.now(timezone.utc).isoformat(),
                            "level": logging.getLevelName(level),
                            "request_id": request_id,
                            "method": request.method,
                            "route": path,
                            "status": status_code,
                            "duration_ms": duration_ms,
                            "error_code": getattr(state, "error_code", None),
                        },
                        ensure_ascii=False,
                    ),
                )
            if should_record(path, status_code):
                record_api_error(
                    request_id=request_id,
                    method=request.method,
                    route=path,
                    status_code=status_code,
                    code=getattr(state, "error_code", None),
                    message=getattr(state, "error_message", None),
                    exception_type=getattr(state, "exception_type", None),
                    user_id=getattr(state, "bea_user_id", None),
                    module_code=getattr(state, "bea_module_code", None),
                    ip_address=get_client_ip(request),
                    duration_ms=duration_ms,
                )
            reset_request_id(token)
