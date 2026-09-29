"""CORE ADMIN — supervision des erreurs API (lecture seule)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import page_offset
from app.models import ApiErrorEvent, User

PERIODES = {"24h": timedelta(hours=24), "7j": timedelta(days=7), "30j": timedelta(days=30)}
CATEGORIES = {
    "serveur": (ApiErrorEvent.status_code >= 500,),
    "refus": (ApiErrorEvent.status_code == 403,),
    "conflits": (ApiErrorEvent.status_code.in_((409, 429)),),
    "validation": (ApiErrorEvent.status_code == 422,),
}


class CoreAdminSupervisionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _count(self, *filters) -> int:
        stmt = select(func.count()).select_from(ApiErrorEvent).where(*filters)
        return int((await self.db.execute(stmt)).scalar() or 0)

    async def kpis(self, since: datetime) -> dict:
        base = ApiErrorEvent.created_at >= since
        out = {"total": await self._count(base)}
        for key, filters in CATEGORIES.items():
            out[key] = await self._count(base, *filters)
        return out

    async def _top(self, column, since: datetime, limit: int = 5) -> list[dict]:
        stmt = (
            select(column, func.count().label("n"))
            .where(ApiErrorEvent.created_at >= since, column.is_not(None))
            .group_by(column)
            .order_by(func.count().desc())
            .limit(limit)
        )
        return [{"label": str(label), "count": int(n)} for label, n in (await self.db.execute(stmt)).all()]

    async def list_events(
        self,
        page: int,
        size: int,
        *,
        periode: str = "24h",
        categorie: str | None = None,
        search: str | None = None,
    ) -> dict:
        since = datetime.now(timezone.utc) - PERIODES.get(periode, PERIODES["24h"])
        filters = [ApiErrorEvent.created_at >= since]
        if categorie in CATEGORIES:
            filters.extend(CATEGORIES[categorie])
        term = (search or "").strip().lower()
        if term:
            like = f"%{term}%"
            filters.append(
                or_(
                    func.lower(ApiErrorEvent.request_id).like(like),
                    func.lower(ApiErrorEvent.route).like(like),
                    func.lower(ApiErrorEvent.code).like(like),
                    func.lower(ApiErrorEvent.message).like(like),
                    func.lower(User.email).like(like),
                )
            )

        joined = select(ApiErrorEvent, User.email, User.full_name).outerjoin(User, ApiErrorEvent.user_id == User.id)
        total_stmt = (
            select(func.count())
            .select_from(ApiErrorEvent)
            .outerjoin(User, ApiErrorEvent.user_id == User.id)
            .where(*filters)
        )
        total = int((await self.db.execute(total_stmt)).scalar() or 0)
        rows = (
            await self.db.execute(
                joined.where(*filters)
                .order_by(ApiErrorEvent.created_at.desc())
                .offset(page_offset(page, size))
                .limit(size)
            )
        ).all()

        return {
            "items": [self._serialize(ev, email, name) for ev, email, name in rows],
            "total": total,
            "page": page,
            "size": size,
            "periode": periode,
            "kpis": await self.kpis(since),
            "top_routes": await self._top(ApiErrorEvent.route, since),
            "top_codes": await self._top(ApiErrorEvent.code, since),
        }

    @staticmethod
    def _serialize(ev: ApiErrorEvent, email: str | None, name: str | None) -> dict:
        return {
            "id": str(ev.id),
            "created_at": ev.created_at.isoformat() if ev.created_at else None,
            "request_id": ev.request_id,
            "method": ev.method,
            "route": ev.route,
            "status_code": ev.status_code,
            "code": ev.code,
            "message": ev.message,
            "exception_type": ev.exception_type,
            "user_id": str(ev.user_id) if ev.user_id else None,
            "user_email": email,
            "user_full_name": name,
            "module_code": ev.module_code,
            "ip_address": ev.ip_address,
            "duration_ms": ev.duration_ms,
        }
