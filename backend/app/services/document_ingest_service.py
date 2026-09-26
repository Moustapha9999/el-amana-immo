"""Document Service — ingestion unique (upload manuel + archivage opération + versions)."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models.enums import TypeNotification
from app.models.ged import SECURITY_LEVELS, GedDocument
from app.services.ged_service import GedService
from app.services.notification_service import NotificationService

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
        notify: bool = True,
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
        row.parent_document_id = None
        row.version_comment = None
        row.ocr_status = "pending"
        row.ocr_text = None
        row.ocr_text_search = None
        row.ocr_error = None
        row.ocr_attempts = 0
        row.security_level = level

        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(row)

        if notify and uploaded_by_id:
            try:
                await NotificationService(self.db).create(
                    user_id=uploaded_by_id,
                    type_notification=TypeNotification.SYSTEME,
                    titre="Document archivé",
                    message=(
                        f"«{row.title or row.filename}» a été déposé. "
                        "L'analyse OCR est en cours."
                    ),
                    entity="ged_document",
                    entity_id=str(row.id),
                    espace_code=row.espace_code,
                    module_code=row.module_code,
                    categorie="ged",
                    event_type="document_archived",
                    priorite="info",
                )
                await self.db.commit()
            except Exception:
                logger.exception("Notification archivage échouée pour %s", row.id)

        if enqueue:
            enqueue_ocr(row.id)
        return row

    async def create_version(
        self,
        *,
        parent_id: UUID,
        file: UploadFile | None = None,
        content: bytes | None = None,
        filename: str | None = None,
        mime_type: str | None = None,
        uploaded_by_id: UUID | None = None,
        version_comment: str | None = None,
        enqueue: bool = True,
        notify: bool = True,
    ) -> GedDocument:
        """Nouvelle version : ne remplace jamais le fichier officiel précédent."""
        parent = await self.ged.get(parent_id)
        root = await self._resolve_root(parent)
        max_version = int(
            await self.db.scalar(
                select(func.coalesce(func.max(GedDocument.version), 0)).where(
                    or_(
                        GedDocument.id == root.id,
                        GedDocument.parent_document_id == root.id,
                    )
                )
            )
            or 0
        )

        if file is not None:
            row = await self.ged.upload(
                file=file,
                espace_code=root.espace_code,
                module_code=root.module_code,
                entity=root.entity,
                entity_id=root.entity_id,
                uploaded_by_id=uploaded_by_id,
            )
        elif content is not None:
            row = await self._upload_bytes(
                content=content,
                filename=filename or parent.filename,
                mime_type=mime_type or parent.mime_type,
                espace_code=root.espace_code,
                module_code=root.module_code,
                entity=root.entity,
                entity_id=root.entity_id,
                uploaded_by_id=uploaded_by_id,
            )
        else:
            raise ValidationError("Fichier requis pour la nouvelle version")

        row.title = root.title or row.filename
        row.description = root.description
        row.doc_type = root.doc_type
        row.reference = root.reference
        row.date_document = root.date_document or date.today()
        row.archived_at = datetime.now(timezone.utc)
        row.agence_id = root.agence_id
        row.department_id = root.department_id
        row.fournisseur_id = root.fournisseur_id
        row.security_level = root.security_level or "internal"
        row.parent_document_id = root.id
        row.version = max_version + 1
        row.version_comment = (version_comment or "").strip()[:500] or None
        row.ocr_status = "pending"
        row.ocr_text = None
        row.ocr_text_search = None
        row.ocr_error = None
        row.ocr_attempts = 0

        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(row)

        if notify and uploaded_by_id:
            try:
                await NotificationService(self.db).create(
                    user_id=uploaded_by_id,
                    type_notification=TypeNotification.SYSTEME,
                    titre="Nouvelle version documentaire",
                    message=f"Version {row.version} créée pour «{row.title or row.filename}».",
                    entity="ged_document",
                    entity_id=str(row.id),
                    espace_code=row.espace_code,
                    module_code=row.module_code,
                    categorie="ged",
                    event_type="document_version_created",
                    priorite="info",
                )
                await self.db.commit()
            except Exception:
                logger.exception("Notification version échouée pour %s", row.id)

        if enqueue:
            enqueue_ocr(row.id)
        return row

    async def _resolve_root(self, row: GedDocument) -> GedDocument:
        current = row
        seen: set[UUID] = set()
        while current.parent_document_id is not None:
            if current.id in seen:
                break
            seen.add(current.id)
            parent = await self.db.get(GedDocument, current.parent_document_id)
            if parent is None:
                break
            current = parent
        return current

    async def update_metadata(self, row: GedDocument, data) -> GedDocument:
        """Met à jour les métadonnées GED. N'altère pas entity / entity_id métier."""
        fields = getattr(data, "model_fields_set", set())
        for field in ("title", "description", "doc_type", "reference", "date_document"):
            if field not in fields:
                continue
            val = getattr(data, field)
            if field == "doc_type" and isinstance(val, str):
                val = val.strip().upper() or None
            if isinstance(val, str):
                val = val.strip() or None
            setattr(row, field, val)
        if "archive" in fields and data.archive is True and row.archived_at is None:
            row.archived_at = datetime.now(timezone.utc)
        row.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def retry_ocr(self, document_id: UUID) -> GedDocument:
        row = await self.ged.get(document_id)
        if int(row.ocr_attempts or 0) >= 3:
            raise ValidationError("Nombre maximum de tentatives OCR atteint (3).")
        row.ocr_status = "pending"
        row.ocr_error = None
        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(row)
        enqueue_ocr(row.id)
        return row

    async def soft_delete(
        self,
        document_id: UUID,
        *,
        user_id: UUID | None = None,
        reason: str | None = None,
    ) -> GedDocument:
        row = await self.ged.get(document_id)
        row.deleted_at = datetime.now(timezone.utc)
        row.is_active = False
        row.deleted_by_id = user_id
        row.delete_reason = (reason or "").strip()[:500] or None
        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def restore(self, document_id: UUID) -> GedDocument:
        row = await self.db.scalar(
            select(GedDocument).where(GedDocument.id == document_id)
        )
        if row is None:
            raise NotFoundError("Document GED", str(document_id))
        row.deleted_at = None
        row.is_active = True
        row.deleted_by_id = None
        row.delete_reason = None
        row.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(row)
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
