from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import TypeAjustement
from app.schemas.common import ORMModel


class CessionCreate(BaseModel):
    immobilisation_id: UUID
    date_cession: date
    prix_cession: Decimal
    libelle: str | None = None


class CessionRead(CessionCreate, ORMModel):
    id: UUID
    vnc: Decimal
    plus_value: Decimal
    moins_value: Decimal
    ecriture_id: UUID | None


class CessionSortieResponse(BaseModel):
    cession: CessionRead
    ecriture_ids: list[UUID]


class RebutCreate(BaseModel):
    immobilisation_id: UUID
    date_rebut: date
    motif: str | None = None


class RebutRead(RebutCreate, ORMModel):
    id: UUID
    vnc: Decimal
    ecriture_id: UUID | None


class CessionListRead(CessionRead):
    code_inventaire: str | None = None
    designation: str | None = None


class RebutListRead(RebutRead):
    code_inventaire: str | None = None
    designation: str | None = None


class RebutSortieResponse(BaseModel):
    rebut: RebutRead
    ecriture_ids: list[UUID]


class SituationComptableRead(BaseModel):
    immobilisation_id: UUID
    valeur_brute: Decimal
    cumul_amortissement: Decimal
    vnc: Decimal


class ReevaluationCreate(BaseModel):
    immobilisation_id: UUID
    date_reevaluation: date
    nouvelle_valeur: Decimal
    justificatif: str | None = None


class ReevaluationRead(ReevaluationCreate, ORMModel):
    id: UUID
    ancienne_valeur: Decimal


class ReevaluationListRead(ReevaluationRead):
    code_inventaire: str | None = None
    designation: str | None = None


class ReevaluationCreateResponse(BaseModel):
    reevaluation: ReevaluationRead
    plan_regenere: bool
    ecriture_ids: list[UUID] = []


class AjustementCreate(BaseModel):
    immobilisation_id: UUID
    type_ajustement: TypeAjustement
    date_ajustement: date
    montant: Decimal
    commentaire: str | None = None


class AjustementRead(AjustementCreate, ORMModel):
    id: UUID


class AjustementCreateResponse(BaseModel):
    ajustement: AjustementRead
    ecriture_ids: list[UUID] = []


class AjustementListRead(AjustementRead):
    code_inventaire: str | None = None
    designation: str | None = None


class TransfertCreate(BaseModel):
    agence_id: UUID
    date_transfert: date
    commentaire: str | None = None
