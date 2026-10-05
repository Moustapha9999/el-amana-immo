"""Moyens Généraux Phase 2 — Achats, Notes de frais, Contrats."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
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
    # RIB / compte (Virement) ou numéro de téléphone (Amanty).
    ref_paiement: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Montant remis en espèces (Cash).
    montant_paiement: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    demandeur_nom: Mapped[str | None] = mapped_column(String(255), nullable=True)
    demandeur_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    statut: Mapped[str] = mapped_column(String(30), default="BROUILLON", index=True)
    # Historique (anciens visas MG / DR, remplacés par la signature papier) : lecture seule.
    visa_mg_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    visa_mg_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    visa_dr_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    visa_dr_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    soumis_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    soumis_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    valide_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valide_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    envoye_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    envoye_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    cloture_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cloture_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    annule_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    annule_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    motif_annulation: Mapped[str | None] = mapped_column(Text, nullable=True)
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
        back_populates="bon", cascade="all, delete-orphan", order_by="MgBcLigne.sort_order"
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


class MgNoteFraisCategorie(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "mg_note_frais_categories"
    __table_args__ = (UniqueConstraint("code", name="uq_mg_note_frais_categories_code"),)

    code: Mapped[str] = mapped_column(String(40), index=True)
    libelle: Mapped[str] = mapped_column(String(120))
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    justificatif_obligatoire: Mapped[bool] = mapped_column(Boolean, default=False)
    plafond: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class MgNoteFraisParametre(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mg_note_frais_parametres"
    __table_args__ = (UniqueConstraint("cle", name="uq_mg_note_frais_parametres_cle"),)

    cle: Mapped[str] = mapped_column(String(60), index=True)
    valeur: Mapped[str] = mapped_column(String(255))
    libelle: Mapped[str | None] = mapped_column(String(120), nullable=True)


class MgNoteFrais(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "mg_notes_frais"
    __table_args__ = (UniqueConstraint("reference", name="uq_mg_notes_frais_reference"),)

    reference: Mapped[str] = mapped_column(String(40), index=True)
    date_demande: Mapped[date] = mapped_column(Date)
    agence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agences.id"), nullable=True, index=True
    )
    agence_libelle_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    agence_code_snapshot: Mapped[str | None] = mapped_column(String(40), nullable=True)
    agence_adresse_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    demandeur_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    demandeur_nom: Mapped[str | None] = mapped_column(String(255), nullable=True)
    departement: Mapped[str | None] = mapped_column(String(120), nullable=True)
    fonction: Mapped[str | None] = mapped_column(String(120), nullable=True)
    objet: Mapped[str | None] = mapped_column(String(255), nullable=True)
    periode_debut: Mapped[date | None] = mapped_column(Date, nullable=True)
    periode_fin: Mapped[date | None] = mapped_column(Date, nullable=True)
    devise: Mapped[str] = mapped_column(String(10), default="MRU")
    statut: Mapped[str] = mapped_column(String(30), default="BROUILLON", index=True)
    visa_mg_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    visa_mg_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    visa_dr_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    visa_dr_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    controle_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    controle_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    total_mru: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    montant_paye: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    date_mise_en_paiement: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_paiement: Mapped[date | None] = mapped_column(Date, nullable=True)
    mode_paiement: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ref_paiement: Mapped[str | None] = mapped_column(String(120), nullable=True)
    commentaire_paiement: Mapped[str | None] = mapped_column(Text, nullable=True)
    motif_rejet: Mapped[str | None] = mapped_column(Text, nullable=True)
    motif_correction: Mapped[str | None] = mapped_column(Text, nullable=True)
    pdf_version: Mapped[int] = mapped_column(Integer, default=1)
    document_final_ged_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    observation: Mapped[str | None] = mapped_column(Text, nullable=True)

    lignes: Mapped[list["MgNoteFraisLigne"]] = relationship(
        back_populates="note", cascade="all, delete-orphan"
    )
    historique: Mapped[list["MgNoteFraisHistorique"]] = relationship(
        back_populates="note", cascade="all, delete-orphan", order_by="MgNoteFraisHistorique.created_at"
    )
    paiements: Mapped[list["MgNoteFraisPaiement"]] = relationship(
        back_populates="note", order_by="MgNoteFraisPaiement.date_paiement"
    )

    @property
    def statut_paiement(self) -> str:
        """Calculé depuis les montants : jamais saisi."""
        if self.statut in {"ANNULEE", "REJETEE"}:
            return "ANNULE"
        total = self.total_mru or Decimal("0")
        paye = self.montant_paye or Decimal("0")
        if total > 0 and paye >= total:
            return "PAYE"
        if paye > 0:
            return "PARTIEL"
        return "NON_PAYE"


class MgNoteFraisPaiement(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Paiement effectif d'une note : bénéficiaire, motif et montant dû restent sur la note."""

    __tablename__ = "mg_note_frais_paiements"
    __table_args__ = (
        UniqueConstraint("numero", name="uq_mg_note_frais_paiements_numero"),
        CheckConstraint("montant > 0", name="ck_mg_note_frais_paiements_montant_positif"),
        CheckConstraint("statut IN ('VALIDE', 'ANNULE')", name="ck_mg_note_frais_paiements_statut"),
    )

    numero: Mapped[str] = mapped_column(String(40), index=True)
    note_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_notes_frais.id", ondelete="RESTRICT"), index=True
    )
    date_paiement: Mapped[date] = mapped_column(Date, index=True)
    montant: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    mode_paiement: Mapped[str] = mapped_column(String(40), index=True)
    reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    numero_cheque: Mapped[str | None] = mapped_column(String(60), nullable=True)
    banque: Mapped[str | None] = mapped_column(String(120), nullable=True)
    compte: Mapped[str | None] = mapped_column(String(120), nullable=True)
    observation: Mapped[str | None] = mapped_column(Text, nullable=True)
    statut: Mapped[str] = mapped_column(String(20), default="VALIDE", index=True)
    motif_annulation: Mapped[str | None] = mapped_column(Text, nullable=True)
    annule_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    annule_par_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    annule_par_nom: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_by_nom: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    updated_by_nom: Mapped[str | None] = mapped_column(String(255), nullable=True)

    note: Mapped[MgNoteFrais] = relationship(back_populates="paiements")


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
    categorie_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_note_frais_categories.id"), nullable=True
    )
    categorie_libelle_snapshot: Mapped[str | None] = mapped_column(String(120), nullable=True)
    devise: Mapped[str] = mapped_column(String(10), default="MRU")
    commentaire: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    note: Mapped[MgNoteFrais] = relationship(back_populates="lignes")


