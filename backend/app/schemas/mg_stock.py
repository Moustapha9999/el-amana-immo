from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.nombres import Qty, QtyGe0, QtyPos


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
    stock_min: Qty = 0
    stock_max: Qty | None = None
    agence_id: UUID | None = None
    emplacement: str | None = None
    fournisseur_habituel: str | None = None
    stock_initial: Qty = 0


class ArticleUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=40)
    designation: str | None = None
    famille_id: UUID | None = None
    uom: str | None = None
    stockable: bool | None = None
    reference: str | None = None
    sous_famille: str | None = None
    stock_min: Qty | None = None
    stock_max: Qty | None = None
    agence_id: UUID | None = None
    emplacement: str | None = None
    fournisseur_habituel: str | None = None
    is_active: bool | None = None
    # Stock cible : l'écart est tracé par un mouvement AJUSTEMENT (jamais écrit directement).
    stock_actuel: QtyGe0 | None = None
    motif_correction: str | None = Field(default=None, max_length=255)


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
    stock_actuel: Qty
    stock_min: Qty
    stock_max: Qty | None
    agence_id: UUID | None
    emplacement: str | None
    fournisseur_habituel: str | None = None
    is_active: bool
    niveau: str | None = None  # faible | normal | epuise


class ArticleFicheOut(ArticleOut):
    """Fiche article : identité + résumé de stock CDC."""

    famille_libelle: str | None = None
    agence_libelle: str | None = None
    stock_initial: Qty = 0
    total_entrees: Qty = 0
    total_sorties: Qty = 0
    total_ajustements: Qty = 0
    total_inventaires: int = 0


class MouvementCreate(BaseModel):
    article_id: UUID
    type_mouvement: str  # ENTREE | SORTIE | AJUSTEMENT | INVENTAIRE
    quantite: QtyPos
    agence_id: UUID | None = None
    departement: str | None = None
    motif: str | None = None
    observation: str | None = None
    date_mouvement: datetime | None = None
    source_type: str | None = None
    source_id: UUID | None = None
    allow_negative: bool = False


class SortieCreate(BaseModel):
    """Sortie de stock : destination DEPARTEMENT (département [+ service]) ou AGENCE, jamais les deux."""

    article_id: UUID
    quantite: QtyPos
    destination_type: Literal["DEPARTEMENT", "AGENCE"]
    departement_id: UUID | None = None
    service_id: UUID | None = None
    # Option « Autre » : texte saisi hors référentiel (None = valeur choisie dans la liste).
    departement_autre: str | None = Field(default=None, max_length=120)
    service_autre: str | None = Field(default=None, max_length=120)
    agence_id: UUID | None = None
    demandeur_id: UUID | None = None
    demandeur_nom: str | None = Field(default=None, max_length=255)
    motif_id: UUID
    observation: str | None = Field(default=None, max_length=2000)
    # Stock affiché à l'ouverture du formulaire : refus si le stock a bougé entre-temps.
    stock_attendu: Qty | None = None


class EntreeCreate(BaseModel):
    """Entrée de stock : une seule provenance (fournisseur, retour département, retour agence ou autre)."""

    article_id: UUID
    quantite: QtyPos
    provenance_type: Literal["FOURNISSEUR", "RETOUR_DEPARTEMENT", "RETOUR_AGENCE", "AUTRE"]
    fournisseur_id: UUID | None = None
    piece_reference: str | None = Field(default=None, max_length=80)
    departement_id: UUID | None = None
    service_id: UUID | None = None
    departement_autre: str | None = Field(default=None, max_length=120)
    service_autre: str | None = Field(default=None, max_length=120)
    agence_id: UUID | None = None
    remis_par: str | None = Field(default=None, max_length=255)
    motif_id: UUID
    observation: str | None = Field(default=None, max_length=2000)
    stock_attendu: Qty | None = None


class MotifSortieOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    libelle: str
    sens: str = "SORTIE"
    observation_obligatoire: bool
    ordre: int
    is_active: bool


