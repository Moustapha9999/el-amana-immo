from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.repositories.base import BaseRepository

ModelT = TypeVar("ModelT")
CreateT = TypeVar("CreateT", bound=BaseModel)
UpdateT = TypeVar("UpdateT", bound=BaseModel)


class BaseCrudService(Generic[ModelT, CreateT, UpdateT]):
    entity_label: str = "Enregistrement"

    def __init__(self, db: AsyncSession, model: type[ModelT]):
        self.db = db
        self.repo = BaseRepository(db, model)
        self.model = model

    async def list(self, page: int, size: int, search: str | None = None) -> tuple[list[ModelT], int]:
        return await self.repo.list(page, size, search)

    async def get(self, entity_id: UUID) -> ModelT:
        item = await self.repo.get_by_id(entity_id)
        if item is None:
            raise NotFoundError(self.entity_label, str(entity_id))
        return item

    async def create(self, payload: CreateT) -> ModelT:
        item = self.model(**payload.model_dump())
        return await self.repo.add(item)

    async def update(self, entity_id: UUID, payload: UpdateT) -> ModelT:
        item = await self.get(entity_id)
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(item, key, value)
        await self.db.flush()
        return item

    async def soft_delete(self, entity_id: UUID) -> None:
        item = await self.get(entity_id)
        await self.repo.delete_soft(item)
