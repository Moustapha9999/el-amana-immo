"""API Contrats & échéances MG."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_module_access, require_permission
from app.models.auth import User
from app.schemas.mg_ops import (
    ContratCreate,
    ContratDetail,
    ContratEcheanceIn,
    ContratOut,
    ContratPaiementIn,
    ContratTransitionIn,
    ContratUpdate,
)
from app.services.mg_contrats_service import MgContratsService

router = APIRouter(prefix="/mg/contrats", tags=["mg-contrats"])
_module = [Depends(require_module_access("contrats-echeances"))]


class ParamIn(BaseModel):
    valeur: str
    libelle: str | None = None


class ParamCreate(BaseModel):
    cle: str
    valeur: str = ""
    libelle: str | None = None


class TypeIn(BaseModel):
    code: str
    libelle: str


class TypePatch(BaseModel):
    libelle: str | None = None
    actif: bool | None = None


@router.get("/dashboard", dependencies=_module)
async def dashboard(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.contrats.view")),
):
    return await MgContratsService(db).dashboard()


@router.get("/alertes", dependencies=_module)
async def list_alertes(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.contrats.view")),
):
    return await MgContratsService(db).alertes()


@router.get("/agences", dependencies=_module)
async def list_agences(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.contrats.view")),
):
    rows = await MgContratsService(db).list_agences()
    return [{"id": str(a.id), "code": a.code, "libelle": a.libelle, "ville": a.ville} for a in rows]


@router.get("/fournisseurs", dependencies=_module)
async def list_fournisseurs(
    q: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.contrats.view")),
):
    return await MgContratsService(db).list_fournisseurs(q)


@router.get("/responsables", dependencies=_module)
async def list_responsables(
    q: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.contrats.view")),
):
    return await MgContratsService(db).list_responsables(q)


@router.get("/echeances", dependencies=_module)
async def list_echeances(
    horizon: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.contrats.view")),
):
    return await MgContratsService(db).list_echeances(horizon)


@router.patch("/echeances/{echeance_id}", dependencies=_module)
async def update_echeance(
    echeance_id: UUID,
    body: ContratEcheanceIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.contrats.manage")),
):
    return await MgContratsService(db).update_echeance(echeance_id, body.model_dump(), user)


@router.delete("/echeances/{echeance_id}", dependencies=_module)
async def delete_echeance(
    echeance_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.contrats.manage")),
):
    await MgContratsService(db).delete_echeance(echeance_id, user)
    return {"ok": True}


@router.get("/paiements", dependencies=_module)
async def list_paiements(
    statut: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.contrats.view")),
):
    return await MgContratsService(db).list_paiements(statut)


@router.get("/types", dependencies=_module)
async def list_types(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.contrats.view")),
):
    rows = await MgContratsService(db).list_types()
    return [{"id": str(t.id), "code": t.code, "libelle": t.libelle, "actif": t.actif} for t in rows]


@router.post("/types", dependencies=_module)
async def create_type(
    body: TypeIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.contrats.manage")),
):
    row = await MgContratsService(db).create_type(body.code, body.libelle)
    return {"id": str(row.id), "code": row.code, "libelle": row.libelle, "actif": row.actif}


@router.patch("/types/{type_id}", dependencies=_module)
async def update_type(
    type_id: UUID,
    body: TypePatch,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.contrats.manage")),
):
    row = await MgContratsService(db).update_type(type_id, libelle=body.libelle, actif=body.actif)
    return {"id": str(row.id), "code": row.code, "libelle": row.libelle, "actif": row.actif}


@router.delete("/types/{type_id}", dependencies=_module)
async def delete_type(
    type_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.contrats.manage")),
):
    return await MgContratsService(db).delete_type(type_id)


@router.get("/parametres", dependencies=_module)
async def list_parametres(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.contrats.manage")),
):
    rows = await MgContratsService(db).list_params()
    return [{"cle": p.cle, "valeur": p.valeur, "libelle": p.libelle} for p in rows]


@router.patch("/parametres/{cle}", dependencies=_module)
async def set_parametre(
    cle: str,
    body: ParamIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.contrats.manage")),
):
    row = await MgContratsService(db).set_param(cle, body.valeur, body.libelle)
    return {"cle": row.cle, "valeur": row.valeur, "libelle": row.libelle}


@router.post("/parametres", dependencies=_module)
async def create_parametre(
    body: ParamCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.contrats.manage")),
):
    row = await MgContratsService(db).create_param(body.cle, body.valeur, body.libelle)
    return {"cle": row.cle, "valeur": row.valeur, "libelle": row.libelle}


@router.delete("/parametres/{cle}", dependencies=_module)
async def delete_parametre(
    cle: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.contrats.manage")),
):
    await MgContratsService(db).delete_param(cle)
    return {"ok": True}


@router.get("/rapports/{report_key}", dependencies=_module)
async def rapport(
    report_key: str,
    fmt: str = Query("json", pattern="^(json|csv|xlsx|pdf)$"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.contrats.view")),
):
    if report_key not in {"liste", "actifs", "expires", "echeances"}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Rapport inconnu")
    if fmt != "json":
        await _require_export(user, db)
    return await MgContratsService(db).export(user, report_key, fmt)


async def _require_export(user: User, db: AsyncSession) -> None:
    from app.services.permission_service import load_user_permission_codes, user_has_permission_codes

    if user.is_superuser:
        return
    have = await load_user_permission_codes(db, user)
    if user_has_permission_codes(have, "mg.contrats.export"):
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Permission refusée")


@router.get("", response_model=list[ContratOut], dependencies=_module)
async def list_contrats(
    statut: str | None = None,
    q: str | None = None,
    agence_id: UUID | None = None,
    horizon: str | None = None,
    renouveles: bool = False,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.contrats.view")),
):
    rows = await MgContratsService(db).list_contrats(
        q=q, statut=statut, agence_id=agence_id, horizon=horizon, renouveles=renouveles
    )
    start = (page - 1) * size
    return rows[start : start + size]


@router.post("", response_model=ContratDetail, dependencies=_module)
async def create_contrat(
    body: ContratCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.contrats.create")),
):
    return await MgContratsService(db).create_contrat(body, user)


@router.get("/{contrat_id}", response_model=ContratDetail, dependencies=_module)
async def get_contrat(
    contrat_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.contrats.view")),
):
    return await MgContratsService(db).get_contrat(contrat_id)


@router.patch("/{contrat_id}", response_model=ContratDetail, dependencies=_module)
async def update_contrat(
    contrat_id: UUID,
    body: ContratUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.contrats.manage")),
):
    return await MgContratsService(db).update_contrat(contrat_id, body, user)


@router.delete("/{contrat_id}", dependencies=_module)
async def delete_contrat(
    contrat_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.contrats.manage")),
):
    await MgContratsService(db).soft_delete(contrat_id, user)
    return {"ok": True}


@router.post("/{contrat_id}/transition", response_model=ContratDetail, dependencies=_module)
async def transition(
    contrat_id: UUID,
    body: ContratTransitionIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.contrats.manage")),
):
    return await MgContratsService(db).transition(contrat_id, body.action, user, body.commentaire)


@router.post("/{contrat_id}/renouveler", response_model=ContratDetail, dependencies=_module)
async def renouveler(
    contrat_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.contrats.manage")),
):
    return await MgContratsService(db).renouveler(contrat_id, user)


@router.post("/{contrat_id}/echeances", response_model=ContratDetail, dependencies=_module)
async def add_echeance(
    contrat_id: UUID,
    body: ContratEcheanceIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.contrats.manage")),
):
    return await MgContratsService(db).add_echeance(contrat_id, body.model_dump(), user)


@router.post("/{contrat_id}/paiements", response_model=ContratDetail, dependencies=_module)
async def add_paiement(
    contrat_id: UUID,
    body: ContratPaiementIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.contrats.manage")),
):
    return await MgContratsService(db).add_paiement(contrat_id, body.model_dump(), user)
