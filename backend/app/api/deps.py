from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import decode_token
from app.db.session import get_db
from app.models import Permission, Role, User
from app.models.auth import SESSION_KIND_MODULE, SESSION_KIND_PLATFORM
from app.services.auth_session_service import AuthSessionService
from app.services.permission_service import load_user_permission_codes, user_has_permission_codes
from app.services.plateforme_access_service import PlateformeAccessService

bearer_scheme = HTTPBearer(auto_error=False)

_USER_LOAD = (
    selectinload(User.roles).selectinload(Role.permissions),
    selectinload(User.espaces),
    selectinload(User.modules),
)


def auth_http_error(
    status_code: int,
    code: str,
    message: str,
    **extra: object,
) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message, **extra})


async def _load_user_and_session(
    credentials: HTTPAuthorizationCredentials | None,
    db: AsyncSession,
) -> tuple[User, object, dict]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise auth_http_error(status.HTTP_401_UNAUTHORIZED, "UNAUTHENTICATED", "Non authentifié")

    try:
        payload = decode_token(credentials.credentials)
    except ValueError as exc:
        raise auth_http_error(status.HTTP_401_UNAUTHORIZED, "TOKEN_INVALID", "Token invalide") from exc

    if payload.get("type") != "access":
        raise auth_http_error(status.HTTP_401_UNAUTHORIZED, "TOKEN_INVALID", "Token invalide")

    user_id = payload.get("sub")
    sid_raw = payload.get("sid")
    if not user_id or not sid_raw:
        raise auth_http_error(status.HTTP_401_UNAUTHORIZED, "TOKEN_INVALID", "Token invalide")

    session = await AuthSessionService(db).get_active_session(UUID(str(sid_raw)))
    if session is None or str(session.user_id) != str(user_id):
        kind = payload.get("kind", SESSION_KIND_PLATFORM)
        code = (
            "MODULE_SESSION_EXPIRED"
            if kind == SESSION_KIND_MODULE
            else "PLATFORM_SESSION_EXPIRED"
        )
        raise auth_http_error(status.HTTP_401_UNAUTHORIZED, code, "Session expirée ou révoquée")

    result = await db.execute(
        select(User).options(*_USER_LOAD).where(User.id == UUID(user_id), User.is_active.is_(True))
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise auth_http_error(status.HTTP_401_UNAUTHORIZED, "USER_NOT_FOUND", "Utilisateur introuvable")
    return user, session, payload


def _bind_request_session(
    request: Request,
    session: object,
    *,
    module_code: str | None = None,
    espace_code: str | None = None,
) -> None:
    request.state.bea_session_id = getattr(session, "id", None)
    request.state.bea_module_code = module_code
    request.state.bea_espace_code = espace_code


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    user, session, _ = await _load_user_and_session(credentials, db)
    kind = getattr(session, "kind", None) or SESSION_KIND_PLATFORM
    module_code = getattr(session, "module_code", None) if kind == SESSION_KIND_MODULE else None
    _bind_request_session(request, session, module_code=module_code)
    return user


async def get_platform_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    user, session, _ = await _load_user_and_session(credentials, db)
    kind = getattr(session, "kind", None) or SESSION_KIND_PLATFORM
    if kind != SESSION_KIND_PLATFORM:
        raise auth_http_error(
            status.HTTP_401_UNAUTHORIZED,
            "PLATFORM_SESSION_EXPIRED",
            "Session BEA DIGITAL requise",
        )
    _bind_request_session(request, session)
    return user


def require_module_access(module_code: str):
    async def _checker(
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        user, session, _ = await _load_user_and_session(credentials, db)
        kind = getattr(session, "kind", None) or SESSION_KIND_PLATFORM
        if kind != SESSION_KIND_MODULE or session.module_code != module_code:
            raise auth_http_error(
                status.HTTP_401_UNAUTHORIZED,
                "MODULE_AUTH_REQUIRED",
                "Authentification du module requise",
                module=module_code,
            )
        parent_id = session.parent_session_id
        if parent_id is None:
            raise auth_http_error(
                status.HTTP_401_UNAUTHORIZED,
                "PLATFORM_SESSION_EXPIRED",
                "Session BEA DIGITAL expirée ou révoquée",
            )
        parent = await AuthSessionService(db).get_active_session(parent_id)
        if parent is None or (parent.kind or SESSION_KIND_PLATFORM) != SESSION_KIND_PLATFORM:
            raise auth_http_error(
                status.HTTP_401_UNAUTHORIZED,
                "PLATFORM_SESSION_EXPIRED",
                "Session BEA DIGITAL expirée ou révoquée",
            )
        access = PlateformeAccessService(db)
        module = await access.get_module(module_code)
        if module is None or not module.is_active or module.statut != "actif":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Module indisponible")
        if not await access.user_has_module(user, module_code):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "MODULE_FORBIDDEN", "message": "Module non autorisé", "module": module_code},
            )
        request.state.bea_module_code = module_code
        request.state.bea_espace_code = module.espace.code if module.espace else None
        request.state.bea_session_id = getattr(session, "id", None)
        return user

    return _checker


def require_roles(*role_codes: str):
    async def _checker(user: User = Depends(get_current_user)) -> User:
        if user.is_superuser:
            return user
        user_codes = {r.code for r in user.roles}
        if not user_codes.intersection(set(role_codes)):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission refusée")
        return user

    return _checker


def require_permission(*permission_codes: str):
    async def _checker(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        have = await load_user_permission_codes(db, user)
        if user_has_permission_codes(have, *permission_codes):
            return user
        raise auth_http_error(
            status.HTTP_403_FORBIDDEN,
            "PERMISSION_DENIED",
            "Permission refusée",
            required=list(permission_codes),
        )

    return _checker


def require_platform_permission(*permission_codes: str):
    """Login 1 uniquement (ex. CORE ADMIN)."""

    async def _checker(
        user: User = Depends(get_platform_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        from app.core.config import get_settings
        from app.services.security_policy_service import get_cached_security_policy

        have = await load_user_permission_codes(db, user)
        if not user_has_permission_codes(have, *permission_codes):
            raise auth_http_error(
                status.HTTP_403_FORBIDDEN,
                "PERMISSION_DENIED",
                "Permission refusée",
                required=list(permission_codes),
            )
        pol = get_cached_security_policy()
        if pol.get("mfa_required_for_core_admin") and not user.totp_enabled:
            is_admin = user.is_superuser or user_has_permission_codes(have, "core.admin.access")
            if is_admin and any(code.startswith("core.admin") for code in permission_codes):
                raise auth_http_error(
                    status.HTTP_403_FORBIDDEN,
                    "MFA_REQUIRED",
                    "Activez l’authentification à deux facteurs pour accéder à CORE ADMIN.",
                )
        return user

    return _checker
