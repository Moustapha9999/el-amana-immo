from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models import Ajustement, Immobilisation
from app.models.enums import TypeAjustement
from app.schemas.operations import TransfertCreate


class TransfertService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def transfer(self, immobilisation_id: UUID, payload: TransfertCreate) -> Ajustement:
        from decimal import Decimal

        immo = await self.db.get(Immobilisation, immobilisation_id)
        if immo is None or immo.deleted_at is not None:
            raise NotFoundError("Immobilisation", str(immobilisation_id))

        old_agence = str(immo.agence_id) if immo.agence_id else None
        new_agence = str(payload.agence_id)
        if old_agence == new_agence:
            raise ValidationError("L'immobilisation est déjà rattachée à cette agence.")

        before = {"agence_id": old_agence, "localisation": immo.localisation}
        immo.agence_id = payload.agence_id
        after = {"agence_id": new_agence, "localisation": immo.localisation}

        row = Ajustement(
            immobilisation_id=immobilisation_id,
            type_ajustement=TypeAjustement.CORRECTION,
            date_ajustement=payload.date_transfert,
            montant=Decimal("0"),
            commentaire=payload.commentaire or "Transfert inter-agences",
            before_json=before,
            after_json=after,
        )
        self.db.add(row)
        await self.db.flush()
        return row
