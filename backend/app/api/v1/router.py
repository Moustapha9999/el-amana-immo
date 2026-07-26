from fastapi import APIRouter

from app.api.v1.endpoints import (
    archives,
    auth,
    comptabilite,
    immobilisations,
    notifications,
    operations,
    organisation,
    reporting,
    users,
)

api_router = APIRouter()
router = api_router
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(organisation.router)
api_router.include_router(immobilisations.router)
api_router.include_router(comptabilite.router)
api_router.include_router(operations.router)
api_router.include_router(notifications.router)
api_router.include_router(reporting.router)
api_router.include_router(archives.router)
