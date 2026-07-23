from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CategorieImmobilisation
from app.schemas.immobilisation import CategorieCreate, CategorieUpdate
from app.services.amortissement_rate import taux_lineaire_from_duree_annees
from app.services.base_crud import BaseCrudService


def sync_categorie_taux(row: CategorieImmobilisation) -> None:
    if not row.amortissable:
        row.duree_annees_defaut = None
        row.taux_lineaire_defaut = None
        return
    row.taux_lineaire_defaut = taux_lineaire_from_duree_annees(row.duree_annees_defaut)


class CategorieService(BaseCrudService[CategorieImmobilisation, CategorieCreate, CategorieUpdate]):
    entity_label = "Catégorie"

    def __init__(self, db: AsyncSession):
        super().__init__(db, CategorieImmobilisation)

    async def create(self, payload: CategorieCreate) -> CategorieImmobilisation:
        data = payload.model_dump()
        data.pop("taux_lineaire_defaut", None)
        row = CategorieImmobilisation(**data)
        sync_categorie_taux(row)
        return await self.repo.add(row)

    async def update(self, entity_id: UUID, payload: CategorieUpdate) -> CategorieImmobilisation:
        row = await self.get(entity_id)
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(row, key, value)
        sync_categorie_taux(row)
        await self.db.flush()
        return row
