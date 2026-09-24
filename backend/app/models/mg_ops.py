"""Moyens Généraux Phase 2 — Achats, Notes de frais, Contrats."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class MgBonCommande(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "mg_bons_commande"
    __table_args__ = (UniqueConstraint("reference", name="uq_mg_bons_commande_reference"),)

    reference: Mapped[str] = mapped_column(String(40), index=True)
    date_bc: Mapped[date] = mapped_column(Date)
    fournisseur_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fournisseurs.id"), nullable=True, index=True
    )
    fournisseur_raison_sociale: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fournisseur_nif: Mapped[str | None] = mapped_column(String(60), nullable=True)
    fournisseur_telephone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    fournisseur_adresse: Mapped[str | None] = mapped_column(Text, nullable=True)
    departement: Mapped[str | None] = mapped_column(String(120), nullable=True)
    projet: Mapped[str | None] = mapped_column(String(255), nullable=True)
    acheteur_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    acheteur_nom: Mapped[str | None] = mapped_column(String(255), nullable=True)
    acheteur_tel: Mapped[str | None] = mapped_column(String(40), nullable=True)
    adresse_facturation: Mapped[str | None] = mapped_column(Text, nullable=True)
    adresse_livraison: Mapped[str | None] = mapped_column(Text, nullable=True)
    conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    incoterm: Mapped[str | None] = mapped_column(String(60), nullable=True)
    conditions_paiement: Mapped[str | None] = mapped_column(String(120), nullable=True)
    moyen_paiement: Mapped[str | None] = mapped_column(String(120), nullable=True)
    demandeur_nom: Mapped[str | None] = mapped_column(String(255), nullable=True)
    demandeur_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    statut: Mapped[str] = mapped_column(String(30), default="BROUILLON", index=True)
    visa_mg_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    visa_mg_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    visa_dr_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    visa_dr_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    total_ht: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    observation: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Cycle achat étendu
    demande_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_achat_demandes.id"), nullable=True, index=True
    )
    consultation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_achat_consultations.id"), nullable=True
    )
    comparaison_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_achat_comparaisons.id"), nullable=True
    )
    contrat_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_contrats.id"), nullable=True, index=True
    )
    agence_facturation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agences.id"), nullable=True
    )
    agence_livraison_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agences.id"), nullable=True
    )
    agence_facturation_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    agence_livraison_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    type_achat: Mapped[str] = mapped_column(String(40), default="FOURNITURE")
    devise: Mapped[str] = mapped_column(String(10), default="MRU")
    total_tva: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    total_ttc: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    date_livraison_prevue: Mapped[date | None] = mapped_column(Date, nullable=True)
    pdf_version: Mapped[int] = mapped_column(Integer, default=1)

    lignes: Mapped[list[MgBcLigne]] = relationship(
        back_populates="bon", cascade="all, delete-orphan"
    )


class MgBcLigne(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mg_bc_lignes"

    bc_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_bons_commande.id", ondelete="CASCADE"), index=True
    )
    code_produit: Mapped[str | None] = mapped_column(String(60), nullable=True)
    departement: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str] = mapped_column(String(255))
    quantite: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal("1"))
    quantite_recue: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal("0"))
    article_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_articles.id"), nullable=True, index=True
    )
    uom: Mapped[str] = mapped_column(String(20), default="U")
    prix_unitaire: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    prix_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    remise_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    taux_tva: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    total_ttc: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    stockable: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    bon: Mapped[MgBonCommande] = relationship(back_populates="lignes")


class MgNoteFrais(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "mg_notes_frais"
    __table_args__ = (UniqueConstraint("reference", name="uq_mg_notes_frais_reference"),)

    reference: Mapped[str] = mapped_column(String(40), index=True)
    date_demande: Mapped[date] = mapped_column(Date)
    agence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agences.id"), nullable=True, index=True
    )
    agence_libelle_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    demandeur_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    demandeur_nom: Mapped[str | None] = mapped_column(String(255), nullable=True)
    departement: Mapped[str | None] = mapped_column(String(120), nullable=True)
    fonction: Mapped[str | None] = mapped_column(String(120), nullable=True)
    statut: Mapped[str] = mapped_column(String(30), default="BROUILLON", index=True)
    visa_mg_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    visa_mg_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    visa_dr_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    visa_dr_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    total_mru: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    observation: Mapped[str | None] = mapped_column(Text, nullable=True)

    lignes: Mapped[list[MgNoteFraisLigne]] = relationship(
        back_populates="note", cascade="all, delete-orphan"
    )


class MgNoteFraisLigne(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mg_note_frais_lignes"

    note_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_notes_frais.id", ondelete="CASCADE"), index=True
    )
    date_depense: Mapped[date] = mapped_column(Date)
    description: Mapped[str] = mapped_column(String(255))
    motif: Mapped[str | None] = mapped_column(String(255), nullable=True)
    montant: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    mode_reglement: Mapped[str | None] = mapped_column(String(80), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    note: Mapped[MgNoteFrais] = relationship(back_populates="lignes")


class MgContrat(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "mg_contrats"
    __table_args__ = (UniqueConstraint("reference", name="uq_mg_contrats_reference"),)

    reference: Mapped[str] = mapped_column(String(40), index=True)
    titre: Mapped[str] = mapped_column(String(255))
    fournisseur_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fournisseurs.id"), nullable=True, index=True
    )
    fournisseur_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    date_debut: Mapped[date] = mapped_column(Date)
    date_fin: Mapped[date | None] = mapped_column(Date, nullable=True)
    montant: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    periodicite: Mapped[str] = mapped_column(String(20), default="ANNUEL")
    prochain_echeance: Mapped[date | None] = mapped_column(Date, nullable=True)
    alerte_jours: Mapped[int] = mapped_column(Integer, default=30)
    statut: Mapped[str] = mapped_column(String(30), default="BROUILLON", index=True)
    observation: Mapped[str | None] = mapped_column(Text, nullable=True)
