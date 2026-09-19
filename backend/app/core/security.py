from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import bcrypt
from jose import ExpiredSignatureError, JWTError, jwt

from app.core.config import get_settings


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def new_jti() -> str:
    return uuid4().hex


def create_access_token(
    subject: str | UUID,
    *,
    sid: str | UUID,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    from app.services.security_policy_service import get_cached_security_policy

    settings = get_settings()
    policy = get_cached_security_policy()
    minutes = int(policy.get("access_token_expire_minutes") or settings.access_token_expire_minutes)
    expire = datetime.now(UTC) + timedelta(minutes=max(1, minutes))
    payload: dict[str, Any] = {
        "sub": str(subject),
        "exp": expire,
        "type": "access",
        "sid": str(sid),
        "jti": new_jti(),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(
    subject: str | UUID,
    *,
    sid: str | UUID,
    refresh_jti: str,
    extra_claims: dict[str, Any] | None = None,
    expire_delta: timedelta | None = None,
) -> str:
    from app.services.security_policy_service import get_cached_security_policy

    settings = get_settings()
    if expire_delta is None:
        policy = get_cached_security_policy()
        days = int(policy.get("refresh_token_expire_days") or settings.refresh_token_expire_days)
        expire_delta = timedelta(days=max(1, days))
    expire = datetime.now(UTC) + expire_delta
    payload: dict[str, Any] = {
        "sub": str(subject),
        "exp": expire,
        "type": "refresh",
        "sid": str(sid),
        "jti": refresh_jti,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


# Lien de réinitialisation Login 1 : 15 minutes.
PASSWORD_RESET_EXPIRE_SECONDS = 900


def create_password_reset_token(subject: str | UUID) -> str:
    settings = get_settings()
    expire = datetime.now(UTC) + timedelta(seconds=PASSWORD_RESET_EXPIRE_SECONDS)
    payload = {"sub": str(subject), "exp": expire, "type": "password_reset", "jti": new_jti()}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except ExpiredSignatureError as exc:
        raise ValueError("Lien expiré — recommencez depuis Mot de passe oublié") from exc
    except JWTError as exc:
        raise ValueError("Token invalide") from exc
