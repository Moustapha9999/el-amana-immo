"""CORE ADMIN — destinations TEST approuvées (Phase 5, Login 1)."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_platform_permission
from app.db.session import get_db
from app.models import User
from app.schemas.integration_execution import (
    BilanSuppression,
    DestinationArchivage,
    DestinationCreation,
    DestinationModification,
    DestinationStatut,
    DestinationStatutIn,
)
from app.services.integrations import destinations as svc
from app.services.integrations import suppression
from app.services.permission_service import load_user_permission_codes

router = APIRouter(prefix="/plateforme/admin/integrations/destinations", tags=["core-admin"])
_VIEW = require_platform_permission(svc.P_VIEW)
_MANAGE = require_platform_permission(svc.P_MANAGE)
_STATUT = require_platform_permission(svc.P_MANAGE, svc.P_APPROVE)


@router.get("")
async def lister(
    q: str | None = Query(None, max_length=120),
    statut: DestinationStatut | None = None,
    fournisseur_id: uuid.UUID | None = None,
    inclure_archivees: bool = False,
    tri: Literal["nom", "code", "statut", "valide_le", "updated_at"] = "updated_at",
    ordre: Literal["asc", "desc"] = "desc",
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=100),
    _: User = Depends(_VIEW),
    db: AsyncSession = Depends(get_db),
):
    return await svc.lister_destinations(
        db, q=q, statut=statut, fournisseur_id=fournisseur_id,
        inclure_archivees=inclure_archivees, tri=tri, ordre=ordre, page=page, size=size,
    )


@router.post("", status_code=201)
async def creer(payload: DestinationCreation, request: Request, actor: User = Depends(_MANAGE),
                db: AsyncSession = Depends(get_db)):
    return await svc.creer_destination(db, actor, payload.model_dump(), request)


@router.get("/{destination_id}")
async def fiche(destination_id: uuid.UUID, _: User = Depends(_VIEW), db: AsyncSession = Depends(get_db)):
    return await svc.fiche_destination(db, destination_id)


@router.patch("/{destination_id}")
async def modifier(destination_id: uuid.UUID, payload: DestinationModification, request: Request,
                   actor: User = Depends(_MANAGE), db: AsyncSession = Depends(get_db)):
    fournis = set(payload.model_fields_set) - {"revision"}
    return await svc.modifier_destination(db, actor, destination_id, payload.model_dump(), fournis, request)


@router.post("/{destination_id}/statut")
async def statut(destination_id: uuid.UUID, payload: DestinationStatutIn, request: Request,
                 actor: User = Depends(_STATUT), db: AsyncSession = Depends(get_db)):
    have = await load_user_permission_codes(db, actor)
    return await svc.changer_statut(
        db, actor, have, destination_id, payload.revision, payload.statut, payload.motif, request
    )


@router.post("/{destination_id}/archive")
async def archiver(destination_id: uuid.UUID, payload: DestinationArchivage, request: Request,
                   actor: User = Depends(_MANAGE), db: AsyncSession = Depends(get_db)):
    return await svc.archiver_destination(db, actor, destination_id, payload.revision, payload.motif, request)


@router.get("/{destination_id}/dependances", response_model=BilanSuppression)
async def dependances(destination_id: uuid.UUID, _: User = Depends(_VIEW), db: AsyncSession = Depends(get_db)):
    return await suppression.dependances_destination(db, destination_id)


@router.delete("/{destination_id}", status_code=204)
async def supprimer(destination_id: uuid.UUID, request: Request, revision: int = Query(..., ge=1),
                    actor: User = Depends(_MANAGE), db: AsyncSession = Depends(get_db)):
    await suppression.supprimer_destination(db, actor, destination_id, revision, request)


@router.get("/{destination_id}/historique")
async def historique(destination_id: uuid.UUID, page: int = Query(1, ge=1),
                     size: int = Query(50, ge=1, le=200), _: User = Depends(_VIEW),
                     db: AsyncSession = Depends(get_db)):
    return await svc.historique(db, destination_id, page=page, size=size)
