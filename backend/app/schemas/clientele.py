from datetime import date
from typing import Any
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


class LotClasserIn(BaseModel):
    origine: str
    motif: str
    forcer: bool = False


class RapprochementIn(BaseModel):
    import_a_id: UUID
    import_b_id: UUID


class ClassifManuelIn(BaseModel):
    niveau: str
    motif_risque: str | None = None
    motif_classement: str
    racine_client: str | None = None


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


class DeclarationBcmCreerIn(BaseModel):
    annee: int = Field(..., ge=2000, le=2100)
    mois: int = Field(..., ge=1, le=12)


class DeclarationBcmValiderIn(BaseModel):
    commentaire: str | None = None
