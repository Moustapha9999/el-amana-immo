"""CORE ADMIN — journal d’audit (Login 1)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.pagination import page_offset
from app.models import AuditLog, User
from app.services.audit_query import list_audit_logs
from app.services.core_admin_service import day_bounds_nouakchott, serialize_activity

_MUTATION_ACTIONS = ("create", "update", "delete", "revoke", "revoke_all", "activate", "deactivate")


class CoreAdminAuditService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _count(self, stmt) -> int:
        result = await self.db.execute(stmt)
        return int(result.scalar() or 0)

    async def kpis(self) -> dict:
        start, end = day_bounds_nouakchott()
        total = await self._count(select(func.count()).select_from(AuditLog))
        aujourd_hui = await self._count(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.created_at >= start, AuditLog.created_at < end)
        )
        logins = await self._count(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == "login")
        )
        mutations = await self._count(
            select(func.count()).select_from(AuditLog).where(AuditLog.action.in_(_MUTATION_ACTIONS))
        )
        core = await self._count(
            select(func.count()).select_from(AuditLog).where(AuditLog.module_code == "core")
        )
        return {
            "total": total,
            "aujourd_hui": aujourd_hui,
            "logins": logins,
            "mutations": mutations,
            "core": core,
        }

    def serialize(self, row: AuditLog) -> dict:
        base = serialize_activity(row)
        return {
            "id": base["id"],
            "user_id": str(row.user_id) if row.user_id else None,
            "user_email": base["email"],
            "user_full_name": base["who"] if row.user else None,
            "action": row.action,
            "entity": row.entity,
            "entity_id": row.entity_id,
            "ip_address": row.ip_address,
            "espace_code": row.espace_code,
            "module_code": row.module_code,
            "session_id": str(row.session_id) if row.session_id else None,
            "created_at": base["created_at"],
        }

    async def options(self) -> dict:
        modules = [
            row[0]
            for row in (
                await self.db.execute(
                    select(AuditLog.module_code)
                    .where(AuditLog.module_code.is_not(None))
                    .distinct()
                    .order_by(AuditLog.module_code.asc())
                )
            ).all()
            if row[0]
        ]
        entities = [
            row[0]
            for row in (
                await self.db.execute(
                    select(AuditLog.entity).distinct().order_by(AuditLog.entity.asc())
                )
            ).all()
            if row[0]
        ]
        return {"modules": modules, "entities": entities}

    async def list_logs(
        self,
        page: int,
        size: int,
        *,
        search: str | None = None,
        entity: str | None = None,
        action: str | None = None,
        module_code: str | None = None,
        date_debut: date | None = None,
        date_fin: date | None = None,
        kind: str = "tous",
    ) -> tuple[list[dict], int, dict, dict]:
        effective_action = action
        effective_module = module_code
        effective_debut = date_debut
        effective_fin = date_fin

        if kind == "aujourd_hui":
            start, _end = day_bounds_nouakchott()
            effective_debut = start.date()
            effective_fin = start.date()
        elif kind == "logins":
            effective_action = "login"
        elif kind == "core":
            effective_module = "core"
        elif kind == "mutations":
            filters = [AuditLog.action.in_(_MUTATION_ACTIONS)]
            if entity:
                filters.append(AuditLog.entity == entity)
            if effective_module:
                filters.append(AuditLog.module_code == effective_module)
            join_user = bool(search and search.strip())
            if join_user:
                term = f"%{search.strip().lower()}%"
                filters.append(
                    or_(
                        func.lower(AuditLog.action).like(term),
                        func.lower(AuditLog.entity).like(term),
                        func.lower(AuditLog.ip_address).like(term),
                        func.lower(User.email).like(term),
                    )
                )
            count_stmt = select(func.count()).select_from(AuditLog)
            if join_user:
                count_stmt = count_stmt.outerjoin(User, AuditLog.user_id == User.id)
            total = int((await self.db.execute(count_stmt.where(*filters))).scalar() or 0)
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
            rows = list((await self.db.execute(stmt)).scalars().unique().all())
            return [self.serialize(row) for row in rows], total, await self.kpis(), await self.options()

        rows, total = await list_audit_logs(
            self.db,
            page,
            size,
            entity=entity or None,
            action=effective_action or None,
            search=search or None,
            date_debut=effective_debut,
            date_fin=effective_fin,
            module_code=effective_module or None,
        )
        return [self.serialize(row) for row in rows], total, await self.kpis(), await self.options()
