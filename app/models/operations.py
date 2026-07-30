import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import TypeAjustement
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Cession(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "cessions"

    immobilisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("immobilisations.id"), index=True
    )
    date_cession: Mapped[date] = mapped_column(Date)
    prix_cession: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    vnc: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    plus_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    moins_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    reference: Mapped[str | None] = mapped_column(String(80), nullable=True)
    observations: Mapped[str | None] = mapped_column(Text, nullable=True)
    libelle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ecriture_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ecritures_comptables.id"), nullable=True
    )


class Rebut(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "rebuts"

    immobilisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("immobilisations.id"), index=True
    )
    date_rebut: Mapped[date] = mapped_column(Date)
    vnc: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    motif: Mapped[str | None] = mapped_column(Text, nullable=True)
    ecriture_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ecritures_comptables.id"), nullable=True
    )


class Reevaluation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "reevaluations"

    immobilisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("immobilisations.id"), index=True
    )
    date_reevaluation: Mapped[date] = mapped_column(Date)
    ancienne_valeur: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    nouvelle_valeur: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    justificatif: Mapped[str | None] = mapped_column(Text, nullable=True)
    stored_justificatif_path: Mapped[str | None] = mapped_column(String(512), nullable=True)


class Ajustement(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ajustements"

    immobilisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("immobilisations.id"), index=True
    )
    type_ajustement: Mapped[TypeAjustement] = mapped_column(Enum(TypeAjustement))
    date_ajustement: Mapped[date] = mapped_column(Date)
    montant: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    commentaire: Mapped[str | None] = mapped_column(Text, nullable=True)
    before_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
