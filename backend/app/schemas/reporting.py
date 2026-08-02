from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import TypeNotification
from app.schemas.common import ORMModel


class NotificationRead(ORMModel):
    id: UUID
    type_notification: TypeNotification
    titre: str
    message: str
    lu: bool
    entity: str | None = None
    entity_id: str | None = None
    created_at: datetime


class AuditLogRead(ORMModel):
    id: UUID
    user_id: UUID | None
    user_email: str | None = None
    action: str
    entity: str
    entity_id: str | None
    ip_address: str | None
    created_at: datetime


class DashboardKpi(BaseModel):
    nombre_immobilisations: int
    valeur_brute_totale: float
    vnc_totale: float
    dotation_periode: float
    annee_reference: int


class DashboardChartPoint(BaseModel):
    label: str
    value: float
    key: str = ""


class DashboardFiltresActifs(BaseModel):
    statut: str | None = None
    famille: str | None = None
    mois: int | None = None


class DashboardComposition(BaseModel):
    valeur_brute: float
    cumul_amortissement: float
    vnc: float


class DashboardCharts(BaseModel):
    par_statut: list[DashboardChartPoint]
    par_famille: list[DashboardChartPoint]
    dotations_mensuelles: list[DashboardChartPoint]
    evolution_vnc: list[DashboardChartPoint]
    composition: DashboardComposition
    filtres_actifs: DashboardFiltresActifs


class RecapAmortissementLigneRead(BaseModel):
    compte_immobilisation: str
    intitule: str
    valeur_brute: float
    compte_amortissement: str | None = None
    amorts_cumules_n1: float
    cessions_annee: float
    dotations_annee: float
    amorts_cumules_n: float
    vnc: float


class RecapAmortissementDetailRead(BaseModel):
    immobilisation_id: str
    code_inventaire: str
    designation: str
    compte_immobilisation: str
    valeur_brute: float
    amorts_cumules_n1: float
    cessions_annee: float
    dotations_annee: float
    amorts_cumules_n: float
    vnc: float


class RecapAmortissementRead(BaseModel):
    annee: int
    date_arrete: str
    lignes: list[RecapAmortissementLigneRead]
    details: list[RecapAmortissementDetailRead] = []
    totaux: RecapAmortissementLigneRead


class RecapImmobilisationsLigneRead(BaseModel):
    compte: str
    intitule: str
    valeurs_ouverture: float
    acquisitions: float
    cessions: float
    valeurs_cloture: float


class RecapImmobilisationsRead(BaseModel):
    annee: int
    annee_ouverture: int
    date_ouverture: str
    date_cloture: str
    lignes: list[RecapImmobilisationsLigneRead]
    totaux: RecapImmobilisationsLigneRead


class CompteNatureLigneRead(BaseModel):
    immobilisation_id: str
    code_inventaire: str
    date_acquisition: str | None = None
    quantite: int
    designation: str
    valeur_acquisition: float
    taux: float | None = None
    amorts_cumules_n1: float
    dotations_annee: float
    amorts_cumules_n: float
    vnc: float
    agence_code: str | None = None
    agence_libelle: str | None = None


class CompteNatureGroupeRead(BaseModel):
    compte_immobilisation: str
    intitule: str
    lignes: list[CompteNatureLigneRead]
    totaux: CompteNatureLigneRead


class CompteOptionRead(BaseModel):
    numero: str
    libelle: str


class ComptesParNatureRead(BaseModel):
    annee: int
    date_arrete: str
    groupes: list[CompteNatureGroupeRead]
    totaux: CompteNatureLigneRead
    compte_filtre: str | None = None
    comptes_disponibles: list[CompteOptionRead] = []


class SoldeNatureLigneRead(BaseModel):
    nature_code: str
    nature: str
    compte_immobilisation: str
    compte_amortissement: str | None = None
    libelle_amortissement: str | None = None
    solde_148: float
    solde_148_n1: float
    compte_dotation: str | None = None
    libelle_dotation: str | None = None
    solde_68: float
    valeur_brute: float
    vnc: float
    nb_biens: int


class Soldes14868DetailLigneRead(BaseModel):
    immobilisation_id: str
    date: str | None = None
    reference: str
    designation: str
    categorie: str | None = None
    valeur_brute: float
    dotation: float
    amortissement_cumule: float
    amortissement_cumule_n1: float = 0
    vnc: float
    agence_code: str | None = None
    agence_libelle: str | None = None
    exercice: int
    compte_immobilisation: str | None = None
    compte_amortissement: str | None = None
    compte_dotation: str | None = None


class Soldes14868Read(BaseModel):
    famille_compte: str = "148"
    compte_numero: str = "148"
    compte_intitule: str = "Amortissements cumulés"
    annee: int
    date_arrete: str
    date_debut: str | None = None
    date_fin: str | None = None
    periode_label: str = ""
    solde_total: float = 0
    nb_immobilisations: int = 0
    nb_mouvements: int = 0
    total_valeur_brute: float = 0
    total_dotation: float = 0
    total_amortissement_cumule: float = 0
    total_amortissement_cumule_n1: float = 0
    total_vnc: float = 0
    lignes: list[SoldeNatureLigneRead]
    detail: list[Soldes14868DetailLigneRead] = []
    exercices_disponibles: list[int] = []
    total_148: float
    total_148_n1: float
    total_68: float
    nb_biens: int


class VentilationAmortAgenceLigneRead(BaseModel):
    immobilisation_id: str
    code_inventaire: str
    designation: str
    date_acquisition: str | None = None
    valeur_brute: float
    taux: float | None = None
    amortissement_cumule: float
    dotation_periode: float
    vnc: float
    agence_id: str | None = None
    agence_code: str | None = None
    agence_libelle: str


class VentilationAmortAgenceGroupeRead(BaseModel):
    agence_id: str | None = None
    agence_code: str | None = None
    agence_libelle: str
    total_dotations: float
    nb_immobilisations: int
    lignes: list[VentilationAmortAgenceLigneRead]


class VentilationAmortissementsAgenceRead(BaseModel):
    annee: int
    periodicite: str
    periode_index: int | None = None
    periode_label: str
    date_arrete: str
    agence_filtre_id: str | None = None
    categorie_filtre_id: str | None = None
    total_compte_68: float
    nb_immobilisations: int
    total_dotations: float
    groupes: list[VentilationAmortAgenceGroupeRead]
    exercices_disponibles: list[int] = []
