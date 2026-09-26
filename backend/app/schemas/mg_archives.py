"""Schemas Archives MG — registre documentaire moyens-generaux."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ArchiveDocOut(BaseModel):
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
    agence_id: UUID | None = None
    department_id: UUID | None = None
    fournisseur_id: UUID | None = None
    uploaded_by_id: UUID | None = None
    deleted_at: datetime | None = None
    delete_reason: str | None = None
    original_name: str | None = None
    ocr_status: str = "pending"
    ocr_error: str | None = None
    ocr_attempts: int = 0
    security_level: str = "internal"


class ArchiveDocUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    doc_type: str | None = None
    reference: str | None = None
    date_document: date | None = None
    agence_id: UUID | None = None
    department_id: UUID | None = None
    fournisseur_id: UUID | None = None


class ArchiveSoftDeleteIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class ArchiveDashboardOut(BaseModel):
    total: int = 0
    ce_mois: int = 0
    cette_annee: int = 0
    achats: int = 0
    stock: int = 0
    notes: int = 0
    contrats: int = 0
    manquants: int = 0
    corbeille: int = 0
    par_mois: list[dict] = Field(default_factory=list)
    par_module: list[dict] = Field(default_factory=list)
    par_type: list[dict] = Field(default_factory=list)
    par_agence: list[dict] = Field(default_factory=list)
    recents: list[ArchiveDocOut] = Field(default_factory=list)


class ArchiveMissingItem(BaseModel):
    code: str
    label: str
    module_code: str
    source_type: str
    source_id: str
    reference: str | None = None
    severity: str = "A_VERIFIER"
    detail: str | None = None
