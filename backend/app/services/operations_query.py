from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import page_offset
from app.models import Ajustement, Cession, Immobilisation, Rebut, Reevaluation


async def get_cession(
    db: AsyncSession,
    cession_id,
) -> tuple[Cession, Immobilisation | None]:
    from app.core.exceptions import NotFoundError

    result = await db.execute(
        select(Cession, Immobilisation)
        .join(Immobilisation, Cession.immobilisation_id == Immobilisation.id, isouter=True)
        .where(Cession.id == cession_id)
    )
    row = result.first()
    if row is None:
        raise NotFoundError("Cession", str(cession_id))
    return row[0], row[1]


async def get_reevaluation(
    db: AsyncSession,
    reevaluation_id,
) -> tuple[Reevaluation, Immobilisation | None]:
    from app.core.exceptions import NotFoundError

    result = await db.execute(
        select(Reevaluation, Immobilisation)
        .join(Immobilisation, Reevaluation.immobilisation_id == Immobilisation.id, isouter=True)
        .where(Reevaluation.id == reevaluation_id)
    )
    row = result.first()
    if row is None:
        raise NotFoundError("Réévaluation", str(reevaluation_id))
    return row[0], row[1]


async def get_rebut(
    db: AsyncSession,
    rebut_id,
) -> tuple[Rebut, Immobilisation | None]:
    from app.core.exceptions import NotFoundError

    result = await db.execute(
        select(Rebut, Immobilisation)
        .join(Immobilisation, Rebut.immobilisation_id == Immobilisation.id, isouter=True)
        .where(Rebut.id == rebut_id)
    )
    row = result.first()
    if row is None:
        raise NotFoundError("Rebut", str(rebut_id))
    return row[0], row[1]


async def list_cessions(
    db: AsyncSession,
    page: int,
    size: int,
    *,
    date_debut: date | None = None,
    date_fin: date | None = None,
    search: str | None = None,
) -> tuple[list[tuple[Cession, Immobilisation | None]], int]:
    filters = []
    if date_debut is not None:
        filters.append(Cession.date_cession >= date_debut)
    if date_fin is not None:
        filters.append(Cession.date_cession <= date_fin)
    if search:
        pattern = f"%{search.strip()}%"
        filters.append(
            or_(
                Immobilisation.code_inventaire.ilike(pattern),
                Immobilisation.designation.ilike(pattern),
            )
        )

    base = select(Cession, Immobilisation).join(
        Immobilisation, Cession.immobilisation_id == Immobilisation.id, isouter=True
    )
    count_stmt = (
        select(func.count())
        .select_from(Cession)
        .join(Immobilisation, Cession.immobilisation_id == Immobilisation.id, isouter=True)
    )
    if filters:
        base = base.where(*filters)
        count_stmt = count_stmt.where(*filters)

    total = int((await db.execute(count_stmt)).scalar_one())
    result = await db.execute(
        base.order_by(Cession.date_cession.desc()).offset(page_offset(page, size)).limit(size)
    )
    return [(c, immo) for c, immo in result.all()], total


async def list_rebuts(
    db: AsyncSession,
    page: int,
    size: int,
    *,
    date_debut: date | None = None,
    date_fin: date | None = None,
    search: str | None = None,
) -> tuple[list[tuple[Rebut, Immobilisation | None]], int]:
    filters = []
    if date_debut is not None:
        filters.append(Rebut.date_rebut >= date_debut)
    if date_fin is not None:
        filters.append(Rebut.date_rebut <= date_fin)
    if search:
        pattern = f"%{search.strip()}%"
        filters.append(
            or_(
                Immobilisation.code_inventaire.ilike(pattern),
                Immobilisation.designation.ilike(pattern),
                Rebut.motif.ilike(pattern),
            )
        )

    base = select(Rebut, Immobilisation).join(
        Immobilisation, Rebut.immobilisation_id == Immobilisation.id, isouter=True
    )
    count_stmt = (
        select(func.count())
        .select_from(Rebut)
        .join(Immobilisation, Rebut.immobilisation_id == Immobilisation.id, isouter=True)
    )
    if filters:
        base = base.where(*filters)
        count_stmt = count_stmt.where(*filters)

    total = int((await db.execute(count_stmt)).scalar_one())
    result = await db.execute(
        base.order_by(Rebut.date_rebut.desc()).offset(page_offset(page, size)).limit(size)
    )
    return [(r, immo) for r, immo in result.all()], total


async def list_reevaluations(
    db: AsyncSession,
    page: int,
    size: int,
    *,
    date_debut: date | None = None,
    date_fin: date | None = None,
    search: str | None = None,
) -> tuple[list[tuple[Reevaluation, Immobilisation | None]], int]:
    filters = []
    if date_debut is not None:
        filters.append(Reevaluation.date_reevaluation >= date_debut)
    if date_fin is not None:
        filters.append(Reevaluation.date_reevaluation <= date_fin)
    if search:
        pattern = f"%{search.strip()}%"
        filters.append(
            or_(
                Immobilisation.code_inventaire.ilike(pattern),
                Immobilisation.designation.ilike(pattern),
                Reevaluation.justificatif.ilike(pattern),
            )
        )

    base = select(Reevaluation, Immobilisation).join(
        Immobilisation, Reevaluation.immobilisation_id == Immobilisation.id, isouter=True
    )
    count_stmt = (
        select(func.count())
        .select_from(Reevaluation)
        .join(Immobilisation, Reevaluation.immobilisation_id == Immobilisation.id, isouter=True)
    )
    if filters:
        base = base.where(*filters)
        count_stmt = count_stmt.where(*filters)

    total = int((await db.execute(count_stmt)).scalar_one())
    result = await db.execute(
        base.order_by(Reevaluation.date_reevaluation.desc())
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