class MgNoteFraisHistorique(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mg_note_frais_historique"

    note_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_notes_frais.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(String(60))
    from_statut: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_statut: Mapped[str | None] = mapped_column(String(30), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    user_nom: Mapped[str | None] = mapped_column(String(255), nullable=True)
    commentaire: Mapped[str | None] = mapped_column(Text, nullable=True)

    note: Mapped[MgNoteFrais] = relationship(back_populates="historique")


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
    agence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agences.id"), nullable=True, index=True
    )
    agence_libelle_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    type_contrat: Mapped[str] = mapped_column(String(40), default="AUTRE")
    numero_contrat: Mapped[str | None] = mapped_column(String(80), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    date_signature: Mapped[date | None] = mapped_column(Date, nullable=True)
    devise: Mapped[str] = mapped_column(String(8), default="MRU")
    montant_ht: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    taux_tva: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    responsable_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    responsable_nom: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mode_paiement: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ref_paiement: Mapped[str | None] = mapped_column(String(120), nullable=True)
    contrat_precedent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_contrats.id"), nullable=True
    )
    reconduction: Mapped[str] = mapped_column(String(20), default="AUCUNE", server_default="AUCUNE")
    preavis_jours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    echeances: Mapped[list["MgContratEcheance"]] = relationship(
        back_populates="contrat", cascade="all, delete-orphan", order_by="MgContratEcheance.date_prevue"
    )
    paiements: Mapped[list["MgContratPaiement"]] = relationship(
        back_populates="contrat", cascade="all, delete-orphan", order_by="MgContratPaiement.date_prevue"
    )
    historique: Mapped[list["MgContratHistorique"]] = relationship(
        back_populates="contrat", cascade="all, delete-orphan", order_by="MgContratHistorique.created_at.desc()"
    )
    avenants: Mapped[list["MgContratAvenant"]] = relationship(
        back_populates="contrat", cascade="all, delete-orphan", order_by="MgContratAvenant.numero"
    )

    @property
    def jours_restants(self) -> int | None:
        return (self.date_fin - date.today()).days if self.date_fin else None

    @property
    def date_preavis(self) -> date | None:
        if not self.date_fin or not self.preavis_jours:
            return None
        return self.date_fin - timedelta(days=self.preavis_jours)

    @property
    def etat(self) -> str:
        """Statut affiché : distingue « échéance ≤ 30 j » et « date dépassée, encore actif »."""
        jours = self.jours_restants
        if self.statut == "ACTIF" and jours is not None:
            if jours < 0:
                return "DATE_DEPASSEE"
            if jours <= 30:
                return "ECHEANCE_30"
        return self.statut


class MgContratEcheance(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mg_contrat_echeances"

    contrat_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_contrats.id", ondelete="CASCADE"), index=True
    )
    type_echeance: Mapped[str] = mapped_column(String(40), default="AUTRE")
    date_prevue: Mapped[date] = mapped_column(Date)
    date_reelle: Mapped[date | None] = mapped_column(Date, nullable=True)
    montant: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    responsable_nom: Mapped[str | None] = mapped_column(String(255), nullable=True)
    statut: Mapped[str] = mapped_column(String(30), default="A_VENIR")
    commentaire: Mapped[str | None] = mapped_column(Text, nullable=True)

    contrat: Mapped[MgContrat] = relationship(back_populates="echeances")
    paiements: Mapped[list["MgContratPaiement"]] = relationship(back_populates="echeance")

    @property
    def montant_paye(self) -> Decimal:
        return sum((p.montant_paye or Decimal("0") for p in self.paiements), Decimal("0"))


class MgContratPaiement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mg_contrat_paiements"

    contrat_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_contrats.id", ondelete="CASCADE"), index=True
    )
    echeance_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_contrat_echeances.id", ondelete="SET NULL"), nullable=True
    )
    reference: Mapped[str | None] = mapped_column(String(40), nullable=True)
    date_prevue: Mapped[date] = mapped_column(Date)
    date_reelle: Mapped[date | None] = mapped_column(Date, nullable=True)
    montant_prevu: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    montant_paye: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    devise: Mapped[str] = mapped_column(String(8), default="MRU")
    statut: Mapped[str] = mapped_column(String(30), default="A_VENIR")
    mode: Mapped[str | None] = mapped_column(String(40), nullable=True)
    commentaire: Mapped[str | None] = mapped_column(Text, nullable=True)

    contrat: Mapped[MgContrat] = relationship(back_populates="paiements")
    echeance: Mapped["MgContratEcheance | None"] = relationship(back_populates="paiements")


class MgContratAvenant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mg_contrat_avenants"
    __table_args__ = (UniqueConstraint("contrat_id", "numero", name="uq_mg_contrat_avenants_numero"),)

    contrat_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_contrats.id", ondelete="CASCADE"), index=True
    )
    numero: Mapped[int] = mapped_column(Integer)
    type_avenant: Mapped[str] = mapped_column(String(30))
    objet: Mapped[str] = mapped_column(String(255))
    date_effet: Mapped[date] = mapped_column(Date)
    montant_ht_avant: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    montant_ht_apres: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    montant_ttc_avant: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    montant_ttc_apres: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    date_fin_avant: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_fin_apres: Mapped[date | None] = mapped_column(Date, nullable=True)
    clauses: Mapped[str | None] = mapped_column(Text, nullable=True)
    version_contrat: Mapped[int] = mapped_column(Integer, default=1)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    user_nom: Mapped[str | None] = mapped_column(String(255), nullable=True)

    contrat: Mapped[MgContrat] = relationship(back_populates="avenants")


class MgContratHistorique(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mg_contrat_historique"

    contrat_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_contrats.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(String(60))
    from_statut: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_statut: Mapped[str | None] = mapped_column(String(30), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    user_nom: Mapped[str | None] = mapped_column(String(255), nullable=True)
    commentaire: Mapped[str | None] = mapped_column(Text, nullable=True)

    contrat: Mapped[MgContrat] = relationship(back_populates="historique")


class MgContratType(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mg_contrat_types"
    __table_args__ = (UniqueConstraint("code", name="uq_mg_contrat_types_code"),)

    code: Mapped[str] = mapped_column(String(40))
    libelle: Mapped[str] = mapped_column(String(120))
    actif: Mapped[bool] = mapped_column(Boolean, default=True)


class MgPointFacturation(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Compteur / abonnement d'un fournisseur pour un site (agence, siège, PDV Amanty…).

    Rattache chaque facture récurrente à ce qu'elle facture. Jamais supprimé physiquement
    s'il porte des factures : passage à INACTIF.
    """

    __tablename__ = "mg_points_facturation"
    __table_args__ = (
        UniqueConstraint("code", name="uq_mg_points_facturation_code"),
        CheckConstraint("type_point IN ('AGENCE','SIEGE','PDV','AUTRE')", name="ck_mg_points_facturation_type"),
        CheckConstraint("statut IN ('ACTIF','INACTIF')", name="ck_mg_points_facturation_statut"),
    )

    code: Mapped[str] = mapped_column(String(20))
    type_point: Mapped[str] = mapped_column(String(20), default="AGENCE", index=True)
    nom: Mapped[str] = mapped_column(String(255))
    agence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agences.id"), nullable=True, index=True
    )
    fournisseur_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fournisseurs.id"), index=True
    )
    contrat_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mg_contrats.id"), nullable=True
    )
    reference_fournisseur: Mapped[str] = mapped_column(String(80))
    # Chiffres seuls : recherche « 363215238221 » quel que soit le format saisi.
    reference_normalisee: Mapped[str] = mapped_column(String(80))
    compteur: Mapped[str | None] = mapped_column(String(40), nullable=True)
    type_facture: Mapped[str | None] = mapped_column(String(40), nullable=True)
    periodicite: Mapped[str] = mapped_column(String(20), default="MENSUEL")
    adresse: Mapped[str | None] = mapped_column(Text, nullable=True)
    date_debut: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_fin: Mapped[date | None] = mapped_column(Date, nullable=True)
    statut: Mapped[str] = mapped_column(String(20), default="ACTIF")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class MgContratParametre(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mg_contrat_parametres"
    __table_args__ = (UniqueConstraint("cle", name="uq_mg_contrat_parametres_cle"),)

    cle: Mapped[str] = mapped_column(String(80))
    valeur: Mapped[str] = mapped_column(String(255), default="")
    libelle: Mapped[str | None] = mapped_column(String(255), nullable=True)
