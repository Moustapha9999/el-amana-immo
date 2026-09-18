from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(_PROJECT_ROOT / ".env"), str(_BACKEND_ROOT / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="BEA DIGITAL", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    app_debug: bool = Field(default=True, alias="APP_DEBUG")
    api_v1_prefix: str = Field(default="/api/v1", alias="API_V1_PREFIX")

    secret_key: str = Field(default="change-me", alias="SECRET_KEY")
    # Access court + refresh pour session active ; idle timeout UI = 2 min (frontend)
    access_token_expire_minutes: int = Field(default=15, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=1, alias="REFRESH_TOKEN_EXPIRE_DAYS")
    module_refresh_token_expire_minutes: int = Field(
        default=45, alias="MODULE_REFRESH_TOKEN_EXPIRE_MINUTES"
    )
    login_lockout_window_minutes: int = Field(default=15, alias="LOGIN_LOCKOUT_WINDOW_MINUTES")
    login_lockout_max_failures: int = Field(default=5, alias="LOGIN_LOCKOUT_MAX_FAILURES")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")

    database_url: str = Field(
        default="postgresql+asyncpg://immo_user:immo_pass@localhost:5432/bea_digital",
        alias="DATABASE_URL",
    )
    database_ssl: bool = Field(default=False, alias="DATABASE_SSL")
    database_ssl_verify: bool = Field(default=True, alias="DATABASE_SSL_VERIFY")

    supabase_url: str | None = Field(default=None, alias="SUPABASE_URL")
    supabase_publishable_key: str | None = Field(default=None, alias="SUPABASE_PUBLISHABLE_KEY")
    supabase_anon_key: str | None = Field(default=None, alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: str | None = Field(default=None, alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_jwt_secret: str | None = Field(default=None, alias="SUPABASE_JWT_SECRET")

    @property
    def uses_supabase_host(self) -> bool:
        return "supabase.co" in self.database_url

    @property
    def database_ssl_enabled(self) -> bool:
        return self.database_ssl or self.uses_supabase_host

    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    celery_broker_url: str = Field(default="redis://localhost:6379/1", alias="CELERY_BROKER_URL")
    celery_result_backend: str = Field(default="redis://localhost:6379/2", alias="CELERY_RESULT_BACKEND")

    cors_origins: str = Field(default="http://localhost", alias="CORS_ORIGINS")

    upload_dir: str = "storage/uploads"
    ged_dir: str = "storage/ged"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def cors_allow_origin_regex(self) -> str | None:
        if self.app_env == "development":
            return r"https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?"
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()
