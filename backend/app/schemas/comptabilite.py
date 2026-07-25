from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import TypeComptePlan
from app.schemas.common import ORMModel


class JournalCreate(BaseModel):
    code: str
    libelle: str


class JournalRead(JournalCreate, ORMModel):
    id: UUID
    is_active: bool


class ComptePlanCreate(BaseModel):
    numero: str
    libelle: str
    type_compte: TypeComptePlan
    centre_analytique: str | None = None


class ComptePlanCreateLinked(ComptePlanCreate):
    """Création compte + nature IMMO (obligatoire si type = immobilisation)."""

    nature_libelle: str | None = None
    nature_code: str | None = None
    duree_annees: int | None = Field(default=None, ge=1, le=100)
    taux_lineaire: Decimal | None = Field(default=None, ge=0, le=100)
    compte_amortissement: str | None = None
    compte_dotation: str | None = None


class ComptePlanUpdate(BaseModel):
    libelle: str | None = None
    type_compte: TypeComptePlan | None = None
    centre_analytique: str | None = None
    is_active: bool | None = None


class ComptePlanRead(ComptePlanCreate, ORMModel):
    id: UUID
    is_active: bool
    # Nature IMMO liée (renseignée en lecture liste si compte immo)
    nature_code: str | None = None
    nature_libelle: str | None = None
    nature_taux: Decimal | None = None
    nature_duree_annees: int | None = None
    nature_compte_amortissement: str | None = None
    nature_compte_dotation: str | None = None


class ParametrageAmortissementRead(ORMModel):
    id: UUID
    periodicite: str
    prorata: bool
    journal_code: str
    compte_dotation_defaut: str
    compte_amortissement_defaut: str


class ParametrageAmortissementUpdate(BaseModel):
    periodicite: str | None = None
    prorata: bool | None = None
    journal_code: str | None = None
    compte_dotation_defaut: str | None = None
    compte_amortissement_defaut: str | None = None


class AmortissementRead(ORMModel):
    id: UUID
    immobilisation_id: UUID
    periode: str
    montant: Decimal
    cumul: Decimal
    vnc: Decimal
    valide: bool
    annule: bool
    simule: bool


class AmortissementSimulateRequest(BaseModel):
    immobilisation_id: UUID
    periode: str


class AmortissementGenererPlanRequest(BaseModel):
    immobilisation_id: UUID


class AmortissementComptabiliserRequest(BaseModel):
    immobilisation_id: UUID
    periode: str
    date_ecriture: date


class EcritureCreate(BaseModel):
    journal_code: str
    date_ecriture: date
    libelle: str
    compte_debit: str
    compte_credit: str
    montant: Decimal
    reference: str | None = None
    immobilisation_id: UUID | None = None


class EcritureRead(EcritureCreate, ORMModel):
    id: UUID
    generee_auto: bool
    validee: bool


class EcritureDetailRead(EcritureRead):
    """Fiche visuelle d'une écriture comptable."""

    code_inventaire: str | None = None
    designation: str | None = None
    type_mouvement: str | None = None  # amortissement | cession | rebut | reevaluation | manuel | autre


class AmortissementComptabiliserResponse(BaseModel):
    amortissement: AmortissementRead
    ecriture: EcritureRead


class AmortissementCalculerRequest(BaseModel):
    periodicite: str  # mensuel | trimestriel | annuel
    annee: int
    periode_index: int  # mois 1-12 | trimestre 1-4 | année = 1
    mode: str  # simulation | validation
    categorie_ids: list[UUID] | None = None
    date_ecriture: date | None = None


class AmortissementCalculerLigneRead(BaseModel):
    immobilisation_id: UUID
    code_inventaire: str
    designation: str
    statut: str
    vnc_avant: Decimal
    dotation: Decimal
    vnc_apres: Decimal
    cumul_avant: Decimal
    cumul_apres: Decimal
    valeur_brute: Decimal
    nature: str | None = None
    compte_dotation: str | None = None
    compte_amortissement: str | None = None
    taux: Decimal | None = None
    message: str | None = None


class AmortissementCalculerResponse(BaseModel):
    periodicite: str
    annee: int
    periode_index: int
    periode: str
    date_debut: date
    date_arrete: date
    date_ecriture: date
    mode: str
    nb_calcules: int
    nb_ignores_vnc: int
    nb_deja_comptabilises: int
    nb_erreurs: int
    total_dotations: Decimal
    lignes: list[AmortissementCalculerLigneRead]
    ignores: list[AmortissementCalculerLigneRead]
    deja_comptabilises: list[AmortissementCalculerLigneRead]
    erreurs: list[AmortissementCalculerLigneRead]
