from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import page_offset

ModelT = TypeVar("ModelT")


class BaseRepository(Generic[ModelT]):
    def __init__(self, db: AsyncSession, model: type[ModelT]):
        self.db = db
        self.model = model

    def _active_filter(self, stmt: Select[Any]) -> Select[Any]:
        if hasattr(self.model, "deleted_at"):
            return stmt.where(self.model.deleted_at.is_(None))  # type: ignore[attr-defined]
        return stmt

    async def get_by_id(self, entity_id: UUID) -> ModelT | None:
        stmt = select(self.model).where(self.model.id == entity_id)  # type: ignore[attr-defined]
        stmt = self._active_filter(stmt)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list(
        self,
        page: int,
        size: int,
        search: str | None = None,
        search_columns: tuple[str, ...] = ("libelle", "code"),
    ) -> tuple[list[ModelT], int]:
        stmt = select(self.model)
        count_stmt = select(func.count()).select_from(self.model)
        stmt = self._active_filter(stmt)
        count_stmt = self._active_filter(count_stmt)

        if search:
            pattern = f"%{search}%"
            filters = []
            for col_name in search_columns:
                if hasattr(self.model, col_name):
                    filters.append(getattr(self.model, col_name).ilike(pattern))
            if filters:
                from sqlalchemy import or_

                filt = or_(*filters)
                stmt = stmt.where(filt)
                count_stmt = count_stmt.where(filt)

        total = int((await self.db.execute(count_stmt)).scalar_one())
        if hasattr(self.model, "created_at"):
            stmt = stmt.order_by(self.model.created_at.desc())  # type: ignore[attr-defined]
        result = await self.db.execute(stmt.offset(page_offset(page, size)).limit(size))
        return list(result.scalars().all()), total

    async def add(self, entity: ModelT) -> ModelT:
        self.db.add(entity)
        await self.db.flush()
        return entity

    async def delete_soft(self, entity: ModelT) -> None:
        from datetime import UTC, datetime

        if hasattr(entity, "is_active"):
            entity.is_active = False  # type: ignore[attr-defined]
        if hasattr(entity, "deleted_at"):
            entity.deleted_at = datetime.now(UTC)  # type: ignore[attr-defined]
        await self.db.flush()