class MotifSortieCreate(BaseModel):
    sens: Literal["SORTIE", "ENTREE"] = "SORTIE"
    code: str = Field(min_length=1, max_length=40)
    libelle: str = Field(min_length=1, max_length=160)
    observation_obligatoire: bool = False
    ordre: int = 0


class MotifSortieUpdate(BaseModel):
    libelle: str | None = Field(default=None, min_length=1, max_length=160)
    observation_obligatoire: bool | None = None
    ordre: int | None = None
    is_active: bool | None = None


class MouvementUpdate(BaseModel):
    date_mouvement: datetime | None = None
    article_id: UUID | None = None
    # Signée pour un AJUSTEMENT, strictement positive pour une entrée / sortie.
    quantite: Qty | None = None
    agence_id: UUID | None = None
    departement: str | None = None
    motif: str | None = None
    observation: str | None = None


class ReceptionLigneIn(BaseModel):
    ligne_id: UUID
    quantite: QtyPos
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
    quantite: Qty
    agence_id: UUID | None
    departement: str | None
    motif: str | None
    observation: str | None
    source_type: str | None
    source_id: UUID | None
    periode_id: UUID | None = None
    periode_libelle: str | None = None
    periode_debut: date | None = None
    periode_fin: date | None = None
    periode_cloturee: bool = False
    quantite_modifiable: bool = False
    initiateur_id: UUID | None = None
    initiateur_nom: str | None = None
    article_code: str | None = None
    article_designation: str | None = None
    stock_disponible: Qty | None = None
    destination_type: str | None = None
    org_entite_id: UUID | None = None
    service_id: UUID | None = None
    service_libelle: str | None = None
    departement_autre: bool = False
    service_autre: bool = False
    agence_libelle: str | None = None
    destination_libelle: str | None = None
    demandeur_id: UUID | None = None
    demandeur_nom: str | None = None
    motif_id: UUID | None = None
    provenance_type: str | None = None
    fournisseur_id: UUID | None = None
    piece_reference: str | None = None
    provenance_libelle: str | None = None


class DemandeLigneIn(BaseModel):
    article_id: UUID | None = None
    designation: str
    quantite_demandee: QtyPos
    quantite_accordee: Qty | None = None


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
    quantite_demandee: Qty
    quantite_accordee: Qty | None
    sort_order: int


class DemandeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reference: str
    date_demande: date
    agence_id: UUID
    agence_libelle_snapshot: str | None
    departement: str | None
    # NULL avec un libellé = saisie « Autre », hors référentiel (rattachement par déclencheur sinon).
    org_entite_id: UUID | None = None
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
    stock_total_unites: Qty
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
    stock_initial_periode: Qty = 0
    entrees_qte_periode: Qty = 0
    sorties_qte_periode: Qty = 0
    ajustements_qte_periode: Qty = 0
    stock_theorique_periode: Qty = 0
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
    stock_physique: QtyGe0
    observation: str | None = None


class InventaireLigneSaisie(BaseModel):
    """Sauvegarde d'une ligne (saisie rapide). ``stock_physique=None`` remet la ligne « non comptée »."""

    stock_physique: QtyGe0 | None = None
    commentaire: str | None = Field(default=None, max_length=255)
    effacer: bool = False
    exclure: bool | None = None


class InventaireLigneAjout(BaseModel):
    article_id: UUID
    commentaire: str | None = Field(default=None, max_length=255)


class InventaireCreate(BaseModel):
    libelle: str | None = Field(default=None, max_length=255)
    date_debut: date | None = None
    annee: int | None = Field(default=None, ge=2000, le=2100)
    mois: int | None = Field(default=None, ge=1, le=12)
    agence_id: UUID | None = None
    famille_id: UUID | None = None
    responsable_id: UUID | None = None
    responsable_nom: str | None = Field(default=None, max_length=160)
    observation: str | None = None
    periode_id: UUID | None = None


