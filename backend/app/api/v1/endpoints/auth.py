from uuid import UUID



from fastapi import APIRouter, Depends, HTTPException, Request, status

from sqlalchemy.ext.asyncio import AsyncSession



from app.api.deps import get_current_user

from app.core.security import decode_token, verify_password

from app.db.session import get_db

from app.models import User

from app.schemas.auth import (

    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
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

from app.services.audit_helpers import record_audit

from app.services.totp_service import generate_secret, provisioning_uri, verify_code
from app.services.inventaire_service import build_qr_png_base64



router = APIRouter(tags=["auth"])





@router.post("/auth/login", response_model=TokenPair)

async def login(payload: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):

    service = AuthService(db)

    user = await service.authenticate(payload.email, payload.password)

    if user is None:

        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Identifiants invalides")



    if user.totp_enabled:

        if not payload.totp_code:

            raise HTTPException(

                status_code=status.HTTP_401_UNAUTHORIZED,

                detail={"code": "TOTP_REQUIRED", "message": "Code authenticator requis"},

            )

        if not verify_code(user.totp_secret, payload.totp_code):

            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Code 2FA invalide")



    await record_audit(

        db,

        user=user,

        action="login",

        entity="user",

        entity_id=str(user.id),

        request=request,

    )

    return service.build_tokens(user)





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

    return service.build_tokens(user)





@router.post("/auth/logout", response_model=MessageResponse)

async def logout(_: User = Depends(get_current_user)):

    return MessageResponse(message="Déconnexion effectuée")





@router.get("/auth/me", response_model=UserRead)

async def me(user: User = Depends(get_current_user)):

    return user





@router.get("/auth/2fa/status", response_model=TotpStatusResponse)

async def totp_status(user: User = Depends(get_current_user)):

    pending = bool(user.totp_secret and not user.totp_enabled)

    return TotpStatusResponse(enabled=user.totp_enabled, pending_setup=pending)





@router.post("/auth/2fa/setup", response_model=TotpSetupResponse)

async def totp_setup(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):

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

    user: User = Depends(get_current_user),

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

    user: User = Depends(get_current_user),

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
async def forgot_password(payload: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    from app.core.config import get_settings
    from app.core.security import create_password_reset_token

    service = AuthService(db)
    user = await service.find_active_by_email(payload.email)
    message = "Si l'email existe, un lien de réinitialisation a été envoyé."
    reset_token: str | None = None
    if user is not None:
        reset_token = create_password_reset_token(user.id)
        if get_settings().app_debug:
            message = f"Mode dev : utilisez le token ci-dessous (validité 1 h)."
    return ForgotPasswordResponse(message=message, reset_token=reset_token)


@router.post("/auth/reset-password", response_model=MessageResponse)
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    service = AuthService(db)
    try:
        await service.reset_password(payload.token, payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return MessageResponse(message="Mot de passe mis à jour")

