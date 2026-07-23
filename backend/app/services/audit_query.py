from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.pagination import page_offset
from app.models import AuditLog


async def list_audit_logs(
    db: AsyncSession,
    page: int,
    size: int,
    *,
    entity: str | None = None,
    action: str | None = None,
) -> tuple[list[AuditLog], int]:
    filters = []
    if entity:
        filters.append(AuditLog.entity == entity)
    if action:
        filters.append(AuditLog.action == action)

    count = await db.execute(select(func.count()).select_from(AuditLog).where(*filters))
    total = int(count.scalar_one())
    result = await db.execute(
        select(AuditLog)
        .options(selectinload(AuditLog.user))
        .where(*filters)
        .order_by(AuditLog.created_at.desc())
        .offset(page_offset(page, size))
        .limit(size)
    )
    return list(result.scalars().all()), total


async def list_audit_for_export(db: AsyncSession, limit: int = 5000) -> list[AuditLog]:
    result = await db.execute(
        select(AuditLog)
        .options(selectinload(AuditLog.user))
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
