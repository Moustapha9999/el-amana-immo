from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, User


class AuditService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def log(
        self,
        *,
        user: User | None,
        action: str,
        entity: str,
        entity_id: str | None,
        before: dict | None = None,
        after: dict | None = None,
        ip_address: str | None = None,
        espace_code: str | None = None,
        module_code: str | None = None,
        session_id: UUID | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            user_id=user.id if user else None,
            action=action,
            entity=entity,
            entity_id=entity_id,
            before_data=before,
            after_data=after,
            ip_address=ip_address,
            espace_code=espace_code,
            module_code=module_code,
            session_id=session_id,
        )
        self.db.add(entry)
        await self.db.flush()
        return entry

    async def list(
        self,
        page: int,
        size: int,
        *,
        entity: str | None = None,
        action: str | None = None,
        search: str | None = None,
        date_debut: date | None = None,
        date_fin: date | None = None,
        espace_code: str | None = None,
        module_code: str | None = None,
    ) -> tuple[list[AuditLog], int]:
        from app.services.audit_query import list_audit_logs

        return await list_audit_logs(
            self.db,
            page,
            size,
            entity=entity,
            action=action,
            search=search,
            date_debut=date_debut,
            date_fin=date_fin,
            espace_code=espace_code,
            module_code=module_code,
        )
