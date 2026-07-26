"""Archive historique Excel / PDF banque — lecture seule (hors parc actif)."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ArchiveDossier(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "archive_dossiers"
    __table_args__ = (UniqueConstraint("annee", name="uq_archive_dossiers_annee"),)

    annee: Mapped[int] = mapped_column(Integer, index=True)
    libelle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    fichiers: Mapped[list[ArchiveFichier]] = relationship(
        back_populates="dossier",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ArchiveFichier(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "archive_fichiers"

    dossier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("archive_dossiers.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32), index=True)  # excel_banque | pdf_banque
    filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(512))
    mime_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    nature_code: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    sheet_names: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    parse_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    lines_count: Mapped[int] = mapped_column(Integer, default=0)

    dossier: Mapped[ArchiveDossier] = relationship(back_populates="fichiers")
    lignes: Mapped[list[ArchiveLigne]] = relationship(
        back_populates="fichier",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ArchiveLigne(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "archive_lignes"

    fichier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("archive_fichiers.id", ondelete="CASCADE"), index=True
    )
    categorie_code: Mapped[str] = mapped_column(String(40), index=True)
    feuille: Mapped[str | None] = mapped_column(String(120), nullable=True)
    row_number: Mapped[int] = mapped_column(Integer, default=0)
    date_acquisition: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    quantite: Mapped[int] = mapped_column(Integer, default=1)
    designation: Mapped[str] = mapped_column(String(512), default="")
    valeur_brute: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    taux: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    amt_n1: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    dotation: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    amt_fin: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    vnc: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    agence_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_report: Mapped[bool] = mapped_column(Boolean, default=False)
    source_kind: Mapped[str] = mapped_column(String(32), default="excel_banque")
    raw_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    fichier: Mapped[ArchiveFichier] = relationship(back_populates="lignes")
