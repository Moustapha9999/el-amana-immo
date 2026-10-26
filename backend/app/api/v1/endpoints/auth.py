from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import bearer_scheme, get_platform_user
from app.core import auth_cookies
from app.core.exceptions import AppError
from app.core.request_client import get_client_ip
from app.core.security import decode_token, verify_password, verify_password_async
from app.db.session import get_db
from app.models import User
from app.models.auth import SESSION_KIND_MODULE, SESSION_KIND_PLATFORM
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    ResetPasswordRequest,
    TokenPair,
    TotpDisableRequest,
    TotpEnableRequest,
    TotpSetupResponse,
    TotpStatusResponse,
    UserRead,
)
from app.schemas.common import MessageResponse
from app.services.auth_service import AuthService
from app.services.auth_session_service import AuthSessionService, RefreshTokenReuseError
from app.services.audit_helpers import record_audit
from app.services.inventaire_service import build_qr_png_base64
from app.services.login_attempt_service import LoginAttemptService
from app.services.plateforme_access_service import PlateformeAccessService
from app.services.totp_service import generate_secret, provisioning_uri, store_secret, verify_code

router = APIRouter(tags=["auth"])

# Message unique : ne révèle pas si le compte existe, est inactif ou si seul le mot de passe est faux.
_INVALID_CREDENTIALS = "Adresse e-mail ou mot de passe incorrect."


def _invalid_credentials() -> AppError:
    return AppError(_INVALID_CREDENTIALS, status.HTTP_401_UNAUTHORIZED, code="AUTH_INVALID_CREDENTIALS")


def _client_meta(request: Request) -> tuple[str | None, str | None]:
    ua = request.headers.get("user-agent")
    return get_client_ip(request), ua


@router.post("/auth/login", response_model=TokenPair)
async def login(
    payload: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)
):
    ip, ua = _client_meta(request)
    attempts = LoginAttemptService(db)
    await attempts.assert_not_locked(
        email=payload.email, ip_address=ip, login_kind=SESSION_KIND_PLATFORM
    )

    service = AuthService(db)
    access = PlateformeAccessService(db)
    await access.ensure_catalogue()
    user = await service.authenticate(payload.email, payload.password)
    if user is None:
        await attempts.record(
            email=payload.email, ip_address=ip, login_kind=SESSION_KIND_PLATFORM, success=False
        )
        await record_audit(
            db,
            user=None,
            action="login_failed",
            entity="user",
            entity_id=None,
            request=request,
            after={"kind": SESSION_KIND_PLATFORM, "email": payload.email},
        )
        await db.commit()
        raise _invalid_credentials()

    if user.totp_enabled:
        if not payload.totp_code:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "TOTP_REQUIRED",
                    "message": "Saisissez le code à 6 chiffres de votre application d’authentification.",
                },
            )
        if not verify_code(user.totp_secret, payload.totp_code):
            await attempts.record(
                email=payload.email, ip_address=ip, login_kind=SESSION_KIND_PLATFORM, success=False
            )
            await record_audit(
                db,
                user=user,
                action="login_failed",
                entity="user",
                entity_id=str(user.id),
                request=request,
                after={"kind": SESSION_KIND_PLATFORM, "reason": "totp"},
            )
            await db.commit()
            raise AppError(
                "Code de vérification incorrect ou expiré.", status.HTTP_401_UNAUTHORIZED, code="TOTP_INVALID"
            )

    await attempts.record(
        email=payload.email, ip_address=ip, login_kind=SESSION_KIND_PLATFORM, success=True
    )
    await record_audit(
        db,
        user=user,
        action="login_platform",
        entity="user",
        entity_id=str(user.id),
        request=request,
    )
    sessions = AuthSessionService(db)
    pair = await sessions.issue_platform_tokens(user, ip_address=ip, user_agent=ua)
    return auth_cookies.respond(
        request,
        response,
        pair,
        auth_cookies.PLATFORM_REFRESH_COOKIE,
        sessions.refresh_max_age_seconds(SESSION_KIND_PLATFORM),
    )


