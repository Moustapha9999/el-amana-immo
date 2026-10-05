"""API Gestion des factures — Moyens Généraux › Contrats & échéances."""

from __future__ import annotations

import json
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, TypeAdapter, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_module_access, require_permission
from app.core.exceptions import AppError
from app.models.auth import User
from app.schemas.mg_facturation import (
    FactureCreate,
    FacturePaiementIn,
    FacturePaiementUpdate,
    FactureTransitionIn,
    FactureUpdate,
    ImportChoix,
    PointFacturationCreate,
    PointFacturationIn,
)
from app.services.mg_facturation_analytics import MgFacturationAnalytics
from app.services.mg_facturation_import import MgFacturationImport
from app.services.mg_facturation_service import MgFacturationService
from app.services.permission_service import load_user_permission_codes, user_has_permission_codes

_module = [Depends(require_module_access("contrats-echeances"))]
router = APIRouter(prefix="/mg/factures", tags=["mg-factures"], dependencies=_module)
points_router = APIRouter(prefix="/mg/points-facturation", tags=["mg-factures"], dependencies=_module)

FORMATS = {"json", "csv", "xlsx", "pdf"}


class ParamIn(BaseModel):
    valeur: str = Field(max_length=255)


class MotifIn(BaseModel):
    motif: str | None = Field(default=None, max_length=2000)


async def _svc(db: AsyncSession, user: User) -> MgFacturationService:
    return await MgFacturationService.for_user(db, user)


def _filtres(
    q: str | None = None,
    vue: str | None = None,
    statut: str | None = None,
    statut_paiement: str | None = None,
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    date_from: date | None = None,
    date_to: date | None = None,
    agency_id: UUID | None = None,
    pdv_id: UUID | None = None,
    point_id: UUID | None = None,
    supplier_id: UUID | None = None,
    contrat_id: UUID | None = None,
    type: str | None = None,
    type_facture: str | None = None,
    echeance: str | None = None,
    inclure_historique: bool = False,
) -> dict:
    """Filtres communs (noms du cahier des charges : year, month, agency_id, pdv_id, supplier_id, type, status)."""
    return {
        "q": q,
        "vue": vue,
        "statut": statut,
        "statut_paiement": statut_paiement,
        "annee": year,
        "mois": month,
        "date_from": date_from,
        "date_to": date_to,
        "agence_id": agency_id,
        "point_id": pdv_id or point_id,
        "fournisseur_id": supplier_id,
        "contrat_id": contrat_id,
        "type_point": type,
        "type_facture": type_facture,
        "echeance": echeance,
        "inclure_historique": inclure_historique,
    }


# ——— Configuration, référentiels, paramètres ———


@router.get("/config")
async def config(db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("mg.factures.view"))):
    return await (await _svc(db, user)).config(user)


@router.get("/referentiels")
async def referentiels(db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("mg.factures.view"))):
    return await (await _svc(db, user)).referentiels()


@router.get("/parametres")
async def list_params(db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("mg.factures.view"))):
    rows = await (await _svc(db, user)).list_params()
    return [{"cle": p.cle, "valeur": p.valeur, "libelle": p.libelle} for p in rows]


@router.put("/parametres/{cle}")
async def set_param(
    cle: str,
    body: ParamIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.facturation.manage")),
):
    p = await (await _svc(db, user)).set_param(cle, body.valeur, user)
    return {"cle": p.cle, "valeur": p.valeur, "libelle": p.libelle}


# ——— Tableau de bord, alertes, échéances, recherche ———


@router.get("/dashboard")
async def dashboard(
    filtres: dict = Depends(_filtres),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.factures.view")),
):
    return await MgFacturationAnalytics(await _svc(db, user)).dashboard(filtres)


@router.get("/alertes")
async def alertes(
    filtres: dict = Depends(_filtres),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.factures.view")),
):
    return await MgFacturationAnalytics(await _svc(db, user)).alertes(filtres)


@router.get("/echeances")
async def echeances(
    filtres: dict = Depends(_filtres),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.factures.view")),
):
    return await MgFacturationAnalytics(await _svc(db, user)).echeances(filtres)


@router.get("/search")
async def search(
    q: str = Query(min_length=1, max_length=120),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.factures.view")),
):
    return await (await _svc(db, user)).recherche(q)


@router.get("/compteurs")
async def compteurs(db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("mg.factures.view"))):
    return await (await _svc(db, user)).compteurs_vues()


# ——— Analyses ———

ANALYSES = {"monthly", "annual", "agencies", "pdv", "suppliers", "points", "comparison"}


@router.get("/analytics/{kind}")
async def analytics(
    kind: str,
    annee_reference: int | None = Query(default=None, ge=2000, le=2100),
    filtres: dict = Depends(_filtres),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.factures.analytics.view")),
):
    if kind not in ANALYSES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Analyse inconnue")
    service = MgFacturationAnalytics(await _svc(db, user))
    if kind == "comparison":
        filtres["annee_reference"] = annee_reference
    return await getattr(service, kind)(filtres)


# ——— Rapports ———


