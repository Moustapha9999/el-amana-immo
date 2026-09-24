import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Direction(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "directions"

    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    libelle: Mapped[str] = mapped_column(String(255))


class Departement(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "departements"

    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    libelle: Mapped[str] = mapped_column(String(255))
    direction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("directions.id"), nullable=True
    )


class CentreCout(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "centres_cout"

    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    libelle: Mapped[str] = mapped_column(String(255))
    departement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departements.id"), nullable=True
    )


class Fournisseur(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "fournisseurs"

    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    raison_sociale: Mapped[str] = mapped_column(String(255))
    nom_commercial: Mapped[str | None] = mapped_column(String(255), nullable=True)
    type_fournisseur: Mapped[str] = mapped_column(String(40), default="FOURNITURE", index=True)
    contact: Mapped[str | None] = mapped_column(String(120), nullable=True)
    contact_fonction: Mapped[str | None] = mapped_column(String(120), nullable=True)
    telephone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    telephone_secondaire: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    site_web: Mapped[str | None] = mapped_column(String(255), nullable=True)
    adresse: Mapped[str | None] = mapped_column(Text, nullable=True)
    ville: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    pays: Mapped[str] = mapped_column(String(80), default="Mauritanie")
    nif: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    rc: Mapped[str | None] = mapped_column(String(60), nullable=True)
    devise_defaut: Mapped[str] = mapped_column(String(10), default="MRU")
    mode_paiement_defaut: Mapped[str | None] = mapped_column(String(80), nullable=True)
    delai_paiement_jours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    conditions_commerciales: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
