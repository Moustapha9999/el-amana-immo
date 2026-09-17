from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_platform_user
from app.db.session import get_db
from app.models import User
from app.schemas.plateforme import PlateformeEspaceRead, PlateformeModuleRead
from app.services.plateforme_access_service import PlateformeAccessService

router = APIRouter(prefix="/plateforme", tags=["plateforme"])


@router.get("/espaces", response_model=list[PlateformeEspaceRead])
async def list_espaces(
    user: User = Depends(get_platform_user),
    db: AsyncSession = Depends(get_db),
):
    service = PlateformeAccessService(db)
    await service.ensure_catalogue()
    espaces = await service.list_espaces()
    return service.serialize_espaces_for(user, espaces)


@router.get("/modules/{module_code}", response_model=PlateformeModuleRead)
async def get_module(
    module_code: str,
    user: User = Depends(get_platform_user),
    db: AsyncSession = Depends(get_db),
):
    service = PlateformeAccessService(db)
    await service.ensure_catalogue()
    payload = await service.serialize_module(user, module_code)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module introuvable")
    return payload


@router.get("/catalogue", response_model=list[PlateformeEspaceRead])
async def catalogue(
    user: User = Depends(get_platform_user),
    db: AsyncSession = Depends(get_db),
):
    """Catalogue complet (pour l'administration des grants), sans filtrer les non-autorisés."""
    service = PlateformeAccessService(db)
    await service.ensure_catalogue()
    espaces = await service.list_espaces()
    items: list[dict] = []
    for espace in espaces:
        items.append(
            {
                "id": espace.code,
                "titre": espace.label,
                "description": espace.description,
                "route": espace.route,
                "statut": espace.statut,
                "accessible": True,
                "modules": [
                    {
                        "id": mod.code,
                        "titre": mod.label,
                        "description": mod.description,
                        "route": f"/modules/{mod.code}/acces" if mod.statut == "actif" else None,
                        "entry_path": mod.entry_path,
                        "statut": mod.statut,
                        "accessible": True,
                    }
                    for mod in sorted(espace.modules, key=lambda m: (m.sort_order, m.label))
                    if mod.is_active
                ],
            }
        )
    return items
