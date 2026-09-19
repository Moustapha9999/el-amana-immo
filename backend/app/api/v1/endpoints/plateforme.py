from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_platform_user, require_platform_permission
from app.core.config import get_settings
from app.data.plateforme_catalogue import FUNCTIONAL_PERMISSIONS, RBAC_ROLES, ROLE_PERMISSIONS
from app.db.session import get_db
from app.models import User
from app.schemas.plateforme import (
    CoreAdminDashboardRead,
    CoreManifestRead,
    PlateformeEspaceRead,
    PlateformeHubActivityRead,
    PlateformeHubSeriePointRead,
    PlateformeHubSummaryRead,
    PlateformeModuleRead,
)
from app.services.core_admin_service import CoreAdminService
from app.services.plateforme_access_service import PlateformeAccessService
from app.services.plateforme_hub_service import PlateformeHubService

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


@router.get("/me/hub", response_model=PlateformeHubSummaryRead)
async def me_hub(
    user: User = Depends(get_platform_user),
    db: AsyncSession = Depends(get_db),
    jours: int = 7,
):
    """Résumé Dashboard Global — scopé par profil (admin / responsable / utilisateur)."""
    return await PlateformeHubService(db).summary(user, jours=jours if jours in {7, 30, 90} else 7)


@router.get("/me/usage", response_model=list[PlateformeHubSeriePointRead])
async def me_usage(
    user: User = Depends(get_platform_user),
    db: AsyncSession = Depends(get_db),
    jours: int = 7,
):
    """Série d'activité agrégée (7 / 30 / 90 jours), filtrée côté backend."""
    return await PlateformeHubService(db).usage_series(
        user, jours=jours if jours in {7, 30, 90} else 7
    )


@router.get("/me/activity", response_model=list[PlateformeHubActivityRead])
async def me_activity(
    user: User = Depends(get_platform_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 20,
    offset: int = 0,
):
    """Activité récente scopée selon le profil (audit)."""
    return await PlateformeHubService(db).activity(
        user,
        limit=min(max(limit, 1), 50),
        offset=max(offset, 0),
    )


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


@router.get("/core", response_model=CoreManifestRead)
async def core_manifest(
    _user: User = Depends(get_platform_user),
    db: AsyncSession = Depends(get_db),
):
    """Inventaire du CORE (départements, modules, permissions, GED prévue)."""
    service = PlateformeAccessService(db)
    await service.ensure_catalogue()
    espaces = await service.list_espaces()
    catalogue = []
    for espace in espaces:
        catalogue.append(
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
    return {
        "chain": "utilisateur → département → module → permission",
        "espaces": catalogue,
        "permissions": [
            {"code": code, "label": label, "module": module}
            for code, label, module in FUNCTIONAL_PERMISSIONS
        ],
        "roles": [
            {
                "code": code,
                "label": label,
                "description": description,
                "permission_codes": list(ROLE_PERMISSIONS.get(code, ())),
            }
            for code, label, description in RBAC_ROLES
        ],
        "ged": {
            "statut": "reserve",
            "table": "ged_documents",
            "storage": get_settings().ged_dir,
        },
    }


@router.get("/admin/dashboard", response_model=CoreAdminDashboardRead)
async def core_admin_dashboard(
    _user: User = Depends(require_platform_permission("core.admin.access")),
    db: AsyncSession = Depends(get_db),
):
    access = PlateformeAccessService(db)
    await access.ensure_catalogue()
    return await CoreAdminService(db).dashboard()
