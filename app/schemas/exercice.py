"""Schémas API — exercices comptables (clôture / ouverture)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class PeriodeAmortissementCategorieRead(BaseModel):
    categorie_id: UUID
    statut: str


class PeriodeAmortissementRead(BaseModel):
    id: UUID
    annee: int
    trimestre: int
    code: str
    date_arrete: date
    statut: str
    calcule_at: datetime | None = None
    valide_at: datetime | None = None
    total_dotation: Decimal = Decimal("0")
    nb_dotations: int = 0
    categories: list[PeriodeAmortissementCategorieRead] = Field(default_factory=list)


class ExerciceRead(BaseModel):
    id: UUID
    annee: int
    statut: str
    archive_dossier_id: UUID | None = None
    cloture_at: datetime | None = None
    ouverture_at: datetime | None = None
    total_valeur_brute: Decimal = Decimal("0")
    total_amortissement: Decimal = Decimal("0")
    total_vnc: Decimal = Decimal("0")
    total_dotation_68: Decimal = Decimal("0")
    nb_immobilisations: int = 0
    message: str | None = None


class ExerciceSituationRead(BaseModel):
    dernier_cloture: int | None = None
    exercice_ouvert: int | None = None
    annee_ouverture_proposee: int | None = None
    peut_ouvrir: bool = False
    exercices: list[ExerciceRead] = Field(default_factory=list)


class ExerciceClotureRequest(BaseModel):
    annee: int = Field(ge=1990, le=2100)


class ExerciceClotureResponse(BaseModel):
    annee: int
    natures_creees: int
    lignes: int
    dossier_id: UUID
    message: str
    annee_ouverture_proposee: int
    total_valeur_brute: Decimal
    total_amortissement: Decimal
    total_vnc: Decimal
    total_dotation_68: Decimal
    nb_immobilisations: int


class ExerciceOuvertureResponse(BaseModel):
    annee_source: int
    annee_ouverture: int
    ouvertures_seed: int
    total_valeur_brute: Decimal
    total_amortissement: Decimal
    total_vnc: Decimal
    message: str
