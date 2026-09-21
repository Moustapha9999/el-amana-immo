"""Modèles Moyens Généraux — Stock & Fournitures (Phase 1)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class MgArticleFamille(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "mg_article_familles"

    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    libelle: Mapped[str] = mapped_column(String(120))
    sort_order: Mapped[int] = mapped_column(default=0)

    articles: Mapped[list[MgArticle]] = relationship(back_populates="famille")


class MgArticle(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "mg_articles"
    __table_args__ = (UniqueConstraint("code", name="uq_mg_articles_code"),)

    code: Mapped[str] = mapped_column(String(40), index=True)
    designation: Mapped[str] = mapped_column(String(255))
    famille_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_article_familles.id"), index=True
    )
    uom: Mapped[str] = mapped_column(String(20), default="U")
    stock_actuel: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal("0"))
    stock_min: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal("0"))
    stock_max: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    agence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agences.id"), nullable=True, index=True
    )
    emplacement: Mapped[str | None] = mapped_column(String(120), nullable=True)

    famille: Mapped[MgArticleFamille] = relationship(back_populates="articles")
    mouvements: Mapped[list[MgStockMouvement]] = relationship(back_populates="article")


class MgStockMouvement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mg_stock_mouvements"

    reference: Mapped[str] = mapped_column(String(40), index=True)
    date_mouvement: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    type_mouvement: Mapped[str] = mapped_column(String(20), index=True)  # ENTREE|SORTIE|AJUSTEMENT|INVENTAIRE
    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_articles.id"), index=True
    )
    quantite: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    agence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agences.id"), nullable=True, index=True
    )
    departement: Mapped[str | None] = mapped_column(String(120), nullable=True)
    initiateur_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    motif: Mapped[str | None] = mapped_column(String(255), nullable=True)
    observation: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    article: Mapped[MgArticle] = relationship(back_populates="mouvements")


class MgDemandeFourniture(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "mg_demandes_fourniture"

    reference: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    date_demande: Mapped[date] = mapped_column(Date)
    agence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agences.id"), index=True
    )
    agence_libelle_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    agence_adresse_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    departement: Mapped[str | None] = mapped_column(String(120), nullable=True)
    demandeur_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    demandeur_nom: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fonction: Mapped[str | None] = mapped_column(String(120), nullable=True)
    statut: Mapped[str] = mapped_column(String(30), default="BROUILLON", index=True)
    visa_agence_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    visa_agence_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    visa_mg_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    visa_mg_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    observation: Mapped[str | None] = mapped_column(Text, nullable=True)

    lignes: Mapped[list[MgDemandeFournitureLigne]] = relationship(
        back_populates="demande", cascade="all, delete-orphan"
    )


class MgDemandeFournitureLigne(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mg_demande_fourniture_lignes"

    demande_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_demandes_fourniture.id", ondelete="CASCADE"), index=True
    )
    article_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_articles.id"), nullable=True
    )
    designation: Mapped[str] = mapped_column(String(255))
    quantite_demandee: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    quantite_accordee: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    sort_order: Mapped[int] = mapped_column(default=0)

    demande: Mapped[MgDemandeFourniture] = relationship(back_populates="lignes")


class MgStockParametre(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mg_stock_parametres"

    cle: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    valeur: Mapped[str] = mapped_column(String(255))
    libelle: Mapped[str | None] = mapped_column(String(120), nullable=True)


class MgInventaire(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "mg_inventaires"
    __table_args__ = (UniqueConstraint("reference", name="uq_mg_inventaires_reference"),)

    reference: Mapped[str] = mapped_column(String(40), index=True)
    libelle: Mapped[str] = mapped_column(String(255))
    date_debut: Mapped[date] = mapped_column(Date)
    date_fin: Mapped[date | None] = mapped_column(Date, nullable=True)
    agence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agences.id"), nullable=True, index=True
    )
    statut: Mapped[str] = mapped_column(String(30), default="OUVERT", index=True)
    observation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    cloture_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cloture_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    lignes: Mapped[list[MgInventaireLigne]] = relationship(
        back_populates="inventaire", cascade="all, delete-orphan"
    )


class MgInventaireLigne(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mg_inventaire_lignes"

    inventaire_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_inventaires.id", ondelete="CASCADE"), index=True
    )
    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_articles.id"), index=True
    )
    stock_theorique: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal("0"))
    stock_physique: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    ecart: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    observation: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sort_order: Mapped[int] = mapped_column(default=0)

    inventaire: Mapped[MgInventaire] = relationship(back_populates="lignes")
    article: Mapped[MgArticle] = relationship()