async def _journaliser_rejeu(
    db: AsyncSession, request: Request, user: User, token_payload: dict, kind: str
) -> None:
    """Révocation + audit validés avant la réponse 401 (get_db annulerait sinon)."""
    await record_audit(
        db,
        user=user,
        action="refresh_token_reuse",
        entity="auth_session",
        entity_id=str(token_payload.get("sid")),
        request=request,
        after={"kind": kind, "module_code": token_payload.get("module")},
    )
    await db.commit()


def _decoder_refresh(raw: str | None) -> dict:
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token invalide")
    try:
        token_payload = decode_token(raw)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token invalide") from exc
    if token_payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token invalide")
    return token_payload


@router.post("/auth/refresh", response_model=TokenPair)
async def refresh(
    request: Request,
    response: Response,
    payload: RefreshRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    cookie_name = auth_cookies.PLATFORM_REFRESH_COOKIE
    raw = auth_cookies.read_refresh(request, cookie_name, payload.refresh_token if payload else None)
    token_payload = _decoder_refresh(raw)

    service = AuthService(db)
    user = await service.get_by_id(UUID(token_payload["sub"]))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Utilisateur introuvable")

    sessions = AuthSessionService(db)
    try:
        pair = await sessions.rotate_refresh(raw, user, expected_kind=SESSION_KIND_PLATFORM)
        return auth_cookies.respond(
            request, response, pair, cookie_name, sessions.refresh_max_age_seconds(SESSION_KIND_PLATFORM)
        )
    except RefreshTokenReuseError as exc:
        await _journaliser_rejeu(db, request, user, token_payload, SESSION_KIND_PLATFORM)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "SESSION_REVOKED", "message": str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.post("/auth/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    response: Response,
    payload: LogoutRequest | None = None,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    """Révoque la session courante (access et/ou refresh). Ne bloque pas si déjà invalide."""
    sessions = AuthSessionService(db)
    if credentials and credentials.credentials:
        await sessions.revoke_by_token(credentials.credentials)
    refresh_token = auth_cookies.read_refresh(
        request, auth_cookies.PLATFORM_REFRESH_COOKIE, payload.refresh_token if payload else None
    )
    if refresh_token:
        await sessions.revoke_by_token(refresh_token)
    if auth_cookies.cookie_mode(request):
        # Les sessions module filles tombent avec la session plateforme.
        for name in [auth_cookies.PLATFORM_REFRESH_COOKIE, *auth_cookies.module_cookie_names(request)]:
            auth_cookies.clear(response, name)

    await record_audit(
        db,
        user=None,
        action="logout_platform",
        entity="user",
        entity_id=None,
        request=request,
        after={"revoked": True},
    )
    return MessageResponse(message="Déconnexion effectuée")


@router.get("/auth/me", response_model=UserRead)
async def me(user: User = Depends(get_platform_user)):
    return user


@router.post("/auth/change-password", response_model=MessageResponse)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    user: User = Depends(get_platform_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await AuthService(db).change_own_password(user, payload.current_password, payload.new_password)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "CURRENT_PASSWORD_INVALID", "message": str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "PASSWORD_POLICY", "message": str(exc)},
        ) from exc
    await record_audit(
        db,
        user=user,
        action="password_change",
        entity="user",
        entity_id=str(user.id),
        request=request,
    )
    return MessageResponse(message="Mot de passe modifié")


@router.get("/auth/2fa/status", response_model=TotpStatusResponse)
async def totp_status(user: User = Depends(get_platform_user)):
    pending = bool(user.totp_secret and not user.totp_enabled)
    return TotpStatusResponse(enabled=user.totp_enabled, pending_setup=pending)


@router.post("/auth/2fa/setup", response_model=TotpSetupResponse)
async def totp_setup(user: User = Depends(get_platform_user), db: AsyncSession = Depends(get_db)):
    if user.totp_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA déjà activée")
    secret = generate_secret()
    user.totp_secret = store_secret(secret)
    user.totp_enabled = False
    await db.flush()
    otpauth_url = provisioning_uri(secret, user.email)
    return TotpSetupResponse(
        secret=secret,
        otpauth_url=otpauth_url,
        qr_image_base64=build_qr_png_base64(otpauth_url),
    )


@router.post("/auth/2fa/enable", response_model=MessageResponse)
async def totp_enable(
    payload: TotpEnableRequest,
    request: Request,
    user: User = Depends(get_platform_user),
    db: AsyncSession = Depends(get_db),
):
    if not user.totp_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Lancez d'abord la configuration 2FA")
    if not verify_code(user.totp_secret, payload.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Code invalide")
    user.totp_enabled = True
    await db.flush()
    await record_audit(
        db,
        user=user,
        action="2fa_enable",
        entity="user",
        entity_id=str(user.id),
        request=request,
    )
    return MessageResponse(message="Authentification à deux facteurs activée")


@router.post("/auth/2fa/disable", response_model=MessageResponse)
async def totp_disable(
    payload: TotpDisableRequest,
    request: Request,
    user: User = Depends(get_platform_user),
    db: AsyncSession = Depends(get_db),
):
    if not user.totp_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA non activée")
    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Mot de passe incorrect")
    if not verify_code(user.totp_secret, payload.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Code invalide")
    user.totp_enabled = False
    user.totp_secret = None
    await db.flush()
    await record_audit(
        db,
        user=user,
        action="2fa_disable",
        entity="user",
        entity_id=str(user.id),
        request=request,
    )
    return MessageResponse(message="Authentification à deux facteurs désactivée")


@router.post("/auth/forgot-password", response_model=ForgotPasswordResponse)
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Désactivé : reset MDP centralisé dans CORE ADMIN → Sécurité (pas de SMTP public)."""
    _ = payload, request, db
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": "PASSWORD_RESET_DISABLED",
            "message": (
                "La réinitialisation publique est désactivée. "
                "Contactez un administrateur CORE ADMIN (Sécurité → Mots de passe)."
            ),
        },
    )


@router.post("/auth/reset-password", response_model=MessageResponse)
async def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Désactivé : utiliser CORE ADMIN → Sécurité."""
    _ = payload, request, db
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": "PASSWORD_RESET_DISABLED",
            "message": (
                "La réinitialisation par lien public est désactivée. "
                "Contactez un administrateur CORE ADMIN."
            ),
        },
    )

@router.post("/auth/modules/{module_code}/login", response_model=TokenPair)
async def module_login(
    module_code: str,
    payload: LoginRequest,
    request: Request,
    response: Response,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    user: User = Depends(get_platform_user),
    db: AsyncSession = Depends(get_db),
):
    ip, ua = _client_meta(request)
    attempts = LoginAttemptService(db)
    await attempts.assert_not_locked(
        email=payload.email,
        ip_address=ip,
        login_kind=SESSION_KIND_MODULE,
        module_code=module_code,
    )

    async def _fail(reason: str = "credentials") -> None:
        await attempts.record(
            email=payload.email,
            ip_address=ip,
            login_kind=SESSION_KIND_MODULE,
            success=False,
            module_code=module_code,
        )
        await record_audit(
            db,
            user=user,
            action="login_module_failed",
            entity="module",
            entity_id=module_code,
            request=request,
            module_code=module_code,
            after={"reason": reason, "email": payload.email},
        )
        await db.commit()
        raise _invalid_credentials()

    if payload.email.strip().lower() != user.email.lower():
        await _fail("email_mismatch")
    if not await verify_password_async(payload.password, user.hashed_password):
        await _fail("password")

    access = PlateformeAccessService(db)
    await access.ensure_catalogue()
    module = await access.get_module(module_code)
    if module is None or not module.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module introuvable")
    if not await access.user_has_module(user, module_code):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "MODULE_FORBIDDEN", "message": "Module non autorisé", "module": module_code},
        )

    from app.services.permission_service import permission_codes_from_user, user_has_permission_codes
    from app.services.platform_ops_service import PlatformOpsService

    have = permission_codes_from_user(user)
    can_bypass = user_has_permission_codes(
        have, "core.admin.maintenance.manage", "core.admin.module_status.manage"
    )
    access_info = PlatformOpsService.module_access_payload(module, can_bypass=can_bypass)
    if not access_info["access_allowed"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "MODULE_UNAVAILABLE",
                "message": access_info["status_message"] or "Module indisponible",
                "statut": module.statut,
                "module": module_code,
            },
        )

    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Non authentifié")
    try:
        token_payload = decode_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalide") from exc
    parent_sid = token_payload.get("sid")
    if not parent_sid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalide")

    await attempts.record(
        email=payload.email,
        ip_address=ip,
        login_kind=SESSION_KIND_MODULE,
        success=True,
        module_code=module_code,
    )
    await record_audit(
        db,
        user=user,
        action="login_module",
        entity="module",
        entity_id=module_code,
        request=request,
        espace_code=module.espace.code if module.espace else None,
        module_code=module_code,
    )
    sessions = AuthSessionService(db)
    pair = await sessions.issue_module_tokens(
        user,
        module_code=module_code,
        parent_session_id=UUID(str(parent_sid)),
        ip_address=ip,
        user_agent=ua,
    )
    return auth_cookies.respond(
        request,
        response,
        pair,
        auth_cookies.module_cookie_name(module_code),
        sessions.refresh_max_age_seconds(SESSION_KIND_MODULE),
    )


