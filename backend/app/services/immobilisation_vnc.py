from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models import Amortissement, Immobilisation


async def compute_situation_comptable(db: AsyncSession, immobilisation_id: UUID) -> tuple[Immobilisation, Decimal, Decimal, Decimal]:
    immo = await db.get(Immobilisation, immobilisation_id)
    if immo is None or immo.deleted_at is not None:
        raise NotFoundError("Immobilisation", str(immobilisation_id))

    result = await db.execute(
        select(func.coalesce(func.sum(Amortissement.montant), 0)).where(
            Amortissement.immobilisation_id == immobilisation_id,
            Amortissement.valide.is_(True),
            Amortissement.annule.is_(False),
            Amortissement.simule.is_(False),
        )
    )
    cumul = Decimal(str(result.scalar_one())).quantize(Decimal("0.01"))
    vnc = (immo.valeur_brute - cumul).quantize(Decimal("0.01"))
    return immo, cumul, vnc
