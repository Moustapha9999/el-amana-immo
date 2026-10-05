"""Schémas — Gestion des factures (Contrats & échéances)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class FactureLigneIn(BaseModel):
    description: str = Field(min_length=1, max_length=255)
    quantite: Decimal | None = Field(default=None, ge=0)
    unite: str | None = Field(default=None, max_length=20)
    prix_unitaire: Decimal | None = Field(default=None, ge=0)
    montant: Decimal | None = Field(default=None, ge=0)
    type_ligne: str | None = Field(default=None, max_length=40)


class FactureBase(BaseModel):
    numero_fournisseur: str | None = Field(default=None, max_length=80)
    fournisseur_id: UUID | None = None
    point_facturation_id: UUID | None = None
    agence_id: UUID | None = None
    contrat_id: UUID | None = None
    type_facture: str | None = Field(default=None, max_length=40)
    reference_fournisseur: str | None = Field(default=None, max_length=80)
    date_facture: date | None = None
    date_reception: date | None = None
    periode_debut: date | None = None
    periode_fin: date | None = None
    mois: int | None = Field(default=None, ge=1, le=12)
    annee: int | None = Field(default=None, ge=2000, le=2100)
    date_echeance: date | None = None
    montant_ht: Decimal | None = Field(default=None, ge=0)
    montant_tva: Decimal | None = Field(default=None, ge=0)
    autres_taxes: Decimal | None = Field(default=None, ge=0)
    remise: Decimal | None = Field(default=None, ge=0)
    montant_ttc: Decimal | None = Field(default=None, ge=0)
    montant_a_payer: Decimal | None = Field(default=None, ge=0)
    devise: str | None = Field(default=None, max_length=10)
    observation: str | None = Field(default=None, max_length=4000)
    lignes: list[FactureLigneIn] | None = None


class FactureCreate(FactureBase):
    date_facture: date
    # False : brouillon ; True : facture reçue et enregistrée.
    enregistrer: bool = True
    # Confirme la saisie d'une 2ᵉ facture sur le même point et la même période.
    forcer: bool = False


class FactureUpdate(FactureBase):
    forcer: bool = False


class FactureTransitionIn(BaseModel):
    motif: str | None = Field(default=None, max_length=2000)


class FacturePaiementIn(BaseModel):
    date_paiement: date
    montant: Decimal = Field(gt=0)
    mode_paiement: str | None = Field(default=None, max_length=80)
    reference_paiement: str | None = Field(default=None, max_length=120)
    observation: str | None = Field(default=None, max_length=2000)
    justificatif_document_id: UUID | None = None


class FacturePaiementUpdate(BaseModel):
    date_paiement: date | None = None
    montant: Decimal | None = Field(default=None, gt=0)
    mode_paiement: str | None = Field(default=None, max_length=80)
    reference_paiement: str | None = Field(default=None, max_length=120)
    observation: str | None = Field(default=None, max_length=2000)
    justificatif_document_id: UUID | None = None


class PointFacturationIn(BaseModel):
    type_point: str | None = Field(default=None, max_length=20)
    nom: str | None = Field(default=None, max_length=255)
    agence_id: UUID | None = None
    fournisseur_id: UUID | None = None
    contrat_id: UUID | None = None
    reference_fournisseur: str | None = Field(default=None, max_length=80)
    compteur: str | None = Field(default=None, max_length=40)
    type_facture: str | None = Field(default=None, max_length=40)
    periodicite: str | None = Field(default=None, max_length=20)
    adresse: str | None = Field(default=None, max_length=2000)
    date_debut: date | None = None
    date_fin: date | None = None
    statut: str | None = Field(default=None, max_length=20)
    description: str | None = Field(default=None, max_length=4000)


class PointFacturationCreate(PointFacturationIn):
    type_point: str = Field(max_length=20)
    nom: str = Field(min_length=1, max_length=255)
    fournisseur_id: UUID
    reference_fournisseur: str = Field(min_length=1, max_length=80)


class ImportChoix(BaseModel):
    normalisee: str = Field(max_length=80)
    inclure: bool = True
    nom: str | None = Field(default=None, max_length=255)
    type_point: str | None = Field(default=None, max_length=20)
    agence_id: UUID | None = None
