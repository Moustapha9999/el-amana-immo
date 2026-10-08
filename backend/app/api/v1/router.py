from fastapi import APIRouter, Depends

from app.api.v1.endpoints import (
    archives,
    archives_vues,
    auth,
    clientele,
    comptabilite,
    core_admin_audit,
    core_admin_catalogue,
    core_admin_control,
    core_admin_ops,
    core_admin_query,
    core_admin_rbac,
    core_admin_sessions,
    core_admin_users,
    documents,
    eer,
    exercices,
    formation,
    ged,
    immobilisations,
    mg_achats,
    mg_archives,
    mg_contrats,
    mg_facturation,
    mg_notes,
    mg_requests,
    mg_stock,
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
api_router.include_router(core_admin_users.router)
api_router.include_router(core_admin_catalogue.router)
api_router.include_router(core_admin_rbac.router)
api_router.include_router(core_admin_sessions.router)
api_router.include_router(core_admin_audit.router)
api_router.include_router(core_admin_ops.router)
api_router.include_router(core_admin_control.router)
api_router.include_router(core_admin_query.router)
api_router.include_router(users.router)
api_router.include_router(notifications.router)
api_router.include_router(ged.router)
api_router.include_router(documents.router)
api_router.include_router(archives_vues.router)
api_router.include_router(mg_stock.router)
api_router.include_router(mg_achats.router)
api_router.include_router(mg_notes.router)
api_router.include_router(mg_contrats.router)
api_router.include_router(mg_facturation.router)
api_router.include_router(mg_facturation.points_router)
api_router.include_router(mg_archives.router)
api_router.include_router(mg_requests.me_router)
api_router.include_router(mg_requests.mg_router)
api_router.include_router(mg_requests.batch_router)
api_router.include_router(eer.router, dependencies=[Depends(require_module_access("eer"))])
api_router.include_router(formation.router, dependencies=[Depends(require_module_access("formation"))])
api_router.include_router(clientele.router, dependencies=[Depends(require_module_access("clientele"))])

_immo = [Depends(require_module_access("immobilisations"))]
api_router.include_router(organisation.router, dependencies=_immo)
api_router.include_router(immobilisations.router, dependencies=_immo)
api_router.include_router(comptabilite.router, dependencies=_immo)
api_router.include_router(operations.router, dependencies=_immo)
api_router.include_router(reporting.router, dependencies=_immo)
api_router.include_router(archives.router, dependencies=_immo)
api_router.include_router(exercices.router, dependencies=_immo)
