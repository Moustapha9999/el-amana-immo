"""Politique sécurité runtime — env (défaut) + override PlatformOpsFlag."""

from __future__ import annotations

import threading
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.platform_ops import PlatformOpsFlag

SECURITY_POLICY_KEY = "security_policy"

_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, Any] | None = None


def _env_defaults() -> dict[str, Any]:
    s = get_settings()
    return {
        "login_lockout_window_minutes": int(s.login_lockout_window_minutes),
        "login_lockout_max_failures": int(s.login_lockout_max_failures),
        "password_min_length": int(s.password_min_length),
        "password_require_uppercase": bool(s.password_require_uppercase),
        "password_require_lowercase": bool(s.password_require_lowercase),
        "password_require_digit": bool(s.password_require_digit),
        "password_require_special": bool(s.password_require_special),
        "mfa_required_for_core_admin": bool(s.mfa_required_for_core_admin),
        "rate_limit_enabled": bool(s.rate_limit_enabled),
        "rate_limit_login_per_minute": int(s.rate_limit_login_per_minute),
        "rate_limit_api_per_minute": int(s.rate_limit_api_per_minute),
        "rate_limit_sensitive_per_minute": int(s.rate_limit_sensitive_per_minute),
        "rate_limit_password_reset_per_minute": int(s.rate_limit_password_reset_per_minute),
    }


def _merge(stored: dict | None) -> dict[str, Any]:
    base = _env_defaults()
    if not stored:
        return base
    out = deepcopy(base)
    for key in base:
        if key in stored and stored[key] is not None:
            out[key] = stored[key]
    # coerce types
    out["login_lockout_window_minutes"] = max(1, min(1440, int(out["login_lockout_window_minutes"])))
    out["login_lockout_max_failures"] = max(1, min(50, int(out["login_lockout_max_failures"])))
    out["password_min_length"] = max(8, min(128, int(out["password_min_length"])))
    for bkey in (
        "password_require_uppercase",
        "password_require_lowercase",
        "password_require_digit",
        "password_require_special",
        "mfa_required_for_core_admin",
        "rate_limit_enabled",
    ):
        out[bkey] = bool(out[bkey])
    for rkey in (
        "rate_limit_login_per_minute",
        "rate_limit_api_per_minute",
        "rate_limit_sensitive_per_minute",
        "rate_limit_password_reset_per_minute",
    ):
        out[rkey] = max(1, min(10_000, int(out[rkey])))
    return out


def get_cached_security_policy() -> dict[str, Any]:
    """Lecture sync pour middleware / validation MDP (cache mémoire)."""
    with _CACHE_LOCK:
        if _CACHE is not None:
            return deepcopy(_CACHE)
    return _env_defaults()


def set_cached_security_policy(policy: dict[str, Any]) -> None:
    with _CACHE_LOCK:
        global _CACHE
        _CACHE = deepcopy(policy)


def invalidate_security_policy_cache() -> None:
    with _CACHE_LOCK:
        global _CACHE
        _CACHE = None


class SecurityPolicyService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_policy(self) -> dict[str, Any]:
        flag = await self.db.get(PlatformOpsFlag, SECURITY_POLICY_KEY)
        stored = flag.value if flag and isinstance(flag.value, dict) else None
        policy = _merge(stored)
        set_cached_security_policy(policy)
        return {
            **policy,
            "source": "database" if stored else "environment",
            "updated_at": flag.updated_at.isoformat() if flag and flag.updated_at else None,
            "editable_keys": list(_env_defaults().keys()),
        }

    async def update_policy(self, patch: dict[str, Any]) -> dict[str, Any]:
        allowed = set(_env_defaults().keys())
        clean = {k: v for k, v in patch.items() if k in allowed}
        current_flag = await self.db.get(PlatformOpsFlag, SECURITY_POLICY_KEY)
        current_stored = (
            dict(current_flag.value)
            if current_flag and isinstance(current_flag.value, dict)
            else {}
        )
        current_stored.update(clean)
        merged = _merge(current_stored)

        # Persist only override keys (merged values as source of truth for ops)
        value = {k: merged[k] for k in allowed}
        now = datetime.now(timezone.utc)
        if current_flag is None:
            self.db.add(PlatformOpsFlag(key=SECURITY_POLICY_KEY, value=value, updated_at=now))
        else:
            current_flag.value = value
            current_flag.updated_at = now
        await self.db.flush()
        set_cached_security_policy(merged)
        return await self.get_policy()

    async def ensure_cache(self) -> dict[str, Any]:
        return await self.get_policy()
