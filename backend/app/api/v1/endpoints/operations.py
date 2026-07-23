from uuid import UUID



from fastapi import APIRouter, Depends, Query, Request, status

from sqlalchemy import select

from sqlalchemy.ext.asyncio import AsyncSession



from app.api.deps import get_current_user, require_roles

from app.core.exceptions import AppError, raise_http_from_app

from app.db.session import get_db

from app.models import Ajustement, Cession, Immobilisation, Rebut, Reevaluation, User

from app.schemas.common import PaginatedResponse

from app.schemas.operations import (

    AjustementCreate,

    AjustementCreateResponse,

    AjustementListRead,

    AjustementRead,

    CessionCreate,

    CessionListRead,

    CessionRead,

    CessionSortieResponse,

    RebutCreate,

    RebutListRead,

    RebutRead,

    RebutSortieResponse,

    ReevaluationCreate,

    ReevaluationCreateResponse,

    ReevaluationListRead,

    ReevaluationRead,

)

from app.services.operations_query import list_ajustements, list_cessions, list_rebuts, list_reevaluations

from app.services.operations_service import CessionService, RebutService

from app.services.reevaluation_service import AjustementService, ReevaluationService

from app.services.audit_helpers import record_audit



router = APIRouter(tags=["operations"])





def _cession_list_read(cession: Cession, immo: Immobilisation | None) -> CessionListRead:

    base = CessionRead.model_validate(cession)

    return CessionListRead(

        **base.model_dump(),

        code_inventaire=immo.code_inventaire if immo else None,

        designation=immo.designation if immo else None,

    )





def _rebut_list_read(rebut: Rebut, immo: Immobilisation | None) -> RebutListRead:

    base = RebutRead.model_validate(rebut)

    return RebutListRead(

        **base.model_dump(),

        code_inventaire=immo.code_inventaire if immo else None,

        designation=immo.designation if immo else None,

    )





def _reevaluation_list_read(row: Reevaluation, immo: Immobilisation | None) -> ReevaluationListRead:

    base = ReevaluationRead.model_validate(row)

    return ReevaluationListRead(

        **base.model_dump(),

        code_inventaire=immo.code_inventaire if immo else None,

        designation=immo.designation if immo else None,

    )





def _ajustement_list_read(row: Ajustement, immo: Immobilisation | None) -> AjustementListRead:

    base = AjustementRead.model_validate(row)

    return AjustementListRead(

        **base.model_dump(),

        code_inventaire=immo.code_inventaire if immo else None,

        designation=immo.designation if immo else None,

    )





@router.get("/cessions", response_model=PaginatedResponse[CessionListRead])

async def list_cessions_endpoint(

    page: int = Query(1, ge=1),

    size: int = Query(20, ge=1, le=100),

    _: User = Depends(get_current_user),

    db: AsyncSession = Depends(get_db),

):

    rows, total = await list_cessions(db, page, size)

    items = [_cession_list_read(c, immo) for c, immo in rows]

    return PaginatedResponse(items=items, total=total, page=page, size=size)





@router.get("/rebuts", response_model=PaginatedResponse[RebutListRead])

async def list_rebuts_endpoint(

    page: int = Query(1, ge=1),

    size: int = Query(20, ge=1, le=100),

    _: User = Depends(get_current_user),

    db: AsyncSession = Depends(get_db),

):

    rows, total = await list_rebuts(db, page, size)

    items = [_rebut_list_read(r, immo) for r, immo in rows]

    return PaginatedResponse(items=items, total=total, page=page, size=size)





@router.get("/reevaluations", response_model=PaginatedResponse[ReevaluationListRead])

async def list_reevaluations_endpoint(

    page: int = Query(1, ge=1),

    size: int = Query(20, ge=1, le=100),

    _: User = Depends(get_current_user),

    db: AsyncSession = Depends(get_db),

):

    rows, total = await list_reevaluations(db, page, size)

    items = [_reevaluation_list_read(r, immo) for r, immo in rows]

    return PaginatedResponse(items=items, total=total, page=page, size=size)





@router.get("/ajustements", response_model=PaginatedResponse[AjustementListRead])

