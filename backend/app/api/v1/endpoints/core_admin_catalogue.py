from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_platform_permission
from app.db.session import get_db
from app.models import User
from app.schemas.common import MessageResponse
from app.schemas.plateforme import (
    CoreAdminEspaceFiche,
    CoreAdminEspaceListRead,
    CoreAdminEspaceUpdate,
    CoreAdminEspaceWrite,
    CoreAdminModuleListRead,
    CoreAdminModuleOptions,
    CoreAdminModuleRead,
    CoreAdminModuleUpdate,
    CoreAdminModuleWrite,
)
from app.services.audit_helpers import record_audit
from app.services.core_admin_catalogue_service import CoreAdminCatalogueService

router = APIRouter(prefix="/plateforme/admin", tags=["core-admin"])

_DEPT_PERM = require_platform_permission("core.admin.departments")
_MOD_PERM = require_platform_permission("core.admin.modules")


def _http_from_value_error(exc: ValueError) -> HTTPException:
    detail = str(exc)
    missing = detail.endswith("introuvable")
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND if missing else status.HTTP_400_BAD_REQUEST,
        detail=detail,
    )


async def _audit(
    db: AsyncSession,
    *,
    actor: User,
    action: str,
    entity: str,
    entity_id: str,
    request: Request,
    after: dict | None = None,
) -> None:
    await record_audit(
        db,
        user=actor,
        action=action,
        entity=entity,
        entity_id=entity_id,
        request=request,
        after=after,
        module_code="core",
    )


@router.get("/departments", response_model=CoreAdminEspaceListRead)
async def list_departments(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    statut: Literal["tous", "actif", "bientot", "inactif"] = Query("tous"),
    _: User = Depends(_DEPT_PERM),
    db: AsyncSession = Depends(get_db),
):
    items, total, kpis = await CoreAdminCatalogueService(db).list_espaces(
        page, size, search=search, statut=statut
    )
    return {"items": items, "total": total, "page": page, "size": size, "kpis": kpis}


