"""API Achats MG — bons de commande."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_module_access, require_permission
from app.models.auth import User
from app.schemas.mg_ops import BonCreate, BonOut, BonUpdate, TransitionIn
from app.services.mg_ops_service import MgOpsService
from app.services.mg_pdf_service import pdf_bon_commande

router = APIRouter(prefix="/mg/achats", tags=["mg-achats"])
_module = [Depends(require_module_access("achats-appro"))]


@router.get("/fournisseurs", dependencies=_module)
async def list_fournisseurs(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.purchase.view")),
):
    rows = await MgOpsService(db).list_fournisseurs()
    return [
        {
            "id": str(f.id),
            "code": f.code,
            "raison_sociale": f.raison_sociale,
            "telephone": f.telephone,
            "email": f.email,
            "adresse": f.adresse,
        }
        for f in rows
    ]


@router.get("/bons", response_model=list[BonOut], dependencies=_module)
async def list_bons(
    statut: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.purchase.view")),
):
    return await MgOpsService(db).list_bons(statut=statut)


@router.post("/bons", response_model=BonOut, dependencies=_module)
async def create_bon(
    body: BonCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.create")),
):
    return await MgOpsService(db).create_bon(body, user)


@router.get("/bons/{bon_id}", response_model=BonOut, dependencies=_module)
async def get_bon(
    bon_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.purchase.view")),
):
    return await MgOpsService(db).get_bon(bon_id)


@router.patch("/bons/{bon_id}", response_model=BonOut, dependencies=_module)
async def update_bon(
    bon_id: UUID,
    body: BonUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.purchase.create")),
):
    return await MgOpsService(db).update_bon(bon_id, body)


@router.post("/bons/{bon_id}/transition", response_model=BonOut, dependencies=_module)
async def transition_bon(
    bon_id: UUID,
    body: TransitionIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.approve")),
):
    return await MgOpsService(db).transition_bon(bon_id, body.action, user)


@router.get("/bons/{bon_id}/pdf", dependencies=_module)
async def bon_pdf(
    bon_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.purchase.export")),
):
    bon = await MgOpsService(db).get_bon(bon_id)
    data = pdf_bon_commande(bon)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{bon.reference}.pdf"'},
    )
