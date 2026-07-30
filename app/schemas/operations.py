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
    reference: str
    observations: str | None = None
    libelle: str | None = None  # compat — fusionné dans observations si besoin


class CessionRead(ORMModel):
    id: UUID
    immobilisation_id: UUID
    date_cession: date
    prix_cession: Decimal
    reference: str | None = None
    observations: str | None = None
    libelle: str | None = None
    vnc: Decimal
    plus_value: Decimal
    moins_value: Decimal
    ecriture_id: UUID | None


class CessionPreviewRequest(BaseModel):
    immobilisation_id: UUID
    date_cession: date
    prix_cession: Decimal


class CessionPreviewResponse(BaseModel):
    cumul_amortissement: Decimal
    vnc: Decimal
    prix_cession: Decimal
    resultat: Decimal
    plus_value: Decimal
    moins_value: Decimal
    cas: str  # plus_value | moins_value | equilibre



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


class CessionDetailRead(CessionListRead):
    """Fiche visuelle complète d'une cession."""

    valeur_brute: Decimal | None = None
    date_acquisition: date | None = None
    compte_immobilisation: str | None = None
    statut_immobilisation: str | None = None
    resultat: Decimal = Decimal("0")
    cas: str = "equilibre"  # plus_value | moins_value | equilibre


class RebutListRead(RebutRead):
    code_inventaire: str | None = None
    designation: str | None = None


class RebutDetailRead(RebutListRead):
    """Fiche visuelle complète d'une mise au rebut."""

    valeur_brute: Decimal | None = None
    date_acquisition: date | None = None
    compte_immobilisation: str | None = None
    statut_immobilisation: str | None = None
    cumul_amortissement: Decimal | None = None


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


class ReevaluationDetailRead(ReevaluationListRead):
    """Fiche visuelle complète d'une réévaluation."""

    valeur_brute: Decimal | None = None
    date_acquisition: date | None = None
    compte_immobilisation: str | None = None
    statut_immobilisation: str | None = None
    ecart: Decimal = Decimal("0")
    sens: str = "neutre"  # hausse | baisse | neutre


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
