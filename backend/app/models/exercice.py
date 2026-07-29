"""Exercices comptables et soldes d'ouverture (142 / 148 / VNC, sans 68)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import StatutExercice, StatutPeriodeAmortissement
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ExerciceComptable(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "exercices_comptables"
    __table_args__ = (UniqueConstraint("annee", name="uq_exercices_comptables_annee"),)

    annee: Mapped[int] = mapped_column(Integer, index=True)
    statut: Mapped[StatutExercice] = mapped_column(
        Enum(
            StatutExercice,
            name="statutexercice",
            native_enum=False,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        default=StatutExercice.OUVERT,
        index=True,
    )
    archive_dossier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("archive_dossiers.id", ondelete="SET NULL"),
        nullable=True,
    )
    cloture_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cloture_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    ouverture_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ouverture_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    total_valeur_brute: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    total_amortissement: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    total_vnc: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    total_dotation_68: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    nb_immobilisations: Mapped[int] = mapped_column(Integer, default=0)
    snapshot_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message: Mapped[str | None] = mapped_column(String(512), nullable=True)


class SoldeOuvertureImmobilisation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Soldes d'ouverture d'un exercice (reprise 142/148/VNC, jamais de 68)."""

    __tablename__ = "soldes_ouverture_immobilisations"
    __table_args__ = (
        UniqueConstraint(
            "exercice_id",
            "immobilisation_id",
            name="uq_solde_ouverture_exercice_immo",
        ),
    )

    exercice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("exercices_comptables.id", ondelete="CASCADE"),
        index=True,
    )
    immobilisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("immobilisations.id", ondelete="CASCADE"),
        index=True,
    )
    annee: Mapped[int] = mapped_column(Integer, index=True)
    annee_source: Mapped[int] = mapped_column(Integer, index=True)
    valeur_brute_142: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    cumul_148: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    vnc: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    code_inventaire: Mapped[str | None] = mapped_column(String(80), nullable=True)


class PeriodeAmortissement(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Période comptable trimestrielle verrouillant l'ordre T1 → T4."""

    __tablename__ = "periodes_amortissement"
    __table_args__ = (
        UniqueConstraint("exercice_id", "trimestre", name="uq_periode_amort_exercice_trimestre"),
    )

    exercice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("exercices_comptables.id", ondelete="CASCADE"),
        index=True,
    )
    annee: Mapped[int] = mapped_column(Integer, index=True)
    trimestre: Mapped[int] = mapped_column(Integer)
    code: Mapped[str] = mapped_column(String(20), index=True)
    date_arrete: Mapped[date] = mapped_column(Date)
    statut: Mapped[StatutPeriodeAmortissement] = mapped_column(
        Enum(
            StatutPeriodeAmortissement,
            name="statutperiodeamortissement",
            native_enum=False,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        default=StatutPeriodeAmortissement.EN_ATTENTE,
        index=True,
    )
    calcule_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valide_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valide_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    total_dotation: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    nb_dotations: Mapped[int] = mapped_column(Integer, default=0)
