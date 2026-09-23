"""API Achats & Approvisionnements — cycle d'achat complet."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_module_access, require_permission
from app.models.auth import Agence, User
from app.schemas.mg_achats import (
    AlerteOut,
    BlCreate,
    BlOut,
    ComparaisonCreate,
    ComparaisonOut,
    ComparaisonUpdate,
    ComparaisonValidateIn,
    ConsultationCreate,
    ConsultationOut,
    ConsultationUpdate,
    DashboardAchatsOut,
    DemandeCreate,
    DemandeOut,
    DemandeUpdate,
    DevisCreate,
    DevisOut,
    DevisUpdate,
    EvenementOut,
    FactureCreate,
    FactureOut,
    FactureUpdate,
    FournisseurSummaryOut,
    PaginatedBonsOut,
    PaiementCreate,
    PaiementOut,
    PaiementUpdate,
    ParametreCreate,
    ParametreOut,
    ParametreUpdate,
    RapportCustomExportIn,
    RapportCustomPreviewIn,
    RapportExportIn,
    RapportSummaryOut,
    ReceptionCreate,
    ReceptionOut,
    ThreeWayMatchOut,
    TransitionIn,
)
from app.schemas.mg_ops import BonCreate, BonOut, BonUpdate
from app.schemas.organisation import FournisseurCreate, FournisseurRead, FournisseurUpdate
from app.services.mg_achats_events import audit_achats, notify_achats_roles
from app.services.mg_achats_service import MgAchatsService
from app.services.mg_pdf_service import _bc_pdf_filename, pdf_bon_commande

router = APIRouter(prefix="/mg/achats", tags=["mg-achats"])
_module = [Depends(require_module_access("achats-appro"))]


def _csv(rows: list[dict], headers: list[str]) -> Response:
    lines = [";".join(headers)]
    for r in rows:
        lines.append(";".join(str(r.get(h, "") or "") for h in headers))
    data = "\n".join(lines).encode("utf-8-sig")
    return Response(
        content=data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="export.csv"'},
    )


# --- Agences / paramètres / dashboard ---


@router.get("/agences", dependencies=_module)
async def list_agences(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.purchase.view")),
):
    rows = (
        await db.execute(
            select(Agence)
            .where(Agence.is_active.is_(True), Agence.deleted_at.is_(None))
            .order_by(Agence.libelle)
        )
    ).scalars().all()
    return [
        {
            "id": str(a.id),
            "code": a.code,
            "libelle": a.libelle,
            "adresse": a.adresse,
            "ville": a.ville,
        }
        for a in rows
    ]


@router.get("/parametres", response_model=list[ParametreOut], dependencies=_module)
async def list_parametres(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.purchase.view")),
):
    return await MgAchatsService(db).list_parametres()


@router.post("/parametres", response_model=ParametreOut, dependencies=_module)
async def create_parametre(
    body: ParametreCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.create")),
):
    row = await MgAchatsService(db).create_parametre(body)
    await audit_achats(db, user, "create", "mg_achat_parametre", row.cle, request)
    return row


@router.patch("/parametres/{cle}", response_model=ParametreOut, dependencies=_module)
async def update_parametre(
    cle: str,
    body: ParametreUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.create")),
):
    row = await MgAchatsService(db).update_parametre(cle, body)
    await audit_achats(db, user, "update", "mg_achat_parametre", cle, request)
    return row


@router.delete("/parametres/{cle}", status_code=status.HTTP_204_NO_CONTENT, dependencies=_module)
async def delete_parametre(
    cle: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.create")),
):
    await MgAchatsService(db).delete_parametre(cle)
    await audit_achats(db, user, "delete", "mg_achat_parametre", cle, request)


@router.get("/dashboard", response_model=DashboardAchatsOut, dependencies=_module)
async def dashboard(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.purchase.view")),
):
    return await MgAchatsService(db).dashboard()


@router.get("/alertes", response_model=list[AlerteOut], dependencies=_module)
async def alertes(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.purchase.view")),
):
    return await MgAchatsService(db).list_alertes()


@router.get("/rapports/summary", response_model=RapportSummaryOut, dependencies=_module)
async def rapports_summary(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.purchase.export")),
):
    return await MgAchatsService(db).rapports_summary()


@router.get("/rapports/catalog", dependencies=_module)
async def rapports_catalog(
    _: User = Depends(require_permission("mg.purchase.view")),
):
    from app.services.mg_achats_reporting import catalog

    return catalog()


@router.post("/rapports/personnalise/preview", dependencies=_module)
async def rapport_custom_preview(
    body: RapportCustomPreviewIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.purchase.view")),
):
    from app.services.mg_achats_reporting import REPORTS, MgAchatsReportingService

    if body.dataset not in REPORTS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Type de données inconnu")
    filters = dict(body.filters or {})
    if body.sort_by:
        filters["sort_by"] = body.sort_by
        filters["sort_dir"] = body.sort_dir
    return await MgAchatsReportingService(db).preview(
        body.dataset,
        filters=filters,
        page=body.page,
        size=body.size,
        columns=body.columns or None,
    )


@router.post("/rapports/personnalise/export", dependencies=_module)
async def rapport_custom_export(
    body: RapportCustomExportIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.export")),
):
    from app.services.mg_achats_reporting import REPORTS, MgAchatsReportingService

    if body.dataset not in REPORTS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Type de données inconnu")
    filters = dict(body.filters or {})
    if body.sort_by:
        filters["sort_by"] = body.sort_by
        filters["sort_dir"] = body.sort_dir
    content, media, filename, volume = await MgAchatsReportingService(db).export(
        body.dataset,
        fmt=body.format,
        scope=body.scope,
        ids=body.ids,
        filters=filters,
        columns=body.columns or None,
        user=user,
    )
    await audit_achats(
        db,
        user,
        "export",
        f"rapport_achats:personnalise:{body.dataset}",
        body.dataset,
        request,
        after={
            "format": body.format,
            "scope": body.scope,
            "volume": volume,
            "columns": body.columns,
            "filters": {k: v for k, v in filters.items() if v},
        },
    )
    await db.commit()
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/rapports/{report_key}/preview", dependencies=_module)
async def rapport_preview(
    report_key: str,
    q: str | None = None,
    statut: str | None = None,
    priorite: str | None = None,
    type_achat: str | None = None,
    type_fournisseur: str | None = None,
    ville: str | None = None,
    pays: str | None = None,
    departement: str | None = None,
    type: str | None = None,
    agence_id: UUID | None = None,
    fournisseur_id: UUID | None = None,
    consultation_id: UUID | None = None,
    bon_id: UUID | None = None,
    date_debut: str | None = None,
    date_fin: str | None = None,
    sort_by: str | None = None,
    sort_dir: str = "desc",
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.purchase.view")),
):
    from app.services.mg_achats_reporting import MgAchatsReportingService

    filters = {
        "q": q,
        "statut": statut,
        "priorite": priorite,
        "type_achat": type_achat,
        "type_fournisseur": type_fournisseur,
        "ville": ville,
        "pays": pays,
        "departement": departement,
        "type": type,
        "agence_id": str(agence_id) if agence_id else None,
        "fournisseur_id": str(fournisseur_id) if fournisseur_id else None,
        "consultation_id": str(consultation_id) if consultation_id else None,
        "bon_id": str(bon_id) if bon_id else None,
        "date_debut": date_debut,
        "date_fin": date_fin,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
    }
    return await MgAchatsReportingService(db).preview(
        report_key, filters=filters, page=page, size=size
    )


@router.post("/rapports/{report_key}/export", dependencies=_module)
async def rapport_export(
    report_key: str,
    body: RapportExportIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.export")),
):
    from app.services.mg_achats_reporting import MgAchatsReportingService

    svc = MgAchatsReportingService(db)
    content, media, filename, volume = await svc.export(
        report_key,
        fmt=body.format,
        scope=body.scope,
        ids=body.ids,
        filters=body.filters,
        columns=body.columns,
        user=user,
    )
    await audit_achats(
        db,
        user,
        "export",
        f"rapport_achats:{report_key}",
        report_key,
        request,
        after={
            "format": body.format,
            "scope": body.scope,
            "volume": volume,
            "filters": {k: v for k, v in (body.filters or {}).items() if v},
            "ids_count": len(body.ids or []),
        },
    )
    await db.commit()
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --- Fournisseurs ---


@router.get("/fournisseurs", dependencies=_module)
async def list_fournisseurs(
    q: str | None = None,
    statut: str | None = None,
    type_fournisseur: str | None = None,
    ville: str | None = None,
    pays: str | None = None,
    actifs_seulement: bool = Query(True),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.purchase.view")),
):
    items, total = await MgAchatsService(db).list_fournisseurs(
        q=q,
        statut=statut,
        type_fournisseur=type_fournisseur,
        ville=ville,
        pays=pays,
        actifs_seulement=actifs_seulement,
        page=page,
        size=size,
    )
    return {"items": items, "total": total, "page": page, "size": size}


@router.post(
    "/fournisseurs",
    response_model=FournisseurRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=_module,
)
async def create_fournisseur(
    body: FournisseurCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.create")),
):
    row = await MgAchatsService(db).create_fournisseur(body, user)
    await audit_achats(
        db,
        user,
        "create",
        "fournisseur",
        row.id,
        request,
        after=MgAchatsService(db)._frs_snapshot(row),
    )
    return row


@router.get(
    "/fournisseurs/{fournisseur_id}",
    response_model=FournisseurSummaryOut,
    dependencies=_module,
)
async def get_fournisseur(
    fournisseur_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.purchase.view")),
):
    return await MgAchatsService(db).get_fournisseur_summary(fournisseur_id)


@router.patch(
    "/fournisseurs/{fournisseur_id}",
    response_model=FournisseurRead,
    dependencies=_module,
)
async def update_fournisseur(
    fournisseur_id: UUID,
    body: FournisseurUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.create")),
):
    svc = MgAchatsService(db)
    row = await svc.update_fournisseur(fournisseur_id, body, user)
    before = getattr(row, "_audit_before", None)
    await audit_achats(
        db,
        user,
        "update",
        "fournisseur",
        row.id,
        request,
        before=before,
        after=svc._frs_snapshot(row),
    )
    return row


@router.post("/fournisseurs/{fournisseur_id}/desactiver", dependencies=_module)
async def desactiver_fournisseur(
    fournisseur_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.create")),
):
    row = await MgAchatsService(db).set_fournisseur_active(fournisseur_id, False, user)
    await audit_achats(
        db,
        user,
        "deactivate",
        "fournisseur",
        row.id,
        request,
        after={"is_active": False, "code": row.code},
    )
    return {"id": str(row.id), "is_active": row.is_active}


@router.post("/fournisseurs/{fournisseur_id}/activer", dependencies=_module)
async def activer_fournisseur(
    fournisseur_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.create")),
):
    row = await MgAchatsService(db).set_fournisseur_active(fournisseur_id, True, user)
    await audit_achats(
        db,
        user,
        "activate",
        "fournisseur",
        row.id,
        request,
        after={"is_active": True, "code": row.code},
    )
    return {"id": str(row.id), "is_active": row.is_active}


@router.delete("/fournisseurs/{fournisseur_id}", dependencies=_module)
async def delete_fournisseur(
    fournisseur_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.create")),
):
    row = await MgAchatsService(db).soft_delete_fournisseur(fournisseur_id, user)
    await audit_achats(
        db,
        user,
        "delete",
        "fournisseur",
        row.id,
        request,
        after={"code": row.code, "deleted": True},
    )
    return {"id": str(row.id), "deleted": True}


# --- Demandes ---


@router.get("/demandes", response_model=list[DemandeOut], dependencies=_module)
async def list_demandes(
    statut: str | None = None,
    q: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.purchase.view")),
):
    svc = MgAchatsService(db)
    rows, _ = await svc.list_demandes(statut=statut, q=q, page=page, size=size)
    return [await svc.serialize_demande(r) for r in rows]


@router.get("/demandes/export", dependencies=_module)
async def export_demandes(
    statut: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.purchase.export")),
):
    rows, _ = await MgAchatsService(db).list_demandes(statut=statut, page=1, size=500)
    return _csv(
        [
            {
                "reference": r.reference,
                "date": r.date_demande,
                "statut": r.statut,
                "priorite": r.priorite,
                "demandeur": r.demandeur_nom,
                "type_achat": r.type_achat,
            }
            for r in rows
        ],
        ["reference", "date", "statut", "priorite", "demandeur", "type_achat"],
    )


@router.post("/demandes", response_model=DemandeOut, dependencies=_module)
async def create_demande(
    body: DemandeCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.demande")),
):
    svc = MgAchatsService(db)
    row = await svc.create_demande(body, user)
    await audit_achats(db, user, "create", "mg_achat_demande", row.id, request)
    return await svc.serialize_demande(row)


@router.get("/demandes/{demande_id}", response_model=DemandeOut, dependencies=_module)
async def get_demande(
    demande_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.purchase.view")),
):
    svc = MgAchatsService(db)
    row = await svc.get_demande(demande_id)
    return await svc.serialize_demande(row)


@router.patch("/demandes/{demande_id}", response_model=DemandeOut, dependencies=_module)
async def update_demande(
    demande_id: UUID,
    body: DemandeUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.demande")),
):
    svc = MgAchatsService(db)
    row = await svc.update_demande(demande_id, body, user)
    await audit_achats(db, user, "update", "mg_achat_demande", row.id, request)
    return await svc.serialize_demande(row)


@router.post(
    "/demandes/{demande_id}/transition",
    response_model=DemandeOut,
    dependencies=_module,
)
async def transition_demande(
    demande_id: UUID,
    body: TransitionIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(
        require_permission("mg.purchase.approve", "mg.purchase.demande", "mg.purchase.create")
    ),
):
    svc = MgAchatsService(db)
    row = await svc.transition_demande(demande_id, body.action, user)
    await audit_achats(
        db, user, f"transition:{body.action}", "mg_achat_demande", row.id, request
    )
    await notify_achats_roles(
        db,
        {"achats-appro.acheteur", "achats-appro.valideur", "achats-appro.admin"},
        titre=f"Demande {row.reference}",
        message=f"Statut → {row.statut}",
        entity="mg_achat_demande",
        entity_id=row.id,
        actor=user,
    )
    return await svc.serialize_demande(row)


@router.get(
    "/demandes/{demande_id}/timeline",
    response_model=list[EvenementOut],
    dependencies=_module,
)
async def demande_timeline(
    demande_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.purchase.view")),
):
    return await MgAchatsService(db).list_evenements("demande", demande_id)


# --- Consultations ---


@router.get("/consultations", response_model=list[ConsultationOut], dependencies=_module)
async def list_consultations(
    statut: str | None = None,
    q: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.purchase.view")),
):
    svc = MgAchatsService(db)
    rows = await svc.list_consultations(statut=statut, q=q)
    return [await svc.consultation_to_out(r) for r in rows]


@router.post("/consultations", response_model=ConsultationOut, dependencies=_module)
async def create_consultation(
    body: ConsultationCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.create")),
):
    svc = MgAchatsService(db)
    row = await svc.create_consultation(body, user)
    await audit_achats(db, user, "create", "mg_achat_consultation", row.id, request)
    return await svc.consultation_to_out(row)


@router.get(
    "/consultations/{consultation_id}",
    response_model=ConsultationOut,
    dependencies=_module,
)
async def get_consultation(
    consultation_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.purchase.view")),
):
    svc = MgAchatsService(db)
    return await svc.consultation_to_out(await svc.get_consultation(consultation_id))


@router.patch(
    "/consultations/{consultation_id}",
    response_model=ConsultationOut,
    dependencies=_module,
)
async def update_consultation(
    consultation_id: UUID,
    body: ConsultationUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.create")),
):
    svc = MgAchatsService(db)
    row = await svc.update_consultation(consultation_id, body, user)
    await audit_achats(db, user, "update", "mg_achat_consultation", row.id, request)
    return await svc.consultation_to_out(row)


@router.post(
    "/consultations/{consultation_id}/transition",
    response_model=ConsultationOut,
    dependencies=_module,
)
async def transition_consultation(
    consultation_id: UUID,
    body: TransitionIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.create", "mg.purchase.approve")),
):
    svc = MgAchatsService(db)
    row = await svc.transition_consultation(consultation_id, body.action, user)
    await audit_achats(
        db, user, f"transition:{body.action}", "mg_achat_consultation", row.id, request
    )
    return await svc.consultation_to_out(row)


@router.delete(
    "/consultations/{consultation_id}",
    response_model=ConsultationOut,
    dependencies=_module,
)
async def delete_consultation(
    consultation_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.create")),
):
    svc = MgAchatsService(db)
    row = await svc.delete_consultation(consultation_id, user)
    await audit_achats(db, user, "delete", "mg_achat_consultation", row.id, request)
    return await svc.consultation_to_out(row)


# --- Devis ---


@router.get("/devis", response_model=list[DevisOut], dependencies=_module)
async def list_devis(
    consultation_id: UUID | None = None,
    fournisseur_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.purchase.view")),
):
    return await MgAchatsService(db).list_devis(
        consultation_id=consultation_id, fournisseur_id=fournisseur_id
    )


@router.post("/devis", response_model=DevisOut, dependencies=_module)
async def create_devis(
    body: DevisCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.create")),
):
    row = await MgAchatsService(db).create_devis(body, user)
    await audit_achats(db, user, "create", "mg_achat_devis", row.id, request)
    return row


@router.get("/devis/{devis_id}", response_model=DevisOut, dependencies=_module)
async def get_devis(
    devis_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.purchase.view")),
):
    return await MgAchatsService(db).get_devis(devis_id)


@router.patch("/devis/{devis_id}", response_model=DevisOut, dependencies=_module)
async def update_devis(
    devis_id: UUID,
    body: DevisUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.create")),
):
    row = await MgAchatsService(db).update_devis(devis_id, body)
    await audit_achats(db, user, "update", "mg_achat_devis", row.id, request)
    return row


# --- Comparaisons ---


@router.get("/comparaisons", response_model=list[ComparaisonOut], dependencies=_module)
async def list_comparaisons(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.purchase.view")),
):
    return await MgAchatsService(db).list_comparaisons()


@router.post("/comparaisons", response_model=ComparaisonOut, dependencies=_module)
async def create_comparaison(
    body: ComparaisonCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.create")),
):
    row = await MgAchatsService(db).create_comparaison(body, user)
    await audit_achats(db, user, "create", "mg_achat_comparaison", row.id, request)
    return row


@router.get(
    "/comparaisons/{comparaison_id}",
    response_model=ComparaisonOut,
    dependencies=_module,
)
async def get_comparaison(
    comparaison_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.purchase.view")),
):
    return await MgAchatsService(db).get_comparaison(comparaison_id)


@router.patch(
    "/comparaisons/{comparaison_id}",
    response_model=ComparaisonOut,
    dependencies=_module,
)
async def update_comparaison(
    comparaison_id: UUID,
    body: ComparaisonUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.create")),
):
    row = await MgAchatsService(db).update_comparaison(comparaison_id, body)
    await audit_achats(db, user, "update", "mg_achat_comparaison", row.id, request)
    return row


@router.post(
    "/comparaisons/{comparaison_id}/valider",
    response_model=ComparaisonOut,
    dependencies=_module,
)
async def validate_comparaison(
    comparaison_id: UUID,
    body: ComparaisonValidateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.approve")),
):
    row = await MgAchatsService(db).validate_comparaison(comparaison_id, body, user)
    await audit_achats(db, user, "valider", "mg_achat_comparaison", row.id, request)
    await notify_achats_roles(
        db,
        {"achats-appro.acheteur", "achats-appro.admin"},
        titre=f"Comparaison {row.reference}",
        message="Fournisseur retenu",
        entity="mg_achat_comparaison",
        entity_id=row.id,
        actor=user,
    )
    return row


# --- Bons de commande ---


@router.get("/bons", response_model=PaginatedBonsOut, dependencies=_module)
async def list_bons(
    statut: str | None = None,
    q: str | None = None,
    fournisseur_id: UUID | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.purchase.view")),
):
    rows, total = await MgAchatsService(db).list_bons(
        page=page, size=size, statut=statut, q=q, fournisseur_id=fournisseur_id
    )
    return PaginatedBonsOut(items=rows, total=total, page=page, size=size)


@router.get("/bons/export", dependencies=_module)
async def export_bons(
    statut: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.purchase.export")),
):
    rows, _ = await MgAchatsService(db).list_bons(statut=statut, page=1, size=500)
    return _csv(
        [
            {
                "reference": r.reference,
                "date": r.date_bc,
                "statut": r.statut,
                "fournisseur": r.fournisseur_raison_sociale,
                "total_ht": r.total_ht,
                "total_ttc": r.total_ttc,
            }
            for r in rows
        ],
        ["reference", "date", "statut", "fournisseur", "total_ht", "total_ttc"],
    )


@router.post("/bons", response_model=BonOut, dependencies=_module)
async def create_bon(
    body: BonCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.create")),
):
    row = await MgAchatsService(db).create_bon(body, user)
    await audit_achats(db, user, "create", "mg_bon_commande", row.id, request)
    return row


@router.get("/bons/{bon_id}", response_model=BonOut, dependencies=_module)
async def get_bon(
    bon_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.purchase.view")),
):
    return await MgAchatsService(db).get_bon(bon_id)


@router.patch("/bons/{bon_id}", response_model=BonOut, dependencies=_module)
async def update_bon(
    bon_id: UUID,
    body: BonUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.create")),
):
    row = await MgAchatsService(db).update_bon(bon_id, body)
    await audit_achats(db, user, "update", "mg_bon_commande", row.id, request)
    return row


@router.delete("/bons/{bon_id}", response_model=BonOut, dependencies=_module)
async def delete_bon(
    bon_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.create")),
):
    row = await MgAchatsService(db).delete_bon(bon_id, user)
    await audit_achats(db, user, "delete", "mg_bon_commande", row.id, request)
    return row


@router.post("/bons/{bon_id}/transition", response_model=BonOut, dependencies=_module)
async def transition_bon(
    bon_id: UUID,
    body: TransitionIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.approve")),
):
    row = await MgAchatsService(db).transition_bon(bon_id, body.action, user)
    await audit_achats(
        db, user, f"transition:{body.action}", "mg_bon_commande", row.id, request
    )
    await notify_achats_roles(
        db,
        {"achats-appro.acheteur", "achats-appro.valideur", "achats-appro.admin"},
        titre=f"BC {row.reference}",
        message=f"Statut → {row.statut}",
        entity="mg_bon_commande",
        entity_id=row.id,
        actor=user,
    )
    return row


@router.post("/bons/{bon_id}/envoyer", response_model=BonOut, dependencies=_module)
async def envoyer_bon(
    bon_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.create")),
):
    row = await MgAchatsService(db).transition_bon(bon_id, "envoyer", user)
    await audit_achats(db, user, "envoyer", "mg_bon_commande", row.id, request)
    return row


@router.post("/bons/{bon_id}/cloturer", response_model=BonOut, dependencies=_module)
async def cloturer_bon(
    bon_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.approve")),
):
    row = await MgAchatsService(db).transition_bon(bon_id, "cloturer", user)
    await audit_achats(db, user, "cloturer", "mg_bon_commande", row.id, request)
    return row


@router.get("/bons/{bon_id}/pdf", dependencies=_module)
async def bon_pdf(
    bon_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.purchase.export")),
    signataire_1: str | None = None,
    signataire_2: str | None = None,
):
    s1 = (signataire_1 or "").strip()
    s2 = (signataire_2 or "").strip()
    if not s1 or not s2:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Veuillez renseigner les deux signataires avant de générer le PDF.",
        )
    bon = await MgAchatsService(db).get_bon(bon_id)
    data = pdf_bon_commande(bon, signataire_1=s1, signataire_2=s2)
    filename = _bc_pdf_filename(bon.reference)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/bons/{bon_id}/timeline",
    response_model=list[EvenementOut],
    dependencies=_module,
)
async def bon_timeline(
    bon_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.purchase.view")),
):
    return await MgAchatsService(db).list_evenements("bon", bon_id)


# --- Livraisons (BL) ---


@router.get("/livraisons", response_model=list[BlOut], dependencies=_module)
async def list_livraisons(
    bon_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.purchase.view")),
):
    svc = MgAchatsService(db)
    rows = await svc.list_bl(bon_id=bon_id)
    return await svc.serialize_bl_list(rows)


@router.post("/livraisons", response_model=BlOut, dependencies=_module)
async def create_livraison(
    body: BlCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.receive")),
):
    svc = MgAchatsService(db)
    row = await svc.create_bl(body, user)
    await audit_achats(db, user, "create", "mg_achat_bl", row.id, request)
    return await svc.serialize_bl(row)


@router.get("/livraisons/{bl_id}", response_model=BlOut, dependencies=_module)
async def get_livraison(
    bl_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.purchase.view")),
):
    svc = MgAchatsService(db)
    return await svc.serialize_bl(await svc.get_bl(bl_id))


# --- Réceptions ---


@router.get("/receptions", response_model=list[ReceptionOut], dependencies=_module)
async def list_receptions(
    bon_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.purchase.view")),
):
    svc = MgAchatsService(db)
    rows = await svc.list_receptions(bon_id=bon_id)
    return await svc.serialize_reception_list(rows)


@router.post("/receptions", response_model=ReceptionOut, dependencies=_module)
async def create_reception(
    body: ReceptionCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.receive")),
):
    svc = MgAchatsService(db)
    row = await svc.create_reception(body, user)
    await audit_achats(db, user, "create", "mg_achat_reception", row.id, request)
    await notify_achats_roles(
        db,
        {"achats-appro.acheteur", "achats-appro.admin"},
        titre=f"Réception {row.reference}",
        message=f"Statut {row.statut}",
        entity="mg_achat_reception",
        entity_id=row.id,
        actor=user,
    )
    return await svc.serialize_reception(row)


@router.get("/receptions/{reception_id}", response_model=ReceptionOut, dependencies=_module)
async def get_reception(
    reception_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.purchase.view")),
):
    svc = MgAchatsService(db)
    return await svc.serialize_reception(await svc.get_reception(reception_id))


# --- Factures ---


@router.get("/factures", response_model=list[FactureOut], dependencies=_module)
async def list_factures(
    bon_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.purchase.view")),
):
    return await MgAchatsService(db).list_factures(bon_id=bon_id)


@router.post("/factures", response_model=FactureOut, dependencies=_module)
async def create_facture(
    body: FactureCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.invoice")),
):
    row = await MgAchatsService(db).create_facture(body, user)
    await audit_achats(db, user, "create", "mg_achat_facture", row.id, request)
    return row


@router.get("/factures/{facture_id}", response_model=FactureOut, dependencies=_module)
async def get_facture(
    facture_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.purchase.view")),
):
    return await MgAchatsService(db).get_facture(facture_id)


@router.patch("/factures/{facture_id}", response_model=FactureOut, dependencies=_module)
async def update_facture(
    facture_id: UUID,
    body: FactureUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.invoice")),
):
    row = await MgAchatsService(db).update_facture(facture_id, body)
    await audit_achats(db, user, "update", "mg_achat_facture", row.id, request)
    return row


@router.post(
    "/factures/{facture_id}/match",
    response_model=ThreeWayMatchOut,
    dependencies=_module,
)
async def match_facture(
    facture_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.invoice")),
):
    result = await MgAchatsService(db).match_facture(facture_id)
    await audit_achats(
        db,
        user,
        "three_way_match",
        "mg_achat_facture",
        facture_id,
        request,
        after={"resultat": result.resultat},
    )
    return result


# --- Paiements ---


@router.get("/paiements", response_model=list[PaiementOut], dependencies=_module)
async def list_paiements(
    facture_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.purchase.view")),
):
    return await MgAchatsService(db).list_paiements(facture_id=facture_id)


@router.post("/paiements", response_model=PaiementOut, dependencies=_module)
async def create_paiement(
    body: PaiementCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.pay")),
):
    row = await MgAchatsService(db).create_paiement(body, user)
    await audit_achats(db, user, "create", "mg_achat_paiement", row.id, request)
    return row


@router.get("/paiements/{paiement_id}", response_model=PaiementOut, dependencies=_module)
async def get_paiement(
    paiement_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.purchase.view")),
):
    return await MgAchatsService(db).get_paiement(paiement_id)


@router.patch("/paiements/{paiement_id}", response_model=PaiementOut, dependencies=_module)
async def update_paiement(
    paiement_id: UUID,
    body: PaiementUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.pay")),
):
    row = await MgAchatsService(db).update_paiement(paiement_id, body)
    await audit_achats(db, user, "update", "mg_achat_paiement", row.id, request)
    return row


# --- Désactivation / suppression (toutes fiches métier) ---

_ENTITY_KINDS = {
    "demandes": "demande",
    "consultations": "consultation",
    "devis": "devis",
    "comparaisons": "comparaison",
    "livraisons": "bl",
    "receptions": "reception",
    "factures": "facture",
    "paiements": "paiement",
}


@router.delete("/demandes/{demande_id}", response_model=DemandeOut, dependencies=_module)
async def delete_demande(
    demande_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.demande")),
):
    row = await MgAchatsService(db).delete_demande(demande_id, user)
    await audit_achats(db, user, "delete", "mg_achat_demande", row.id, request)
    return row


@router.post("/{collection}/{entity_id}/desactiver", dependencies=_module)
async def desactiver_entite(
    collection: str,
    entity_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.create")),
):
    kind = _ENTITY_KINDS.get(collection)
    if kind is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Ressource inconnue")
    row = await MgAchatsService(db).deactivate_entity(kind, entity_id, user)
    await audit_achats(db, user, "deactivate", f"mg_achat_{kind}", row.id, request)
    return row


@router.delete("/{collection}/{entity_id}", dependencies=_module)
async def supprimer_entite(
    collection: str,
    entity_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.purchase.create")),
):
    kind = _ENTITY_KINDS.get(collection)
    if kind is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Ressource inconnue")
    if kind == "demande":
        row = await MgAchatsService(db).delete_demande(entity_id, user)
    elif kind == "consultation":
        row = await MgAchatsService(db).delete_consultation(entity_id, user)
    else:
        row = await MgAchatsService(db).soft_delete_entity(kind, entity_id, user)
    await audit_achats(db, user, "delete", f"mg_achat_{kind}", row.id, request)
    return row
