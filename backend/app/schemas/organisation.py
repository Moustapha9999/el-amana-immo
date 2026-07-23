from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ReferentielBase(BaseModel):
    code: str = Field(max_length=30)
    libelle: str = Field(max_length=255)


class AgenceCreate(ReferentielBase):
    adresse: str | None = None
    ville: str | None = None


class AgenceUpdate(BaseModel):
    libelle: str | None = None
    adresse: str | None = None
    ville: str | None = None
    is_active: bool | None = None


class AgenceRead(AgenceCreate, ORMModel):
    id: UUID
    is_active: bool


class DirectionCreate(ReferentielBase):
    pass


class DirectionRead(DirectionCreate, ORMModel):
    id: UUID
    is_active: bool


class DepartementCreate(ReferentielBase):
    direction_id: UUID | None = None


class DepartementRead(DepartementCreate, ORMModel):
    id: UUID
    is_active: bool


class CentreCoutCreate(ReferentielBase):
    departement_id: UUID | None = None


class CentreCoutRead(CentreCoutCreate, ORMModel):
    id: UUID
    is_active: bool


class FournisseurCreate(BaseModel):
    code: str
    raison_sociale: str
    contact: str | None = None
    telephone: str | None = None
    email: str | None = None
    adresse: str | None = None


class FournisseurRead(FournisseurCreate, ORMModel):
    id: UUID
    is_active: bool
