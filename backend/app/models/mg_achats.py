"""Modèles Moyens Généraux — Achats & Approvisionnements."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class MgAchatParametre(TimestampMixin, Base):
    __tablename__ = "mg_achat_parametres"

    cle: Mapped[str] = mapped_column(String(80), primary_key=True)
    valeur: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class MgAchatDemande(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "mg_achat_demandes"
    __table_args__ = (UniqueConstraint("reference", name="uq_mg_achat_demandes_reference"),)

    reference: Mapped[str] = mapped_column(String(40), index=True)
    date_demande: Mapped[date] = mapped_column(Date)
    agence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agences.id"), index=True
    )
    departement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departements.id"), nullable=True
    )
    demandeur_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    demandeur_nom: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fonction: Mapped[str | None] = mapped_column(String(120), nullable=True)
    type_achat: Mapped[str] = mapped_column(String(40), default="FOURNITURE")
    priorite: Mapped[str] = mapped_column(String(20), default="NORMAL")
    projet: Mapped[str | None] = mapped_column(String(255), nullable=True)
    motif: Mapped[str | None] = mapped_column(Text, nullable=True)
    date_souhaitee: Mapped[date | None] = mapped_column(Date, nullable=True)
    budget_estime: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    statut: Mapped[str] = mapped_column(String(30), default="BROUILLON", index=True)
    observation: Mapped[str | None] = mapped_column(Text, nullable=True)

    lignes: Mapped[list[MgAchatDemandeLigne]] = relationship(
        back_populates="demande", cascade="all, delete-orphan"
    )


class MgAchatDemandeLigne(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mg_achat_demande_lignes"

    demande_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_achat_demandes.id", ondelete="CASCADE"), index=True
    )
    designation: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantite: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal("1"))
    uom: Mapped[str] = mapped_column(String(20), default="U")
    prix_estime: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    montant_estime: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    article_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_articles.id"), nullable=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    demande: Mapped[MgAchatDemande] = relationship(back_populates="lignes")


class MgAchatConsultation(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "mg_achat_consultations"
    __table_args__ = (UniqueConstraint("reference", name="uq_mg_achat_consultations_reference"),)

    reference: Mapped[str] = mapped_column(String(40), index=True)
    date_consultation: Mapped[date] = mapped_column(Date)
    demande_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_achat_demandes.id"), nullable=True
    )
    agence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agences.id"), index=True
    )
    objet: Mapped[str] = mapped_column(String(255))
    date_limite: Mapped[date | None] = mapped_column(Date, nullable=True)
    responsable_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    statut: Mapped[str] = mapped_column(String(30), default="BROUILLON", index=True)
    observation: Mapped[str | None] = mapped_column(Text, nullable=True)

    fournisseurs: Mapped[list[MgAchatConsultationFournisseur]] = relationship(
        back_populates="consultation", cascade="all, delete-orphan"
    )


class MgAchatConsultationFournisseur(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mg_achat_consultation_fournisseurs"
    __table_args__ = (
        UniqueConstraint("consultation_id", "fournisseur_id", name="uq_mg_achat_cons_fourn"),
    )

    consultation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mg_achat_consultations.id", ondelete="CASCADE"),
        index=True,
    )
    fournisseur_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fournisseurs.id")
    )

    consultation: Mapped[MgAchatConsultation] = relationship(back_populates="fournisseurs")


class MgAchatDevis(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "mg_achat_devis"
    __table_args__ = (UniqueConstraint("reference", name="uq_mg_achat_devis_reference"),)

    reference: Mapped[str] = mapped_column(String(40), index=True)
    fournisseur_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fournisseurs.id"), index=True
    )
    consultation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_achat_consultations.id"), nullable=True
    )
    date_devis: Mapped[date] = mapped_column(Date)
    date_validite: Mapped[date | None] = mapped_column(Date, nullable=True)
    montant_ht: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    montant_tva: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    montant_ttc: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    devise: Mapped[str] = mapped_column(String(10), default="MRU")
    conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    delai_livraison: Mapped[str | None] = mapped_column(String(120), nullable=True)
    conditions_paiement: Mapped[str | None] = mapped_column(String(120), nullable=True)
    statut: Mapped[str] = mapped_column(String(30), default="RECU", index=True)
    observation: Mapped[str | None] = mapped_column(Text, nullable=True)

    lignes: Mapped[list[MgAchatDevisLigne]] = relationship(
        back_populates="devis", cascade="all, delete-orphan"
    )


class MgAchatDevisLigne(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mg_achat_devis_lignes"

    devis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_achat_devis.id", ondelete="CASCADE"), index=True
    )
    designation: Mapped[str] = mapped_column(String(255))
    quantite: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal("1"))
    prix_unitaire: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    remise_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    taux_tva: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    total_ht: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    devis: Mapped[MgAchatDevis] = relationship(back_populates="lignes")


class MgAchatComparaison(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "mg_achat_comparaisons"
    __table_args__ = (UniqueConstraint("reference", name="uq_mg_achat_comparaisons_reference"),)

    reference: Mapped[str] = mapped_column(String(40), index=True)
    consultation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_achat_consultations.id"), index=True
    )
    demande_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_achat_demandes.id"), nullable=True
    )
    statut: Mapped[str] = mapped_column(String(30), default="BROUILLON", index=True)
    fournisseur_retenu_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fournisseurs.id"), nullable=True
    )
    motif_choix: Mapped[str | None] = mapped_column(Text, nullable=True)
    snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    observation: Mapped[str | None] = mapped_column(Text, nullable=True)


class MgAchatBl(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "mg_achat_bl"
    __table_args__ = (UniqueConstraint("reference", name="uq_mg_achat_bl_reference"),)

    reference: Mapped[str] = mapped_column(String(40), index=True)
    bon_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_bons_commande.id"), index=True
    )
    fournisseur_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fournisseurs.id")
    )
    date_bl: Mapped[date] = mapped_column(Date)
    date_livraison: Mapped[date | None] = mapped_column(Date, nullable=True)
    agence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agences.id"), nullable=True
    )
    transporteur: Mapped[str | None] = mapped_column(String(255), nullable=True)
    observation: Mapped[str | None] = mapped_column(Text, nullable=True)
    statut: Mapped[str] = mapped_column(String(30), default="RECU", index=True)


class MgAchatReception(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "mg_achat_receptions"
    __table_args__ = (UniqueConstraint("reference", name="uq_mg_achat_receptions_reference"),)

    reference: Mapped[str] = mapped_column(String(40), index=True)
    bon_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_bons_commande.id"), index=True
    )
    bl_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_achat_bl.id"), nullable=True
    )
    date_reception: Mapped[date] = mapped_column(Date)
    agence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agences.id"), nullable=True
    )
    statut: Mapped[str] = mapped_column(String(30), default="PARTIEL", index=True)
    observation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    lignes: Mapped[list[MgAchatReceptionLigne]] = relationship(
        back_populates="reception", cascade="all, delete-orphan"
    )


class MgAchatReceptionLigne(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mg_achat_reception_lignes"

    reception_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mg_achat_receptions.id", ondelete="CASCADE"),
        index=True,
    )
    bc_ligne_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_bc_lignes.id")
    )
    quantite_recue: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    article_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_articles.id"), nullable=True
    )

    reception: Mapped[MgAchatReception] = relationship(back_populates="lignes")


class MgAchatFacture(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "mg_achat_factures"
    __table_args__ = (UniqueConstraint("reference", name="uq_mg_achat_factures_reference"),)

    reference: Mapped[str] = mapped_column(String(40), index=True)
    numero_fournisseur: Mapped[str | None] = mapped_column(String(80), nullable=True)
    fournisseur_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fournisseurs.id"), index=True
    )
    bon_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_bons_commande.id"), index=True
    )
    bl_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_achat_bl.id"), nullable=True
    )
    reception_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_achat_receptions.id"), nullable=True
    )
    date_facture: Mapped[date] = mapped_column(Date)
    date_echeance: Mapped[date | None] = mapped_column(Date, nullable=True)
    montant_ht: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    montant_tva: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    montant_ttc: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    devise: Mapped[str] = mapped_column(String(10), default="MRU")
    statut: Mapped[str] = mapped_column(String(30), default="RECUE", index=True)
    ecart_quantite: Mapped[bool] = mapped_column(Boolean, default=False)
    ecart_montant: Mapped[bool] = mapped_column(Boolean, default=False)
    observation: Mapped[str | None] = mapped_column(Text, nullable=True)

    lignes: Mapped[list[MgAchatFactureLigne]] = relationship(
        back_populates="facture", cascade="all, delete-orphan"
    )


class MgAchatFactureLigne(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mg_achat_facture_lignes"

    facture_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_achat_factures.id", ondelete="CASCADE"), index=True
    )
    designation: Mapped[str] = mapped_column(String(255))
    quantite: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal("1"))
    prix_unitaire: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    total_ht: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    facture: Mapped[MgAchatFacture] = relationship(back_populates="lignes")


class MgAchatPaiement(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "mg_achat_paiements"
    __table_args__ = (UniqueConstraint("reference", name="uq_mg_achat_paiements_reference"),)

    reference: Mapped[str] = mapped_column(String(40), index=True)
    facture_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_achat_factures.id"), index=True
    )
    fournisseur_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fournisseurs.id")
    )
    montant: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    date_echeance: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_paiement: Mapped[date | None] = mapped_column(Date, nullable=True)
    mode_paiement: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reference_paiement: Mapped[str | None] = mapped_column(String(120), nullable=True)
    statut: Mapped[str] = mapped_column(String(30), default="A_PAYER", index=True)
    observation: Mapped[str | None] = mapped_column(Text, nullable=True)


class MgAchatEvenement(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "mg_achat_evenements"

    entity_type: Mapped[str] = mapped_column(String(40), index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    action: Mapped[str] = mapped_column(String(60))
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
