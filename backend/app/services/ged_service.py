"""GED CORE — convention de stockage, sans API d'upload métier pour l'instant."""

from __future__ import annotations

import re
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.ged import GedDocument

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_segment(value: str) -> str:
    cleaned = _SAFE.sub("-", (value or "").strip())[:80]
    return cleaned or "x"


class GedService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def relative_path(
        self,
        *,
        module_code: str,
        entity: str,
        entity_id: str,
        filename: str,
    ) -> str:
        name = Path(filename).name or "fichier"
        return "/".join(
            (
                _safe_segment(module_code),
                _safe_segment(entity),
                _safe_segment(entity_id),
                name,
            )
        )

    def absolute_path(self, stored_path: str) -> Path:
        root = Path(get_settings().ged_dir)
        return root / stored_path

    async def register(
        self,
        *,
        espace_code: str,
        module_code: str,
        entity: str,
        entity_id: str,
        filename: str,
        stored_path: str | None = None,
        mime_type: str | None = None,
        size_bytes: int = 0,
        uploaded_by_id: UUID | None = None,
    ) -> GedDocument:
        path = stored_path or self.relative_path(
            module_code=module_code,
            entity=entity,
            entity_id=entity_id,
            filename=filename,
        )
        row = GedDocument(
            espace_code=espace_code,
            module_code=module_code,
            entity=entity,
            entity_id=str(entity_id),
            filename=Path(filename).name,
            stored_path=path,
            mime_type=mime_type,
            size_bytes=size_bytes,
            uploaded_by_id=uploaded_by_id,
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def list_for_entity(
        self,
        *,
        module_code: str,
        entity: str,
        entity_id: str,
    ) -> list[GedDocument]:
        result = await self.db.execute(
            select(GedDocument)
            .where(
                GedDocument.module_code == module_code,
                GedDocument.entity == entity,
                GedDocument.entity_id == str(entity_id),
                GedDocument.deleted_at.is_(None),
            )
            .order_by(GedDocument.created_at.desc())
        )
        return list(result.scalars().all())
