from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

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


class ComptePlanRead(ComptePlanCreate, ORMModel):
    id: UUID
    is_active: bool


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


class AmortissementComptabiliserResponse(BaseModel):
    amortissement: AmortissementRead
    ecriture: EcritureRead
