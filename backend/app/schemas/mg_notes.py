"""Schémas API — Notes de frais MG."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TransitionIn(BaseModel):
    action: str
    commentaire: str | None = None


class NoteLigneIn(BaseModel):
    date_depense: date
    description: str = Field(min_length=1, max_length=255)
    motif: str | None = None
    montant: Decimal = Field(gt=0)
    mode_reglement: str | None = None
    categorie_id: UUID | None = None
    devise: str = "MRU"
    commentaire: str | None = None


class NoteLigneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    date_depense: date
    description: str
    motif: str | None
    montant: Decimal
    mode_reglement: str | None
    categorie_id: UUID | None = None
    categorie_libelle_snapshot: str | None = None
    devise: str = "MRU"
    commentaire: str | None = None
    sort_order: int


class NoteCreate(BaseModel):
    date_demande: date
    agence_id: UUID | None = None
    intitule: str | None = None  # titre libre si pas d'agence (ex. Frais Carburant)
    demandeur_nom: str | None = None
    departement: str | None = None
    fonction: str | None = None
    objet: str | None = None
    periode_debut: date | None = None
    periode_fin: date | None = None
    devise: str = "MRU"
    observation: str | None = None
    lignes: list[NoteLigneIn] = Field(default_factory=list)


class NoteUpdate(BaseModel):
    date_demande: date | None = None
    agence_id: UUID | None = None
    intitule: str | None = None
    demandeur_nom: str | None = None
    departement: str | None = None
    fonction: str | None = None
    objet: str | None = None
    periode_debut: date | None = None
    periode_fin: date | None = None
    devise: str | None = None
    observation: str | None = None
    lignes: list[NoteLigneIn] | None = None


class NoteHistoriqueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    action: str
    from_statut: str | None
    to_statut: str | None
    user_id: UUID | None
    user_nom: str | None
    commentaire: str | None
    created_at: datetime | None = None


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reference: str
    date_demande: date
    agence_id: UUID | None
    agence_libelle_snapshot: str | None
    agence_code_snapshot: str | None = None
    agence_adresse_snapshot: str | None = None
    demandeur_id: UUID | None = None
    demandeur_nom: str | None
    departement: str | None
    fonction: str | None
    objet: str | None = None
    periode_debut: date | None = None
    periode_fin: date | None = None
    devise: str = "MRU"
    statut: str
    total_mru: Decimal
    montant_paye: Decimal = Decimal("0")
    statut_paiement: str = "NON_PAYE"
    date_mise_en_paiement: date | None = None
    date_paiement: date | None = None
    mode_paiement: str | None = None
    ref_paiement: str | None = None
    commentaire_paiement: str | None = None
    motif_rejet: str | None = None
    motif_correction: str | None = None
    pdf_version: int = 1
    observation: str | None
    lignes: list[NoteLigneOut] = []
    historique: list[NoteHistoriqueOut] = []


class NoteListOut(BaseModel):
    items: list[NoteOut]
    total: int
    page: int
    size: int


class PaiementIn(BaseModel):
    montant: Decimal = Field(gt=0)
    date_paiement: date | None = None
    mode_paiement: str | None = None
    ref_paiement: str | None = None
    commentaire: str | None = None


MODES_PAIEMENT = ("Espèces", "Virement", "Chèque", "Carte", "Amanty")


class NotePaiementCreate(BaseModel):
    note_id: UUID
    date_paiement: date
    montant: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    mode_paiement: str = Field(min_length=1, max_length=40)
    reference: str | None = Field(None, max_length=120)
    numero_cheque: str | None = Field(None, max_length=60)
    banque: str | None = Field(None, max_length=120)
    compte: str | None = Field(None, max_length=120)
    observation: str | None = None


class NotePaiementUpdate(BaseModel):
    date_paiement: date | None = None
    montant: Decimal | None = Field(None, gt=0, max_digits=18, decimal_places=2)
    mode_paiement: str | None = Field(None, min_length=1, max_length=40)
    reference: str | None = Field(None, max_length=120)
    numero_cheque: str | None = Field(None, max_length=60)
    banque: str | None = Field(None, max_length=120)
    compte: str | None = Field(None, max_length=120)
    observation: str | None = None


class NotePaiementAnnulation(BaseModel):
    motif: str = Field(min_length=3, max_length=1000)


class NoteRegistreOut(BaseModel):
    """Registre concerné : données lues sur la note (source principale), jamais copiées."""

    id: UUID
    reference: str
    date_demande: date
    beneficiaire: str | None
    departement: str | None
    fonction: str | None
    motif: str | None
    intitule: str | None
    statut: str
    statut_paiement: str
    montant_initial: Decimal
    montant_paye: Decimal
    solde: Decimal
    devise: str = "MRU"
    nb_paiements: int = 0


class NotePaiementOut(BaseModel):
    id: UUID
    numero: str
    note_id: UUID
    date_paiement: date
    montant: Decimal
    mode_paiement: str
    reference: str | None
    numero_cheque: str | None
    banque: str | None
    compte: str | None
    observation: str | None
    statut: str
    motif_annulation: str | None
    annule_at: datetime | None
    annule_par_nom: str | None
    created_by_nom: str | None
    updated_by_nom: str | None
    created_at: datetime | None
    updated_at: datetime | None
    registre: NoteRegistreOut


class NotePaiementListOut(BaseModel):
    items: list[NotePaiementOut]
    total: int
    page: int
    size: int
    montant_total: Decimal = Decimal("0")


class NotePayableListOut(BaseModel):
    items: list[NoteRegistreOut]


class CategorieIn(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    libelle: str = Field(min_length=1, max_length=120)
    actif: bool = True
    justificatif_obligatoire: bool = False
    plafond: Decimal | None = None
    sort_order: int = 0


class CategorieUpdate(BaseModel):
    libelle: str | None = None
    actif: bool | None = None
    justificatif_obligatoire: bool | None = None
    plafond: Decimal | None = None
    sort_order: int | None = None


class CategorieOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    libelle: str
    actif: bool
    justificatif_obligatoire: bool
    plafond: Decimal | None
    sort_order: int


class ParametreIn(BaseModel):
    cle: str = Field(min_length=1, max_length=60)
    valeur: str = Field(min_length=1, max_length=255)
    libelle: str | None = None


class ParametreUpdate(BaseModel):
    valeur: str = Field(min_length=1, max_length=255)
    libelle: str | None = None


class ParametreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cle: str
    valeur: str
    libelle: str | None


class DashboardOut(BaseModel):
    total: int
    brouillons: int
    soumises: int
    en_controle: int
    en_visa: int
    validees: int
    a_payer: int
    partiellement_payees: int
    payees: int
    rejetees: int
    montant_total: Decimal
    montant_a_payer: Decimal
    montant_paye: Decimal


class AlerteOut(BaseModel):
    type: str
    titre: str
    message: str
    note_id: UUID
    reference: str
    statut: str
