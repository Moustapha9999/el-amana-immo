import ssl

import certifi

from app.core.config import get_settings


def build_asyncpg_ssl_context() -> ssl.SSLContext | bool:
    settings = get_settings()
    if not settings.database_ssl_enabled:
        return False

    if settings.database_ssl_verify:
        ctx = ssl.create_default_context(cafile=certifi.where())
        return ctx

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx
