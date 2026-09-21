"""Schémas Moyens Généraux Phase 2."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BcLigneIn(BaseModel):
    code_produit: str | None = None
    departement: str | None = None
    description: str = Field(min_length=1, max_length=255)
    quantite: Decimal = Field(gt=0)
    uom: str = "U"
    prix_unitaire: Decimal = Field(ge=0)
    article_id: UUID | None = None
    remise_pct: Decimal = Field(default=Decimal("0"), ge=0)
    taux_tva: Decimal = Field(default=Decimal("0"), ge=0)
    stockable: bool = False


class BcLigneOut(BcLigneIn):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    prix_total: Decimal
    total_ttc: Decimal = Decimal("0")
    sort_order: int
    quantite_recue: Decimal = Decimal("0")


class BonCreate(BaseModel):
    date_bc: date
    fournisseur_id: UUID | None = None
    fournisseur_raison_sociale: str | None = None
    fournisseur_nif: str | None = None
    fournisseur_telephone: str | None = None
    fournisseur_adresse: str | None = None
    departement: str | None = None
    projet: str | None = None
    acheteur_nom: str | None = None
    acheteur_tel: str | None = None
    adresse_facturation: str | None = None
    adresse_livraison: str | None = None
    conditions: str | None = None
    incoterm: str | None = None
    conditions_paiement: str | None = None
    moyen_paiement: str | None = None
    demandeur_nom: str | None = None
    demandeur_date: date | None = None
    observation: str | None = None
    demande_id: UUID | None = None
    consultation_id: UUID | None = None
    comparaison_id: UUID | None = None
    contrat_id: UUID | None = None
    agence_facturation_id: UUID | None = None
    agence_livraison_id: UUID | None = None
    type_achat: str = "FOURNITURE"
    devise: str = "MRU"
    date_livraison_prevue: date | None = None
    lignes: list[BcLigneIn] = Field(default_factory=list)


class BonUpdate(BaseModel):
    date_bc: date | None = None
    fournisseur_id: UUID | None = None
    fournisseur_raison_sociale: str | None = None
    fournisseur_nif: str | None = None
    fournisseur_telephone: str | None = None
    fournisseur_adresse: str | None = None
    departement: str | None = None
    projet: str | None = None
    acheteur_nom: str | None = None
    acheteur_tel: str | None = None
    adresse_facturation: str | None = None
    adresse_livraison: str | None = None
    conditions: str | None = None
    incoterm: str | None = None
    conditions_paiement: str | None = None
    moyen_paiement: str | None = None
    demandeur_nom: str | None = None
    demandeur_date: date | None = None
    observation: str | None = None
    demande_id: UUID | None = None
    consultation_id: UUID | None = None
    comparaison_id: UUID | None = None
    contrat_id: UUID | None = None
    agence_facturation_id: UUID | None = None
    agence_livraison_id: UUID | None = None
    type_achat: str | None = None
    devise: str | None = None
    date_livraison_prevue: date | None = None
    lignes: list[BcLigneIn] | None = None


class BonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reference: str
    date_bc: date
    fournisseur_id: UUID | None
    fournisseur_raison_sociale: str | None
    fournisseur_nif: str | None
    fournisseur_telephone: str | None
    fournisseur_adresse: str | None
    departement: str | None
    projet: str | None
    acheteur_nom: str | None
    acheteur_tel: str | None
    adresse_facturation: str | None
    adresse_livraison: str | None
    conditions: str | None
    incoterm: str | None
    conditions_paiement: str | None
    moyen_paiement: str | None
    demandeur_nom: str | None
    demandeur_date: date | None
    statut: str
    total_ht: Decimal
    total_tva: Decimal = Decimal("0")
    total_ttc: Decimal = Decimal("0")
    type_achat: str = "FOURNITURE"
    devise: str = "MRU"
    demande_id: UUID | None = None
    consultation_id: UUID | None = None
    comparaison_id: UUID | None = None
    contrat_id: UUID | None = None
    agence_facturation_id: UUID | None = None
    agence_livraison_id: UUID | None = None
    agence_facturation_snapshot: str | None = None
    agence_livraison_snapshot: str | None = None
    date_livraison_prevue: date | None = None
    pdf_version: int = 1
    observation: str | None
    lignes: list[BcLigneOut] = []


class TransitionIn(BaseModel):
    action: str


class NoteLigneIn(BaseModel):
    date_depense: date
    description: str = Field(min_length=1, max_length=255)
    motif: str | None = None
    montant: Decimal = Field(ge=0)
    mode_reglement: str | None = None


class NoteLigneOut(NoteLigneIn):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sort_order: int


class NoteCreate(BaseModel):
    date_demande: date
    agence_id: UUID | None = None
    demandeur_nom: str | None = None
    departement: str | None = None
    fonction: str | None = None
    observation: str | None = None
    lignes: list[NoteLigneIn] = Field(default_factory=list)


class NoteUpdate(BaseModel):
    date_demande: date | None = None
    agence_id: UUID | None = None
    demandeur_nom: str | None = None
    departement: str | None = None
    fonction: str | None = None
    observation: str | None = None
    lignes: list[NoteLigneIn] | None = None


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reference: str
    date_demande: date
    agence_id: UUID | None
    agence_libelle_snapshot: str | None
    demandeur_nom: str | None
    departement: str | None
    fonction: str | None
    statut: str
    total_mru: Decimal
    observation: str | None
    lignes: list[NoteLigneOut] = []


class ContratCreate(BaseModel):
    titre: str = Field(min_length=1, max_length=255)
    fournisseur_id: UUID | None = None
    fournisseur_snapshot: str | None = None
    date_debut: date
    date_fin: date | None = None
    montant: Decimal | None = None
    periodicite: str = "ANNUEL"
    prochain_echeance: date | None = None
    alerte_jours: int = 30
    observation: str | None = None


class ContratUpdate(BaseModel):
    titre: str | None = None
    fournisseur_id: UUID | None = None
    fournisseur_snapshot: str | None = None
    date_debut: date | None = None
    date_fin: date | None = None
    montant: Decimal | None = None
    periodicite: str | None = None
    prochain_echeance: date | None = None
    alerte_jours: int | None = None
    statut: str | None = None
    observation: str | None = None


class ContratOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reference: str
    titre: str
    fournisseur_id: UUID | None
    fournisseur_snapshot: str | None
    date_debut: date
    date_fin: date | None
    montant: Decimal | None
    periodicite: str
    prochain_echeance: date | None
    alerte_jours: int
    statut: str
    observation: str | None


class ArchiveDocOut(BaseModel):
    id: UUID
    filename: str | None = None
    original_name: str | None = None
    module_code: str | None = None
    espace_code: str | None = None
    entity: str | None = None
    entity_id: str | None = None
    created_at: datetime | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
