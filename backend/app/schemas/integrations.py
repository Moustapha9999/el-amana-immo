"""Studio d'intégration API (CORE ADMIN) — catalogue et console en lecture seule."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class IntegrationParametre(BaseModel):
    nom: str
    emplacement: str
    requis: bool
    type: str
    description: str | None = None
    defaut: str | int | float | bool | None = None
    valeurs: list[str] = Field(default_factory=list)


class IntegrationChamp(BaseModel):
    nom: str
    type: str
    requis: bool
    description: str | None = None


class IntegrationCorps(BaseModel):
    type_contenu: str
    requis: bool
    schema_nom: str | None = None
    champs: list[IntegrationChamp] = Field(default_factory=list)


class IntegrationReponse(BaseModel):
    code: str
    description: str | None = None
    schema_nom: str | None = None
    champs: list[IntegrationChamp] = Field(default_factory=list)


class IntegrationOperationResume(BaseModel):
    operation_id: str
    nom: str
    methode: str
    chemin: str
    module: str
    module_code: str | None = None
    module_etat: str
    authentification: str
    permissions: list[str] = Field(default_factory=list)
    exigence_permissions: str | None = None
    permission_statut: str
    schema_reponse_statut: str
    disponibilite: str
    categorie_exclusion: str | None = None
    motifs: list[str] = Field(default_factory=list)
    exemples_disponibles: bool
    console: bool
    console_motif: str | None = None


class IntegrationOperationFiche(IntegrationOperationResume):
    resume: str | None = None
    description: str | None = None
    dans_openapi: bool
    dependances_non_analysees: list[str] = Field(default_factory=list)
    parametres: list[IntegrationParametre] = Field(default_factory=list)
    corps: IntegrationCorps | None = None
    reponses: list[IntegrationReponse] = Field(default_factory=list)
    avertissement: str


class IntegrationCatalogueKpis(BaseModel):
    total: int
    documentees: int
    restreintes: int
    exclues: int
    console: int
    par_methode: dict[str, int]
    par_authentification: dict[str, int]
    par_permission_statut: dict[str, int]
    par_schema_reponse: dict[str, int]


class IntegrationCatalogueFiltres(BaseModel):
    modules: list[str]
    methodes: list[str]
    authentifications: list[str]


class IntegrationCataloguePage(BaseModel):
    items: list[IntegrationOperationResume]
    total: int
    page: int
    size: int
    kpis: IntegrationCatalogueKpis
    filtres: IntegrationCatalogueFiltres
    avertissement: str


class IntegrationExemple(BaseModel):
    langage: Literal["curl", "python", "typescript"]
    libelle: str
    code: str


class IntegrationExemples(BaseModel):
    operation_id: str
    disponible: bool
    motif: str | None = None
    authentification: str
    prerequis: list[str] = Field(default_factory=list)
    exemples: list[IntegrationExemple] = Field(default_factory=list)


class IntegrationConsoleLimites(BaseModel):
    methodes: list[str]
    taille_max_octets: int
    delai_max_secondes: float


class IntegrationConsoleOperation(BaseModel):
    operation_id: str
    nom: str
    methode: str
    chemin: str
    module: str
    permissions: list[str]
    justification: str
    parametres: list[IntegrationParametre] = Field(default_factory=list)


class IntegrationConsoleOperations(BaseModel):
    items: list[IntegrationConsoleOperation]
    environnement: str
    limites: IntegrationConsoleLimites
    avertissement: str


ConsoleValeur = str | int | float | bool


class IntegrationConsoleRequete(BaseModel):
    """Seuls un identifiant d'opération et des valeurs de paramètres sont acceptés : jamais d'URL ni de méthode."""

    model_config = ConfigDict(extra="forbid")

    operation_id: str = Field(min_length=1, max_length=160)
    parametres_chemin: dict[str, str] = Field(default_factory=dict)
    parametres_requete: dict[str, ConsoleValeur | list[ConsoleValeur]] = Field(default_factory=dict)


class IntegrationConsoleResultat(BaseModel):
    operation_id: str
    methode: str
    chemin: str
    statut_http: int
    duree_ms: float
    taille_octets: int
    tronquee: bool
    corps: Any | None = None
    champs_masques: int
    request_id: str | None = None
    environnement: str
    message: str | None = None
