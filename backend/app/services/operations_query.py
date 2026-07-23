from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import page_offset
from app.models import Cession, Immobilisation, Rebut, Reevaluation, Ajustement


async def list_cessions(db: AsyncSession, page: int, size: int) -> tuple[list[tuple[Cession, Immobilisation | None]], int]:
    count = await db.execute(select(func.count()).select_from(Cession))
    total = int(count.scalar_one())
    result = await db.execute(
        select(Cession, Immobilisation)
        .join(Immobilisation, Cession.immobilisation_id == Immobilisation.id, isouter=True)
        .order_by(Cession.date_cession.desc())
        .offset(page_offset(page, size))
        .limit(size)
    )
    rows = [(c, immo) for c, immo in result.all()]
    return rows, total


async def list_rebuts(db: AsyncSession, page: int, size: int) -> tuple[list[tuple[Rebut, Immobilisation | None]], int]:
    count = await db.execute(select(func.count()).select_from(Rebut))
    total = int(count.scalar_one())
    result = await db.execute(
        select(Rebut, Immobilisation)
        .join(Immobilisation, Rebut.immobilisation_id == Immobilisation.id, isouter=True)
        .order_by(Rebut.date_rebut.desc())
        .offset(page_offset(page, size))
        .limit(size)
    )
    rows = [(r, immo) for r, immo in result.all()]
    return rows, total


async def list_reevaluations(
    db: AsyncSession, page: int, size: int
) -> tuple[list[tuple[Reevaluation, Immobilisation | None]], int]:
    count = await db.execute(select(func.count()).select_from(Reevaluation))
    total = int(count.scalar_one())
    result = await db.execute(
        select(Reevaluation, Immobilisation)
        .join(Immobilisation, Reevaluation.immobilisation_id == Immobilisation.id, isouter=True)
        .order_by(Reevaluation.date_reevaluation.desc())
        .offset(page_offset(page, size))
        .limit(size)
    )
    return [(r, immo) for r, immo in result.all()], total


async def list_ajustements(
    db: AsyncSession, page: int, size: int
) -> tuple[list[tuple[Ajustement, Immobilisation | None]], int]:
    count = await db.execute(select(func.count()).select_from(Ajustement))
    total = int(count.scalar_one())
    result = await db.execute(
        select(Ajustement, Immobilisation)
        .join(Immobilisation, Ajustement.immobilisation_id == Immobilisation.id, isouter=True)
        .order_by(Ajustement.date_ajustement.desc())
        .offset(page_offset(page, size))
        .limit(size)
    )
    return [(a, immo) for a, immo in result.all()], total
