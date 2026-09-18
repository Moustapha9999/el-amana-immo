"""GED plateforme — documents transverses (pas encore branchée aux modules)."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class GedDocument(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """Fichier CORE : espace + module + entité métier.

    Les pièces immo (`pieces_jointes`) et archives Excel/PDF ne sont pas
    migrées ici. Les modules futurs (Crédit, RH, …) écriront via GedService.
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
