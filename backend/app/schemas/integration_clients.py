"""Studio d'intégration API (CORE ADMIN) — applications clientes et demandes de droits (Phase 2).

Aucun champ d'authentification : ni clé, ni secret, ni client ID. Les textes libres refusent ce qui
ressemble à un secret, pour éviter qu'un mot de passe ou un jeton soit collé dans une fiche.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.integrations import IntegrationExemple

Environnement = Literal["DEV", "TEST"]
ClientStatut = Literal["brouillon", "en_preparation", "active", "suspendue", "archivee"]
GrantStatut = Literal["demandee", "en_attente", "approuvee", "refusee", "revoquee", "retiree"]

_CONTROLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SECRET_SUSPECT = re.compile(
    r"(?i)\bbearer\s+[a-z0-9._~+/=-]{12,}"
    r"|\b(?:password|passwd|pwd|mot\s+de\s+passe|secret|client[_ -]?secret|api[_ -]?key|token|jeton)\s*[:=]\s*\S+"
    r"|\beyJ[a-z0-9_-]{8,}\.[a-z0-9_-]{8,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
)


def _texte(valeur: str | None, *, multiligne: bool) -> str | None:
    if valeur is None:
        return None
    if not multiligne and ("\n" in valeur or "\r" in valeur):
        raise ValueError("Une seule ligne attendue")
    if _CONTROLE.search(valeur):
        raise ValueError("Caractères de contrôle non autorisés")
    if _SECRET_SUSPECT.search(valeur):
        raise ValueError("Ne saisissez aucun secret (mot de passe, jeton, clé) dans une fiche d'application")
    propre = valeur.strip() if multiligne else " ".join(valeur.split())
    return propre or None


class _Entree(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("nom", "contact_technique", check_fields=False)
    @classmethod
    def _une_ligne(cls, v: str | None) -> str | None:
        return _texte(v, multiligne=False)

    @field_validator("description", "finalite", "notes", check_fields=False)
    @classmethod
    def _multiligne(cls, v: str | None) -> str | None:
        return _texte(v, multiligne=True)


class IntegrationClientCreation(_Entree):
    nom: str = Field(min_length=1, max_length=120)
    description: str | None = Field(None, max_length=2000)
    org_entite_id: uuid.UUID | None = None
    contact_technique: str | None = Field(None, max_length=160)
    environnement: Environnement
    finalite: str | None = Field(None, max_length=2000)
    statut: Literal["brouillon", "en_preparation"] = "brouillon"
    notes: str | None = Field(None, max_length=4000)

    @field_validator("nom")
    @classmethod
    def _nom_requis(cls, v: str | None) -> str:
        if not v:
            raise ValueError("Le nom est obligatoire")
        return v


class IntegrationClientModification(_Entree):
    """Champs absents = inchangés. ``revision`` = version lue (verrou optimiste)."""

    revision: int = Field(ge=1)
    nom: str | None = Field(None, min_length=1, max_length=120)
    description: str | None = Field(None, max_length=2000)
    org_entite_id: uuid.UUID | None = None
    contact_technique: str | None = Field(None, max_length=160)
    environnement: Environnement | None = None
    finalite: str | None = Field(None, max_length=2000)
    statut: Literal["brouillon", "en_preparation", "active", "suspendue"] | None = None
    notes: str | None = Field(None, max_length=4000)


class IntegrationClientArchivage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int = Field(ge=1)
    motif: str = Field(min_length=3, max_length=1000)

    @field_validator("motif")
    @classmethod
    def _motif(cls, v: str) -> str:
        propre = _texte(v, multiligne=True)
        if not propre or len(propre) < 3:
            raise ValueError("Motif obligatoire (3 caractères minimum)")
        return propre


class IntegrationGrantDemande(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_ids: list[str] = Field(min_length=1, max_length=50)
    justification: str | None = Field(None, max_length=1000)

    @field_validator("operation_ids")
    @classmethod
    def _ids(cls, v: list[str]) -> list[str]:
        propres = []
        for op_id in v:
            if not op_id or len(op_id) > 160 or _CONTROLE.search(op_id):
                raise ValueError("Identifiant d'opération invalide")
            if op_id not in propres:
                propres.append(op_id)
        return propres

    @field_validator("justification")
    @classmethod
    def _justification(cls, v: str | None) -> str | None:
        return _texte(v, multiligne=True)


class IntegrationGrantDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statut: Literal["demandee", "en_attente", "approuvee", "refusee", "revoquee", "retiree"]
    motif: str | None = Field(None, max_length=1000)

    @field_validator("motif")
    @classmethod
    def _motif(cls, v: str | None) -> str | None:
        return _texte(v, multiligne=True)


# ----------------------------------------------------------------------------------- réponses
class IntegrationPersonne(BaseModel):
    id: uuid.UUID
    nom: str | None = None


class IntegrationEntite(BaseModel):
    id: uuid.UUID
    code: str | None = None
    libelle: str | None = None
    actif: bool = True


class IntegrationClientResume(BaseModel):
    id: uuid.UUID
    code: str
    nom: str
    description: str | None = None
    entite: IntegrationEntite | None = None
    environnement: Environnement
    statut: ClientStatut
    nb_operations: int = 0
    nb_approuvees: int = 0
    created_at: datetime
    updated_at: datetime
    cree_par: IntegrationPersonne | None = None
    modifie_par: IntegrationPersonne | None = None


class IntegrationClientPage(BaseModel):
    items: list[IntegrationClientResume]
    total: int
    page: int
    size: int
    avertissement: str


class IntegrationClientFiche(IntegrationClientResume):
    contact_technique: str | None = None
    finalite: str | None = None
    notes: str | None = None
    revision: int
    archived_at: datetime | None = None
    archive_par: IntegrationPersonne | None = None
    motif_archivage: str | None = None
    transitions: list[str] = Field(default_factory=list)
    avertissement: str


class IntegrationGrant(BaseModel):
    id: uuid.UUID
    operation_id: str
    methode: str
    chemin: str
    module: str | None = None
    permissions: list[str] = Field(default_factory=list)
    exigence_permissions: str | None = None
    statut: GrantStatut
    justification: str | None = None
    motif: str | None = None
    demande_par: IntegrationPersonne | None = None
    decide_par: IntegrationPersonne | None = None
    decide_le: datetime | None = None
    created_at: datetime
    updated_at: datetime
    catalogue_present: bool
    admissible: bool
    motif_inadmissible: str | None = None


class IntegrationGrantListe(BaseModel):
    items: list[IntegrationGrant]
    compteurs: dict[str, int]
    avertissement: str


class IntegrationGrantEvenement(BaseModel):
    id: uuid.UUID
    grant_id: uuid.UUID
    operation_id: str
    ancien_statut: GrantStatut | None = None
    nouveau_statut: GrantStatut
    motif: str | None = None
    acteur: IntegrationPersonne | None = None
    created_at: datetime


class IntegrationHistorique(BaseModel):
    items: list[IntegrationGrantEvenement]
    total: int
    page: int
    size: int


class IntegrationOperationAdmissible(BaseModel):
    operation_id: str
    nom: str
    methode: str
    chemin: str
    module: str
    module_code: str | None = None
    resume: str | None = None
    permissions: list[str] = Field(default_factory=list)
    exigence_permissions: str | None = None
    authentification: str
    admissible: bool
    motif_inadmissible: str | None = None
    deja_demandee: GrantStatut | None = None


class IntegrationOperationsAdmissibles(BaseModel):
    items: list[IntegrationOperationAdmissible]
    total: int
    page: int
    size: int
    avertissement: str


class IntegrationDocOperation(BaseModel):
    operation_id: str
    methode: str
    chemin: str
    module: str | None = None
    resume: str | None = None
    permissions: list[str] = Field(default_factory=list)
    exigence_permissions: str | None = None
    statut: GrantStatut
    decide_le: datetime | None = None
    prerequis: list[str] = Field(default_factory=list)
    exemples: list[IntegrationExemple] = Field(default_factory=list)
    exemples_motif: str | None = None


class IntegrationDocumentation(BaseModel):
    client_code: str
    nom: str
    environnement: Environnement
    statut: ClientStatut
    genere_le: datetime
    operations: list[IntegrationDocOperation]
    en_attente: int
    avertissements: list[str]
    markdown: str
