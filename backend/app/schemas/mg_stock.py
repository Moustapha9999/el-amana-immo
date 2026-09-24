from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FamilleCreate(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    libelle: str = Field(min_length=1, max_length=120)
    sort_order: int = 0


class FamilleUpdate(BaseModel):
    libelle: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class FamilleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    libelle: str
    sort_order: int
    is_active: bool


class ArticleCreate(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    designation: str = Field(min_length=1, max_length=255)
    famille_id: UUID
    uom: str = "U"
    stockable: bool = True
    reference: str | None = None
    sous_famille: str | None = None
    stock_min: Decimal = Decimal("0")
    stock_max: Decimal | None = None
    agence_id: UUID | None = None
    emplacement: str | None = None
    fournisseur_habituel: str | None = None
    stock_initial: Decimal = Decimal("0")


class ArticleUpdate(BaseModel):
    designation: str | None = None
    famille_id: UUID | None = None
    uom: str | None = None
    stockable: bool | None = None
    reference: str | None = None
    sous_famille: str | None = None
    stock_min: Decimal | None = None
    stock_max: Decimal | None = None
    agence_id: UUID | None = None
    emplacement: str | None = None
    fournisseur_habituel: str | None = None
    is_active: bool | None = None


class ArticleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    designation: str
    famille_id: UUID
    uom: str
    stockable: bool = True
    reference: str | None = None
    sous_famille: str | None = None
    stock_actuel: Decimal
    stock_min: Decimal
    stock_max: Decimal | None
    agence_id: UUID | None
    emplacement: str | None
    fournisseur_habituel: str | None = None
    is_active: bool
    niveau: str | None = None  # faible | normal | epuise


class ArticleFicheOut(ArticleOut):
    """Fiche article : identité + résumé de stock CDC."""

    famille_libelle: str | None = None
    agence_libelle: str | None = None
    stock_initial: Decimal = Decimal("0")
    total_entrees: Decimal = Decimal("0")
    total_sorties: Decimal = Decimal("0")
    total_ajustements: Decimal = Decimal("0")
    total_inventaires: int = 0


class MouvementCreate(BaseModel):
    article_id: UUID
    type_mouvement: str  # ENTREE | SORTIE | AJUSTEMENT | INVENTAIRE
    quantite: Decimal
    agence_id: UUID | None = None
    departement: str | None = None
    motif: str | None = None
    observation: str | None = None
    date_mouvement: datetime | None = None
    source_type: str | None = None
    source_id: UUID | None = None
    allow_negative: bool = False


class ReceptionLigneIn(BaseModel):
    ligne_id: UUID
    quantite: Decimal = Field(gt=0)
    article_id: UUID | None = None


class ReceptionBcIn(BaseModel):
    lignes: list[ReceptionLigneIn] = Field(min_length=1)
    agence_id: UUID | None = None
    motif: str | None = None


class MouvementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reference: str
    date_mouvement: datetime
    type_mouvement: str
    article_id: UUID
    quantite: Decimal
    agence_id: UUID | None
    departement: str | None
    motif: str | None
    observation: str | None
    source_type: str | None
    source_id: UUID | None
    periode_id: UUID | None = None
    initiateur_id: UUID | None = None
    initiateur_nom: str | None = None
    article_code: str | None = None
    article_designation: str | None = None
    stock_disponible: Decimal | None = None


class DemandeLigneIn(BaseModel):
    article_id: UUID | None = None
    designation: str
    quantite_demandee: Decimal = Field(gt=0)
    quantite_accordee: Decimal | None = None


class DemandeCreate(BaseModel):
    date_demande: date | None = None
    agence_id: UUID
    departement: str | None = None
    fonction: str | None = None
    observation: str | None = None
    lignes: list[DemandeLigneIn] = Field(min_length=1)


class DemandeUpdate(BaseModel):
    departement: str | None = None
    fonction: str | None = None
    observation: str | None = None
    lignes: list[DemandeLigneIn] | None = None


class DemandeTransition(BaseModel):
    action: str  # soumettre | visa_agence | visa_mg | servir | archiver | rejeter | annuler
    lignes: list[DemandeLigneIn] | None = None  # qty accordées au visa_mg


class DemandeLigneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    article_id: UUID | None
    designation: str
    quantite_demandee: Decimal
    quantite_accordee: Decimal | None
    sort_order: int


class DemandeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reference: str
    date_demande: date
    agence_id: UUID
    agence_libelle_snapshot: str | None
    departement: str | None
    demandeur_id: UUID | None
    demandeur_nom: str | None
    fonction: str | None
    statut: str
    observation: str | None
    lignes: list[DemandeLigneOut] = []


class DashboardOut(BaseModel):
    articles_total: int
    articles_actifs: int
    articles_inactifs: int
    stock_total_unites: float
    entrees_mois: int
    sorties_mois: int
    articles_crees_mois: int
    stock_faible: int
    stock_epuise: int
    demandes_en_attente: int
    demandes_en_cours: int
    demandes_validees: int
    demandes_rejetees: int
    inventaires_en_cours: int
    inventaire_progression: float
    mouvements_aujourd_hui: int
    mouvements_mois: int
    evolution: list[dict]
    conso_par_famille: list[dict]
    conso_par_agence: list[dict]
    conso_par_mois: list[dict]
    periode_active: dict | None = None
    stock_initial_periode: float = 0
    entrees_qte_periode: float = 0
    sorties_qte_periode: float = 0
    ajustements_qte_periode: float = 0
    stock_theorique_periode: float = 0
    ajustements_mois: int = 0
    cloture_statut: str | None = None
    cloture_message: str | None = None


class RapportConsoOut(BaseModel):
    periode: str
    granularity: str
    lignes: list[dict]


class ParametreCreate(BaseModel):
    cle: str = Field(min_length=1, max_length=60)
    valeur: str = Field(min_length=1, max_length=255)
    libelle: str | None = None


class ParametreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cle: str
    valeur: str
    libelle: str | None


class ParametreUpdate(BaseModel):
    valeur: str = Field(min_length=1, max_length=255)


class InventaireLigneIn(BaseModel):
    id: UUID
    stock_physique: Decimal = Field(ge=0)
    observation: str | None = None


class InventaireCreate(BaseModel):
    libelle: str = Field(min_length=1, max_length=255)
    date_debut: date | None = None
    agence_id: UUID | None = None
    observation: str | None = None
    famille_id: UUID | None = None
    periode_id: UUID | None = None


class InventaireTransition(BaseModel):
    action: str
    motif: str | None = None


class InventaireLigneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    article_id: UUID
    stock_theorique: Decimal
    stock_physique: Decimal | None
    ecart: Decimal | None
    nature_ecart: str | None = None
    observation: str | None
    sort_order: int
    article_code: str | None = None
    article_designation: str | None = None
    famille_libelle: str | None = None


class InventaireOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reference: str
    libelle: str
    date_debut: date
    date_fin: date | None
    agence_id: UUID | None
    statut: str
    observation: str | None
    periode_id: UUID | None = None
    lignes: list[InventaireLigneOut] = []
    nb_conforme: int = 0
    nb_surplus: int = 0
    nb_manquant: int = 0


class AlerteOut(BaseModel):
    article_id: UUID | None = None
    code: str | None = None
    designation: str | None = None
    stock_actuel: Decimal | None = None
    stock_min: Decimal | None = None
    niveau: str
    agence_id: UUID | None = None
    type_alerte: str = "STOCK"
    titre: str | None = None
    message: str | None = None
    lien: str | None = None


class PeriodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    annee: int
    mois: int
    libelle: str
    date_debut: date
    date_fin: date
    statut: str
    agence_id: UUID | None = None
    periode_precedente_id: UUID | None = None
    cloture_at: datetime | None = None
    reopen_at: datetime | None = None
    reopen_motif: str | None = None
    periode_verrouillee: dict | None = None


class PeriodeReopenIn(BaseModel):
    motif: str = Field(min_length=5, max_length=500)


class RapportExportIn(BaseModel):
    format: str = Field(pattern="^(xlsx|pdf|csv)$")
    scope: str = "filtered"
    ids: list[UUID] = []
    filters: dict = {}
    columns: list[str] | None = None


class RapportCustomPreviewIn(BaseModel):
    dataset: str
    columns: list[str] = []
    filters: dict = {}
    sort_by: str | None = None
    sort_dir: str = "desc"
    page: int = 1
    size: int = 50


class RapportCustomExportIn(BaseModel):
    dataset: str
    format: str = Field(pattern="^(xlsx|pdf|csv)$")
    scope: str = "filtered"
    ids: list[UUID] = []
    filters: dict = {}
    columns: list[str] = []
    sort_by: str | None = None
    sort_dir: str = "desc"
