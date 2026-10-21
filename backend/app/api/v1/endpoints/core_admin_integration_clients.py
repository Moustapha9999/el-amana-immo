"""CORE ADMIN — Studio d'intégration API, applications clientes (Phase 2, Login 1).

Fiches de configuration et demandes de droits sur les opérations du catalogue. Aucune authentification
machine-à-machine : rien ici ne permet à une application d'appeler l'API.
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_platform_permission
from app.db.session import get_db
from app.models import User
from app.schemas.integration_clients import (
    ClientStatut,
    Environnement,
    GrantStatut,
    IntegrationClientArchivage,
    IntegrationClientCreation,
    IntegrationClientFiche,
    IntegrationClientModification,
    IntegrationClientPage,
    IntegrationDocumentation,
    IntegrationGrant,
    IntegrationGrantDecision,
    IntegrationGrantDemande,
    IntegrationGrantListe,
    IntegrationHistorique,
    IntegrationOperationsAdmissibles,
)
from app.schemas.integration_execution import BilanSuppression
from app.services.integrations import clients as svc
from app.services.integrations import suppression
from app.services.permission_service import load_user_permission_codes

router = APIRouter(prefix="/plateforme/admin/integrations/clients", tags=["core-admin"])

_CLIENTS_VIEW = require_platform_permission(svc.P_CLIENTS_VIEW)
_CLIENTS_MANAGE = require_platform_permission(svc.P_CLIENTS_MANAGE)
_GRANTS_VIEW = require_platform_permission(svc.P_GRANTS_VIEW)
_GRANTS_MANAGE = require_platform_permission(svc.P_GRANTS_MANAGE)
_GRANTS_DECIDE = require_platform_permission(svc.P_GRANTS_MANAGE, svc.P_GRANTS_APPROVE)
_EXPORT = require_platform_permission(svc.P_EXPORT)

Tri = Literal["nom", "code", "statut", "environnement", "created_at", "updated_at", "nb_operations"]
Methode = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]


@router.get("", response_model=IntegrationClientPage)
async def lister_clients(
    q: str | None = Query(None, max_length=120),
    statut: ClientStatut | None = None,
    environnement: Environnement | None = None,
    inclure_archivees: bool = False,
    tri: Tri = "updated_at",
    ordre: Literal["asc", "desc"] = "desc",
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=100),
    _: User = Depends(_CLIENTS_VIEW),
    db: AsyncSession = Depends(get_db),
):
    return await svc.lister_clients(
        db, q=q, statut=statut, environnement=environnement, inclure_archivees=inclure_archivees,
        tri=tri, ordre=ordre, page=page, size=size,
    )


@router.post("", response_model=IntegrationClientFiche, status_code=201)
async def creer_client(
    payload: IntegrationClientCreation,
    request: Request,
    actor: User = Depends(_CLIENTS_MANAGE),
    db: AsyncSession = Depends(get_db),
):
    return await svc.creer_client(db, actor, payload.model_dump(), request)


@router.get("/{client_id}", response_model=IntegrationClientFiche)
async def fiche_client(
    client_id: uuid.UUID,
    _: User = Depends(_CLIENTS_VIEW),
    db: AsyncSession = Depends(get_db),
):
    return await svc.fiche_client(db, client_id)


@router.patch("/{client_id}", response_model=IntegrationClientFiche)
async def modifier_client(
    client_id: uuid.UUID,
    payload: IntegrationClientModification,
    request: Request,
    actor: User = Depends(_CLIENTS_MANAGE),
    db: AsyncSession = Depends(get_db),
):
    fournis = set(payload.model_fields_set) - {"revision"}
    return await svc.modifier_client(db, actor, client_id, payload.model_dump(), fournis, request)


@router.post("/{client_id}/archive", response_model=IntegrationClientFiche)
async def archiver_client(
    client_id: uuid.UUID,
    payload: IntegrationClientArchivage,
    request: Request,
    actor: User = Depends(_CLIENTS_MANAGE),
    db: AsyncSession = Depends(get_db),
):
    return await svc.archiver_client(db, actor, client_id, payload.revision, payload.motif, request)


@router.get("/{client_id}/dependances", response_model=BilanSuppression)
async def dependances_client(client_id: uuid.UUID, _: User = Depends(_CLIENTS_VIEW),
                             db: AsyncSession = Depends(get_db)):
    return await suppression.dependances_client(db, client_id)


@router.delete("/{client_id}", status_code=204)
async def supprimer_client(client_id: uuid.UUID, request: Request, revision: int = Query(..., ge=1),
                           actor: User = Depends(_CLIENTS_MANAGE), db: AsyncSession = Depends(get_db)):
    await suppression.supprimer_client(db, actor, client_id, revision, request)


@router.get("/{client_id}/grants", response_model=IntegrationGrantListe)
async def lister_grants(
    client_id: uuid.UUID,
    request: Request,
    statut: GrantStatut | None = None,
    _: User = Depends(_GRANTS_VIEW),
    db: AsyncSession = Depends(get_db),
):
    return await svc.lister_grants(db, request.app, client_id, statut)


@router.post("/{client_id}/grants", response_model=IntegrationGrantListe, status_code=201)
async def demander_operations(
    client_id: uuid.UUID,
    payload: IntegrationGrantDemande,
    request: Request,
    actor: User = Depends(_GRANTS_MANAGE),
    db: AsyncSession = Depends(get_db),
):
    return await svc.demander_operations(
        db, request.app, actor, client_id, payload.operation_ids, payload.justification, request
    )


@router.patch("/{client_id}/grants/{grant_id}", response_model=IntegrationGrant)
async def decider(
    client_id: uuid.UUID,
    grant_id: uuid.UUID,
    payload: IntegrationGrantDecision,
    request: Request,
    actor: User = Depends(_GRANTS_DECIDE),
    db: AsyncSession = Depends(get_db),
):
    have = await load_user_permission_codes(db, actor)
    return await svc.decider(db, request.app, actor, have, client_id, grant_id, payload.statut, payload.motif, request)


@router.get("/{client_id}/historique", response_model=IntegrationHistorique)
async def historique(
    client_id: uuid.UUID,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    _: User = Depends(_GRANTS_VIEW),
    db: AsyncSession = Depends(get_db),
):
    return await svc.historique(db, client_id, page=page, size=size)


@router.get("/{client_id}/operations-admissibles", response_model=IntegrationOperationsAdmissibles)
async def operations_admissibles(
    client_id: uuid.UUID,
    request: Request,
    q: str | None = Query(None, max_length=120),
    module: str | None = Query(None, max_length=80),
    methode: Methode | None = None,
    admissibles_seulement: bool = True,
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=100),
    _: User = Depends(_GRANTS_MANAGE),
    db: AsyncSession = Depends(get_db),
):
    return await svc.operations_admissibles(
        db, request.app, client_id, q=q, module=module, methode=methode,
        admissibles_seulement=admissibles_seulement, page=page, size=size,
    )


@router.get("/{client_id}/documentation", response_model=IntegrationDocumentation)
async def documentation(
    client_id: uuid.UUID,
    request: Request,
    actor: User = Depends(_EXPORT),
    db: AsyncSession = Depends(get_db),
):
    return await svc.documentation(db, request.app, actor, client_id, request)