@router.get("/rapports/{key}")
async def rapport(
    key: str,
    format: str = Query(default="json"),
    filtres: dict = Depends(_filtres),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.factures.view")),
):
    fmt = format.lower()
    if fmt not in FORMATS:
        raise AppError("Format non pris en charge", code="FORMAT_INVALIDE")
    if fmt != "json" or key == "paiements":
        have = await load_user_permission_codes(db, user)
        if key == "paiements" and not (user.is_superuser or user_has_permission_codes(have, "mg.factures.payment.view")):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Consultation des paiements requise")
        if fmt != "json" and not (
            user.is_superuser or user_has_permission_codes(have, "mg.factures.reports.export", "mg.factures.export")
        ):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Permission d'export requise")
    return await MgFacturationAnalytics(await _svc(db, user)).export(user, key, fmt, filtres)


# ——— Paiements (vue transverse) ———


@router.get("/paiements")
async def list_paiements(
    q: str | None = None,
    statut: str | None = None,
    mode_paiement: str | None = None,
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    date_from: date | None = None,
    date_to: date | None = None,
    agency_id: UUID | None = None,
    supplier_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.factures.payment.view")),
):
    return await (await _svc(db, user)).list_paiements(
        {
            "q": q, "statut": statut, "mode_paiement": mode_paiement, "annee": year, "mois": month,
            "date_from": date_from, "date_to": date_to, "agence_id": agency_id, "fournisseur_id": supplier_id,
        }
    )


@router.patch("/paiements/{paiement_id}")
async def update_paiement(
    paiement_id: UUID,
    body: FacturePaiementUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.factures.payment.update")),
):
    return await (await _svc(db, user)).update_paiement(paiement_id, body, user)


@router.post("/paiements/{paiement_id}/annuler")
async def annuler_paiement(
    paiement_id: UUID,
    body: MotifIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.factures.payment.delete")),
):
    return await (await _svc(db, user)).annuler_paiement(paiement_id, user, body.motif)


# ——— Synthèses agence / fournisseur / contrat ———


