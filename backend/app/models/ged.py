"""GED plateforme — documents transverses (espace MG + autres)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

OCR_STATUSES = ("pending", "processing", "done", "failed")
SECURITY_LEVELS = ("public", "internal", "confidential", "restricted")


class GedDocument(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """Fichier CORE : espace + module + entité métier.

    Les pièces immo (`pieces_jointes`) et archives Excel/PDF ne sont pas
    migrées ici. Document Service + Archives départementales enrichissent
    les métadonnées et l'OCR sur cette table unique.
    """

    __tablename__ = "ged_documents"

    espace_code: Mapped[str] = mapped_column(String(80), index=True)
    module_code: Mapped[str] = mapped_column(String(80), index=True)
    entity: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(512))
    mime_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )

    # Métadonnées Archives (nullable = rétrocompat uploads existants)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    doc_type: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    reference: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    date_document: Mapped[date | None] = mapped_column(Date, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    agence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agences.id"), nullable=True, index=True
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departements.id"), nullable=True, index=True
    )
    fournisseur_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fournisseurs.id"), nullable=True, index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    parent_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ged_documents.id"), nullable=True, index=True
    )
    deleted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    delete_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Document Service — OCR + confidentialité
    ocr_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True
    )
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_text_search: Mapped[str | None] = mapped_column(TSVECTOR(), nullable=True)
    ocr_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    security_level: Mapped[str] = mapped_column(
        String(40), default="internal", nullable=False, index=True
    )
