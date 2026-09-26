"""Schemas Document Service (GED centrale + OCR)."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    title: str | None = None
    description: str | None = None
    doc_type: str | None = None
    reference: str | None = None
    module_code: str
    espace_code: str
    entity: str
    entity_id: str
    date_document: date | None = None
    archived_at: datetime | None = None
    created_at: datetime | None = None
    mime_type: str | None = None
    size_bytes: int = 0
    version: int = 1
    agence_id: UUID | None = None
    department_id: UUID | None = None
    fournisseur_id: UUID | None = None
    uploaded_by_id: UUID | None = None
    ocr_status: str = "pending"
    ocr_text: str | None = None
    ocr_error: str | None = None
    ocr_attempts: int = 0
    security_level: str = "internal"


class DocumentListOut(BaseModel):
    items: list[DocumentOut] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    size: int = 50
    ocr_pending_hint: bool = False


def document_out(row, *, include_ocr_text: bool = False) -> DocumentOut:
    text = None
    if include_ocr_text and getattr(row, "ocr_status", None) == "done":
        text = row.ocr_text
    return DocumentOut(
        id=row.id,
        filename=row.filename,
        title=row.title,
        description=row.description,
        doc_type=row.doc_type,
        reference=row.reference,
        module_code=row.module_code,
        espace_code=row.espace_code,
        entity=row.entity,
        entity_id=row.entity_id,
        date_document=row.date_document,
        archived_at=row.archived_at,
        created_at=row.created_at,
        mime_type=row.mime_type,
        size_bytes=row.size_bytes or 0,
        version=row.version or 1,
        agence_id=row.agence_id,
        department_id=row.department_id,
        fournisseur_id=row.fournisseur_id,
        uploaded_by_id=row.uploaded_by_id,
        ocr_status=getattr(row, "ocr_status", None) or "pending",
        ocr_text=text,
        ocr_error=getattr(row, "ocr_error", None),
        ocr_attempts=int(getattr(row, "ocr_attempts", 0) or 0),
        security_level=getattr(row, "security_level", None) or "internal",
    )
