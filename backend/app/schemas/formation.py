"""Formation & Sensibilisation — schémas d'entrée (les sorties sont des dictionnaires de service)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

Domaine = Literal["THEME", "FORMATEUR", "LIEU", "FONCTION", "PERIMETRE"]


class ReferentielCreate(BaseModel):
    domaine: Domaine
    libelle: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class ReferentielPatch(BaseModel):
    libelle: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    actif: bool | None = None
    ordre: int | None = None


class ReferentielFusion(BaseModel):
    source_id: uuid.UUID
    cible_id: uuid.UUID


class EntiteIn(BaseModel):
    libelle: str | None = Field(default=None, max_length=200)
    perimetre_id: uuid.UUID | None = None
    lieu_id: uuid.UUID | None = None
    agence_id: uuid.UUID | None = None
    actif: bool | None = None


class EmployeIn(BaseModel):
    nom: str | None = Field(default=None, max_length=120)
    prenom: str | None = Field(default=None, max_length=120)
    fonction_id: uuid.UUID | None = None
    entite_id: uuid.UUID | None = None
    email: str | None = Field(default=None, max_length=255)
    telephone: str | None = Field(default=None, max_length=40)


class ActivationIn(BaseModel):
    actif: bool
    motif: str | None = Field(default=None, max_length=1000)


class SessionCreate(BaseModel):
    date_session: date
    theme_ids: list[uuid.UUID] = Field(min_length=1)
    lieu_id: uuid.UUID
    formateur_ids: list[uuid.UUID] = Field(min_length=1)
    employe_ids: list[uuid.UUID] = Field(default_factory=list)
    intitule: str | None = Field(default=None, max_length=255)
    observations: str | None = Field(default=None, max_length=4000)


class SessionPatch(BaseModel):
    revision: int
    date_session: date | None = None
    theme_ids: list[uuid.UUID] | None = None
    lieu_id: uuid.UUID | None = None
    formateur_ids: list[uuid.UUID] | None = None
    employe_ids: list[uuid.UUID] | None = None
    intitule: str | None = Field(default=None, max_length=255)
    observations: str | None = Field(default=None, max_length=4000)
    motif: str | None = Field(default=None, max_length=1000)


class ParticipantsIn(BaseModel):
    revision: int
    employe_ids: list[uuid.UUID] = Field(min_length=1)


class RetraitIn(BaseModel):
    revision: int
    motif: str | None = Field(default=None, max_length=1000)


class PresencesIn(BaseModel):
    revision: int
    presences: dict[str, Literal["PRESENT", "ABSENT"] | None]
    motif: str | None = Field(default=None, max_length=1000)


class StatutIn(BaseModel):
    revision: int
    action: Literal["cloturer", "rouvrir", "annuler", "retablir", "archiver", "desarchiver"]
    motif: str | None = Field(default=None, max_length=1000)


class SuppressionIn(BaseModel):
    motif: str = Field(min_length=3, max_length=1000)


class SuppressionMultipleIn(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=200)
    motif: str = Field(min_length=3, max_length=1000)


class ImportConfirmIn(BaseModel):
    decisions: dict[str, dict[str, dict[str, Any]]] = Field(default_factory=dict)
    personnes: dict[str, dict[str, Any]] = Field(default_factory=dict)
    verification_noms: bool = False
    forcer: bool = False
