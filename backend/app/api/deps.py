from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import decode_token
from app.db.session import get_db
from app.models import User
from app.services.auth_session_service import AuthSessionService

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Non authentifié")

    try:
        payload = decode_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalide") from exc

    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalide")

    user_id = payload.get("sub")
    sid_raw = payload.get("sid")
    if not user_id or not sid_raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalide")

    session = await AuthSessionService(db).get_active_session(UUID(str(sid_raw)))
    if session is None or str(session.user_id) != str(user_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expirée ou révoquée",
        )

    result = await db.execute(
        select(User).options(selectinload(User.roles)).where(User.id == UUID(user_id), User.is_active.is_(True))
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Utilisateur introuvable")
    return user


def require_roles(*role_codes: str):
    async def _checker(user: User = Depends(get_current_user)) -> User:
        if user.is_superuser:
            return user
        user_codes = {r.code for r in user.roles}
        if not user_codes.intersection(set(role_codes)):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission refusée")
        return user

    return _checker
