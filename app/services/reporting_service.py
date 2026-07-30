from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EcritureComptable, Immobilisation


async def list_ecritures_for_export(
    db: AsyncSession,
    *,
    date_debut: date | None = None,
    date_fin: date | None = None,
) -> list[EcritureComptable]:
    query = select(EcritureComptable).order_by(EcritureComptable.date_ecriture.desc(), EcritureComptable.created_at.desc())
    if date_debut is not None:
        query = query.where(EcritureComptable.date_ecriture >= date_debut)
    if date_fin is not None:
        query = query.where(EcritureComptable.date_ecriture <= date_fin)
    result = await db.execute(query)
    return list(result.scalars().all())


async def list_immobilisations_for_export(
    db: AsyncSession,
    *,
    search: str | None = None,
    statuts: list | None = None,
    famille: str | None = None,
    amortissable: bool | None = None,
) -> list[Immobilisation]:
    from app.services.immobilisation_service import ImmobilisationService

    items, _total = await ImmobilisationService(db).list(
        1,
        100_000,
        search,
        amortissable=amortissable,
        statuts=statuts,
        famille=famille,
    )
    return items