@router.get("/agences/{agence_id}/synthese")
async def agence_synthese(
    agence_id: UUID,
    year: int | None = Query(default=None, ge=2000, le=2100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.factures.view")),
):
    return await (await _svc(db, user)).agence_synthese(agence_id, year)


@router.get("/fournisseurs/{fournisseur_id}/synthese")
async def fournisseur_synthese(
    fournisseur_id: UUID,
    year: int | None = Query(default=None, ge=2000, le=2100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.factures.view")),
):
    return await (await _svc(db, user)).fournisseur_synthese(fournisseur_id, year)


@router.get("/contrats/{contrat_id}")
async def factures_du_contrat(
    contrat_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.factures.view")),
):
    return await (await _svc(db, user)).factures_du_contrat(contrat_id)


# ——— Factures : CRUD et workflow ———


@router.get("")
async def list_factures(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    sort: str | None = None,
    filtres: dict = Depends(_filtres),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.factures.view")),
):
    return await (await _svc(db, user)).list_factures(filtres, page=page, page_size=page_size, sort=sort)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_facture(
    body: FactureCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.factures.create")),
):
    return await (await _svc(db, user)).create_facture(body, user)


@router.get("/{facture_id}")
async def get_facture(
    facture_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.factures.view")),
):
    return await (await _svc(db, user)).get_facture(facture_id, user)


@router.patch("/{facture_id}")
async def update_facture(
    facture_id: UUID,
    body: FactureUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.factures.update")),
):
    return await (await _svc(db, user)).update_facture(facture_id, body, user)


@router.delete("/{facture_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_facture(
    facture_id: UUID,
    motif: str | None = Query(default=None, max_length=2000),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.factures.delete")),
):
    await (await _svc(db, user)).delete_facture(facture_id, user, motif)


@router.post("/{facture_id}/dupliquer", status_code=status.HTTP_201_CREATED)
async def dupliquer(
    facture_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.factures.create")),
):
    return await (await _svc(db, user)).dupliquer(facture_id, user)


for _action in ("enregistrer", "controler", "valider", "contester", "annuler", "archiver"):

    def _make(action: str):
        async def _transition(
            facture_id: UUID,
            body: FactureTransitionIn | None = None,
            db: AsyncSession = Depends(get_db),
            user: User = Depends(require_permission("mg.factures.view")),
        ):
            # Permission spécifique à l'action contrôlée dans le service (PERMISSION_ACTION).
            return await (await _svc(db, user)).transition(facture_id, action, user, body.motif if body else None)

        _transition.__name__ = f"facture_{action}"
        return _transition

    router.add_api_route(f"/{{facture_id}}/{_action}", _make(_action), methods=["POST"], name=f"facture_{_action}")


# ——— Paiements d'une facture ———


@router.get("/{facture_id}/paiements")
async def paiements_facture(
    facture_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.factures.payment.view")),
):
    svc = await _svc(db, user)
    await svc._facture(facture_id)
    return await svc._paiements_dicts(facture_id)


@router.post("/{facture_id}/paiements", status_code=status.HTTP_201_CREATED)
async def add_paiement(
    facture_id: UUID,
    body: FacturePaiementIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.factures.payment.create")),
):
    return await (await _svc(db, user)).add_paiement(facture_id, body, user)


# ——— Documents (GED centrale) ———


@router.get("/{facture_id}/documents")
async def documents(
    facture_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.factures.documents.view")),
):
    return await (await _svc(db, user)).list_documents(facture_id)


@router.post("/{facture_id}/documents", status_code=status.HTTP_201_CREATED)
async def upload_document(
    facture_id: UUID,
    file: UploadFile = File(...),
    doc_type: str | None = Form(default=None),
    title: str | None = Form(default=None),
    reference: str | None = Form(default=None),
    date_document: date | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.factures.documents.create")),
):
    return await (await _svc(db, user)).upload_document(
        facture_id, file, user, doc_type=doc_type, title=title, reference=reference, date_document=date_document
    )


@router.get("/{facture_id}/documents/{document_id}/download")
async def download_document(
    facture_id: UUID,
    document_id: UUID,
    inline: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.factures.documents.view")),
):
    from app.services.ged_service import GedService

    doc = await (await _svc(db, user)).document_de_facture(facture_id, document_id)
    path = GedService(db).absolute_path(doc.stored_path)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Fichier introuvable sur le serveur")
    return FileResponse(
        path,
        filename=doc.filename,
        media_type=doc.mime_type or "application/octet-stream",
        content_disposition_type="inline" if inline else "attachment",
    )


@router.delete("/{facture_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    facture_id: UUID,
    document_id: UUID,
    motif: str | None = Query(default=None, max_length=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.factures.documents.delete")),
):
    await (await _svc(db, user)).delete_document(facture_id, document_id, user, motif)


@router.get("/{facture_id}/historique")
async def historique(
    facture_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.factures.view")),
):
    svc = await _svc(db, user)
    f = await svc._facture(facture_id)
    return await svc._historique("facture", f.id)


# ——— Points de facturation ———


@points_router.get("")
async def list_points(
    q: str | None = None,
    type: str | None = None,
    statut: str | None = None,
    supplier_id: UUID | None = None,
    agency_id: UUID | None = None,
    type_facture: str | None = None,
    year: int | None = Query(default=None, ge=2000, le=2100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.factures.view")),
):
    return await (await _svc(db, user)).list_points(
        {"q": q, "type_point": type, "statut": statut, "fournisseur_id": supplier_id, "agence_id": agency_id,
         "type_facture": type_facture, "annee": year}
    )


@points_router.post("", status_code=status.HTTP_201_CREATED)
async def create_point(
    body: PointFacturationCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.facturation.manage")),
):
    svc = await _svc(db, user)
    p = await svc.create_point(body, user)
    return await svc.point_synthese(p.id, None, user)


@points_router.post("/import/preview")
async def import_preview(
    file: UploadFile = File(...),
    fournisseur_id: UUID = Form(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.facturation.manage")),
):
    return await MgFacturationImport(await _svc(db, user)).preview(file, fournisseur_id)


@points_router.post("/import/confirm")
async def import_confirm(
    file: UploadFile = File(...),
    fournisseur_id: UUID = Form(...),
    choix: str = Form(default="[]"),
    suivi_depuis: date | None = Form(default=None),
    periodicite: str = Form(default="MENSUEL"),
    type_facture: str | None = Form(default="ELECTRICITE"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.facturation.manage")),
):
    try:
        selection = TypeAdapter(list[ImportChoix]).validate_python(json.loads(choix or "[]"))
    except (ValueError, ValidationError) as exc:
        raise AppError("Sélection d'import invalide", code="IMPORT_CHOIX_INVALIDE") from exc
    return await MgFacturationImport(await _svc(db, user)).confirm(
        file, fournisseur_id, user, choix=selection, suivi_depuis=suivi_depuis, periodicite=periodicite,
        type_facture=type_facture or None,
    )


@points_router.get("/{point_id}")
async def get_point(
    point_id: UUID,
    year: int | None = Query(default=None, ge=2000, le=2100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.factures.view")),
):
    return await (await _svc(db, user)).point_synthese(point_id, year, user)


@points_router.patch("/{point_id}")
async def update_point(
    point_id: UUID,
    body: PointFacturationIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.facturation.manage")),
):
    svc = await _svc(db, user)
    p = await svc.update_point(point_id, body, user)
    return await svc.point_synthese(p.id, None, user)


@points_router.post("/{point_id}/desactiver")
async def deactivate_point(
    point_id: UUID,
    body: MotifIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.facturation.manage")),
):
    svc = await _svc(db, user)
    p = await svc.set_point_statut(point_id, False, user, body.motif)
    return await svc.point_synthese(p.id, None, user)


@points_router.post("/{point_id}/activer")
async def activate_point(
    point_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.facturation.manage")),
):
    svc = await _svc(db, user)
    p = await svc.set_point_statut(point_id, True, user, None)
    return await svc.point_synthese(p.id, None, user)


@points_router.delete("/{point_id}")
async def delete_point(
    point_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.facturation.manage")),
):
    return await (await _svc(db, user)).delete_point(point_id, user)
