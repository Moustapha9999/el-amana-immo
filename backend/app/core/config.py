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
    app_version: str = Field(default="0.0.0-dev", alias="APP_VERSION")
    git_sha: str = Field(default="unknown", alias="GIT_SHA")
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

    # Politique mots de passe (appliquée côté serveur)
    password_min_length: int = Field(default=10, alias="PASSWORD_MIN_LENGTH")
    password_require_uppercase: bool = Field(default=True, alias="PASSWORD_REQUIRE_UPPERCASE")
    password_require_lowercase: bool = Field(default=True, alias="PASSWORD_REQUIRE_LOWERCASE")
    password_require_digit: bool = Field(default=True, alias="PASSWORD_REQUIRE_DIGIT")
    password_require_special: bool = Field(default=True, alias="PASSWORD_REQUIRE_SPECIAL")

    # MFA obligatoire pour comptes CORE ADMIN / superuser
    mfa_required_for_core_admin: bool = Field(default=False, alias="MFA_REQUIRED_FOR_CORE_ADMIN")

    # Rate limiting (fenêtre glissante, mémoire processus)
    rate_limit_enabled: bool = Field(default=True, alias="RATE_LIMIT_ENABLED")
    rate_limit_login_per_minute: int = Field(default=20, alias="RATE_LIMIT_LOGIN_PER_MINUTE")
    rate_limit_api_per_minute: int = Field(default=300, alias="RATE_LIMIT_API_PER_MINUTE")
    rate_limit_sensitive_per_minute: int = Field(default=60, alias="RATE_LIMIT_SENSITIVE_PER_MINUTE")
    rate_limit_password_reset_per_minute: int = Field(
        default=10, alias="RATE_LIMIT_PASSWORD_RESET_PER_MINUTE"
    )

    # Headers de sécurité HTTP (middleware FastAPI)
    security_headers_enabled: bool = Field(default=True, alias="SECURITY_HEADERS_ENABLED")
    # Docs OpenAPI : désactivés hors développement si False
    api_docs_enabled: bool | None = Field(default=None, alias="API_DOCS_ENABLED")

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
    backup_dir: str = Field(default="backups", alias="BACKUP_DIR")

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
