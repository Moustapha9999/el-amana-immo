from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router as api_v1_router
from app.core.config import get_settings
from app.middleware.rate_limit import RateLimitMiddleware
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
        version="0.1.0",
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
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    app.include_router(api_v1_router, prefix=settings.api_v1_prefix)

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": settings.app_name}

    return app


app = create_app()
