from uuid import uuid4

from app.core.security import create_access_token, create_refresh_token, decode_token
from app.models.auth import SESSION_KIND_MODULE, SESSION_KIND_PLATFORM
from app.services.login_attempt_service import LoginAttemptService


def test_platform_access_token_claims():
    sid = uuid4()
    uid = uuid4()
    token = create_access_token(
        uid,
        sid=sid,
        extra_claims={"kind": SESSION_KIND_PLATFORM, "roles": ["comptable"], "is_superuser": False},
    )
    payload = decode_token(token)
    assert payload["type"] == "access"
    assert payload["kind"] == SESSION_KIND_PLATFORM
    assert payload["sid"] == str(sid)
    assert payload["sub"] == str(uid)
    assert "module" not in payload


def test_module_access_token_claims():
    sid = uuid4()
    parent = uuid4()
    uid = uuid4()
    token = create_access_token(
        uid,
        sid=sid,
        extra_claims={
            "kind": SESSION_KIND_MODULE,
            "module": "immobilisations",
            "parent_sid": str(parent),
            "roles": ["comptable"],
            "is_superuser": False,
        },
    )
    payload = decode_token(token)
    assert payload["kind"] == SESSION_KIND_MODULE
    assert payload["module"] == "immobilisations"
    assert payload["parent_sid"] == str(parent)


def test_refresh_tokens_keep_kind():
    sid = uuid4()
    uid = uuid4()
    platform = create_refresh_token(
        uid, sid=sid, refresh_jti="abc", extra_claims={"kind": SESSION_KIND_PLATFORM}
    )
    module = create_refresh_token(
        uid,
        sid=sid,
        refresh_jti="def",
        extra_claims={"kind": SESSION_KIND_MODULE, "module": "immobilisations"},
    )
    assert decode_token(platform)["kind"] == SESSION_KIND_PLATFORM
    decoded_mod = decode_token(module)
    assert decoded_mod["kind"] == SESSION_KIND_MODULE
    assert decoded_mod["module"] == "immobilisations"


def test_login_lockout_threshold_from_settings():
    from app.core.config import get_settings

    settings = get_settings()
    assert settings.login_lockout_max_failures == 5
    assert settings.login_lockout_window_minutes == 15
    assert settings.module_refresh_token_expire_minutes == 45
    assert LoginAttemptService is not None
