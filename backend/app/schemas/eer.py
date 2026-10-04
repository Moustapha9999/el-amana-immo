"""Schémas API EER (Gestion des Entrées en Relation) — jamais de modèle SQLAlchemy exposé."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Orm(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class _Mutation(BaseModel):
    """Toute mutation porte la révision connue du client (concurrence optimiste → 409)."""

    revision: int = Field(ge=0)


# --- Périmètre ------------------------------------------------------------------------------

class EerPerimetreOut(BaseModel):
    user_id: str
    agence_id: str | None
    perimetre: Literal["TOUTES_AGENCES", "AGENCE", "AUCUN"]
    roles: list[str]
    permissions: list[str]
    capacites: dict[str, bool]


class EerAgenceOut(BaseModel):
    id: uuid.UUID
    code: str
    libelle: str


class EerReferentielOut(BaseModel):
    domaine: str
    code: str
    libelle: str
    parent_code: str | None = None
    ordre: int
    meta: dict[str, Any]


class EerAnalysteOut(BaseModel):
    id: uuid.UUID
    nom: str


# --- Dossiers -------------------------------------------------------------------------------

class EerPieceIn(BaseModel):
    type: str = Field(min_length=1, max_length=40)
    numero: str = Field(min_length=1, max_length=60)
    date_delivrance: date | None = None
    date_expiration: date | None = None
    pays_emission: str | None = None


class EerPartieIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nom: str = Field(min_length=1, max_length=255)
    nationalite: str | None = None
    pays_residence: str | None = None
    adresse: str | None = None
    telephone_1: str | None = None
    telephone_2: str | None = None
    telephone_3: str | None = None
    email: str | None = None
    racine_client: str | None = None
    piece: EerPieceIn | None = None
    pp: dict[str, Any] | None = None
    pm: dict[str, Any] | None = None


class EerDossierCreate(BaseModel):
    agence_id: uuid.UUID
    type_client: str
    profil: str
    operation_type: Literal["ENTREE_RELATION", "MISE_A_JOUR"] = "ENTREE_RELATION"
    client: EerPartieIn
    client_role: dict[str, Any] = Field(default_factory=dict)
    dossier: dict[str, Any] = Field(default_factory=dict)


class EerChampIn(BaseModel):
    chemin: str = Field(min_length=3, max_length=120)
    valeur: Any = None
    dossier_partie_id: uuid.UUID | None = None


class EerDossierPatch(_Mutation):
    """Saisie unique : chaque champ est écrit dans sa donnée source (la fiche n'est qu'une vue)."""

    champs: list[EerChampIn] = Field(min_length=1, max_length=200)


class EerPartieAjout(_Mutation):
    role: str
    nature: Literal["PHYSIQUE", "MORALE"] = "PHYSIQUE"
    partie: EerPartieIn | None = None
    partie_id: uuid.UUID | None = None
    role_attrs: dict[str, Any] = Field(default_factory=dict)


class EerDetentionIn(_Mutation):
    detenteur_partie_id: uuid.UUID
    detenue_partie_id: uuid.UUID
    pourcentage: Decimal | None = Field(default=None, ge=0, le=100)
    lien: str | None = None


class EerActionIn(_Mutation):
    motif: str | None = Field(default=None, max_length=4000)


class EerAssignIn(_Mutation):
    analyste_id: uuid.UUID


class EerCiblesIn(BaseModel):
    item_ids: list[uuid.UUID] = Field(default_factory=list)
    anomalie_ids: list[uuid.UUID] = Field(default_factory=list)
    champs: list[str] = Field(default_factory=list)


class EerComplementIn(_Mutation):
    consigne: str = Field(min_length=1, max_length=4000)
    echeance: date | None = None
    cibles: EerCiblesIn


class EerComplementFourniIn(_Mutation):
    item_id: uuid.UUID
    document_id: uuid.UUID | None = None


class EerAvisIn(_Mutation):
    favorable: bool
    commentaire: str | None = Field(default=None, max_length=4000)
    cibles: EerCiblesIn | None = None
    fonction: str = Field(default="Service Conformité KYC", max_length=120)


class EerDecisionIn(_Mutation):
    """Décision de l'analyste : doit être égale à la décision calculée (sinon refus motivé)."""

    resultat: Literal["CONFORME", "NON_CONFORME"]
    motif: str | None = None


