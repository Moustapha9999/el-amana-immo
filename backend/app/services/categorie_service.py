from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CategorieImmobilisation
from app.schemas.immobilisation import CategorieCreate, CategorieUpdate
from app.services.amortissement_rate import taux_lineaire_from_duree_annees
from app.services.base_crud import BaseCrudService
from app.services.nature_immo_referentiel import bank_taux_for_code


def sync_categorie_taux(row: CategorieImmobilisation, *, explicit_taux=None) -> None:
    """Aligne le taux sur le référentiel banque / durée — sans écraser un taux banque explicite."""
    if not row.amortissable:
        row.duree_annees_defaut = None
        row.taux_lineaire_defaut = None
        return
    bank = bank_taux_for_code(row.code)
    if explicit_taux is not None:
        row.taux_lineaire_defaut = explicit_taux
        return
    if bank is not None:
        row.taux_lineaire_defaut = bank
        return
    if row.taux_lineaire_defaut is None:
        row.taux_lineaire_defaut = taux_lineaire_from_duree_annees(row.duree_annees_defaut)


class CategorieService(BaseCrudService[CategorieImmobilisation, CategorieCreate, CategorieUpdate]):
    entity_label = "Catégorie"

    def __init__(self, db: AsyncSession):
        super().__init__(db, CategorieImmobilisation)

    async def create(self, payload: CategorieCreate) -> CategorieImmobilisation:
        data = payload.model_dump()
        explicit = data.pop("taux_lineaire_defaut", None)
        row = CategorieImmobilisation(**data)
        sync_categorie_taux(row, explicit_taux=explicit)
        return await self.repo.add(row)

    async def update(self, entity_id: UUID, payload: CategorieUpdate) -> CategorieImmobilisation:
        row = await self.get(entity_id)
        data = payload.model_dump(exclude_unset=True)
        explicit = data.pop("taux_lineaire_defaut", None) if "taux_lineaire_defaut" in data else None
        for key, value in data.items():
            setattr(row, key, value)
        # Si durée change sans taux explicite → re-sync banque / durée
        if explicit is not None or "duree_annees_defaut" in data or "amortissable" in data:
            sync_categorie_taux(row, explicit_taux=explicit)
        await self.db.flush()
        return row
