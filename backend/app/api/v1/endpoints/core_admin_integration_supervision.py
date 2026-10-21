"""CORE ADMIN — supervision des intégrations (Phase 6, Login 1). Aucun appel sortant."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_platform_permission
from app.db.session import get_db
from app.models import User
from app.schemas.integration_execution import AlerteStatutIn
from app.services.integrations import supervision as svc

router = APIRouter(prefix="/plateforme/admin/integrations/supervision", tags=["core-admin"])
_VIEW = require_platform_permission(svc.P_VIEW)
_MANAGE = require_platform_permission(svc.P_MANAGE)
_EXPORT = require_platform_permission(svc.P_EXPORT)


@router.get("")
async def tableau(
    depuis: datetime | None = None,
    jusqua: datetime | None = None,
    fournisseur_id: uuid.UUID | None = None,
    destination_id: uuid.UUID | None = None,
    _: User = Depends(_VIEW),
    db: AsyncSession = Depends(get_db),
):
    return await svc.tableau_bord(
        db, depuis=depuis, jusqua=jusqua, fournisseur_id=fournisseur_id, destination_id=destination_id,
    )


@router.get("/alertes")
async def alertes(
    statut: str | None = Query(None, max_length=20),
    type_: str | None = Query(None, alias="type", max_length=40),
    niveau: str | None = Query(None, max_length=20),
    depuis: datetime | None = None,
    jusqua: datetime | None = None,
    fournisseur_id: uuid.UUID | None = None,
    q: str | None = Query(None, max_length=120),
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=100),
    _: User = Depends(_VIEW),
    db: AsyncSession = Depends(get_db),
):
    return await svc.lister_alertes(
        db, statut=statut, type_=type_, niveau=niveau, depuis=depuis, jusqua=jusqua,
        fournisseur_id=fournisseur_id, q=q, page=page, size=size,
    )


@router.patch("/alertes/{alerte_id}")
async def changer_alerte(alerte_id: uuid.UUID, payload: AlerteStatutIn, request: Request,
                         actor: User = Depends(_MANAGE), db: AsyncSession = Depends(get_db)):
    return await svc.changer_alerte(db, actor, alerte_id, payload.statut, request)


@router.get("/alertes/{alerte_id}/historique")
async def historique_alerte(alerte_id: uuid.UUID, _: User = Depends(_VIEW), db: AsyncSession = Depends(get_db)):
    return await svc.historique_alerte(db, alerte_id)


@router.get("/export")
async def exporter(
    request: Request,
    fournisseur_id: uuid.UUID | None = None,
    destination_id: uuid.UUID | None = None,
    operation_id: uuid.UUID | None = None,
    statut: str | None = Query(None, max_length=30),
    depuis: datetime | None = None,
    jusqua: datetime | None = None,
    q: str | None = Query(None, max_length=120),
    actor: User = Depends(_EXPORT),
    db: AsyncSession = Depends(get_db),
):
    nom, contenu = await svc.exporter_csv(
        db, actor, request, fournisseur_id=fournisseur_id, destination_id=destination_id,
        operation_id=operation_id, statut=statut, depuis=depuis, jusqua=jusqua, q=q,
    )
    return Response(
        content=contenu,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nom}"'},
    )
