"""Schémas Achats & Approvisionnements."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.mg_ops import BonOut, TransitionIn

__all__ = [
    "TransitionIn",
    "BonOut",
    "ParametreCreate",
    "ParametreUpdate",
    "ParametreOut",
    "DashboardAchatsOut",
    "DemandeLigneIn",
    "DemandeLigneOut",
    "DemandeCreate",
    "DemandeUpdate",
    "DemandeOut",
    "ConsultationCreate",
    "ConsultationUpdate",
    "ConsultationOut",
    "DevisLigneIn",
    "DevisLigneOut",
    "DevisCreate",
    "DevisUpdate",
    "DevisOut",
    "ComparaisonCreate",
    "ComparaisonUpdate",
    "ComparaisonOut",
    "ComparaisonValidateIn",
    "BlCreate",
    "BlOut",
    "ReceptionLigneIn",
    "ReceptionLigneOut",
    "ReceptionCreate",
    "ReceptionUpdate",
    "ReceptionOut",
    "FactureLigneIn",
    "FactureLigneOut",
    "FactureCreate",
    "FactureUpdate",
    "FactureOut",
    "ThreeWayMatchOut",
    "PaiementCreate",
    "PaiementUpdate",
    "PaiementOut",
    "EvenementOut",
    "AlerteOut",
    "RapportSummaryOut",
    "FournisseurSummaryOut",
    "PaginatedBonsOut",
]


class ParametreCreate(BaseModel):
    cle: str = Field(min_length=1, max_length=80)
    valeur: str
    description: str | None = None


class ParametreUpdate(BaseModel):
    valeur: str | None = None
    description: str | None = None


class ParametreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cle: str
    valeur: str
    description: str | None = None


class DashboardAchatsOut(BaseModel):
    demandes_ouvertes: int = 0
    consultations_ouvertes: int = 0
    devis_ouverts: int = 0
    comparaisons_ouvertes: int = 0
    bons_en_cours: int = 0
    bons_partiels: int = 0
    receptions_mois: int = 0
    factures_ouvertes: int = 0
    paiements_a_payer: int = 0
    montant_bc_mois: Decimal = Decimal("0")
    montant_factures_mois: Decimal = Decimal("0")
    alertes: int = 0


class DemandeLigneIn(BaseModel):
    designation: str = Field(min_length=1, max_length=255)
    description: str | None = None
    quantite: Decimal = Field(gt=0)
    uom: str = "U"
    prix_estime: Decimal = Field(default=Decimal("0"), ge=0)
    article_id: UUID | None = None


class DemandeLigneOut(DemandeLigneIn):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    montant_estime: Decimal
    sort_order: int


class DemandeCreate(BaseModel):
    date_demande: date
    agence_id: UUID
    departement_id: UUID | None = None
    demandeur_nom: str | None = None
    fonction: str | None = None
    type_achat: str = "FOURNITURE"
    priorite: str = "NORMAL"
    projet: str | None = None
    motif: str | None = None
    date_souhaitee: date | None = None
    budget_estime: Decimal | None = None
    observation: str | None = None
    lignes: list[DemandeLigneIn] = Field(default_factory=list)


class DemandeUpdate(BaseModel):
    date_demande: date | None = None
    agence_id: UUID | None = None
    departement_id: UUID | None = None
    demandeur_nom: str | None = None
    fonction: str | None = None
    type_achat: str | None = None
    priorite: str | None = None
    projet: str | None = None
    motif: str | None = None
    date_souhaitee: date | None = None
    budget_estime: Decimal | None = None
    observation: str | None = None
    lignes: list[DemandeLigneIn] | None = None


class DemandeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reference: str
    date_demande: date
    agence_id: UUID
    departement_id: UUID | None
    demandeur_id: UUID | None
    demandeur_nom: str | None
    fonction: str | None
    type_achat: str
    priorite: str
    projet: str | None
    motif: str | None
    date_souhaitee: date | None
    budget_estime: Decimal | None
    statut: str
    observation: str | None
    lignes: list[DemandeLigneOut] = []
    consultation_id: UUID | None = None
    bon_id: UUID | None = None


class ConsultationCreate(BaseModel):
    date_consultation: date
    demande_id: UUID | None = None
    agence_id: UUID
    objet: str = Field(min_length=1, max_length=255)
    date_limite: date | None = None
    observation: str | None = None
    fournisseur_ids: list[UUID] = Field(default_factory=list)


class ConsultationUpdate(BaseModel):
    date_consultation: date | None = None
    demande_id: UUID | None = None
    agence_id: UUID | None = None
    objet: str | None = None
    date_limite: date | None = None
    observation: str | None = None
    fournisseur_ids: list[UUID] | None = None
    statut: str | None = None


class ConsultationFournisseurOut(BaseModel):
    id: str
    code: str
    raison_sociale: str
    is_active: bool = True


class ConsultationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reference: str
    date_consultation: date
    demande_id: UUID | None
    agence_id: UUID
    objet: str
    date_limite: date | None
    responsable_id: UUID | None
    statut: str
    observation: str | None
    fournisseur_ids: list[UUID] = []
    fournisseurs: list[ConsultationFournisseurOut] = []
    demande_reference: str | None = None
    nb_devis: int = 0
    nb_fournisseurs: int = 0


class DevisLigneIn(BaseModel):
    designation: str = Field(min_length=1, max_length=255)
    quantite: Decimal = Field(gt=0)
    prix_unitaire: Decimal = Field(ge=0)
    remise_pct: Decimal = Field(default=Decimal("0"), ge=0)
    taux_tva: Decimal = Field(default=Decimal("0"), ge=0)


class DevisLigneOut(DevisLigneIn):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    total_ht: Decimal
    sort_order: int


class DevisCreate(BaseModel):
    fournisseur_id: UUID
    consultation_id: UUID | None = None
    date_devis: date
    date_validite: date | None = None
    devise: str = "MRU"
    conditions: str | None = None
    delai_livraison: str | None = None
    conditions_paiement: str | None = None
    observation: str | None = None
    lignes: list[DevisLigneIn] = Field(default_factory=list)


class DevisUpdate(BaseModel):
    date_devis: date | None = None
    date_validite: date | None = None
    devise: str | None = None
    conditions: str | None = None
    delai_livraison: str | None = None
    conditions_paiement: str | None = None
    observation: str | None = None
    statut: str | None = None
    lignes: list[DevisLigneIn] | None = None


class DevisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reference: str
    fournisseur_id: UUID
    consultation_id: UUID | None
    date_devis: date
    date_validite: date | None
    montant_ht: Decimal
    montant_tva: Decimal
    montant_ttc: Decimal
    devise: str
    conditions: str | None
    delai_livraison: str | None
    conditions_paiement: str | None
    statut: str
    observation: str | None
    lignes: list[DevisLigneOut] = []


class ComparaisonCreate(BaseModel):
    consultation_id: UUID
    demande_id: UUID | None = None
    observation: str | None = None
    snapshot_json: str | None = None


class ComparaisonUpdate(BaseModel):
    observation: str | None = None
    snapshot_json: str | None = None
    motif_choix: str | None = None
    fournisseur_retenu_id: UUID | None = None


class ComparaisonValidateIn(BaseModel):
    fournisseur_retenu_id: UUID
    motif_choix: str | None = None


class ComparaisonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reference: str
    consultation_id: UUID
    demande_id: UUID | None
    statut: str
    fournisseur_retenu_id: UUID | None
    motif_choix: str | None
    snapshot_json: str | None
    observation: str | None


class BlCreate(BaseModel):
    bon_id: UUID
    fournisseur_id: UUID | None = None
    date_bl: date
    date_livraison: date | None = None
    agence_id: UUID | None = None
    transporteur: str | None = None
    observation: str | None = None


class BlOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reference: str
    bon_id: UUID
    bon_reference: str | None = None
    fournisseur_id: UUID
    date_bl: date
    date_livraison: date | None
    agence_id: UUID | None
    transporteur: str | None
    observation: str | None
    statut: str


class ReceptionLigneIn(BaseModel):
    bc_ligne_id: UUID
    quantite_recue: Decimal = Field(gt=0)
    article_id: UUID | None = None


class ReceptionLigneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    bc_ligne_id: UUID
    quantite_recue: Decimal
    article_id: UUID | None


class ReceptionCreate(BaseModel):
    bon_id: UUID
    bl_id: UUID | None = None
    date_reception: date
    agence_id: UUID | None = None
    observation: str | None = None
    lignes: list[ReceptionLigneIn] = Field(min_length=1)


class ReceptionUpdate(BaseModel):
    date_reception: date | None = None
    agence_id: UUID | None = None
    observation: str | None = None
    statut: str | None = None


class ReceptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reference: str
    bon_id: UUID
    bon_reference: str | None = None
    bl_id: UUID | None
    date_reception: date
    agence_id: UUID | None
    statut: str
    observation: str | None
    created_by: UUID | None
    lignes: list[ReceptionLigneOut] = []


class FactureLigneIn(BaseModel):
    designation: str = Field(min_length=1, max_length=255)
    quantite: Decimal = Field(gt=0)
    prix_unitaire: Decimal = Field(ge=0)


class FactureLigneOut(FactureLigneIn):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    total_ht: Decimal
    sort_order: int


class FactureCreate(BaseModel):
    numero_fournisseur: str | None = None
    fournisseur_id: UUID
    bon_id: UUID
    bl_id: UUID | None = None
    reception_id: UUID | None = None
    date_facture: date
    date_echeance: date | None = None
    montant_ht: Decimal | None = None
    montant_tva: Decimal | None = None
    montant_ttc: Decimal | None = None
    devise: str = "MRU"
    observation: str | None = None
    lignes: list[FactureLigneIn] = Field(default_factory=list)


class FactureUpdate(BaseModel):
    numero_fournisseur: str | None = None
    date_facture: date | None = None
    date_echeance: date | None = None
    montant_ht: Decimal | None = None
    montant_tva: Decimal | None = None
    montant_ttc: Decimal | None = None
    devise: str | None = None
    statut: str | None = None
    observation: str | None = None
    lignes: list[FactureLigneIn] | None = None


class FactureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reference: str
    numero_fournisseur: str | None
    fournisseur_id: UUID
    bon_id: UUID
    bl_id: UUID | None
    reception_id: UUID | None
    date_facture: date
    date_echeance: date | None
    montant_ht: Decimal
    montant_tva: Decimal
    montant_ttc: Decimal
    devise: str
    statut: str
    ecart_quantite: bool
    ecart_montant: bool
    observation: str | None
    lignes: list[FactureLigneOut] = []


class ThreeWayMatchOut(BaseModel):
    resultat: str  # CONFORME | ANOMALIE
    ecart_quantite: bool
    ecart_montant: bool
    detail: str | None = None
    bc_total_ttc: Decimal | None = None
    facture_ttc: Decimal | None = None
    qty_commandee: Decimal | None = None
    qty_recue: Decimal | None = None
    qty_facturee: Decimal | None = None


class PaiementCreate(BaseModel):
    facture_id: UUID
    fournisseur_id: UUID | None = None
    montant: Decimal = Field(gt=0)
    date_echeance: date | None = None
    date_paiement: date | None = None
    mode_paiement: str | None = None
    reference_paiement: str | None = None
    observation: str | None = None


class PaiementUpdate(BaseModel):
    montant: Decimal | None = None
    date_echeance: date | None = None
    date_paiement: date | None = None
    mode_paiement: str | None = None
    reference_paiement: str | None = None
    statut: str | None = None
    observation: str | None = None


class PaiementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reference: str
    facture_id: UUID
    fournisseur_id: UUID
    montant: Decimal
    date_echeance: date | None
    date_paiement: date | None
    mode_paiement: str | None
    reference_paiement: str | None
    statut: str
    observation: str | None


class EvenementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    entity_type: str
    entity_id: UUID
    action: str
    message: str | None
    user_id: UUID | None
    created_at: datetime


class AlerteOut(BaseModel):
    type: str
    reference: str
    entity_id: UUID
    message: str
    date_echeance: date | None = None
    priorite: str = "NORMAL"


class RapportSummaryOut(BaseModel):
    nb_demandes: int = 0
    nb_consultations: int = 0
    nb_devis: int = 0
    nb_comparaisons: int = 0
    nb_bons: int = 0
    nb_receptions: int = 0
    nb_factures: int = 0
    montant_bons: Decimal = Decimal("0")
    montant_factures: Decimal = Decimal("0")
    montant_paiements: Decimal = Decimal("0")


class RapportExportIn(BaseModel):
    format: str = Field(pattern="^(pdf|xlsx|csv)$")
    scope: str = Field(default="filtered", pattern="^(selection|filtered)$")
    ids: list[UUID] = Field(default_factory=list)
    filters: dict[str, str | None] = Field(default_factory=dict)
    columns: list[str] | None = None


class RapportCustomPreviewIn(BaseModel):
    dataset: str
    columns: list[str] = Field(default_factory=list)
    filters: dict[str, str | None] = Field(default_factory=dict)
    sort_by: str | None = None
    sort_dir: str = "desc"
    page: int = Field(default=1, ge=1)
    size: int = Field(default=50, ge=1, le=200)


class RapportCustomExportIn(RapportCustomPreviewIn):
    format: str = Field(pattern="^(pdf|xlsx|csv)$")
    scope: str = Field(default="filtered", pattern="^(selection|filtered)$")
    ids: list[UUID] = Field(default_factory=list)


class FournisseurSummaryOut(BaseModel):
    id: UUID
    code: str | None = None
    raison_sociale: str
    nom_commercial: str | None = None
    type_fournisseur: str = "FOURNITURE"
    contact: str | None = None
    contact_fonction: str | None = None
    telephone: str | None = None
    telephone_secondaire: str | None = None
    email: str | None = None
    site_web: str | None = None
    adresse: str | None = None
    ville: str | None = None
    pays: str | None = None
    nif: str | None = None
    rc: str | None = None
    devise_defaut: str | None = "MRU"
    mode_paiement_defaut: str | None = None
    delai_paiement_jours: int | None = None
    conditions_commerciales: str | None = None
    is_active: bool = True
    nb_consultations: int = 0
    nb_devis: int = 0
    nb_bons: int = 0
    nb_receptions: int = 0
    nb_factures: int = 0
    nb_paiements: int = 0
    montant_bons: Decimal = Decimal("0")
    montant_factures: Decimal = Decimal("0")


class PaginatedBonsOut(BaseModel):
    items: list[BonOut]
    total: int
    page: int
    size: int
