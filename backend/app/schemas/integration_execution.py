"""Schémas Phase 5 (destinations, tests) et Phase 6 (supervision). Aucun champ de secret."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.integration_clients import _texte
from app.services.integrations.ssrf import RefusSsrf, normaliser_hote

DestinationStatut = Literal["brouillon", "a_valider", "active", "suspendue", "archivee"]
MethodeTest = Literal["GET", "HEAD"]


class _Entree(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("nom", check_fields=False)
    @classmethod
    def _nom(cls, v: str | None) -> str | None:
        return _texte(v, multiligne=False)

    @field_validator("notes", "motif", check_fields=False)
    @classmethod
    def _notes(cls, v: str | None) -> str | None:
        return _texte(v, multiligne=True)


class DestinationCreation(_Entree):
    nom: str = Field(min_length=1, max_length=120)
    fournisseur_id: uuid.UUID
    hotes: list[str] = Field(min_length=1, max_length=10)
    ports: list[int] = Field(default_factory=lambda: [443], max_length=3)
    methodes: list[MethodeTest] = Field(default_factory=lambda: ["GET", "HEAD"])
    operations: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    notes: str | None = Field(None, max_length=4000)

    @field_validator("hotes")
    @classmethod
    def _hotes(cls, v: list[str]) -> list[str]:
        propres = []
        for h in v:
            try:
                propres.append(normaliser_hote(h))
            except RefusSsrf as exc:
                raise ValueError(exc.message) from exc
        return propres


class DestinationModification(_Entree):
    revision: int = Field(ge=1)
    nom: str | None = Field(None, min_length=1, max_length=120)
    hotes: list[str] | None = Field(None, max_length=10)
    ports: list[int] | None = None
    methodes: list[MethodeTest] | None = None
    operations: list[uuid.UUID] | None = None
    notes: str | None = Field(None, max_length=4000)

    @field_validator("hotes")
    @classmethod
    def _hotes(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        return DestinationCreation._hotes(v)


class DestinationStatutIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    statut: Literal["brouillon", "a_valider", "active", "suspendue"]
    motif: str | None = Field(None, max_length=1000)

    @field_validator("motif")
    @classmethod
    def _motif(cls, v: str | None) -> str | None:
        return _texte(v, multiligne=True)


class DestinationArchivage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    motif: str = Field(min_length=3, max_length=1000)

    @field_validator("motif")
    @classmethod
    def _motif(cls, v: str) -> str:
        propre = _texte(v, multiligne=True)
        if not propre or len(propre) < 3:
            raise ValueError("Motif obligatoire")
        return propre


class ApercuTestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fournisseur_id: uuid.UUID
    operation_id: uuid.UUID
    destination_id: uuid.UUID
    parametres_chemin: dict[str, str] = Field(default_factory=dict)
    parametres_requete: dict[str, str] = Field(default_factory=dict)

    @field_validator("parametres_chemin", "parametres_requete")
    @classmethod
    def _params(cls, v: dict[str, str]) -> dict[str, str]:
        if len(v) > 30:
            raise ValueError("Trop de paramètres")
        for k, val in v.items():
            if len(k) > 100 or len(val) > 200:
                raise ValueError("Paramètre trop long")
            if _texte(val, multiligne=False) is None and val != "":
                raise ValueError("Paramètre invalide")
        return v


class ExecuterTestIn(ApercuTestIn):
    confirmation: Literal[True]


class AlerteStatutIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    statut: Literal["nouvelle", "en_cours", "resolue", "ignoree"]


class DependanceSuppression(BaseModel):
    code: str
    libelle: str
    nombre: int


class BilanSuppression(BaseModel):
    """Ce qui empêche une suppression définitive ; jamais de cascade."""

    supprimable: bool
    conditions: list[str]
    dependances: list[DependanceSuppression]
    alternative: str
    revision: int
