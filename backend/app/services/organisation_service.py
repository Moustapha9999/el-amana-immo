from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Agence, CentreCout, Departement, Direction, Fournisseur, Journal, ComptePlanComptable
from app.schemas.comptabilite import ComptePlanCreate, ComptePlanUpdate, JournalCreate
from app.schemas.organisation import (
    AgenceCreate,
    AgenceUpdate,
    CentreCoutCreate,
    DepartementCreate,
    DirectionCreate,
    FournisseurCreate,
)
from app.services.base_crud import BaseCrudService


class AgenceService(BaseCrudService[Agence, AgenceCreate, AgenceUpdate]):
    entity_label = "Agence"

    def __init__(self, db: AsyncSession):
        super().__init__(db, Agence)


class DirectionService(BaseCrudService[Direction, DirectionCreate, DirectionCreate]):
    entity_label = "Direction"

    def __init__(self, db: AsyncSession):
        super().__init__(db, Direction)


class DepartementService(BaseCrudService[Departement, DepartementCreate, DepartementCreate]):
    entity_label = "Departement"

    def __init__(self, db: AsyncSession):
        super().__init__(db, Departement)


class CentreCoutService(BaseCrudService[CentreCout, CentreCoutCreate, CentreCoutCreate]):
    entity_label = "Centre de coût"

    def __init__(self, db: AsyncSession):
        super().__init__(db, CentreCout)


async def prochain_code_fournisseur(db: AsyncSession) -> str:
    """Code FRS-NNN suivant, attribué par la séquence PostgreSQL `fournisseurs_code_seq`."""
    return await db.scalar(select(func.fournisseur_code_suivant()))


class FournisseurService(BaseCrudService[Fournisseur, FournisseurCreate, FournisseurCreate]):
    entity_label = "Fournisseur"

    def __init__(self, db: AsyncSession):
        super().__init__(db, Fournisseur)

    async def create(self, payload: FournisseurCreate) -> Fournisseur:
        data = payload.model_dump()
        data["code"] = (data.get("code") or "").strip().upper() or await prochain_code_fournisseur(self.db)
        return await self.repo.add(Fournisseur(**data))

    async def list(self, page: int, size: int, search: str | None = None):
        return await self.repo.list(page, size, search, search_columns=("raison_sociale", "code"))


class JournalService(BaseCrudService[Journal, JournalCreate, JournalCreate]):
    entity_label = "Journal"

    def __init__(self, db: AsyncSession):
        super().__init__(db, Journal)


class ComptePlanService(BaseCrudService[ComptePlanComptable, ComptePlanCreate, ComptePlanUpdate]):
    entity_label = "Compte plan comptable"

    def __init__(self, db: AsyncSession):
        super().__init__(db, ComptePlanComptable)

    async def list(self, page: int, size: int, search: str | None = None):
        return await self.repo.list(page, size, search, search_columns=("numero", "libelle"))
