"""Document Service — ingestion unique (upload manuel + archivage opération)."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.models.ged import SECURITY_LEVELS, GedDocument
from app.services.ged_service import GedService

logger = logging.getLogger(__name__)


def enqueue_ocr(document_id: UUID) -> None:
    """Enfile le job OCR sans bloquer l'appelant. Échec soft si broker down."""
    try:
        from app.workers.tasks_ocr import ocr_document

        ocr_document.delay(str(document_id))
    except Exception:
        logger.exception("Impossible d'enfiler OCR pour %s", document_id)


class DocumentIngestService:
    """Point d'entrée unique vers ged_documents + pipeline OCR."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.ged = GedService(db)

    async def ingest_document(
        self,
        *,
        file: UploadFile | None = None,
        content: bytes | None = None,
        filename: str | None = None,
        mime_type: str | None = None,
        espace_code: str,
        module_code: str,
        entity: str,
        entity_id: str,
        uploaded_by_id: UUID | None = None,
        title: str | None = None,
        description: str | None = None,
        doc_type: str | None = None,
        reference: str | None = None,
        date_document: date | None = None,
        agence_id: UUID | None = None,
        department_id: UUID | None = None,
        fournisseur_id: UUID | None = None,
        security_level: str = "internal",
        enqueue: bool = True,
    ) -> GedDocument:
        espace = (espace_code or "").strip().lower()
        module = (module_code or "").strip().lower()
        ent = (entity or "").strip()
        eid = str(entity_id).strip()
        if not espace or not module or not ent or not eid:
            raise ValidationError("espace_code, module_code, entity et entity_id sont requis")

        level = (security_level or "internal").strip().lower()
        if level not in SECURITY_LEVELS:
            raise ValidationError(
                f"security_level invalide (attendu: {', '.join(SECURITY_LEVELS)})"
            )

        if file is not None:
            row = await self.ged.upload(
                file=file,
                espace_code=espace,
                module_code=module,
                entity=ent,
                entity_id=eid,
                uploaded_by_id=uploaded_by_id,
            )
        elif content is not None:
            row = await self._upload_bytes(
                content=content,
                filename=filename or "document.bin",
                mime_type=mime_type,
                espace_code=espace,
                module_code=module,
                entity=ent,
                entity_id=eid,
                uploaded_by_id=uploaded_by_id,
            )
        else:
            raise ValidationError("Fichier requis pour l'ingestion")

        row.title = (title or row.filename)[:255]
        row.description = description
        row.doc_type = (doc_type or "JUSTIFICATIF").strip().upper()[:80]
        if reference:
            row.reference = reference.strip()[:120]
        row.date_document = date_document or date.today()
        row.archived_at = datetime.now(timezone.utc)
        row.agence_id = agence_id
        row.department_id = department_id
        row.fournisseur_id = fournisseur_id
        row.version = row.version or 1
        row.ocr_status = "pending"
        row.ocr_text = None
        row.ocr_text_search = None
        row.ocr_error = None
        row.ocr_attempts = 0
        row.security_level = level

        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(row)

        if enqueue:
            enqueue_ocr(row.id)
        return row

    async def retry_ocr(self, document_id: UUID) -> GedDocument:
        row = await self.ged.get(document_id)
        row.ocr_status = "pending"
        row.ocr_error = None
        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(row)
        enqueue_ocr(row.id)
        return row

    async def _upload_bytes(
        self,
        *,
        content: bytes,
        filename: str,
        mime_type: str | None,
        espace_code: str,
        module_code: str,
        entity: str,
        entity_id: str,
        uploaded_by_id: UUID | None,
    ) -> GedDocument:
        import uuid as uuid_mod

        from app.services.ged_service import _ALLOWED_SUFFIXES, _MAX_BYTES

        original = Path(filename).name or "fichier"
        suffix = Path(original).suffix.lower()
        if suffix and suffix not in _ALLOWED_SUFFIXES:
            raise ValidationError(f"Type de fichier non autorisé ({suffix})")
        if not content:
            raise ValidationError("Fichier vide")
        if len(content) > _MAX_BYTES:
            raise ValidationError("Fichier trop volumineux (max 25 Mo)")

        stored_name = f"{uuid_mod.uuid4().hex}{suffix or '.bin'}"
        rel = self.ged.relative_path(
            module_code=module_code,
            entity=entity,
            entity_id=entity_id,
            filename=stored_name,
        )
        abs_path = self.ged.absolute_path(rel)
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_bytes(content)

        return await self.ged.register(
            espace_code=espace_code,
            module_code=module_code,
            entity=entity,
            entity_id=entity_id,
            filename=original,
            stored_path=rel,
            mime_type=mime_type,
            size_bytes=len(content),
            uploaded_by_id=uploaded_by_id,
        )