class EerDossierLigne(BaseModel):
    id: uuid.UUID
    reference: str
    statut: str
    etape: str | None
    operation_type: str
    agence_id: uuid.UUID
    agence_code: str
    agence_libelle: str
    type_client: str
    profil: str
    client_nom: str
    racine_client: str | None
    risque: str | None
    decision: str | None
    avis_requis: bool
    analyste_id: uuid.UUID | None
    analyste_nom: str | None
    version_courante: int
    revision: int
    date_eer: date
    soumis_le: datetime | None
    valide_le: datetime | None
    created_at: datetime
    updated_at: datetime


class EerDossierPage(BaseModel):
    items: list[EerDossierLigne]
    total: int
    page: int
    size: int


class EerPartieOut(BaseModel):
    dossier_partie_id: uuid.UUID
    partie_id: uuid.UUID
    role: str
    nature: str
    nom: str
    ordre: int
    ppe: bool | None = None
    fatca_indice: bool | None = None
    risque_lbcft: str | None = None
    be_source: str | None = None
    be_pourcentage_calcule: Decimal | None = None


class EerDossierOut(BaseModel):
    id: uuid.UUID
    reference: str
    statut: str
    etape: str | None
    operation_type: str
    agence_id: uuid.UUID
    type_client: str
    profil: str
    sous_profil: str | None
    risque: str | None
    ppe: bool
    fatca: bool
    avis_requis: bool
    conformite_physique: str | None
    conformite_systeme: str | None
    conformite_coherence: str | None
    decision: str | None
    version_courante: int
    revision: int
    nb_relances: int
    motif_abandon: str | None
    parametres_snapshot: dict[str, Any]
    created_by_id: uuid.UUID
    analyste_id: uuid.UUID | None
    controleur_id: uuid.UUID | None
    date_eer: date
    soumis_le: datetime | None
    valide_le: datetime | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    parties: list[EerPartieOut]
    transitions_possibles: list[str] = Field(default_factory=list)


# --- Checklist ------------------------------------------------------------------------------

class EerChecklistItemOut(_Orm):
    id: uuid.UUID
    regle_code: str
    regle_version: int
    dossier_partie_id: uuid.UUID | None
    libelle: str
    categorie: str
    axe: str
    nature: str
    obligatoire: bool
    ordre: int
    statut: str
    presence: str | None
    motif: str | None
    motif_code: str | None
    neutralise_auto: bool
    derogation_acceptee: bool
    raison_applicabilite: list[Any]
    document_id: uuid.UUID | None
    pointe_par_id: uuid.UUID | None
    pointe_le: datetime | None
    controle_par_id: uuid.UUID | None
    controle_le: datetime | None
    donnee_connue: bool | None = None


class EerChecklistOut(BaseModel):
    dossier_id: uuid.UUID
    etape: str | None
    revision: int
    items: list[EerChecklistItemOut]
    non_pointes: int


class EerPointageIn(_Mutation):
    presence: Literal["PRESENT", "ABSENT", "SANS_OBJET"]
    motif: str | None = None
    document_id: uuid.UUID | None = None


class EerControleManuelIn(_Mutation):
    conforme: bool
    motif: str | None = None
    motif_code: str | None = Field(default=None, max_length=40)


# --- Contrôles / décisions ------------------------------------------------------------------

class EerControleOut(_Orm):
    id: uuid.UUID
    item_id: uuid.UUID | None
    code: str
    type_controle: str
    resultat: str
    detail: dict[str, Any]
    version: int
    execute_par_id: uuid.UUID | None
    execute_le: datetime


class EerConstatOut(BaseModel):
    code: str
    type_controle: str
    resultat: str
    message: str
    item_id: str | None
    detail: dict[str, Any]


class EerControlesAutoOut(BaseModel):
    revision: int
    constats: list[EerConstatOut]


class EerDecisionOut(_Orm):
    id: uuid.UUID
    version: int
    resultat: str
    conformite_physique: str
    conformite_systeme: str
    conformite_coherence: str
    explication: list[Any]
    decide_par_id: uuid.UUID | None
    decide_le: datetime


# --- Anomalies ------------------------------------------------------------------------------

class EerAnomalieOut(_Orm):
    id: uuid.UUID
    item_id: uuid.UUID | None
    dossier_partie_id: uuid.UUID | None
    champ: str | None
    type_code: str
    gravite: str
    description: str
    observation: str | None
    action_attendue: str | None
    statut: str
    justification: str | None
    echeance_regularisation: date | None
    version_detection: int
    version_resolution: int | None
    created_by_id: uuid.UUID | None
    resolved_by_id: uuid.UUID | None
    resolved_at: datetime | None
    created_at: datetime


