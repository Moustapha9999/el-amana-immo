from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.api.v1.endpoints.helpers import to_paginated
from app.core.exceptions import AppError, raise_http_from_app
from app.core.pagination import page_offset
from app.db.session import get_db
from app.models import EcritureComptable, User
from app.schemas.comptabilite import (
    AmortissementComptabiliserRequest,
    AmortissementComptabiliserResponse,
    AmortissementGenererPlanRequest,
    AmortissementRead,
    AmortissementSimulateRequest,
    ComptePlanCreate,
    ComptePlanRead,
    EcritureCreate,
    EcritureRead,
    JournalCreate,
    JournalRead,
    ParametrageAmortissementRead,
    ParametrageAmortissementUpdate,
)
from app.schemas.common import PaginatedResponse
from app.services.amortissement_service import AmortissementService
from app.services.audit_helpers import record_audit
from app.services.immobilisation_service import ParametrageService
from app.services.organisation_service import ComptePlanService, JournalService

router = APIRouter(tags=["comptabilite"])


@router.get("/journaux", response_model=PaginatedResponse[JournalRead])
async def list_journaux(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), search: str | None = None, _: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    items, total = await JournalService(db).list(page, size, search)
    return to_paginated(items, total, page, size, JournalRead.model_validate)


@router.post("/journaux", response_model=JournalRead, status_code=status.HTTP_201_CREATED)
async def create_journal(payload: JournalCreate, _: User = Depends(require_roles("administrateur", "comptable")), db: AsyncSession = Depends(get_db)):
    return await JournalService(db).create(payload)


@router.get("/plan-comptable", response_model=PaginatedResponse[ComptePlanRead])
async def list_plan(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), search: str | None = None, _: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.models import ComptePlanComptable
    from app.repositories.base import BaseRepository

    items, total = await BaseRepository(db, ComptePlanComptable).list(page, size, search, ("numero", "libelle"))
    return to_paginated(items, total, page, size, ComptePlanRead.model_validate)


@router.post("/plan-comptable", response_model=ComptePlanRead, status_code=status.HTTP_201_CREATED)
async def create_compte(payload: ComptePlanCreate, _: User = Depends(require_roles("administrateur", "comptable")), db: AsyncSession = Depends(get_db)):
    return await ComptePlanService(db).create(payload)


@router.get("/parametrage/amortissement", response_model=ParametrageAmortissementRead)
async def get_parametrage(_: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await ParametrageService(db).get_or_create()


@router.patch("/parametrage/amortissement", response_model=ParametrageAmortissementRead)
async def update_parametrage(payload: ParametrageAmortissementUpdate, _: User = Depends(require_roles("administrateur")), db: AsyncSession = Depends(get_db)):
    return await ParametrageService(db).update(payload.model_dump(exclude_unset=True))


@router.get("/amortissements/immobilisation/{immobilisation_id}", response_model=list[AmortissementRead])
async def list_amortissements(immobilisation_id: UUID, _: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = await AmortissementService(db).list_for_immobilisation(immobilisation_id)
    return [AmortissementRead.model_validate(r) for r in rows]


@router.post("/amortissements/simuler", response_model=AmortissementRead, status_code=status.HTTP_201_CREATED)
async def simuler_amortissement(payload: AmortissementSimulateRequest, _: User = Depends(require_roles("administrateur", "comptable")), db: AsyncSession = Depends(get_db)):
    try:
        row = await AmortissementService(db).simulate(payload.immobilisation_id, payload.periode)
        return row
    except AppError as exc:
        raise_http_from_app(exc)


@router.post("/amortissements/generer-plan", response_model=list[AmortissementRead], status_code=status.HTTP_201_CREATED)
async def generer_plan_amortissement(
    payload: AmortissementGenererPlanRequest,
    _: User = Depends(require_roles("administrateur", "comptable")),
    db: AsyncSession = Depends(get_db),
):
    try:
        rows = await AmortissementService(db).generer_plan(payload.immobilisation_id)
        return [AmortissementRead.model_validate(r) for r in rows]
    except AppError as exc:
        raise_http_from_app(exc)


@router.post("/amortissements/comptabiliser", response_model=AmortissementComptabiliserResponse)
async def comptabiliser_amortissement(
    payload: AmortissementComptabiliserRequest,
    request: Request,
    user: User = Depends(require_roles("administrateur", "comptable")),
    db: AsyncSession = Depends(get_db),
):
    try:
        row, ecriture = await AmortissementService(db).comptabiliser(
            payload.immobilisation_id,
            payload.periode,
            payload.date_ecriture,
        )
        await record_audit(
            db,
            user=user,
            action="comptabiliser_amortissement",
            entity="ecriture_comptable",
            entity_id=str(ecriture.id),
            request=request,
            after={"periode": payload.periode, "montant": str(ecriture.montant)},
        )
        return AmortissementComptabiliserResponse(
            amortissement=AmortissementRead.model_validate(row),
            ecriture=EcritureRead.model_validate(ecriture),
        )
    except AppError as exc:
        raise_http_from_app(exc)


@router.get("/ecritures", response_model=PaginatedResponse[EcritureRead])
async def list_ecritures(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    date_debut: date | None = None,
    date_fin: date | None = None,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    filters = []
    if date_debut is not None:
        filters.append(EcritureComptable.date_ecriture >= date_debut)
    if date_fin is not None:
        filters.append(EcritureComptable.date_ecriture <= date_fin)

    count = await db.execute(select(func.count()).select_from(EcritureComptable).where(*filters))
    total = int(count.scalar_one())
    result = await db.execute(
        select(EcritureComptable)
        .where(*filters)
        .order_by(EcritureComptable.date_ecriture.desc())
        .offset(page_offset(page, size))
        .limit(size)
    )
    items = list(result.scalars().all())
    return to_paginated(items, total, page, size, EcritureRead.model_validate)


@router.post("/ecritures", response_model=EcritureRead, status_code=status.HTTP_201_CREATED)
async def create_ecriture(payload: EcritureCreate, _: User = Depends(require_roles("administrateur", "comptable")), db: AsyncSession = Depends(get_db)):
    row = EcritureComptable(**payload.model_dump(), generee_auto=False)
    db.add(row)
    await db.flush()
    return row