class InventaireUpdate(BaseModel):
    libelle: str | None = Field(default=None, min_length=1, max_length=255)
    date_debut: date | None = None
    agence_id: UUID | None = None
    famille_id: UUID | None = None
    responsable_id: UUID | None = None
    responsable_nom: str | None = Field(default=None, max_length=160)
    observation: str | None = None


class InventaireTransition(BaseModel):
    action: str
    motif: str | None = Field(default=None, max_length=2000)
    forcer: bool = False


class InventaireStats(BaseModel):
    total: int = 0
    a_compter: int = 0
    comptes: int = 0
    non_comptes: int = 0
    exclus: int = 0
    sans_ecart: int = 0
    ecarts_negatifs: int = 0
    ecarts_positifs: int = 0
    total_theorique: Qty = 0
    total_physique: Qty = 0
    ecart_net: Qty = 0
    progression: float = 0.0
    total_systeme: Qty = 0
    total_retenu: Qty = 0
    ajustement_net: Qty = 0
    ajustements_prevus: int = 0
    a_regulariser: int = 0
    ecart_a_regulariser: Qty = 0
    rapprochement: bool = False


class InventaireLigneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    article_id: UUID
    stock_theorique: Qty
    stock_physique: Qty | None
    ecart: Qty | None
    ecart_absolu: Qty | None = None
    ecart_pourcentage: float | None = None
    nature_ecart: str | None = None
    observation: str | None
    sort_order: int
    statut_comptage: str = "NON_COMPTE"
    statut_ligne: str = "NON_COMPTE"
    compte_par: UUID | None = None
    compte_par_nom: str | None = None
    compte_at: datetime | None = None
    stock_theorique_source: Qty | None = None
    theorique_reference: Qty | None = None
    stock_cible: Qty | None = None
    ajustement_prevu: Qty | None = None
    ecart_a_regulariser: Qty | None = None
    a_regulariser: bool = False
    ancienne_agence: bool = False
    donnees_source: dict | None = None
    ajout_manuel: bool = False
    updated_at: datetime | None = None
    article_code: str | None = None
    article_reference: str | None = None
    article_designation: str | None = None
    famille_id: UUID | None = None
    famille_libelle: str | None = None
    unite: str | None = None
    emplacement: str | None = None


class InventaireOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reference: str
    libelle: str
    date_debut: date
    date_fin: date | None
    annee: int | None = None
    mois: int | None = None
    periode_libelle: str | None = None
    agence_id: UUID | None
    agence_libelle: str | None = None
    famille_id: UUID | None = None
    famille_libelle: str | None = None
    responsable_id: UUID | None = None
    responsable_nom: str | None = None
    statut: str
    observation: str | None
    source: str = "MANUEL"
    import_meta: dict | None = None
    periode_id: UUID | None = None
    snapshot_at: datetime | None = None
    created_at: datetime | None = None
    created_by: UUID | None = None
    created_by_nom: str | None = None
    updated_at: datetime | None = None
    valide_at: datetime | None = None
    valide_by_nom: str | None = None
    validation_forcee: bool = False
    ajustements_at: datetime | None = None
    ajustements_by_nom: str | None = None
    cloture_at: datetime | None = None
    annule_at: datetime | None = None
    motif_annulation: str | None = None
    stats: InventaireStats = Field(default_factory=InventaireStats)
    mouvements_depuis: int = 0
    nb_ajustements: int = 0


class InventaireSynthese(BaseModel):
    dernier: InventaireOut | None = None
    en_cours: InventaireOut | None = None
    nb_en_cours: int = 0
    nb_a_controler: int = 0
    nb_total: int = 0


class InventaireHistoriqueOut(BaseModel):
    id: UUID
    created_at: datetime
    action: str
    entity: str
    user_nom: str | None = None
    before: dict | None = None
    after: dict | None = None


class InventaireLigneDetailOut(BaseModel):
    ligne: InventaireLigneOut
    historique: list[InventaireHistoriqueOut] = []


