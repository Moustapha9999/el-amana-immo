"""CORE ADMIN — sessions (Login 1, core.admin.sessions)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_platform_permission
from app.db.session import get_db
from app.models import User
from app.schemas.common import MessageResponse
from app.schemas.plateforme import CoreAdminSessionListRead, CoreAdminSessionRead
from app.services.audit_helpers import record_audit
from app.services.core_admin_sessions_service import CoreAdminSessionsService

router = APIRouter(prefix="/plateforme/admin", tags=["core-admin"])

_SESSIONS_PERM = require_platform_permission("core.admin.sessions")


def _http_from_value_error(exc: ValueError) -> HTTPException:
    detail = str(exc)
    missing = detail.endswith("introuvable")
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND if missing else status.HTTP_400_BAD_REQUEST,
        detail=detail,
    )


def _current_session_id(request: Request) -> UUID | None:
    raw = getattr(request.state, "bea_session_id", None)
    if raw is None:
        return None
    try:
        return UUID(str(raw))
    except ValueError:
        return None


@router.get("/sessions", response_model=CoreAdminSessionListRead)
async def list_sessions(
    request: Request,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    kind: str = Query("tous", pattern="^(tous|platform|module)$"),
    status_filter: str = Query("actives", alias="status", pattern="^(tous|actives|expirees|revoquees)$"),
    _: User = Depends(_SESSIONS_PERM),
    db: AsyncSession = Depends(get_db),
):
    current_id = _current_session_id(request)
    items, total, kpis = await CoreAdminSessionsService(db).list_sessions(
        page,
        size,
        search=search,
        kind=kind,
        status=status_filter,
        current_session_id=current_id,
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "kpis": kpis,
        "current_session_id": str(current_id) if current_id else None,
    }


@router.post("/sessions/{session_id}/revoke", response_model=CoreAdminSessionRead)
async def revoke_session(
    session_id: UUID,
    request: Request,
    actor: User = Depends(_SESSIONS_PERM),
    db: AsyncSession = Depends(get_db),
):
    current_id = _current_session_id(request)
    try:
        row = await CoreAdminSessionsService(db).revoke(session_id, actor_session_id=current_id)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    await record_audit(
        db,
        user=actor,
        action="revoke",
        entity="auth_session",
        entity_id=str(session_id),
        request=request,
        after={"user_id": row["user_id"], "kind": row["kind"], "module_code": row.get("module_code")},
        module_code="core",
    )
    return row


@router.post("/sessions/users/{user_id}/revoke-all", response_model=MessageResponse)
async def revoke_all_user_sessions(
    user_id: UUID,
    request: Request,
    actor: User = Depends(_SESSIONS_PERM),
    db: AsyncSession = Depends(get_db),
):
    from app.services.auth_session_service import AuthSessionService

    current_id = _current_session_id(request)
    if actor.id == user_id:
        # Révoque tout sauf la session courante : revoke_all puis on ne peut pas « un-revoke ».
        # On refuse pour éviter un auto-logout silencieux.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Impossible de révoquer toutes vos sessions d’un coup",
        )
    _ = current_id
    await AuthSessionService(db).revoke_all_for_user(user_id)
    await record_audit(
        db,
        user=actor,
        action="revoke_all",
        entity="user_sessions",
        entity_id=str(user_id),
        request=request,
        after={"user_id": str(user_id)},
        module_code="core",
    )
    return MessageResponse(message="Sessions utilisateur révoquées")
