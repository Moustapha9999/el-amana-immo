from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ReferentielBase(BaseModel):
    code: str = Field(max_length=30)
    libelle: str = Field(max_length=255)


class AgenceCreate(ReferentielBase):
    adresse: str | None = None
    ville: str | None = None
    code_banque: str | None = Field(default="00007", max_length=10)
    banque_sigle: str | None = Field(default="BEA", max_length=20)
    banque_raison_sociale: str | None = Field(default="Banque El Amana", max_length=255)
    code_swift: str | None = Field(default="AMDHMRMRXXX", max_length=20)


class AgenceUpdate(BaseModel):
    libelle: str | None = None
    adresse: str | None = None
    ville: str | None = None
    is_active: bool | None = None
    code_banque: str | None = Field(default=None, max_length=10)
    banque_sigle: str | None = Field(default=None, max_length=20)
    banque_raison_sociale: str | None = Field(default=None, max_length=255)
    code_swift: str | None = Field(default=None, max_length=20)


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
    code: str = Field(min_length=1, max_length=30)
    raison_sociale: str = Field(min_length=1, max_length=255)
    nom_commercial: str | None = Field(default=None, max_length=255)
    type_fournisseur: str = Field(default="FOURNITURE", max_length=40)
    contact: str | None = Field(default=None, max_length=120)
    contact_fonction: str | None = Field(default=None, max_length=120)
    telephone: str | None = Field(default=None, max_length=40)
    telephone_secondaire: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=255)
    site_web: str | None = Field(default=None, max_length=255)
    adresse: str | None = None
    ville: str | None = Field(default=None, max_length=120)
    pays: str = Field(default="Mauritanie", max_length=80)
    nif: str | None = Field(default=None, max_length=60)
    rc: str | None = Field(default=None, max_length=60)
    devise_defaut: str = Field(default="MRU", max_length=10)
    mode_paiement_defaut: str | None = Field(default=None, max_length=80)
    delai_paiement_jours: int | None = Field(default=None, ge=0, le=3650)
    conditions_commerciales: str | None = None


class FournisseurUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=30)
    raison_sociale: str | None = Field(default=None, min_length=1, max_length=255)
    nom_commercial: str | None = Field(default=None, max_length=255)
    type_fournisseur: str | None = Field(default=None, max_length=40)
    contact: str | None = Field(default=None, max_length=120)
    contact_fonction: str | None = Field(default=None, max_length=120)
    telephone: str | None = Field(default=None, max_length=40)
    telephone_secondaire: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=255)
    site_web: str | None = Field(default=None, max_length=255)
    adresse: str | None = None
    ville: str | None = Field(default=None, max_length=120)
    pays: str | None = Field(default=None, max_length=80)
    nif: str | None = Field(default=None, max_length=60)
    rc: str | None = Field(default=None, max_length=60)
    devise_defaut: str | None = Field(default=None, max_length=10)
    mode_paiement_defaut: str | None = Field(default=None, max_length=80)
    delai_paiement_jours: int | None = Field(default=None, ge=0, le=3650)
    conditions_commerciales: str | None = None
    is_active: bool | None = None


class FournisseurRead(FournisseurCreate, ORMModel):
    id: UUID
    is_active: bool
