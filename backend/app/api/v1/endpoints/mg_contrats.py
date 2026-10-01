"""API Contrats & échéances MG."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_module_access, require_permission
from app.models.auth import User
from app.schemas.mg_ops import (
    ContratAvenantIn,
    ContratCreate,
    ContratDetail,
    ContratEcheanceIn,
    ContratEcheancierIn,
    ContratOut,
    ContratPaiementIn,
    ContratPaiementUpdate,
    ContratTransitionIn,
    ContratUpdate,
)
from app.services.mg_contrats_service import VALIDATION_ACTIONS, MgContratsService
from app.services.mg_pdf_service import pdf_contrat
from app.services.permission_service import load_user_permission_codes, user_has_permission_codes

router = APIRouter(prefix="/mg/contrats", tags=["mg-contrats"])
_module = [Depends(require_module_access("contrats-echeances"))]
RAPPORTS = {
    "liste",
    "actifs",
    "expires",
    "echeances",
    "paiements",
    "financier_fournisseur",
    "financier_agence",
    "financier_periode",
    "renouvellements",
}


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


class SimulationIn(BaseModel):
    date_debut: date
    date_fin: date | None = None
    periodicite: str = "ANNUEL"
    montant_ht: Decimal | None = None
    taux_tva: Decimal | None = None


async def _svc(db: AsyncSession, user: User) -> MgContratsService:
    return await MgContratsService.for_user(db, user)


async def _require(user: User, db: AsyncSession, *codes: str) -> None:
    if user.is_superuser:
        return
    if user_has_permission_codes(await load_user_permission_codes(db, user), *codes):
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Permission refusée")


@router.get("/config", dependencies=_module)
async def config(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.contrats.view")),
):
    return await (await _svc(db, user)).config(user)


@router.get("/dashboard", dependencies=_module)
async def dashboard(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.contrats.view")),
):
    return await (await _svc(db, user)).dashboard()


@router.get("/alertes", dependencies=_module)
async def list_alertes(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.contrats.view")),
):
    return await (await _svc(db, user)).alertes()


@router.post("/alertes/envoyer", dependencies=_module)
async def envoyer_rappels(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.contrats.manage")),
):
    return await MgContratsService(db).envoyer_rappels(force=True)


@router.get("/agences", dependencies=_module)
async def list_agences(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.contrats.view")),
):
    rows = await (await _svc(db, user)).list_agences()
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


@router.post("/echeancier/simuler", dependencies=_module)
async def simuler_echeancier(
    body: SimulationIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.contrats.view")),
):
    return await MgContratsService(db).simuler(
        date_debut=body.date_debut,
        date_fin=body.date_fin,
        periodicite=body.periodicite,
        montant_ht=body.montant_ht,
        taux_tva=body.taux_tva,
    )


@router.get("/echeances", dependencies=_module)
async def list_echeances(
    horizon: str | None = None,
    statut: str | None = None,
    type_echeance: str | None = None,
    contrat_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.contrats.view")),
):
    return await (await _svc(db, user)).list_echeances(horizon, statut, type_echeance, contrat_id)


@router.patch("/echeances/{echeance_id}", dependencies=_module)
async def update_echeance(
    echeance_id: UUID,
    body: ContratEcheanceIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.contrats.manage")),
):
    return await MgContratsService(db).update_echeance(echeance_id, body.model_dump(exclude_unset=True), user)


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
    contrat_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.contrats.view")),
):
    return await (await _svc(db, user)).list_paiements(statut, contrat_id)


@router.patch("/paiements/{paiement_id}", response_model=ContratDetail, dependencies=_module)
async def update_paiement(
    paiement_id: UUID,
    body: ContratPaiementUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.contrats.manage")),
):
    return await MgContratsService(db).update_paiement(paiement_id, body, user)


@router.delete("/paiements/{paiement_id}", response_model=ContratDetail, dependencies=_module)
async def delete_paiement(
    paiement_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.contrats.manage")),
):
    return await MgContratsService(db).delete_paiement(paiement_id, user)


@router.get("/renouvellements/a-traiter", dependencies=_module)
async def a_renouveler(
    horizon: int = Query(90, ge=1, le=730),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.contrats.view")),
):
    return await (await _svc(db, user)).a_renouveler(horizon)


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
    _: User = Depends(require_permission("mg.contrats.settings")),
):
    row = await MgContratsService(db).create_type(body.code, body.libelle)
    return {"id": str(row.id), "code": row.code, "libelle": row.libelle, "actif": row.actif}


@router.patch("/types/{type_id}", dependencies=_module)
async def update_type(
    type_id: UUID,
    body: TypePatch,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.contrats.settings")),
):
    row = await MgContratsService(db).update_type(type_id, libelle=body.libelle, actif=body.actif)
    return {"id": str(row.id), "code": row.code, "libelle": row.libelle, "actif": row.actif}


@router.delete("/types/{type_id}", dependencies=_module)
async def delete_type(
    type_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.contrats.settings")),
):
    return await MgContratsService(db).delete_type(type_id)


@router.get("/parametres", dependencies=_module)
async def list_parametres(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.contrats.settings")),
):
    rows = await MgContratsService(db).list_params()
    return [{"cle": p.cle, "valeur": p.valeur, "libelle": p.libelle} for p in rows]


@router.patch("/parametres/{cle}", dependencies=_module)
async def set_parametre(
    cle: str,
    body: ParamIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.contrats.settings")),
):
    row = await MgContratsService(db).set_param(cle, body.valeur, body.libelle)
    return {"cle": row.cle, "valeur": row.valeur, "libelle": row.libelle}


@router.post("/parametres", dependencies=_module)
async def create_parametre(
    body: ParamCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.contrats.settings")),
):
    row = await MgContratsService(db).create_param(body.cle, body.valeur, body.libelle)
    return {"cle": row.cle, "valeur": row.valeur, "libelle": row.libelle}


@router.delete("/parametres/{cle}", dependencies=_module)
async def delete_parametre(
    cle: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.contrats.settings")),
):
    await MgContratsService(db).delete_param(cle)
    return {"ok": True}


@router.get("/rapports/{report_key}", dependencies=_module)
async def rapport(
    report_key: str,
    fmt: str = Query("json", pattern="^(json|csv|xlsx|pdf)$"),
    annee: int | None = Query(None, ge=2000, le=2100),
    periode: str | None = Query(None, pattern="^(trimestre|annee)$"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.contrats.view")),
):
    if report_key not in RAPPORTS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Rapport inconnu")
    if fmt != "json":
        await _require(user, db, "mg.contrats.export")
    return await (await _svc(db, user)).export(user, report_key, fmt, annee=annee, periode=periode)


@router.get("", response_model=list[ContratOut], dependencies=_module)
async def list_contrats(
    statut: str | None = None,
    etat: str | None = None,
    q: str | None = None,
    agence_id: UUID | None = None,
    fournisseur_id: UUID | None = None,
    type_contrat: str | None = None,
    horizon: str | None = None,
    renouveles: bool = False,
    page: int = Query(1, ge=1),
    size: int = Query(200, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.contrats.view")),
):
    rows = await (await _svc(db, user)).list_contrats(
        q=q,
        statut=statut,
        etat=etat,
        agence_id=agence_id,
        fournisseur_id=fournisseur_id,
        type_contrat=type_contrat,
        horizon=horizon,
        renouveles=renouveles,
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
    user: User = Depends(require_permission("mg.contrats.view")),
):
    return await (await _svc(db, user)).get_contrat(contrat_id)


@router.get("/{contrat_id}/pdf", dependencies=_module)
async def contrat_pdf(
    contrat_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.contrats.view")),
):
    contrat = await (await _svc(db, user)).get_contrat(contrat_id)
    return Response(
        content=pdf_contrat(contrat),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="Contrat-{contrat.reference}.pdf"'},
    )


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
    user: User = Depends(require_permission("mg.contrats.manage", "mg.contrats.validate")),
):
    action = body.action.strip().lower()
    await _require(user, db, "mg.contrats.validate" if action in VALIDATION_ACTIONS else "mg.contrats.manage")
    return await MgContratsService(db).transition(contrat_id, action, user, body.commentaire)


@router.post("/{contrat_id}/echeancier", response_model=ContratDetail, dependencies=_module)
async def generer_echeancier(
    contrat_id: UUID,
    body: ContratEcheancierIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.contrats.manage")),
):
    return await MgContratsService(db).generer_echeancier(contrat_id, user, remplacer=body.remplacer)


@router.post("/{contrat_id}/avenants", response_model=ContratDetail, dependencies=_module)
async def add_avenant(
    contrat_id: UUID,
    body: ContratAvenantIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.contrats.manage")),
):
    return await MgContratsService(db).add_avenant(contrat_id, body, user)


@router.post("/{contrat_id}/reconduire", response_model=ContratDetail, dependencies=_module)
async def reconduire(
    contrat_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.contrats.manage")),
):
    return await MgContratsService(db).reconduire(contrat_id, user)


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