class InventaireLigneSaveOut(BaseModel):
    ligne: InventaireLigneOut
    stats: InventaireStats
    statut: str


class InventaireValidationPreview(BaseModel):
    total: int
    a_compter: int
    comptes: int
    non_comptes: int
    exclus: int
    ecarts: int
    ecarts_negatifs: int
    ecarts_positifs: int
    ecart_net: Qty
    mouvements_depuis: int
    peut_valider: bool
    peut_forcer: bool
    message: str | None = None


class InventaireImportOptions(BaseModel):
    date_inventaire: date
    annee: int | None = Field(default=None, ge=2000, le=2100)
    mois: int | None = Field(default=None, ge=1, le=12)
    agence_id: UUID | None = None
    responsable_nom: str | None = Field(default=None, max_length=160)
    observation: str | None = None
    feuille: str | None = None
    mapping: dict[str, str | None] = Field(default_factory=dict)
    # n° de ligne Excel → article_id (str) ou "IGNORER"
    resolutions: dict[str, str] = Field(default_factory=dict)


class AlerteOut(BaseModel):
    alerte_id: UUID | None = None
    article_id: UUID | None = None
    code: str | None = None
    designation: str | None = None
    stock_actuel: Qty | None = None
    stock_min: Qty | None = None
    niveau: str
    agence_id: UUID | None = None
    type_alerte: str = "STOCK"
    titre: str | None = None
    message: str | None = None
    lien: str | None = None


class AlerteSuiviOut(BaseModel):
    id: UUID
    reference: str
    article_id: UUID
    article_code: str | None = None
    article_reference: str | None = None
    article_designation: str | None = None
    famille_id: UUID | None = None
    famille_libelle: str | None = None
    agence_id: UUID | None = None
    agence_libelle: str | None = None
    emplacement: str | None = None
    uom: str | None = None
    type_alerte: str
    type_libelle: str
    statut: str
    statut_libelle: str
    origine: str
    seuil: Qty
    quantite_detection: Qty
    quantite_actuelle: Qty
    stock_actuel: Qty | None = None
    detectee_at: datetime
    rupture_at: datetime | None = None
    retour_normal_at: datetime | None = None
    quantite_retour: Qty | None = None
    episode_ouvert: bool
    mouvement_reference: str | None = None
    responsable_id: UUID | None = None
    responsable_nom: str | None = None
    commentaire: str | None = None
    traite_par_nom: str | None = None
    traite_at: datetime | None = None
    deleted_at: datetime | None = None
    deleted_by_nom: str | None = None
    motif_suppression: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AlerteKpisOut(BaseModel):
    seuil: Qty
    alertes_actives: bool
    articles_stock_faible: int
    articles_rupture: int
    alertes_non_traitees: int
    alertes_en_cours: int
    alertes_resolues: int
    alertes_cloturees: int


class AlerteSuiviListOut(BaseModel):
    items: list[AlerteSuiviOut]
    total: int
    page: int
    size: int
    kpis: AlerteKpisOut


class AlerteHistoriqueOut(BaseModel):
    action: str
    user_nom: str | None = None
    created_at: datetime
    before: dict | None = None
    after: dict | None = None


class AlerteDetailOut(AlerteSuiviOut):
    historique: list[AlerteHistoriqueOut] = Field(default_factory=list)


class AlerteUpdate(BaseModel):
    statut: Literal["NOUVELLE", "EN_COURS", "RESOLUE", "CLOTUREE"] | None = None
    responsable_id: UUID | None = None
    commentaire: str | None = Field(default=None, max_length=2000)


class AlerteSuppression(BaseModel):
    ids: list[UUID] = Field(min_length=1, max_length=500)
    motif: str = Field(min_length=3, max_length=500)


class AlerteControleOut(BaseModel):
    seuil: Qty | None = None
    articles: int
    ouvertes: int
    ruptures: int
    retours: int


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
