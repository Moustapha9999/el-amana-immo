"""Studio d'intégration API (CORE ADMIN) — fournisseurs d'API externes et import OpenAPI (Phase 4).

Configuration seulement : aucun champ de secret, aucune URL appelée. Les textes libres refusent ce qui
ressemble à un secret ; les schémas JSON saisis à la main sont bornés et sans référence ``$ref``.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.integration_clients import IntegrationPersonne, _texte
from app.schemas.integrations import IntegrationExemple
from app.services.integrations import openapi_import as oa

Environnement = Literal["DEV", "TEST"]
FournisseurStatut = Literal["brouillon", "a_valider", "valide", "suspendu", "archive"]
Methode = Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
MecanismeAuth = Literal[
    "aucun", "api_key_header", "api_key_query", "http_basic", "http_bearer", "oauth2_client_credentials",
    "oauth2_autre", "mtls", "autre", "non_precise",
]

_NOM_PARAMETRE = re.compile(r"^[A-Za-z0-9_.\-\[\]]{1,100}$")
_ENTETES_RESERVES = {"authorization", "proxy-authorization", "cookie", "set-cookie", "host", "content-length"}
SCHEMA_MANUEL_MAX = 64 * 1024
SCHEMA_MANUEL_PROFONDEUR = 20


class _Entree(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("nom", "responsable_interne", "contact_technique", check_fields=False)
    @classmethod
    def _une_ligne(cls, v: str | None) -> str | None:
        return _texte(v, multiligne=False)

    @field_validator("description", "documentation", "notes", check_fields=False)
    @classmethod
    def _multiligne(cls, v: str | None) -> str | None:
        return _texte(v, multiligne=True)

    @field_validator("url_base", check_fields=False)
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        propre = _texte(v, multiligne=False)
        return propre if propre is None else verifier_url_base(propre)


def verifier_url_base(url: str) -> str:
    """Forme seulement : l'URL n'est ni résolue ni contactée."""
    from urllib.parse import urlsplit

    if len(url) > 300 or re.search(r"\s", url):
        raise ValueError("URL de base invalide")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise ValueError("URL de base invalide") from exc
    if parts.scheme not in ("https", "http") or not parts.hostname:
        raise ValueError("URL absolue http(s) attendue")
    if parts.username or parts.password or "@" in parts.netloc:
        raise ValueError("Aucun identifiant dans l'URL")
    if parts.query or parts.fragment:
        raise ValueError("Ni paramètre ni fragment dans l'URL de base")
    if port is not None and not 0 < port < 65536:
        raise ValueError("Port invalide")
    return url.rstrip("/")


class FournisseurCreation(_Entree):
    nom: str = Field(min_length=1, max_length=120)
    description: str | None = Field(None, max_length=2000)
    org_entite_id: uuid.UUID | None = None
    responsable_interne: str | None = Field(None, max_length=160)
    contact_technique: str | None = Field(None, max_length=160)
    environnement: Environnement
    url_base: str | None = Field(None, max_length=300)
    documentation: str | None = Field(None, max_length=4000)
    notes: str | None = Field(None, max_length=4000)

    @field_validator("nom")
    @classmethod
    def _nom_requis(cls, v: str | None) -> str:
        if not v:
            raise ValueError("Le nom est obligatoire")
        return v


class FournisseurModification(_Entree):
    """Champs absents = inchangés. ``revision`` = version lue (verrou optimiste)."""

    revision: int = Field(ge=1)
    nom: str | None = Field(None, min_length=1, max_length=120)
    description: str | None = Field(None, max_length=2000)
    org_entite_id: uuid.UUID | None = None
    responsable_interne: str | None = Field(None, max_length=160)
    contact_technique: str | None = Field(None, max_length=160)
    environnement: Environnement | None = None
    url_base: str | None = Field(None, max_length=300)
    documentation: str | None = Field(None, max_length=4000)
    notes: str | None = Field(None, max_length=4000)


class FournisseurChangementStatut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int = Field(ge=1)
    statut: Literal["brouillon", "a_valider", "valide", "suspendu"]
    motif: str | None = Field(None, max_length=1000)

    @field_validator("motif")
    @classmethod
    def _motif(cls, v: str | None) -> str | None:
        return _texte(v, multiligne=True)


class FournisseurArchivage(BaseModel):
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


# --------------------------------------------------------------------------- opérations manuelles


class ParametreManuel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nom: str = Field(min_length=1, max_length=100)
    emplacement: Literal["path", "query"]
    requis: bool = False
    type: Literal["string", "integer", "number", "boolean", "array", "object"] = "string"
    description: str | None = Field(None, max_length=500)

    @field_validator("nom")
    @classmethod
    def _nom(cls, v: str) -> str:
        if not _NOM_PARAMETRE.match(v):
            raise ValueError("Nom de paramètre invalide (lettres, chiffres, _ . - [ ])")
        return v

    @field_validator("description")
    @classmethod
    def _description(cls, v: str | None) -> str | None:
        return _texte(v, multiligne=False)


class EnteteManuel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nom: str = Field(min_length=1, max_length=100)
    requis: bool = False
    description: str | None = Field(None, max_length=500)

    @field_validator("nom")
    @classmethod
    def _nom(cls, v: str) -> str:
        if not oa.NOM_ENTETE.match(v):
            raise ValueError("Nom d'en-tête invalide")
        if v.lower() in _ENTETES_RESERVES:
            raise ValueError("En-tête réservé : déclarer l'authentification avec le mécanisme dédié")
        return v

    @field_validator("description")
    @classmethod
    def _description(cls, v: str | None) -> str | None:
        return _texte(v, multiligne=False)


def verifier_schema_manuel(schema: dict[str, Any] | None) -> dict[str, Any] | None:
    if schema is None:
        return None
    if len(json.dumps(schema, ensure_ascii=False)) > SCHEMA_MANUEL_MAX:
        raise ValueError("Schéma trop volumineux (64 Ko maximum)")
    pile: list[tuple[Any, int]] = [(schema, 1)]
    while pile:
        noeud, profondeur = pile.pop()
        if profondeur > SCHEMA_MANUEL_PROFONDEUR:
            raise ValueError("Schéma trop profond")
        if isinstance(noeud, dict):
            if "$ref" in noeud:
                raise ValueError("Références $ref non prises en charge dans une configuration manuelle")
            pile.extend((v, profondeur + 1) for v in noeud.values())
        elif isinstance(noeud, list):
            pile.extend((v, profondeur + 1) for v in noeud)
        elif isinstance(noeud, float) and noeud != noeud:
            raise ValueError("Valeur numérique invalide")
    if "type" in schema and schema["type"] not in ("object", "array", "string", "integer", "number", "boolean"):
        raise ValueError("Type de schéma non pris en charge")
    controle = oa.Analyse(nom_fichier="manuel", taille=0, empreinte="")
    oa.assainir(json.loads(json.dumps(schema)), controle)
    if controle.erreurs or controle.avertissements:
        raise ValueError("Le schéma contient une valeur sensible : utiliser un espace réservé (<valeur>)")
    return schema


class OperationManuelle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nom: str = Field(min_length=1, max_length=200)
    description: str | None = Field(None, max_length=4000)
    methode: Methode
    chemin: str = Field(min_length=1, max_length=300)
    parametres: list[ParametreManuel] = Field(default_factory=list, max_length=50)
    entetes: list[EnteteManuel] = Field(default_factory=list, max_length=30)
    corps_schema: dict[str, Any] | None = None
    reponse_schema: dict[str, Any] | None = None
    mecanisme_auth: MecanismeAuth = "non_precise"
    nom_cle_api: str | None = Field(None, max_length=100)
    codes_reponse: list[int] = Field(default_factory=lambda: [200], min_length=1, max_length=20)
    notes: str | None = Field(None, max_length=4000)

    @field_validator("nom")
    @classmethod
    def _nom(cls, v: str) -> str:
        propre = _texte(v, multiligne=False)
        if not propre:
            raise ValueError("Le nom est obligatoire")
        return propre

    @field_validator("description", "notes")
    @classmethod
    def _multiligne(cls, v: str | None) -> str | None:
        return _texte(v, multiligne=True)

    @field_validator("chemin")
    @classmethod
    def _chemin(cls, v: str) -> str:
        if not oa.CHEMIN_VALIDE.match(v) or "//" in v or "/../" in v + "/" or "/./" in v + "/":
            raise ValueError("Chemin relatif invalide (commence par /, sans espace, ?, # ni ..)")
        return v

    @field_validator("corps_schema", "reponse_schema")
    @classmethod
    def _schema(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return verifier_schema_manuel(v)

    @field_validator("codes_reponse")
    @classmethod
    def _codes(cls, v: list[int]) -> list[int]:
        if any(not 100 <= c <= 599 for c in v):
            raise ValueError("Codes HTTP entre 100 et 599")
        return sorted(set(v))

    @model_validator(mode="after")
    def _coherence(self) -> OperationManuelle:
        places = set(oa.PLACEHOLDER.findall(self.chemin))
        declares = [p.nom for p in self.parametres if p.emplacement == "path"]
        if places != set(declares) or len(declares) != len(set(declares)):
            raise ValueError("Chaque {paramètre} du chemin doit être déclaré une fois, en emplacement « path »")
        noms = [(p.nom, p.emplacement) for p in self.parametres]
        if len(noms) != len(set(noms)):
            raise ValueError("Paramètre déclaré deux fois")
        if len({e.nom.lower() for e in self.entetes}) != len(self.entetes):
            raise ValueError("En-tête déclaré deux fois")
        if self.mecanisme_auth.startswith("api_key"):
            if not self.nom_cle_api or not oa.NOM_ENTETE.match(self.nom_cle_api):
                raise ValueError("Nom de l'en-tête ou du paramètre de la clé d'API requis")
        elif self.nom_cle_api:
            raise ValueError("Nom de clé d'API réservé aux mécanismes « clé d'API »")
        if self.corps_schema is not None and self.methode in ("GET", "HEAD", "DELETE", "OPTIONS"):
            raise ValueError("Corps de requête non attendu pour cette méthode")
        return self


class OperationManuelleModification(OperationManuelle):
    revision: int = Field(ge=1)


class OperationArchivage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int = Field(ge=1)


# ----------------------------------------------------------------------------------- réponses


class FournisseurEntite(BaseModel):
    id: uuid.UUID
    code: str | None = None
    libelle: str | None = None
    actif: bool = True


class FournisseurResume(BaseModel):
    id: uuid.UUID
    code: str
    nom: str
    description: str | None = None
    entite: FournisseurEntite | None = None
    environnement: Environnement
    statut: FournisseurStatut
    url_base: str | None = None
    version_courante: int | None = None
    nb_operations: int = 0
    created_at: datetime
    updated_at: datetime
    cree_par: IntegrationPersonne | None = None
    modifie_par: IntegrationPersonne | None = None


class FournisseurPage(BaseModel):
    items: list[FournisseurResume]
    total: int
    page: int
    size: int
    avertissement: str


class FournisseurFiche(FournisseurResume):
    responsable_interne: str | None = None
    contact_technique: str | None = None
    documentation: str | None = None
    notes: str | None = None
    motif_statut: str | None = None
    revision: int
    valide_par: IntegrationPersonne | None = None
    valide_le: datetime | None = None
    archived_at: datetime | None = None
    archive_par: IntegrationPersonne | None = None
    motif_archivage: str | None = None
    modifiable: bool
    transitions: list[str] = Field(default_factory=list)
    avertissement: str


class MessageAnalyse(BaseModel):
    niveau: Literal["erreur", "avertissement"]
    code: str
    message: str
    emplacement: str | None = None


class OperationApercu(BaseModel):
    cle: str
    methode: str
    chemin: str
    operation_id: str | None = None
    nom: str | None = None
    deprecie: bool = False


class DiffVersion(BaseModel):
    ajoutees: list[str] = Field(default_factory=list)
    supprimees: list[str] = Field(default_factory=list)
    modifiees: list[str] = Field(default_factory=list)
    inchangees: int = 0


class AnalyseSpec(BaseModel):
    valide: bool
    nom_fichier: str
    taille: int
    empreinte: str
    format: str | None = None
    openapi_version: str | None = None
    titre: str | None = None
    version_api: str | None = None
    serveurs: list[dict] = Field(default_factory=list)
    securite: list[dict] = Field(default_factory=list)
    nb_operations: int = 0
    operations: list[OperationApercu] = Field(default_factory=list)
    erreurs: list[MessageAnalyse] = Field(default_factory=list)
    avertissements: list[MessageAnalyse] = Field(default_factory=list)
    version_courante: int | None = None
    deja_importee: int | None = None
    diff: DiffVersion | None = None
    conflits: list[str] = Field(default_factory=list)
    avertissement: str


class SpecResume(BaseModel):
    id: uuid.UUID
    numero: int
    courante: bool
    format: str
    nom_fichier: str
    taille: int
    empreinte: str
    openapi_version: str
    titre: str
    version_api: str
    nb_operations: int
    nb_avertissements: int
    importe_par: IntegrationPersonne | None = None
    created_at: datetime


class SpecListe(BaseModel):
    items: list[SpecResume]
    avertissement: str


class SpecDetail(SpecResume):
    serveurs: list[dict] = Field(default_factory=list)
    securite: list[dict] = Field(default_factory=list)
    description: str | None = None
    avertissements: list[MessageAnalyse] = Field(default_factory=list)
    avertissement: str


class OperationResume(BaseModel):
    id: uuid.UUID
    origine: Literal["openapi", "manuelle"]
    statut: Literal["active", "archivee"]
    methode: str
    chemin: str
    operation_id: str | None = None
    nom: str | None = None
    tags: list[str] = Field(default_factory=list)
    deprecie: bool = False
    spec_numero: int | None = None
    conflit: bool = False
    updated_at: datetime


class OperationListe(BaseModel):
    items: list[OperationResume]
    total: int
    page: int
    size: int
    version_courante: int | None = None
    avertissement: str


class OperationDetail(OperationResume):
    description: str | None = None
    parametres: list[dict] = Field(default_factory=list)
    entetes: list[dict] = Field(default_factory=list)
    corps: dict | None = None
    reponses: list[dict] = Field(default_factory=list)
    authentification: list[dict] = Field(default_factory=list)
    mecanismes: list[dict] = Field(default_factory=list)
    configuration: dict | None = None
    notes: str | None = None
    revision: int
    source: str
    avertissements: list[str] = Field(default_factory=list)
    elements_declares: list[str] = Field(default_factory=list)
    elements_verifies: list[str] = Field(default_factory=list)
    exemples: list[IntegrationExemple] = Field(default_factory=list)
    cree_par: IntegrationPersonne | None = None
    modifie_par: IntegrationPersonne | None = None
    created_at: datetime


class EvenementFournisseur(BaseModel):
    id: uuid.UUID
    action: str
    libelle: str
    acteur: IntegrationPersonne | None = None
    details: dict = Field(default_factory=dict)
    request_id: str | None = None
    created_at: datetime


class HistoriqueFournisseur(BaseModel):
    items: list[EvenementFournisseur]
    total: int
    page: int
    size: int
