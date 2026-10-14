"""Schémas du référentiel organisationnel central (CORE ADMIN + API partagée des modules)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

TypeEntite = Literal[
    "CONSEIL", "COMITE", "DIRECTION_GENERALE", "DIRECTION", "DEPARTEMENT", "SERVICE", "SECTION", "CELLULE"
]
TypeAffectation = Literal["PRINCIPALE", "SECONDAIRE", "INTERIM"]
Perimetre = Literal["PERSONNEL", "ENTITE", "ENTITE_ET_SOUS_ENTITES"]


class EntiteCreate(BaseModel):
    type_entite: TypeEntite
    libelle: str = Field(min_length=1, max_length=255)
    code: str | None = Field(default=None, max_length=20)
    sigle: str | None = Field(default=None, max_length=40)
    parent_id: uuid.UUID | None = None
    description: str | None = Field(default=None, max_length=4000)
    ordre: int | None = Field(default=None, ge=0, le=100000)
    alias: list[str] | None = Field(default=None, max_length=50)
    a_confirmer: bool = False
    note_confirmation: str | None = Field(default=None, max_length=2000)


class EntitePatch(BaseModel):
    type_entite: TypeEntite | None = None
    libelle: str | None = Field(default=None, max_length=255)
    code: str | None = Field(default=None, max_length=20)
    sigle: str | None = Field(default=None, max_length=40)
    parent_id: uuid.UUID | None = None
    detacher_parent: bool = False
    description: str | None = Field(default=None, max_length=4000)
    ordre: int | None = Field(default=None, ge=0, le=100000)
    alias: list[str] | None = Field(default=None, max_length=50)
    a_confirmer: bool | None = None
    note_confirmation: str | None = Field(default=None, max_length=2000)


class EntiteStatut(BaseModel):
    motif: str | None = Field(default=None, max_length=1000)


class PosteCreate(BaseModel):
    intitule: str = Field(min_length=1, max_length=200)
    est_responsable: bool = False
    effectif_prevu: int | None = Field(default=None, ge=1, le=10000)
    titulaire_user_id: uuid.UUID | None = None
    a_confirmer: bool = False
    note_confirmation: str | None = Field(default=None, max_length=2000)


class PostePatch(BaseModel):
    intitule: str | None = Field(default=None, max_length=200)
    est_responsable: bool | None = None
    effectif_prevu: int | None = Field(default=None, ge=0, le=10000)
    titulaire_user_id: uuid.UUID | None = None
    retirer_titulaire: bool = False
    actif: bool | None = None
    a_confirmer: bool | None = None
    note_confirmation: str | None = Field(default=None, max_length=2000)
    ordre: int | None = Field(default=None, ge=0, le=100000)


class AffectationCreate(BaseModel):
    user_id: uuid.UUID
    entite_id: uuid.UUID
    poste_id: uuid.UUID | None = None
    type_affectation: TypeAffectation = "PRINCIPALE"
    perimetre: Perimetre = "PERSONNEL"
    date_debut: date | None = None
    commentaire: str | None = Field(default=None, max_length=1000)


class AffectationPatch(BaseModel):
    perimetre: Perimetre | None = None
    poste_id: uuid.UUID | None = None
    retirer_poste: bool = False
    commentaire: str | None = Field(default=None, max_length=1000)


class AffectationCloture(BaseModel):
    date_fin: date | None = None


class CorrespondanceApply(BaseModel):
    liaison: str = Field(min_length=1, max_length=60)
    valeur: str = Field(min_length=1, max_length=255)
    entite_id: uuid.UUID
    memoriser_alias: bool = True


class AgenceRattachement(BaseModel):
    org_entite_id: uuid.UUID | None = None
