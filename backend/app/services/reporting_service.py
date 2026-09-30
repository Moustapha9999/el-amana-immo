from datetime import date

from sqlalchemy import String, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EcritureComptable, Immobilisation


def ecriture_filters(
    *,
    date_debut: date | None = None,
    date_fin: date | None = None,
    search: str | None = None,
    journal_code: str | None = None,
) -> list:
    filters = []
    if date_debut is not None:
        filters.append(EcritureComptable.date_ecriture >= date_debut)
    if date_fin is not None:
        filters.append(EcritureComptable.date_ecriture <= date_fin)
    if journal_code and journal_code.strip():
        filters.append(EcritureComptable.journal_code.ilike(journal_code.strip()))
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        filters.append(
            or_(
                EcritureComptable.libelle.ilike(pattern),
                EcritureComptable.journal_code.ilike(pattern),
                EcritureComptable.compte_debit.ilike(pattern),
                EcritureComptable.compte_credit.ilike(pattern),
                EcritureComptable.reference.ilike(pattern),
                cast(EcritureComptable.montant, String).ilike(pattern),
            )
        )
    return filters


async def list_ecritures_for_export(
    db: AsyncSession,
    *,
    date_debut: date | None = None,
    date_fin: date | None = None,
    search: str | None = None,
    journal_code: str | None = None,
) -> list[EcritureComptable]:
    filters = ecriture_filters(
        date_debut=date_debut, date_fin=date_fin, search=search, journal_code=journal_code
    )
    query = (
        select(EcritureComptable)
        .where(*filters)
        .order_by(EcritureComptable.date_ecriture.desc(), EcritureComptable.created_at.desc())
    )
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
