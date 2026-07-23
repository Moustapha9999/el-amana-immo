import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import TypeComptePlan
from app.models.mixins import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Journal(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "journaux"

    code: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    libelle: Mapped[str] = mapped_column(String(120))


class ComptePlanComptable(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "plan_comptable"

    numero: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    libelle: Mapped[str] = mapped_column(String(255))
    type_compte: Mapped[TypeComptePlan] = mapped_column(Enum(TypeComptePlan))
    centre_analytique: Mapped[str | None] = mapped_column(String(30), nullable=True)


class ParametrageEcriture(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """Comptes et libellé automatique des dotations par type d'immobilisation."""

    __tablename__ = "parametrage_ecritures"

    categorie_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories_immobilisation.id", ondelete="CASCADE"), unique=True, index=True
    )
    journal_code: Mapped[str] = mapped_column(String(10), default="OD")
    compte_debit: Mapped[str] = mapped_column(String(20))
    compte_credit: Mapped[str] = mapped_column(String(20))
    libelle_modele: Mapped[str] = mapped_column(String(255), default="Dotation amortissement — {code_inventaire}")


class ParametrageAmortissement(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "parametrage_amortissement"

    periodicite: Mapped[str] = mapped_column(String(20), default="mensuel")
    prorata: Mapped[bool] = mapped_column(Boolean, default=True)
    journal_code: Mapped[str] = mapped_column(String(10), default="OD")
    compte_dotation_defaut: Mapped[str] = mapped_column(String(20), default="681000")
    compte_amortissement_defaut: Mapped[str] = mapped_column(String(20), default="148000")


class Amortissement(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "amortissements"
    __table_args__ = (UniqueConstraint("immobilisation_id", "periode", name="uq_amort_periode"),)

    immobilisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("immobilisations.id", ondelete="CASCADE"), index=True
    )
    periode: Mapped[str] = mapped_column(String(7), index=True)
    montant: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    cumul: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    vnc: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    valide: Mapped[bool] = mapped_column(Boolean, default=False)
    annule: Mapped[bool] = mapped_column(Boolean, default=False)
    simule: Mapped[bool] = mapped_column(Boolean, default=False)


class EcritureComptable(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ecritures_comptables"

    journal_code: Mapped[str] = mapped_column(String(10))
    date_ecriture: Mapped[date] = mapped_column(Date)
    libelle: Mapped[str] = mapped_column(String(255))
    compte_debit: Mapped[str] = mapped_column(String(20))
    compte_credit: Mapped[str] = mapped_column(String(20))
    montant: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    reference: Mapped[str | None] = mapped_column(String(80), nullable=True)
    immobilisation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("immobilisations.id"), nullable=True
    )
    generee_auto: Mapped[bool] = mapped_column(Boolean, default=True)
    validee: Mapped[bool] = mapped_column(Boolean, default=False)
