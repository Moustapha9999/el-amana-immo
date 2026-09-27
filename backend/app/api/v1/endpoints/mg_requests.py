"""API Demandes — demandeur (tout département) + inbox / regroupements MG."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_demandes_module, require_module_access, require_permission
from app.data.demandes_engine import espace_for_module
from app.models.auth import User
from app.schemas.common import MessageResponse
from app.schemas.mg_requests import (
    AssignIn,
    BatchCreate,
    BatchItemsIn,
    BatchListOut,
    BatchOut,
    BatchUpdate,
    CategoryIn,
    CategoryOut,
    CommentBody,
    CommentIn,
    DashboardOut,
    GrantedIn,
    HistoryListOut,
    MineDashboardOut,
    MineDocumentListOut,
    RecategorizeIn,
    RequestCreate,
    RequestListOut,
    RequestOut,
    RequestUpdate,
)
from app.services.mg_pdf_service import pdf_employee_request
from app.services.mg_requests_events import audit_request
from app.services.mg_requests_service import MgRequestsService

me_router = APIRouter(prefix="/me/requests", tags=["demandes"])
mg_router = APIRouter(prefix="/mg/requests", tags=["demandes-mg"])

_me = [Depends(require_demandes_module())]
_mg = [Depends(require_module_access("demandes-mg"))]


def _source(request: Request) -> tuple[str, str]:
    module = getattr(request.state, "bea_module_code", None) or "demandes-comptabilite"
    espace = getattr(request.state, "bea_espace_code", None) or espace_for_module(module) or "comptabilite"
    return espace, module


async def _serialize_many(svc: MgRequestsService, rows) -> list[RequestOut]:
    return [await svc.serialize(r) for r in rows]


@me_router.get("/categories", response_model=list[CategoryOut], dependencies=_me)
async def me_categories(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.request.mine.view", "mg.request.mine.create")),
):
    source, _ = _source(request)
    return await MgRequestsService(db).list_categories(active_only=True, source_espace=source)


@me_router.get("/refs", dependencies=_me)
async def me_refs(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.request.mine.view", "mg.request.mine.create")),
):
    return await MgRequestsService(db).refs()


@me_router.get("/dashboard", response_model=MineDashboardOut, dependencies=_me)
async def me_dashboard(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.request.mine.view")),
):
    return await MgRequestsService(db).mine_dashboard(user.id)


@me_router.get("/documents", response_model=MineDocumentListOut, dependencies=_me)
async def me_documents(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.request.mine.view")),
):
    items = await MgRequestsService(db).mine_documents(user.id)
    return MineDocumentListOut(items=items, total=len(items))


@me_router.get("/history", response_model=HistoryListOut, dependencies=_me)
async def me_history(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.request.mine.view")),
):
    items = await MgRequestsService(db).mine_history(user.id)
    return HistoryListOut(items=items, total=len(items))


@me_router.get("", response_model=RequestListOut, dependencies=_me)
async def me_list(
    q: str | None = None,
    statut: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.request.mine.view")),
):
    svc = MgRequestsService(db)
    rows, total = await svc.list_requests(q=q, statut=statut, mine=user.id, page=page, size=size)
    return RequestListOut(items=await _serialize_many(svc, rows), total=total, page=page, size=size)


@me_router.post("", response_model=RequestOut, dependencies=_me)
async def me_create(
    data: RequestCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.request.mine.create")),
):
    source, module = _source(request)
    svc = MgRequestsService(db)
    row = await svc.create_request(data, user, source_espace_code=source, source_module_code=module)
    await audit_request(
        db, user, "REQUEST_CREATED", "mg_employee_request", row.id, request=request,
        espace_code=source, module_code=module,
    )
    return await svc.serialize(row)


@me_router.get("/{request_id}", response_model=RequestOut, dependencies=_me)
async def me_get(
    request_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.request.mine.view")),
):
    svc = MgRequestsService(db)
    row = await svc._load(request_id)
    if row.requester_id != user.id and not user.is_superuser:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Demande non autorisée")
    return await svc.serialize(row)


@me_router.get("/{request_id}/pdf", dependencies=_me)
async def me_pdf(
    request_id: UUID,
    visas: str = Query("agence,mg"),
    department: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.request.mine.view")),
):
    from app.data.demandes_engine import ESPACE_LABELS
    from app.models.organisation import Departement

    svc = MgRequestsService(db)
    row = await svc._load(request_id)
    if row.requester_id != user.id and not user.is_superuser:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Demande non autorisée")
    requester = await db.get(User, row.requester_id)
    dept = await db.get(Departement, row.department_id) if row.department_id else None
    department_label = (department or "").strip() or (
        (dept.libelle if dept else None)
        or ESPACE_LABELS.get(row.source_espace_code or "", "")
        or "—"
    )
    payload = pdf_employee_request(
        row,
        requester_name=(requester.full_name if requester else None) or "—",
        department_label=department_label,
        category_name=(row.category.name if row.category else None) or "—",
        visas=visas,
    )
    filename = f"{row.request_number}.pdf"
    return Response(
        content=payload,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@me_router.patch("/{request_id}", response_model=RequestOut, dependencies=_me)
async def me_update(
    request_id: UUID,
    data: RequestUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.request.mine.update")),
):
    svc = MgRequestsService(db)
    row = await svc.update_request(request_id, data, user, owner_only=True)
    return await svc.serialize(row)


@me_router.delete("/{request_id}", response_model=MessageResponse, dependencies=_me)
async def me_delete(
    request_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.request.mine.cancel", "mg.request.mine.update")),
):
    await MgRequestsService(db).delete_draft(request_id, user)
    return MessageResponse(message="Brouillon supprimé")


@me_router.post("/{request_id}/submit", response_model=RequestOut, dependencies=_me)
async def me_submit(
    request_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.request.mine.create")),
):
    svc = MgRequestsService(db)
    row = await svc.submit(request_id, user)
    return await svc.serialize(row)


@me_router.post("/{request_id}/cancel", response_model=RequestOut, dependencies=_me)
async def me_cancel(
    request_id: UUID,
    data: CommentIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.request.mine.cancel")),
):
    svc = MgRequestsService(db)
    row = await svc.cancel(request_id, user, data.comment)
    return await svc.serialize(row)


@me_router.post("/{request_id}/comments", response_model=RequestOut, dependencies=_me)
async def me_comment(
    request_id: UUID,
    data: CommentBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.request.mine.update", "mg.request.mine.view")),
):
    svc = MgRequestsService(db)
    row = await svc._load(request_id)
    if row.requester_id != user.id and not user.is_superuser:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Demande non autorisée")
    row = await svc.add_comment(request_id, user, data.body)
    return await svc.serialize(row)


@mg_router.get("/dashboard", response_model=DashboardOut, dependencies=_mg)
async def mg_dashboard(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.request.view")),
):
    return await MgRequestsService(db).dashboard(target_espace="moyens-generaux")


@mg_router.get("/categories", response_model=list[CategoryOut], dependencies=_mg)
async def mg_categories(
    all: bool = False,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.request.view")),
):
    return await MgRequestsService(db).list_categories(active_only=not all)


@mg_router.post("/categories", response_model=CategoryOut, dependencies=_mg)
async def mg_upsert_category(
    data: CategoryIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.request.admin")),
):
    return await MgRequestsService(db).upsert_category(data)


@mg_router.get("/refs", dependencies=_mg)
async def mg_refs(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.request.view")),
):
    return await MgRequestsService(db).refs()


@mg_router.get("", response_model=RequestListOut, dependencies=_mg)
async def mg_list(
    q: str | None = None,
    statut: str | None = None,
    category_id: UUID | None = None,
    agency_id: UUID | None = None,
    requester_id: UUID | None = None,
    priority: str | None = None,
    source_espace: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.request.view")),
):
    svc = MgRequestsService(db)
    rows, total = await svc.list_requests(
        q=q, statut=statut, category_id=category_id, agency_id=agency_id,
        requester_id=requester_id, priority=priority, source_espace=source_espace,
        target_espace="moyens-generaux", page=page, size=size,
    )
    return RequestListOut(items=await _serialize_many(svc, rows), total=total, page=page, size=size)


@mg_router.get("/{request_id}", response_model=RequestOut, dependencies=_mg)
async def mg_get(
    request_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.request.view")),
):
    svc = MgRequestsService(db)
    row = await svc.get_mg(request_id, user, target_espace="moyens-generaux")
    return await svc.serialize(row, with_stock=True)


@mg_router.get("/{request_id}/pdf", dependencies=_mg)
async def mg_pdf(
    request_id: UUID,
    visas: str = Query("agence,mg"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.request.view")),
):
    from app.data.demandes_engine import ESPACE_LABELS
    from app.models.organisation import Departement

    svc = MgRequestsService(db)
    row = await svc._load(request_id)
    if row.target_espace_code != "moyens-generaux" and not user.is_superuser:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Demande hors de votre périmètre")
    requester = await db.get(User, row.requester_id)
    dept = await db.get(Departement, row.department_id) if row.department_id else None
    department_label = (
        (dept.libelle if dept else None)
        or ESPACE_LABELS.get(row.source_espace_code or "", "")
        or "—"
    )
    payload = pdf_employee_request(
        row,
        requester_name=(requester.full_name if requester else None) or "—",
        department_label=department_label,
        category_name=(row.category.name if row.category else None) or "—",
        visas=visas,
    )
    filename = f"{row.request_number}.pdf"
    return Response(
        content=payload,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@mg_router.post("/{request_id}/cancel", response_model=RequestOut, dependencies=_mg)
async def mg_cancel(
    request_id: UUID,
    data: CommentIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.request.validate", "mg.request.admin")),
):
    svc = MgRequestsService(db)
    row = await svc.mg_cancel(request_id, user, data.comment)
    return await svc.serialize(row, with_stock=True)


@mg_router.delete("/{request_id}", response_model=MessageResponse, dependencies=_mg)
async def mg_delete(
    request_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.request.admin", "mg.request.validate")),
):
    svc = MgRequestsService(db)
    await svc.mg_delete(request_id, user)
    return MessageResponse(message="Demande supprimée")


@mg_router.post("/{request_id}/granted", response_model=RequestOut, dependencies=_mg)
async def mg_granted(
    request_id: UUID,
    data: GrantedIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.request.validate", "mg.request.admin")),
):
    svc = MgRequestsService(db)
    row = await svc.set_granted_quantities(request_id, user, data)
    return await svc.serialize(row, with_stock=True)


@mg_router.post("/{request_id}/request-info", response_model=RequestOut, dependencies=_mg)
async def mg_request_info(
    request_id: UUID,
    data: CommentIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.request.request_info")),
):
    svc = MgRequestsService(db)
    row = await svc.request_info(request_id, user, data.comment)
    return await svc.serialize(row, with_stock=True)


@mg_router.post("/{request_id}/validate", response_model=RequestOut, dependencies=_mg)
async def mg_validate(
    request_id: UUID,
    data: CommentIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.request.validate")),
):
    svc = MgRequestsService(db)
    row = await svc.validate(request_id, user, data.comment)
    return await svc.serialize(row, with_stock=True)


@mg_router.post("/{request_id}/reject", response_model=RequestOut, dependencies=_mg)
async def mg_reject(
    request_id: UUID,
    data: CommentIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.request.reject")),
):
    svc = MgRequestsService(db)
    row = await svc.reject(request_id, user, data.comment)
    return await svc.serialize(row)


@mg_router.post("/{request_id}/serve", response_model=RequestOut, dependencies=_mg)
async def mg_serve(
    request_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.request.serve")),
):
    svc = MgRequestsService(db)
    row = await svc.serve_from_stock(request_id, user)
    return await svc.serialize(row, with_stock=True)


@mg_router.post("/{request_id}/assign", response_model=RequestOut, dependencies=_mg)
async def mg_assign(
    request_id: UUID,
    data: AssignIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.request.assign")),
):
    svc = MgRequestsService(db)
    row = await svc.assign(request_id, user, data.assigned_to_id)
    return await svc.serialize(row, with_stock=True)


@mg_router.post("/{request_id}/recategorize", response_model=RequestOut, dependencies=_mg)
async def mg_recategorize(
    request_id: UUID,
    data: RecategorizeIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.request.validate", "mg.request.admin")),
):
    svc = MgRequestsService(db)
    row = await svc.recategorize(request_id, user, data.category_id)
    return await svc.serialize(row, with_stock=True)


@mg_router.post("/{request_id}/comments", response_model=RequestOut, dependencies=_mg)
async def mg_comment(
    request_id: UUID,
    data: CommentBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.request.view")),
):
    svc = MgRequestsService(db)
    row = await svc.add_comment(request_id, user, data.body)
    return await svc.serialize(row, with_stock=True)


batch_router = APIRouter(prefix="/mg/batches", tags=["demandes-mg-batches"])


@batch_router.get("", response_model=BatchListOut, dependencies=_mg)
async def batch_list(
    page: int = Query(1, ge=1),
    size: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.batch.view")),
):
    svc = MgRequestsService(db)
    rows, total = await svc.list_batches(page=page, size=size)
    items = [await svc.serialize_batch(r) for r in rows]
    return BatchListOut(items=items, total=total, page=page, size=size)


@batch_router.post("", response_model=BatchOut, dependencies=_mg)
async def batch_create(
    data: BatchCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.batch.create")),
):
    svc = MgRequestsService(db)
    row = await svc.create_batch(data, user)
    return await svc.serialize_batch(row)


@batch_router.get("/{batch_id}", response_model=BatchOut, dependencies=_mg)
async def batch_get(
    batch_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.batch.view")),
):
    svc = MgRequestsService(db)
    return await svc.serialize_batch(await svc._load_batch(batch_id))


@batch_router.patch("/{batch_id}", response_model=BatchOut, dependencies=_mg)
async def batch_update(
    batch_id: UUID,
    data: BatchUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.batch.update")),
):
    svc = MgRequestsService(db)
    row = await svc.update_batch(batch_id, data, user)
    return await svc.serialize_batch(row)


@batch_router.post("/{batch_id}/items", response_model=BatchOut, dependencies=_mg)
async def batch_add_items(
    batch_id: UUID,
    data: BatchItemsIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.batch.update", "mg.request.group")),
):
    svc = MgRequestsService(db)
    row = await svc.add_batch_items(batch_id, data, user)
    return await svc.serialize_batch(row)


@batch_router.delete("/{batch_id}/items/{item_id}", response_model=BatchOut, dependencies=_mg)
async def batch_remove_item(
    batch_id: UUID,
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.batch.update")),
):
    svc = MgRequestsService(db)
    row = await svc.remove_batch_item(batch_id, item_id, user)
    return await svc.serialize_batch(row)


@batch_router.delete("/{batch_id}", response_model=MessageResponse, dependencies=_mg)
async def batch_delete(
    batch_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.batch.update", "mg.batch.admin")),
):
    svc = MgRequestsService(db)
    await svc.delete_batch(batch_id, user)
    return MessageResponse(message="Regroupement supprimé")


@batch_router.post("/{batch_id}/validate", response_model=BatchOut, dependencies=_mg)
async def batch_validate(
    batch_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.batch.validate")),
):
    svc = MgRequestsService(db)
    row = await svc.validate_batch(batch_id, user)
    return await svc.serialize_batch(row)
