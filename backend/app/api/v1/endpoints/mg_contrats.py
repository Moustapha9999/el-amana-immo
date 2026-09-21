"""API Contrats & échéances MG."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_module_access, require_permission
from app.models.auth import User
from app.schemas.mg_ops import ContratCreate, ContratOut, ContratUpdate
from app.services.mg_ops_service import MgOpsService

router = APIRouter(prefix="/mg/contrats", tags=["mg-contrats"])
_module = [Depends(require_module_access("contrats-echeances"))]


@router.get("", response_model=list[ContratOut], dependencies=_module)
async def list_contrats(
    statut: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.contrats.view")),
):
    return await MgOpsService(db).list_contrats(statut=statut)


@router.get("/alertes", response_model=list[ContratOut], dependencies=_module)
async def list_alertes(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.contrats.view")),
):
    return await MgOpsService(db).list_alertes()


@router.post("", response_model=ContratOut, dependencies=_module)
async def create_contrat(
    body: ContratCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.contrats.create")),
):
    return await MgOpsService(db).create_contrat(body)


@router.get("/{contrat_id}", response_model=ContratOut, dependencies=_module)
async def get_contrat(
    contrat_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.contrats.view")),
):
    return await MgOpsService(db).get_contrat(contrat_id)


@router.patch("/{contrat_id}", response_model=ContratOut, dependencies=_module)
async def update_contrat(
    contrat_id: UUID,
    body: ContratUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.contrats.manage")),
):
    return await MgOpsService(db).update_contrat(contrat_id, body)
