"""GED CORE — stockage `storage/ged/{module}/{entity}/{id}/` + métadonnées DB."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import NotFoundError, ValidationError
from app.models.ged import GedDocument

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")
_MAX_BYTES = 25 * 1024 * 1024  # 25 Mo
_ALLOWED_SUFFIXES = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".csv",
    ".txt",
    ".zip",
}


def _safe_segment(value: str) -> str:
    cleaned = _SAFE.sub("-", (value or "").strip())[:80]
    return cleaned or "x"


class GedService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.root = Path(get_settings().ged_dir)
        self.root.mkdir(parents=True, exist_ok=True)

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
        """Résout un chemin relatif sous ged_dir — refuse le path traversal."""
        raw = (stored_path or "").replace("\\", "/").lstrip("/")
        if not raw or ".." in Path(raw).parts:
            raise ValidationError("Chemin de fichier invalide")
        root = self.root.resolve()
        candidate = (root / raw).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValidationError("Chemin de fichier hors zone GED") from exc
        return candidate

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

    async def upload(
        self,
        *,
        file: UploadFile,
        espace_code: str,
        module_code: str,
        entity: str,
        entity_id: str,
        uploaded_by_id: UUID | None = None,
    ) -> GedDocument:
        original = Path(file.filename or "fichier").name
        suffix = Path(original).suffix.lower()
        if suffix and suffix not in _ALLOWED_SUFFIXES:
            raise ValidationError(f"Type de fichier non autorisé ({suffix})")
        content = await file.read()
        if not content:
            raise ValidationError("Fichier vide")
        if len(content) > _MAX_BYTES:
            raise ValidationError("Fichier trop volumineux (max 25 Mo)")

        stored_name = f"{uuid.uuid4().hex}{suffix or '.bin'}"
        rel = self.relative_path(
            module_code=module_code,
            entity=entity,
            entity_id=entity_id,
            filename=stored_name,
        )
        abs_path = self.absolute_path(rel)
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_bytes(content)

        return await self.register(
            espace_code=espace_code,
            module_code=module_code,
            entity=entity,
            entity_id=entity_id,
            filename=original,
            stored_path=rel,
            mime_type=file.content_type,
            size_bytes=len(content),
            uploaded_by_id=uploaded_by_id,
        )

    async def get(self, document_id: UUID) -> GedDocument:
        result = await self.db.execute(
            select(GedDocument).where(
                GedDocument.id == document_id,
                GedDocument.deleted_at.is_(None),
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise NotFoundError("Document GED", str(document_id))
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

    async def soft_delete(self, document_id: UUID) -> GedDocument:
        from datetime import datetime, timezone

        row = await self.get(document_id)
        row.deleted_at = datetime.now(timezone.utc)
        await self.db.flush()
        return row
