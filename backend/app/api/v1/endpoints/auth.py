from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import bearer_scheme, get_platform_user
from app.core.security import decode_token, verify_password
from app.db.session import get_db
from app.models import User
from app.models.auth import SESSION_KIND_MODULE, SESSION_KIND_PLATFORM
from app.schemas.auth import (
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
from app.services.auth_session_service import AuthSessionService
from app.services.audit_helpers import record_audit
from app.services.inventaire_service import build_qr_png_base64
from app.services.login_attempt_service import LoginAttemptService
from app.services.plateforme_access_service import PlateformeAccessService
from app.services.totp_service import generate_secret, provisioning_uri, verify_code

router = APIRouter(tags=["auth"])


def _client_meta(request: Request) -> tuple[str | None, str | None]:
    forwarded = request.headers.get("x-forwarded-for")
    ip = (forwarded.split(",")[0].strip() if forwarded else None) or (
        request.client.host if request.client else None
    )
    ua = request.headers.get("user-agent")
    return ip, ua


@router.post("/auth/login", response_model=TokenPair)
async def login(payload: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Identifiants invalides")

    if user.totp_enabled:
        if not payload.totp_code:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "TOTP_REQUIRED", "message": "Code authenticator requis"},
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
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Code 2FA invalide")

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
    return await AuthSessionService(db).issue_platform_tokens(user, ip_address=ip, user_agent=ua)


@router.post("/auth/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        token_payload = decode_token(payload.refresh_token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token invalide") from exc

    if token_payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token invalide")

    service = AuthService(db)
    user = await service.get_by_id(UUID(token_payload["sub"]))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Utilisateur introuvable")

    try:
        return await AuthSessionService(db).rotate_refresh(
            payload.refresh_token, user, expected_kind=SESSION_KIND_PLATFORM
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.post("/auth/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    payload: LogoutRequest | None = None,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    """Révoque la session courante (access et/ou refresh). Ne bloque pas si déjà invalide."""
    sessions = AuthSessionService(db)
    if credentials and credentials.credentials:
        await sessions.revoke_by_token(credentials.credentials)
    if payload and payload.refresh_token:
        await sessions.revoke_by_token(payload.refresh_token)

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


@router.get("/auth/2fa/status", response_model=TotpStatusResponse)
async def totp_status(user: User = Depends(get_platform_user)):
    pending = bool(user.totp_secret and not user.totp_enabled)
    return TotpStatusResponse(enabled=user.totp_enabled, pending_setup=pending)


@router.post("/auth/2fa/setup", response_model=TotpSetupResponse)
async def totp_setup(user: User = Depends(get_platform_user), db: AsyncSession = Depends(get_db)):
    if user.totp_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA déjà activée")
    secret = generate_secret()
    user.totp_secret = secret
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
    """Réinitialisation : pas d'envoi SMTP pour l'instant.

    En mode développement (`APP_DEBUG=true`), le token est renvoyé dans la réponse
    pour permettre de réinitialiser sans boîte mail. En production, seul un message
    générique est renvoyé (le token n'est jamais exposé).
    """
    import logging

    from app.core.config import get_settings
    from app.core.security import PASSWORD_RESET_EXPIRE_SECONDS, create_password_reset_token

    settings = get_settings()
    service = AuthService(db)
    user = await service.find_active_by_email(payload.email)
    dev_mode = bool(settings.app_debug) or settings.app_env.lower() in {"development", "dev", "local"}

    message = "Si l'email existe, un lien de réinitialisation a été envoyé."
    reset_token: str | None = None
    account_found = user is not None
    expires_in: int | None = None

    if user is not None:
        reset_token = create_password_reset_token(user.id)
        expires_in = PASSWORD_RESET_EXPIRE_SECONDS
        logging.getLogger("bea.auth").info(
            "Password reset token generated for user_id=%s (dev_mode=%s, ttl=%ss)",
            user.id,
            dev_mode,
            PASSWORD_RESET_EXPIRE_SECONDS,
        )
        await record_audit(
            db,
            user=user,
            action="password_forgot",
            entity="user",
            entity_id=str(user.id),
            request=request,
            after={"dev_mode": dev_mode},
        )
        await db.commit()
        if not dev_mode:
            reset_token = None
            expires_in = None
        else:
            message = (
                f"Compte trouvé — cliquez sur le lien ci-dessous pour choisir un nouveau mot de passe "
                f"(valide {PASSWORD_RESET_EXPIRE_SECONDS // 60} min)."
            )
    elif dev_mode:
        message = (
            "Aucun compte actif avec cet email. "
            "Utilisez un email existant (ex. admin@el-amana.mr)."
        )

    return ForgotPasswordResponse(
        message=message,
        reset_token=reset_token if dev_mode else None,
        account_found=account_found if dev_mode else False,
        dev_mode=dev_mode,
        expires_in_seconds=expires_in if dev_mode else None,
    )


@router.post("/auth/reset-password", response_model=MessageResponse)
async def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    try:
        await service.reset_password(payload.token, payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await record_audit(
        db,
        user=None,
        action="password_reset",
        entity="user",
        entity_id=None,
        request=request,
        after={"via": "reset_token"},
    )
    await db.commit()
    return MessageResponse(message="Mot de passe mis à jour")


@router.post("/auth/modules/{module_code}/login", response_model=TokenPair)
async def module_login(
    module_code: str,
    payload: LoginRequest,
    request: Request,
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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Identifiants invalides")

    if payload.email.strip().lower() != user.email.lower():
        await _fail("email_mismatch")
    if not verify_password(payload.password, user.hashed_password):
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
    return await AuthSessionService(db).issue_module_tokens(
        user,
        module_code=module_code,
        parent_session_id=UUID(str(parent_sid)),
        ip_address=ip,
        user_agent=ua,
    )


@router.post("/auth/modules/refresh", response_model=TokenPair)
async def module_refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        token_payload = decode_token(payload.refresh_token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token invalide") from exc

    if token_payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token invalide")

    service = AuthService(db)
    user = await service.get_by_id(UUID(token_payload["sub"]))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Utilisateur introuvable")

    try:
        return await AuthSessionService(db).rotate_refresh(
            payload.refresh_token, user, expected_kind=SESSION_KIND_MODULE
        )
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
    if payload and payload.refresh_token:
        decoded = sessions._decode_unverified(payload.refresh_token)
        if decoded and decoded.get("kind") == SESSION_KIND_MODULE:
            await sessions.revoke_by_token(payload.refresh_token)

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
