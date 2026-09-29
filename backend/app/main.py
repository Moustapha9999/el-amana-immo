from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router as api_v1_router
from app.core.api_errors import install_error_handlers
from app.core.config import get_settings
from app.middleware.idempotency import IdempotencyMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_context import RequestContextMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Charge la politique sécurité (env + override DB) dans le cache mémoire.
    try:
        from app.db.session import AsyncSessionLocal
        from app.services.security_policy_service import SecurityPolicyService

        async with AsyncSessionLocal() as session:
            await SecurityPolicyService(session).ensure_cache()
    except Exception:
        pass
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    docs_on = settings.api_docs_enabled
    if docs_on is None:
        docs_on = settings.app_env.lower() in {"development", "dev", "local"} or settings.app_debug

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs" if docs_on else None,
        redoc_url="/redoc" if docs_on else None,
    )

    # Ordre : derniers ajoutés = exécutés en premier sur la requête.
    cors_origin_regex = settings.cors_allow_origin_regex
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_origin_regex=cors_origin_regex,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["*"],
    )
    app.add_middleware(IdempotencyMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)
    install_error_handlers(app)

    app.include_router(api_v1_router, prefix=settings.api_v1_prefix)

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "service": settings.app_name,
            "version": settings.app_version,
            "git_sha": settings.git_sha,
        }

    @app.get("/health/ready")
    async def health_ready():
        import time

        from fastapi.responses import JSONResponse
        from sqlalchemy import text

        from app.db.session import AsyncSessionLocal
        from app.middleware.idempotency import _redis

        checks: dict[str, dict] = {}
        t0 = time.perf_counter()
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
            checks["database"] = {"status": "ok", "ms": round((time.perf_counter() - t0) * 1000, 1)}
        except Exception:
            checks["database"] = {"status": "ko"}
        t0 = time.perf_counter()
        try:
            await _redis().ping()
            checks["redis"] = {"status": "ok", "ms": round((time.perf_counter() - t0) * 1000, 1)}
        except Exception:
            checks["redis"] = {"status": "ko"}
        ready = all(c["status"] == "ok" for c in checks.values())
        return JSONResponse(
            status_code=200 if ready else 503,
            content={"status": "ok" if ready else "degraded", "version": settings.app_version, "checks": checks},
        )

    @app.get("/version")
    async def version():
        return {
            "service": settings.app_name,
            "version": settings.app_version,
            "git_sha": settings.git_sha,
            "env": settings.app_env,
        }

    return app


app = create_app()