async def list_ajustements_endpoint(

    page: int = Query(1, ge=1),

    size: int = Query(20, ge=1, le=100),

    _: User = Depends(get_current_user),

    db: AsyncSession = Depends(get_db),

):

    rows, total = await list_ajustements(db, page, size)

    items = [_ajustement_list_read(a, immo) for a, immo in rows]

    return PaginatedResponse(items=items, total=total, page=page, size=size)





@router.post("/cessions", response_model=CessionSortieResponse, status_code=status.HTTP_201_CREATED)

async def create_cession(

    payload: CessionCreate,

    request: Request,

    user: User = Depends(require_roles("administrateur", "comptable")),

    db: AsyncSession = Depends(get_db),

):

    try:

        row, ecriture_ids = await CessionService(db).create(payload)

        await record_audit(

            db,

            user=user,

            action="cession",

            entity="immobilisation",

            entity_id=str(payload.immobilisation_id),

            request=request,

            after={"prix": str(payload.prix_cession), "ecritures": len(ecriture_ids)},

        )

        return CessionSortieResponse(cession=CessionRead.model_validate(row), ecriture_ids=ecriture_ids)

    except AppError as exc:

        raise_http_from_app(exc)





@router.post("/rebuts", response_model=RebutSortieResponse, status_code=status.HTTP_201_CREATED)

async def create_rebut(

    payload: RebutCreate,

    request: Request,

    user: User = Depends(require_roles("administrateur", "comptable")),

    db: AsyncSession = Depends(get_db),

):

    try:

        row, ecriture_ids = await RebutService(db).create(payload)

        await record_audit(

            db,

            user=user,

            action="rebut",

            entity="immobilisation",

            entity_id=str(payload.immobilisation_id),

            request=request,

            after={"vnc": str(row.vnc), "ecritures": len(ecriture_ids)},

        )

        return RebutSortieResponse(rebut=RebutRead.model_validate(row), ecriture_ids=ecriture_ids)

    except AppError as exc:

        raise_http_from_app(exc)





@router.post("/reevaluations", response_model=ReevaluationCreateResponse, status_code=status.HTTP_201_CREATED)

async def create_reevaluation(

    payload: ReevaluationCreate,

    request: Request,

    user: User = Depends(require_roles("administrateur", "comptable")),

    db: AsyncSession = Depends(get_db),

):

    try:

        row, plan_regenere, ecriture_ids = await ReevaluationService(db).create(payload)

        await record_audit(

            db,

            user=user,

            action="reevaluation",

            entity="immobilisation",

            entity_id=str(payload.immobilisation_id),

            request=request,

            after={

                "ancienne": str(row.ancienne_valeur),

                "nouvelle": str(row.nouvelle_valeur),

                "plan_regenere": plan_regenere,

                "ecritures": len(ecriture_ids),

            },

        )

        return ReevaluationCreateResponse(

            reevaluation=ReevaluationRead.model_validate(row),

            plan_regenere=plan_regenere,

            ecriture_ids=ecriture_ids,

        )

    except AppError as exc:

        raise_http_from_app(exc)





@router.post("/ajustements", response_model=AjustementCreateResponse, status_code=status.HTTP_201_CREATED)

async def create_ajustement(

    payload: AjustementCreate,

    request: Request,

    user: User = Depends(require_roles("administrateur", "comptable")),

    db: AsyncSession = Depends(get_db),

):

    try:

        row, ecriture_ids = await AjustementService(db).create(payload)

        await record_audit(

            db,

            user=user,

            action="ajustement",

            entity="immobilisation",

            entity_id=str(payload.immobilisation_id),

            request=request,

            after={

                "type": payload.type_ajustement.value,

                "montant": str(payload.montant),

                "ecritures": len(ecriture_ids),

            },

        )

        return AjustementCreateResponse(ajustement=AjustementRead.model_validate(row), ecriture_ids=ecriture_ids)

    except AppError as exc:

        raise_http_from_app(exc)





@router.get("/reevaluations/immobilisation/{immobilisation_id}", response_model=list[ReevaluationRead])

async def list_reevaluations_for_immo(

    immobilisation_id: UUID,

    _: User = Depends(get_current_user),

    db: AsyncSession = Depends(get_db),

):

    result = await db.execute(

        select(Reevaluation)

        .where(Reevaluation.immobilisation_id == immobilisation_id)

        .order_by(Reevaluation.date_reevaluation.desc())

    )

    return list(result.scalars().all())


