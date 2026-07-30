from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.pagination import page_offset
from app.models import AuditLog, User

_TZ = ZoneInfo("Africa/Nouakchott")


def _day_start(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=_TZ)


def _day_end(d: date) -> datetime:
    return datetime.combine(d, time.max, tzinfo=_TZ)


def _audit_filters(
    *,
    entity: str | None = None,
    action: str | None = None,
    search: str | None = None,
    date_debut: date | None = None,
    date_fin: date | None = None,
) -> list:
    filters = []
    if entity:
        filters.append(AuditLog.entity == entity)
    if action and action.strip():
        filters.append(func.lower(AuditLog.action).like(f"%{action.strip().lower()}%"))
    if date_debut:
        filters.append(AuditLog.created_at >= _day_start(date_debut))
    if date_fin:
        filters.append(AuditLog.created_at <= _day_end(date_fin))
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        filters.append(
            or_(
                func.lower(AuditLog.action).like(term),
                func.lower(AuditLog.entity).like(term),
                func.lower(AuditLog.ip_address).like(term),
                func.lower(User.email).like(term),
            )
        )
    return filters


async def list_audit_logs(
    db: AsyncSession,
    page: int,
    size: int,
    *,
    entity: str | None = None,
    action: str | None = None,
    search: str | None = None,
    date_debut: date | None = None,
    date_fin: date | None = None,
) -> tuple[list[AuditLog], int]:
    filters = _audit_filters(
        entity=entity,
        action=action,
        search=search,
        date_debut=date_debut,
        date_fin=date_fin,
    )
    join_user = bool(search and search.strip())

    count_stmt = select(func.count()).select_from(AuditLog)
    if join_user:
        count_stmt = count_stmt.outerjoin(User, AuditLog.user_id == User.id)
    count = await db.execute(count_stmt.where(*filters))
    total = int(count.scalar_one())

    stmt = (
        select(AuditLog)
        .options(selectinload(AuditLog.user))
        .where(*filters)
        .order_by(AuditLog.created_at.desc())
        .offset(page_offset(page, size))
        .limit(size)
    )
    if join_user:
        stmt = stmt.outerjoin(User, AuditLog.user_id == User.id)
    result = await db.execute(stmt)
    return list(result.scalars().unique().all()), total


async def list_audit_for_export(
    db: AsyncSession,
    limit: int = 5000,
    *,
    entity: str | None = None,
    action: str | None = None,
    search: str | None = None,
    date_debut: date | None = None,
    date_fin: date | None = None,
) -> list[AuditLog]:
    filters = _audit_filters(
        entity=entity,
        action=action,
        search=search,
        date_debut=date_debut,
        date_fin=date_fin,
    )
    stmt = (
        select(AuditLog)
        .options(selectinload(AuditLog.user))
        .where(*filters)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    if search and search.strip():
        stmt = stmt.outerjoin(User, AuditLog.user_id == User.id)
    result = await db.execute(stmt)
    return list(result.scalars().unique().all())