@router.post("/auth/modules/refresh", response_model=TokenPair)
async def module_refresh(
    request: Request,
    response: Response,
    payload: RefreshRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    body_token = payload.refresh_token if payload else None
    cookie_name: str | None = None
    if auth_cookies.cookie_mode(request):
        cookie_name = auth_cookies.module_cookie_name(payload.module_code if payload else None)
        raw = auth_cookies.read_refresh(request, cookie_name, body_token)
    else:
        raw = body_token
    token_payload = _decoder_refresh(raw)
    if cookie_name and token_payload.get("module") != (payload.module_code or "").strip().lower():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "MODULE_SESSION_EXPIRED", "message": "Session module invalide"},
        )

    service = AuthService(db)
    user = await service.get_by_id(UUID(token_payload["sub"]))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Utilisateur introuvable")

    sessions = AuthSessionService(db)
    try:
        pair = await sessions.rotate_refresh(raw, user, expected_kind=SESSION_KIND_MODULE)
        if cookie_name is None:
            return pair
        return auth_cookies.respond(
            request, response, pair, cookie_name, sessions.refresh_max_age_seconds(SESSION_KIND_MODULE)
        )
    except RefreshTokenReuseError as exc:
        await _journaliser_rejeu(db, request, user, token_payload, SESSION_KIND_MODULE)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "MODULE_SESSION_EXPIRED", "message": str(exc)},
        ) from exc
    except ValueError as exc:
        message = str(exc)
        code = (
            "PLATFORM_SESSION_EXPIRED"
            if "plateforme" in message.lower()
            else "MODULE_SESSION_EXPIRED"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": code, "message": message},
        ) from exc


