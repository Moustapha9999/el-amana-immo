from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.request_client import get_client_ip
from app.models import User
from app.services.audit_service import AuditService


def _state_value(request: Request | None, name: str):
    if request is None:
        return None
    return getattr(request.state, name, None)


async def record_audit(
    db: AsyncSession,
    *,
    user: User | None,
    action: str,
    entity: str,
    entity_id: str | None,
    request: Request | None = None,
    before: dict | None = None,
    after: dict | None = None,
    espace_code: str | None = None,
    module_code: str | None = None,
    session_id: UUID | None = None,
) -> None:
    ip = get_client_ip(request)
    await AuditService(db).log(
        user=user,
        action=action,
        entity=entity,
        entity_id=entity_id,
        before=before,
        after=after,
        ip_address=ip,
        espace_code=espace_code or _state_value(request, "bea_espace_code"),
        module_code=module_code or _state_value(request, "bea_module_code"),
        session_id=session_id or _state_value(request, "bea_session_id"),
    )
