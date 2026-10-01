"""Modèles Moyens Généraux — Stock & Fournitures (Phase 1)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
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
    reference: Mapped[str | None] = mapped_column(String(80), nullable=True)
    designation: Mapped[str] = mapped_column(String(255))
    famille_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_article_familles.id"), index=True
    )
    sous_famille: Mapped[str | None] = mapped_column(String(120), nullable=True)
    uom: Mapped[str] = mapped_column(String(20), default="U")
    stockable: Mapped[bool] = mapped_column(Boolean, default=True)
    stock_actuel: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal("0"))
    stock_min: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal("0"))
    stock_max: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    agence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agences.id"), nullable=True, index=True
    )
    emplacement: Mapped[str | None] = mapped_column(String(120), nullable=True)
    fournisseur_habituel: Mapped[str | None] = mapped_column(String(255), nullable=True)

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
    periode_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_stock_periodes.id"), nullable=True, index=True
    )

    article: Mapped[MgArticle] = relationship(back_populates="mouvements")
    periode: Mapped[MgStockPeriode | None] = relationship(back_populates="mouvements")


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
    periode_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_stock_periodes.id"), nullable=True, index=True
    )
    valide_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valide_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    ajustements_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ajustements_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    lignes: Mapped[list[MgInventaireLigne]] = relationship(
        back_populates="inventaire", cascade="all, delete-orphan"
    )
    periode: Mapped[MgStockPeriode | None] = relationship(back_populates="inventaires")


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
    nature_ecart: Mapped[str | None] = mapped_column(String(20), nullable=True)
    observation: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sort_order: Mapped[int] = mapped_column(default=0)

    inventaire: Mapped[MgInventaire] = relationship(back_populates="lignes")
    article: Mapped[MgArticle] = relationship()


class MgStockPeriode(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Période mensuelle de stock — une seule ouverte par périmètre global."""

    __tablename__ = "mg_stock_periodes"
    __table_args__ = (UniqueConstraint("annee", "mois", name="uq_mg_stock_periodes_annee_mois"),)

    annee: Mapped[int] = mapped_column(Integer, index=True)
    mois: Mapped[int] = mapped_column(Integer, index=True)
    libelle: Mapped[str] = mapped_column(String(80))
    date_debut: Mapped[date] = mapped_column(Date)
    date_fin: Mapped[date] = mapped_column(Date)
    statut: Mapped[str] = mapped_column(String(20), default="OUVERTE", index=True)
    agence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agences.id"), nullable=True, index=True
    )
    periode_precedente_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_stock_periodes.id"), nullable=True
    )
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opened_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    cloture_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cloture_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reopen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reopen_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reopen_motif: Mapped[str | None] = mapped_column(Text, nullable=True)

    soldes: Mapped[list[MgStockSolde]] = relationship(
        back_populates="periode", cascade="all, delete-orphan"
    )
    mouvements: Mapped[list[MgStockMouvement]] = relationship(back_populates="periode")
    inventaires: Mapped[list[MgInventaire]] = relationship(back_populates="periode")


class MgStockSolde(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Soldes article × période — report sans mouvement ENTREE artificiel."""

    __tablename__ = "mg_stock_soldes"
    __table_args__ = (UniqueConstraint("periode_id", "article_id", name="uq_mg_stock_soldes_periode_article"),)

    periode_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_stock_periodes.id", ondelete="CASCADE"), index=True
    )
    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_articles.id"), index=True
    )
    stock_initial: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal("0"))
    entrees: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal("0"))
    sorties: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal("0"))
    ajustements: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal("0"))
    stock_theorique: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal("0"))
    stock_physique: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    ecart: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    stock_final: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)

    periode: Mapped[MgStockPeriode] = relationship(back_populates="soldes")
    article: Mapped[MgArticle] = relationship()
