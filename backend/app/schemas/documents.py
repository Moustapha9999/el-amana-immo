"""Schemas Document Service (GED centrale + OCR + versions)."""

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
    parent_document_id: UUID | None = None
    version_comment: str | None = None
    agence_id: UUID | None = None
    department_id: UUID | None = None
    fournisseur_id: UUID | None = None
    uploaded_by_id: UUID | None = None
    deleted_at: datetime | None = None
    delete_reason: str | None = None
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


class DocumentAuditEventOut(BaseModel):
    id: UUID
    action: str
    created_at: datetime | None = None
    user_id: UUID | None = None
    after: dict | None = None
    before: dict | None = None


class DocumentDashboardOut(BaseModel):
    total: int = 0
    ce_mois: int = 0
    cette_annee: int = 0
    ocr_done: int = 0
    ocr_pending: int = 0
    ocr_processing: int = 0
    ocr_failed: int = 0
    ocr_en_cours: int = 0  # pending + processing (alias KPI)
    corbeille: int = 0
    manquants: int = 0
    a_verifier: int = 0
    dossiers_actifs: int = 0
    departements_actifs: int = 0
    par_mois: list[dict] = Field(default_factory=list)
    par_espace: list[dict] = Field(default_factory=list)
    par_module: list[dict] = Field(default_factory=list)
    par_type: list[dict] = Field(default_factory=list)
    par_agence: list[dict] = Field(default_factory=list)
    activite: list[dict] = Field(default_factory=list)
    activite_recente: list[dict] = Field(default_factory=list)
    recents: list[DocumentOut] = Field(default_factory=list)
    ocr: dict = Field(default_factory=dict)


class SoftDeleteIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class DocumentMetadataIn(BaseModel):
    """Métadonnées GED uniquement — ne touche pas l'objet métier source."""

    title: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    doc_type: str | None = Field(default=None, max_length=80)
    reference: str | None = Field(default=None, max_length=120)
    date_document: date | None = None
    archive: bool | None = None


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
        parent_document_id=getattr(row, "parent_document_id", None),
        version_comment=getattr(row, "version_comment", None),
        agence_id=row.agence_id,
        department_id=row.department_id,
        fournisseur_id=row.fournisseur_id,
        uploaded_by_id=row.uploaded_by_id,
        deleted_at=getattr(row, "deleted_at", None),
        delete_reason=getattr(row, "delete_reason", None),
        ocr_status=getattr(row, "ocr_status", None) or "pending",
        ocr_text=text,
        ocr_error=getattr(row, "ocr_error", None),
        ocr_attempts=int(getattr(row, "ocr_attempts", 0) or 0),
        security_level=getattr(row, "security_level", None) or "internal",
    )
