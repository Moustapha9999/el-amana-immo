from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.api.v1.endpoints.helpers import to_paginated
from app.core.exceptions import AppError
from app.core.exceptions import raise_http_from_app
from app.db.session import get_db
from app.models import User
from app.schemas.common import MessageResponse, PaginatedResponse
from app.schemas.organisation import (
    AgenceCreate,
    AgenceRead,
    AgenceUpdate,
    CentreCoutCreate,
    CentreCoutRead,
    DepartementCreate,
    DepartementRead,
    DirectionCreate,
    DirectionRead,
    FournisseurCreate,
    FournisseurRead,
)
from app.services.organisation_service import (
    AgenceService,
    CentreCoutService,
    DepartementService,
    DirectionService,
    FournisseurService,
)

router = APIRouter(tags=["organisation"])


def _handle_app_error(exc: AppError):
    raise_http_from_app(exc)


@router.get("/agences", response_model=PaginatedResponse[AgenceRead])
async def list_agences(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await AgenceService(db).list(page, size, search)
    return to_paginated(items, total, page, size, AgenceRead.model_validate)


@router.post("/agences", response_model=AgenceRead, status_code=status.HTTP_201_CREATED)
async def create_agence(
    payload: AgenceCreate,
    _: User = Depends(require_roles("administrateur", "comptable")),
    db: AsyncSession = Depends(get_db),
):
    return await AgenceService(db).create(payload)


@router.patch("/agences/{entity_id}", response_model=AgenceRead)
async def update_agence(entity_id: UUID, payload: AgenceUpdate, db: AsyncSession = Depends(get_db), _: User = Depends(require_roles("administrateur", "comptable"))):
    try:
        return await AgenceService(db).update(entity_id, payload)
    except AppError as exc:
        _handle_app_error(exc)


@router.delete("/agences/{entity_id}", response_model=MessageResponse)
async def delete_agence(entity_id: UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_roles("administrateur"))):
    try:
        await AgenceService(db).soft_delete(entity_id)
        return MessageResponse(message="Agence désactivée")
    except AppError as exc:
        _handle_app_error(exc)


@router.get("/directions", response_model=PaginatedResponse[DirectionRead])
async def list_directions(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), search: str | None = None, _: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    items, total = await DirectionService(db).list(page, size, search)
    return to_paginated(items, total, page, size, DirectionRead.model_validate)


@router.post("/directions", response_model=DirectionRead, status_code=status.HTTP_201_CREATED)
async def create_direction(payload: DirectionCreate, _: User = Depends(require_roles("administrateur", "comptable")), db: AsyncSession = Depends(get_db)):
    return await DirectionService(db).create(payload)


@router.get("/departements", response_model=PaginatedResponse[DepartementRead])
async def list_departements(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), search: str | None = None, _: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    items, total = await DepartementService(db).list(page, size, search)
    return to_paginated(items, total, page, size, DepartementRead.model_validate)


@router.post("/departements", response_model=DepartementRead, status_code=status.HTTP_201_CREATED)
async def create_departement(payload: DepartementCreate, _: User = Depends(require_roles("administrateur", "comptable")), db: AsyncSession = Depends(get_db)):
    return await DepartementService(db).create(payload)


@router.get("/centres-cout", response_model=PaginatedResponse[CentreCoutRead])
async def list_centres(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), search: str | None = None, _: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    items, total = await CentreCoutService(db).list(page, size, search)
    return to_paginated(items, total, page, size, CentreCoutRead.model_validate)


@router.post("/centres-cout", response_model=CentreCoutRead, status_code=status.HTTP_201_CREATED)
async def create_centre(payload: CentreCoutCreate, _: User = Depends(require_roles("administrateur", "comptable")), db: AsyncSession = Depends(get_db)):
    return await CentreCoutService(db).create(payload)


@router.get("/fournisseurs", response_model=PaginatedResponse[FournisseurRead])
async def list_fournisseurs(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), search: str | None = None, _: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    items, total = await FournisseurService(db).list(page, size, search)
    return to_paginated(items, total, page, size, FournisseurRead.model_validate)


@router.post("/fournisseurs", response_model=FournisseurRead, status_code=status.HTTP_201_CREATED)
async def create_fournisseur(payload: FournisseurCreate, _: User = Depends(require_roles("administrateur", "comptable")), db: AsyncSession = Depends(get_db)):
    return await FournisseurService(db).create(payload)
