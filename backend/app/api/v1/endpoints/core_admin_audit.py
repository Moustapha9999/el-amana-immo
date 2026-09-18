"""CORE ADMIN — audit (Login 1, core.admin.audit)."""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_platform_permission
from app.db.session import get_db
from app.models import User
from app.schemas.plateforme import CoreAdminAuditListRead
from app.services.core_admin_audit_service import CoreAdminAuditService

router = APIRouter(prefix="/plateforme/admin", tags=["core-admin"])

_AUDIT_PERM = require_platform_permission("core.admin.audit")


@router.get("/audit", response_model=CoreAdminAuditListRead)
async def list_core_admin_audit(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    entity: str | None = None,
    action: str | None = None,
    module_code: str | None = None,
    date_debut: date | None = None,
    date_fin: date | None = None,
    kind: str = Query("tous", pattern="^(tous|aujourd_hui|logins|mutations|core)$"),
    _: User = Depends(_AUDIT_PERM),
    db: AsyncSession = Depends(get_db),
):
    items, total, kpis, options = await CoreAdminAuditService(db).list_logs(
        page,
        size,
        search=search,
        entity=entity,
        action=action,
        module_code=module_code,
        date_debut=date_debut,
        date_fin=date_fin,
        kind=kind,
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "kpis": kpis,
        "modules": options["modules"],
        "entities": options["entities"],
    }
