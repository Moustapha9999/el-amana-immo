from datetime import date
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ImportConfirmIn(BaseModel):
    date_extraction: date | None = None
    forcer: bool = False


class ImportMappingIn(BaseModel):
    mapping: dict[str, str] = Field(default_factory=dict)


class LotMappingIn(BaseModel):
    type: str | None = None
    colonne_racine: str | None = None
    colonne_niveau: str | None = None
    colonne_motif: str | None = None
    colonne_entreprise_recente: str | None = None
    colonne_date_ouverture: str | None = None
    colonne_date_maj: str | None = None
    colonne_analyste: str | None = None
    periode_reference: date | None = None


class LotMajIn(BaseModel):
    fichier_nom: str | None = Field(None, max_length=255)
    periode_reference: date | None = None


class LotClasserIn(BaseModel):
    origine: str
    motif: str
    forcer: bool = False
    confirmation: bool = False


class LotDateOuvertureIn(BaseModel):
    ligne: int
    date_ouverture: str | None = None


class LotDecisionLigneIn(BaseModel):
    ligne: int
    choix: str
    niveau: str | None = None
    motif: str


class LotDivergencesIn(BaseModel):
    decisions: list[LotDecisionLigneIn] = Field(default_factory=list)
    forcer: bool = False
    confirmation: bool = False


class LotControleDecisionIn(BaseModel):
    ligne: int
    choix: Literal["MOTEUR", "FICHIER"]
    justification: str | None = Field(None, max_length=2000)
    forcer: bool = False
    confirmation: bool = False


class LotLignesDecisionIn(BaseModel):
    lignes: list[int] = Field(..., max_length=5000)
    decision: Literal["ACCEPTER", "MODIFIER", "REJETER"]
    niveau: str | None = Field(None, max_length=10)
    motif: str | None = Field(None, max_length=2000)
    analyste_kyc: str | None = Field(None, max_length=120)
    forcer: bool = False
    confirmation: bool = False


class ClassifMoteurScoringIn(BaseModel):
    motif: str
    analyste_kyc: str | None = Field(None, max_length=120)
    forcer: bool = False
    confirmation: bool = False


class ClassifMasseIn(BaseModel):
    motif: str
    profil: str | None = None
    code_agence: str | None = None
    apres: str | None = None
    taille: int | None = None


class ClassifTacheIn(BaseModel):
    motif: str
    population: str = "TOUS"
    code_agence: str | None = None


class ReexamenTraiterIn(BaseModel):
    decision: str
    niveau: str | None = None
    forcer: bool = False
    confirmation: bool = False


class DivergenceArbitrerIn(BaseModel):
    statut: str
    decision: str | None = None
    justification: str


class RapprochementIn(BaseModel):
    import_a_id: UUID
    import_b_id: UUID


class ClassifManuelIn(BaseModel):
    niveau: str
    motif_risque: str | None = None
    motif_classement: str
    analyste_kyc: str | None = Field(None, max_length=120)
    racine_client: str | None = None
    forcer: bool = False
    confirmation: bool = False


class ClassifMoteurIn(BaseModel):
    racine: str | None = None
    forcer: bool = False


class ClassifEvaluerIn(BaseModel):
    racine: str
    persister: bool = True


class ClassifBacktestIn(BaseModel):
    limite: int = 50


class ClassifExcelIn(BaseModel):
    lignes: list[dict[str, Any]] = Field(default_factory=list)


class ClassifRegleIn(BaseModel):
    critere_id: UUID
    niveau_cible: str
    operateur: str
    champ_source: str
    portee: str | None = None
    valeur: Any = None
    motif: str
    priorite: int = 100
    poids: int = 0
    actif: bool = True


class ClassifVersionIn(BaseModel):
    libelle: str | None = None
    mode: str | None = None
    seuils: dict | None = None
    date_effet: date | None = None
    copier_version_id: UUID | None = None


class FiltrageEntreeIn(BaseModel):
    nom: str | None = None
    prenom: str | None = None
    raison_sociale: str | None = None
    date_naissance: date | None = None
    nationalite: str | None = None
    identifiant: str | None = None
    type_identifiant: str | None = None


class AlerteDecisionIn(BaseModel):
    statut: str
    commentaire: str | None = None


class AlerteAttribuerIn(BaseModel):
    assignee_id: UUID | None = None
    commentaire: str | None = Field(None, max_length=2000)


class AlerteCommentaireIn(BaseModel):
    commentaire: str = Field(..., min_length=1, max_length=2000)


class DeclarationBcmCreerIn(BaseModel):
    annee: int = Field(..., ge=2000, le=2100)
    mois: int = Field(..., ge=1, le=12)


class DeclarationBcmMotifIn(BaseModel):
    motif: str


class DeclarationBcmValiderIn(BaseModel):
    commentaire: str | None = None