@router.post("/departments", response_model=CoreAdminEspaceFiche, status_code=status.HTTP_201_CREATED)
async def create_department(
    payload: CoreAdminEspaceWrite,
    request: Request,
    actor: User = Depends(_DEPT_PERM),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await CoreAdminCatalogueService(db).create_espace(payload)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    await _audit(
        db,
        actor=actor,
        action="create",
        entity="espace",
        entity_id=row["id"],
        request=request,
        after={"code": row["code"], "statut": row["statut"]},
    )
    return row


@router.get("/departments/{espace_id}", response_model=CoreAdminEspaceFiche)
async def get_department(
    espace_id: UUID,
    _: User = Depends(_DEPT_PERM),
    db: AsyncSession = Depends(get_db),
):
    fiche = await CoreAdminCatalogueService(db).espace_fiche(espace_id)
    if fiche is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Département introuvable")
    return fiche


@router.patch("/departments/{espace_id}", response_model=CoreAdminEspaceFiche)
async def update_department(
    espace_id: UUID,
    payload: CoreAdminEspaceUpdate,
    request: Request,
    actor: User = Depends(_DEPT_PERM),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await CoreAdminCatalogueService(db).update_espace(espace_id, payload)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    await _audit(
        db,
        actor=actor,
        action="update",
        entity="espace",
        entity_id=row["id"],
        request=request,
        after={"code": row["code"], "statut": row["statut"]},
    )
    return row


@router.post("/departments/{espace_id}/deactivate", response_model=CoreAdminEspaceFiche)
async def deactivate_department(
    espace_id: UUID,
    request: Request,
    actor: User = Depends(_DEPT_PERM),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await CoreAdminCatalogueService(db).set_espace_active(espace_id, active=False)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    await _audit(db, actor=actor, action="deactivate", entity="espace", entity_id=row["id"], request=request)
    return row


@router.post("/departments/{espace_id}/activate", response_model=CoreAdminEspaceFiche)
async def activate_department(
    espace_id: UUID,
    request: Request,
    actor: User = Depends(_DEPT_PERM),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await CoreAdminCatalogueService(db).set_espace_active(espace_id, active=True)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    await _audit(db, actor=actor, action="activate", entity="espace", entity_id=row["id"], request=request)
    return row


@router.delete("/departments/{espace_id}", response_model=MessageResponse)
async def delete_department(
    espace_id: UUID,
    request: Request,
    actor: User = Depends(_DEPT_PERM),
    db: AsyncSession = Depends(get_db),
):
    try:
        await CoreAdminCatalogueService(db).delete_espace(espace_id)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    await _audit(db, actor=actor, action="delete", entity="espace", entity_id=str(espace_id), request=request)
    return MessageResponse(message="Département supprimé")


@router.get("/modules", response_model=CoreAdminModuleListRead)
async def list_modules(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    statut: Literal["tous", "actif", "bientot", "inactif"] = Query("tous"),
    espace_id: UUID | None = Query(None),
    _: User = Depends(_MOD_PERM),
    db: AsyncSession = Depends(get_db),
):
    items, total, kpis = await CoreAdminCatalogueService(db).list_modules(
        page, size, search=search, statut=statut, espace_id=espace_id
    )
    return {"items": items, "total": total, "page": page, "size": size, "kpis": kpis}


@router.get("/modules/options", response_model=CoreAdminModuleOptions)
async def module_options(
    _: User = Depends(_MOD_PERM),
    db: AsyncSession = Depends(get_db),
):
    items, _, _ = await CoreAdminCatalogueService(db).list_espaces(1, 100, statut="tous")
    return {
        "espaces": [
            {"id": row["id"], "code": row["code"], "label": row["label"], "is_active": row["is_active"]}
            for row in items
        ]
    }


@router.post("/modules", response_model=CoreAdminModuleRead, status_code=status.HTTP_201_CREATED)
async def create_module(
    payload: CoreAdminModuleWrite,
    request: Request,
    actor: User = Depends(_MOD_PERM),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await CoreAdminCatalogueService(db).create_module(payload)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    await _audit(
        db,
        actor=actor,
        action="create",
        entity="module",
        entity_id=row["id"],
        request=request,
        after={"code": row["code"], "statut": row["statut"]},
    )
    return row


@router.get("/modules/{module_id}", response_model=CoreAdminModuleRead)
async def get_module(
    module_id: UUID,
    _: User = Depends(_MOD_PERM),
    db: AsyncSession = Depends(get_db),
):
    fiche = await CoreAdminCatalogueService(db).module_fiche(module_id)
    if fiche is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module introuvable")
    return fiche


@router.patch("/modules/{module_id}", response_model=CoreAdminModuleRead)
async def update_module(
    module_id: UUID,
    payload: CoreAdminModuleUpdate,
    request: Request,
    actor: User = Depends(_MOD_PERM),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await CoreAdminCatalogueService(db).update_module(module_id, payload)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    await _audit(
        db,
        actor=actor,
        action="update",
        entity="module",
        entity_id=row["id"],
        request=request,
        after={"code": row["code"], "statut": row["statut"]},
    )
    return row


@router.post("/modules/{module_id}/deactivate", response_model=CoreAdminModuleRead)
async def deactivate_module(
    module_id: UUID,
    request: Request,
    actor: User = Depends(_MOD_PERM),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await CoreAdminCatalogueService(db).set_module_active(module_id, active=False)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    await _audit(db, actor=actor, action="deactivate", entity="module", entity_id=row["id"], request=request)
    return row


@router.post("/modules/{module_id}/activate", response_model=CoreAdminModuleRead)
async def activate_module(
    module_id: UUID,
    request: Request,
    actor: User = Depends(_MOD_PERM),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await CoreAdminCatalogueService(db).set_module_active(module_id, active=True)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    await _audit(db, actor=actor, action="activate", entity="module", entity_id=row["id"], request=request)
    return row


@router.delete("/modules/{module_id}", response_model=MessageResponse)
async def delete_module(
    module_id: UUID,
    request: Request,
    actor: User = Depends(_MOD_PERM),
    db: AsyncSession = Depends(get_db),
):
    try:
        await CoreAdminCatalogueService(db).delete_module(module_id)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    await _audit(db, actor=actor, action="delete", entity="module", entity_id=str(module_id), request=request)
    return MessageResponse(message="Module supprimé")