@router.post("/auth/modules/logout", response_model=MessageResponse)
async def module_logout(
    request: Request,
    response: Response,
    payload: LogoutRequest | None = None,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    sessions = AuthSessionService(db)
    if credentials and credentials.credentials:
        decoded = sessions._decode_unverified(credentials.credentials)
        if decoded and decoded.get("kind") == SESSION_KIND_MODULE:
            await sessions.revoke_by_token(credentials.credentials)
        elif decoded and decoded.get("sid"):
            # jeton module sans claim kind (ne devrait pas arriver) : révoquer uniquement si kind module en base
            session = await sessions.get_active_session(UUID(str(decoded["sid"])))
            if session is not None and session.kind == SESSION_KIND_MODULE:
                await sessions.revoke_session(session.id)
    refresh_token = payload.refresh_token if payload else None
    if auth_cookies.cookie_mode(request) and payload and payload.module_code:
        cookie_name = auth_cookies.module_cookie_name(payload.module_code)
        refresh_token = auth_cookies.read_refresh(request, cookie_name, refresh_token)
        auth_cookies.clear(response, cookie_name)
    if refresh_token:
        decoded = sessions._decode_unverified(refresh_token)
        if decoded and decoded.get("kind") == SESSION_KIND_MODULE:
            await sessions.revoke_by_token(refresh_token)

    await record_audit(
        db,
        user=None,
        action="logout_module",
        entity="module",
        entity_id=None,
        request=request,
        after={"revoked": True},
    )
    return MessageResponse(message="Déconnexion du module effectuée")
