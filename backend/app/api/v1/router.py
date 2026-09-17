from fastapi import APIRouter, Depends

from app.api.v1.endpoints import (
    archives,
    auth,
    comptabilite,
    exercices,
    immobilisations,
    notifications,
    operations,
    organisation,
    plateforme,
    reporting,
    users,
)
from app.api.deps import require_module_access

api_router = APIRouter()
router = api_router
api_router.include_router(auth.router)
api_router.include_router(plateforme.router)

_immo = [Depends(require_module_access("immobilisations"))]
api_router.include_router(users.router, dependencies=_immo)
api_router.include_router(organisation.router, dependencies=_immo)
api_router.include_router(immobilisations.router, dependencies=_immo)
api_router.include_router(comptabilite.router, dependencies=_immo)
api_router.include_router(operations.router, dependencies=_immo)
api_router.include_router(notifications.router, dependencies=_immo)
api_router.include_router(reporting.router, dependencies=_immo)
api_router.include_router(archives.router, dependencies=_immo)
api_router.include_router(exercices.router, dependencies=_immo)
