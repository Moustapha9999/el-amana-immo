from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.services.audit_service import AuditService


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
) -> None:
    ip = request.client.host if request and request.client else None
    await AuditService(db).log(
        user=user,
        action=action,
        entity=entity,
        entity_id=entity_id,
        before=before,
        after=after,
        ip_address=ip,
    )