class EerAnomalieCreate(_Mutation):
    type_code: str = Field(min_length=1, max_length=60)
    gravite: Literal["BLOQUANTE", "MAJEURE", "MINEURE"]
    description: str = Field(min_length=1, max_length=4000)
    item_id: uuid.UUID | None = None
    champ: str | None = Field(default=None, max_length=120)
    observation: str | None = None
    action_attendue: str | None = None


class EerAnomaliePatch(_Mutation):
    gravite: Literal["BLOQUANTE", "MAJEURE", "MINEURE"] | None = None
    observation: str | None = None
    action_attendue: str | None = None
    annuler_motif: str | None = None
    accepter_justification: str | None = None


# --- Compléments ----------------------------------------------------------------------------

class EerComplementElementOut(_Orm):
    id: uuid.UUID
    item_id: uuid.UUID | None
    anomalie_id: uuid.UUID | None
    champ: str | None
    fourni: bool


class EerComplementOut(_Orm):
    id: uuid.UUID
    numero: int
    origine: str
    consigne: str | None
    echeance: date | None
    statut: str
    version_demande: int
    demande_par_id: uuid.UUID | None
    recu_par_id: uuid.UUID | None
    recu_le: datetime | None
    created_at: datetime
    elements: list[EerComplementElementOut]


# --- Avis, versions, historique, documents --------------------------------------------------

class EerVisaOut(_Orm):
    id: uuid.UUID
    user_id: uuid.UUID
    fonction: str
    avis: str
    commentaire: str | None
    version: int
    vise_le: datetime


class EerVersionLigne(_Orm):
    id: uuid.UUID
    numero: int
    evenement: str
    empreinte: str
    cree_par_id: uuid.UUID | None
    cree_le: datetime


class EerVersionOut(EerVersionLigne):
    contenu: dict[str, Any]
    empreinte_verifiee: bool


class EerHistoriqueOut(_Orm):
    id: uuid.UUID
    action: str
    de_statut: str | None
    vers_statut: str | None
    etape: str | None
    version: int
    motif: str | None
    details: dict[str, Any]
    acteur_id: uuid.UUID | None
    cree_le: datetime


class EerDocumentOut(_Orm):
    id: uuid.UUID
    filename: str
    title: str | None
    doc_type: str | None
    mime_type: str | None
    size_bytes: int
    version: int
    uploaded_by_id: uuid.UUID | None
    created_at: datetime


class EerAuditOut(BaseModel):
    id: uuid.UUID
    action: str
    user_id: uuid.UUID | None
    created_at: datetime
    after: dict[str, Any] | None = None


class EerFicheChampOut(BaseModel):
    chemin: str
    libelle: str
    section: str | None = None
    obligatoire: bool
    etat: str
    valeur: Any = None
    bloquant: bool


class EerTableauDeBordOut(BaseModel):
    total: int
    en_cours: int
    brouillons: int
    a_affecter: int
    affectes: int
    en_controle: int
    non_conformes: int
    a_completer: int
    conformes: int
    avis_en_attente: int
    valides: int
    abandonnes: int
    delai_moyen_jours: float | None
    par_statut: dict[str, int]
    par_agence: list[dict[str, Any]]
    par_profil: list[dict[str, Any]]
    par_type_client: list[dict[str, Any]]
    par_risque: list[dict[str, Any]]


class EerConfirmIn(_Mutation):
    chemin: str = Field(min_length=3, max_length=120)
    dossier_partie_id: uuid.UUID | None = None


class EerControlesOut(BaseModel):
    controles: list[EerControleOut]
    decisions: list[EerDecisionOut]


class EerBeneficiaireOut(BaseModel):
    partie_id: str
    pourcentage: str | None = None


class EerBeneficiairesOut(BaseModel):
    seuil: str
    complet: bool
    aucun_be_au_seuil: bool
    beneficiaires: list[EerBeneficiaireOut]
    a_verifier: list[EerBeneficiaireOut]
    problemes: list[dict[str, str]]


class EerMutationOut(BaseModel):
    id: uuid.UUID
    statut: str
    etape: str | None
    revision: int
    version_courante: int
    message: str
