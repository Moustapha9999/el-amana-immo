"""CORE ADMIN — exécution contrôlée de tests d'API externes (Phase 5, Login 1).

Aucune de ces routes ne prend une URL en entrée. L'aperçu ne fait aucun appel réseau.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_platform_permission
from app.db.session import get_db
from app.models import User
from app.schemas.integration_execution import ApercuTestIn, ExecuterTestIn
from app.services.integrations import executeur as exe
from app.services.integrations import supervision as sup

router = APIRouter(prefix="/plateforme/admin/integrations", tags=["core-admin"])
_VIEW = require_platform_permission(exe.P_VIEW)
_EXEC = require_platform_permission(exe.P_EXECUTE)


@router.post("/tests/apercu")
async def apercu(payload: ApercuTestIn, _: User = Depends(_EXEC), db: AsyncSession = Depends(get_db)):
    return await exe.apercu(
        db, fournisseur_id=payload.fournisseur_id, operation_id=payload.operation_id,
        destination_id=payload.destination_id, parametres_chemin=payload.parametres_chemin,
        parametres_requete=payload.parametres_requete,
    )


@router.post("/tests/executer")
async def executer(payload: ExecuterTestIn, request: Request, actor: User = Depends(_EXEC),
                   db: AsyncSession = Depends(get_db)):
    return await exe.executer(
        db, actor, request, fournisseur_id=payload.fournisseur_id,
        operation_id=payload.operation_id, destination_id=payload.destination_id,
        parametres_chemin=payload.parametres_chemin, parametres_requete=payload.parametres_requete,
    )


@router.get("/executions")
async def lister_executions(
    fournisseur_id: uuid.UUID | None = None,
    destination_id: uuid.UUID | None = None,
    operation_id: uuid.UUID | None = None,
    statut: str | None = Query(None, max_length=30),
    depuis: datetime | None = None,
    jusqua: datetime | None = None,
    q: str | None = Query(None, max_length=120),
    tri: Literal["started_at", "duree_ms", "statut", "http_status"] = "started_at",
    ordre: Literal["asc", "desc"] = "desc",
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=100),
    _: User = Depends(_VIEW),
    db: AsyncSession = Depends(get_db),
):
    return await sup.lister_executions(
        db, page=page, size=size, tri=tri, ordre=ordre, fournisseur_id=fournisseur_id,
        destination_id=destination_id, operation_id=operation_id, statut=statut, depuis=depuis, jusqua=jusqua, q=q,
    )


@router.get("/executions/{execution_id}")
async def execution(execution_id: uuid.UUID, _: User = Depends(_VIEW), db: AsyncSession = Depends(get_db)):
    return await exe.execution_detail(db, execution_id)
