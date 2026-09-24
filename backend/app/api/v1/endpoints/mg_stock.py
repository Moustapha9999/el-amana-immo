"""API Stock & Fournitures — Moyens Généraux."""

from __future__ import annotations

import csv
import io
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_module_access, require_permission
from app.models.auth import User
from app.schemas.common import PaginatedResponse
from app.schemas.mg_ops import BonOut
from app.schemas.mg_stock import (
    AlerteOut,
    ArticleCreate,
    ArticleFicheOut,
    ArticleOut,
    ArticleUpdate,
    DashboardOut,
    DemandeCreate,
    DemandeOut,
    DemandeTransition,
    DemandeUpdate,
    FamilleCreate,
    FamilleOut,
    FamilleUpdate,
    InventaireCreate,
    InventaireLigneIn,
    InventaireOut,
    InventaireLigneOut,
    InventaireTransition,
    MouvementCreate,
    MouvementOut,
    PeriodeOut,
    PeriodeReopenIn,
    RapportCustomExportIn,
    RapportCustomPreviewIn,
    RapportExportIn,
    ParametreCreate,
    ParametreOut,
    ParametreUpdate,
    RapportConsoOut,
    ReceptionBcIn,
)
from app.services.mg_stock_events import audit_stock, notify_stock_roles, notify_stock_user
from app.services.mg_stock_service import MgStockService
from app.services.mg_pdf_service import pdf_demande_fourniture

router = APIRouter(prefix="/mg/stock", tags=["mg-stock"])

_module = [Depends(require_module_access("stock-fournitures"))]


def _article_out(svc: MgStockService, article) -> ArticleOut:
    data = ArticleOut.model_validate(article)
    data.niveau = svc.niveau_stock(article)
    return data


def _article_fiche_out(svc: MgStockService, payload: dict) -> ArticleFicheOut:
    article = payload["article"]
    base = _article_out(svc, article)
    return ArticleFicheOut(
        **base.model_dump(),
        famille_libelle=payload.get("famille_libelle"),
        agence_libelle=payload.get("agence_libelle"),
        stock_initial=payload.get("stock_initial") or 0,
        total_entrees=payload.get("total_entrees") or 0,
        total_sorties=payload.get("total_sorties") or 0,
        total_ajustements=payload.get("total_ajustements") or 0,
        total_inventaires=int(payload.get("total_inventaires") or 0),
    )


def _inventaire_out(inv) -> InventaireOut:
    lignes = []
    for row in inv.lignes:
        item = InventaireLigneOut.model_validate(row)
        if row.article is not None:
            item.article_code = row.article.code
            item.article_designation = row.article.designation
            if getattr(row.article, "famille", None) is not None:
                item.famille_libelle = row.article.famille.libelle
        lignes.append(item)
    data = InventaireOut.model_validate(inv)
    data.lignes = lignes
    data.nb_conforme = sum(1 for l in lignes if l.nature_ecart == "CONFORME")
    data.nb_surplus = sum(1 for l in lignes if l.nature_ecart == "SURPLUS")
    data.nb_manquant = sum(1 for l in lignes if l.nature_ecart == "MANQUANT")
    return data


@router.get("/agences", dependencies=_module)
async def list_agences_stock(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.view")),
):
    from sqlalchemy import select
    from app.models.auth import Agence

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


@router.get("/familles", response_model=list[FamilleOut], dependencies=_module)
async def list_familles(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.view")),
):
    return await MgStockService(db).list_familles()


@router.post("/familles", response_model=FamilleOut, dependencies=_module)
async def create_famille(
    body: FamilleCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.create")),
):
    return await MgStockService(db).create_famille(body)


@router.patch("/familles/{famille_id}", response_model=FamilleOut, dependencies=_module)
async def update_famille(
    famille_id: UUID,
    body: FamilleUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.create")),
):
    return await MgStockService(db).update_famille(famille_id, body)


@router.delete("/familles/{famille_id}", response_model=FamilleOut, dependencies=_module)
async def deactivate_famille(
    famille_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.create")),
):
    """Désactivation logique (pas de suppression physique)."""
    return await MgStockService(db).update_famille(famille_id, FamilleUpdate(is_active=False))


@router.get("/articles", response_model=PaginatedResponse[ArticleOut], dependencies=_module)
async def list_articles(
    q: str | None = None,
    famille_id: UUID | None = None,
    agence_id: UUID | None = None,
    bas_stock: bool = False,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.view")),
):
    svc = MgStockService(db)
    rows, total = await svc.list_articles(
        q=q, famille_id=famille_id, agence_id=agence_id, bas_stock=bas_stock, page=page, size=size
    )
    return PaginatedResponse(
        items=[_article_out(svc, a) for a in rows],
        total=total,
        page=page,
        size=size,
    )


@router.get("/articles/export", dependencies=_module)
async def export_articles(
    q: str | None = None,
    famille_id: UUID | None = None,
    agence_id: UUID | None = None,
    bas_stock: bool = False,
    format: str = Query("xlsx", pattern="^(xlsx|pdf)$"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.export")),
):
    svc = MgStockService(db)
    rows, _ = await svc.list_articles(
        q=q, famille_id=famille_id, agence_id=agence_id, bas_stock=bas_stock, page=1, size=500
    )
    familles = {f.id: f.libelle for f in await svc.list_familles()}
    headers = ["Code", "Désignation", "Famille", "UOM", "Stock", "Min", "Niveau"]
    data_rows = [
        [
            a.code,
            a.designation,
            familles.get(a.famille_id, ""),
            a.uom,
            float(a.stock_actuel or 0),
            float(a.stock_min or 0),
            svc.niveau_stock(a),
        ]
        for a in rows
    ]
    from app.services.reporting_export import build_styled_pdf, build_styled_workbook

    title = "Référentiel articles — Stock & Fournitures"
    subtitle = f"{len(data_rows)} article(s)"
    if format == "xlsx":
        content = build_styled_workbook(
            sheet_title="Articles",
            report_title=title,
            headers=headers,
            rows=data_rows,
            subtitle=subtitle,
        )
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="articles-stock.xlsx"'},
        )
    content = build_styled_pdf(
        report_title=title,
        headers=headers,
        rows=data_rows,
        subtitle=subtitle,
        landscape_mode=True,
    )
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="articles-stock.pdf"'},
    )


@router.get("/articles/{article_id}", response_model=ArticleFicheOut, dependencies=_module)
async def get_article(
    article_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.view")),
):
    svc = MgStockService(db)
    payload = await svc.get_article_fiche(article_id)
    return _article_fiche_out(svc, payload)


@router.post("/articles", response_model=ArticleOut, dependencies=_module)
async def create_article(
    body: ArticleCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.stock.create")),
):
    svc = MgStockService(db)
    article = await svc.create_article(body, user)
    await audit_stock(
        db, user, "create", "mg_article", article.id, request=request,
        after={"code": article.code, "designation": article.designation},
    )
    return _article_out(svc, article)


@router.patch("/articles/{article_id}", response_model=ArticleOut, dependencies=_module)
async def update_article(
    article_id: UUID,
    body: ArticleUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.stock.create")),
):
    svc = MgStockService(db)
    article = await svc.update_article(article_id, body)
    await audit_stock(
        db, user, "update", "mg_article", article.id, request=request,
        after={"code": article.code, "is_active": article.is_active},
    )
    return _article_out(svc, article)


@router.delete("/articles/{article_id}", response_model=ArticleOut, dependencies=_module)
async def deactivate_article(
    article_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.stock.create")),
):
    """Désactivation logique (pas de suppression physique)."""
    from app.schemas.mg_stock import ArticleUpdate

    svc = MgStockService(db)
    article = await svc.update_article(article_id, ArticleUpdate(is_active=False))
    await audit_stock(
        db, user, "deactivate", "mg_article", article.id, request=request,
        after={"code": article.code, "is_active": False},
    )
    return _article_out(svc, article)


@router.get("/mouvements/export", dependencies=_module)
async def export_mouvements(
    type_mouvement: str | None = None,
    agence_id: UUID | None = None,
    format: str = Query("xlsx", pattern="^(xlsx|pdf)$"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.export")),
):
    svc = MgStockService(db)
    rows, _ = await svc.list_mouvements(
        type_mouvement=type_mouvement, agence_id=agence_id, page=1, size=500
    )
    enriched = await svc.enrich_mouvements(rows)
    headers = [
        "Référence",
        "Date",
        "Type",
        "Article",
        "Quantité",
        "Stock disponible",
        "Initiateur",
        "Département",
        "Motif",
    ]
    data_rows = [
        [
            m["reference"],
            m["date_mouvement"].strftime("%Y-%m-%d %H:%M") if m.get("date_mouvement") else "",
            m["type_mouvement"],
            (
                f"{m['article_code']} — {m['article_designation']}"
                if m.get("article_code")
                else str(m.get("article_id") or "")
            ),
            float(m["quantite"] or 0),
            float(m["stock_disponible"] or 0) if m.get("stock_disponible") is not None else "",
            m.get("initiateur_nom") or "",
            m.get("departement") or "",
            m.get("motif") or "",
        ]
        for m in enriched
    ]
    from app.services.reporting_export import build_styled_pdf, build_styled_workbook

    title = "Mouvements de stock — Stock & Fournitures"
    subtitle = f"{len(data_rows)} mouvement(s)"
    if format == "xlsx":
        content = build_styled_workbook(
            sheet_title="Mouvements",
            report_title=title,
            headers=headers,
            rows=data_rows,
            subtitle=subtitle,
        )
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="mouvements-stock.xlsx"'},
        )
    content = build_styled_pdf(
        report_title=title,
        headers=headers,
        rows=data_rows,
        subtitle=subtitle,
        landscape_mode=True,
    )
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="mouvements-stock.pdf"'},
    )


@router.get("/mouvements", response_model=PaginatedResponse[MouvementOut], dependencies=_module)
async def list_mouvements(
    article_id: UUID | None = None,
    type_mouvement: str | None = None,
    agence_id: UUID | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.view")),
):
    svc = MgStockService(db)
    rows, total = await svc.list_mouvements(
        article_id=article_id,
        type_mouvement=type_mouvement,
        agence_id=agence_id,
        page=page,
        size=size,
    )
    items = await svc.enrich_mouvements(rows)
    return PaginatedResponse(items=items, total=total, page=page, size=size)


@router.post("/mouvements", response_model=MouvementOut, dependencies=_module)
async def create_mouvement(
    body: MouvementCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Permission selon type
    t = body.type_mouvement.upper()
    needed = {
        "ENTREE": "mg.stock.entry",
        "SORTIE": "mg.stock.exit",
        "AJUSTEMENT": "mg.stock.adjust",
        "INVENTAIRE": "mg.stock.inventory",
    }.get(t, "mg.stock.entry")
    # Re-check via require pattern manually
    from app.api.deps import load_user_permission_codes, user_has_permission_codes

    have = await load_user_permission_codes(db, user)
    if not user_has_permission_codes(have, needed):
        raise HTTPException(403, detail=f"Permission requise : {needed}")
    if body.allow_negative and not user_has_permission_codes(have, "mg.stock.negative"):
        raise HTTPException(403, detail="Permission requise : mg.stock.negative")
    if body.allow_negative and not (body.motif or "").strip():
        raise HTTPException(400, detail="Motif obligatoire pour un stock négatif.")
    svc = MgStockService(db)
    mvt = await svc.create_mouvement(body, user)
    await audit_stock(
        db, user, "create", "mg_stock_mouvement", mvt.id, request=request,
        after={
            "reference": mvt.reference,
            "type_mouvement": mvt.type_mouvement,
            "article_id": str(mvt.article_id),
            "quantite": str(mvt.quantite),
        },
    )
    return (await svc.enrich_mouvements([mvt]))[0]


@router.get("/receptions/bons", response_model=list[BonOut], dependencies=_module)
async def list_bons_reception(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.entry")),
):
    return await MgStockService(db).list_bons_reception()


@router.post("/receptions/bc/{bon_id}", dependencies=_module)
async def receive_from_bc(
    bon_id: UUID,
    body: ReceptionBcIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.stock.entry")),
):
    result = await MgStockService(db).receive_from_bc(bon_id, body, user)
    bon = result["bon"]
    await audit_stock(
        db, user, "receive", "mg_bon_commande", bon.id, request=request,
        after={
            "reference": bon.reference,
            "statut": bon.statut,
            "mouvements_count": result["mouvements_count"],
        },
    )
    return {
        "bon": BonOut.model_validate(bon),
        "mouvements_count": result["mouvements_count"],
    }


@router.get("/demandes", response_model=PaginatedResponse[DemandeOut], dependencies=_module)
async def list_demandes(
    statut: str | None = None,
    agence_id: UUID | None = None,
    article_id: UUID | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.view")),
):
    rows, total = await MgStockService(db).list_demandes(
        statut=statut, agence_id=agence_id, article_id=article_id, page=page, size=size
    )
    return PaginatedResponse(items=rows, total=total, page=page, size=size)


@router.get("/demandes/export", dependencies=_module)
async def export_demandes(
    statut: str | None = None,
    agence_id: UUID | None = None,
    format: str = Query("xlsx", pattern="^(xlsx|pdf)$"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.export")),
):
    rows, _ = await MgStockService(db).list_demandes(
        statut=statut, agence_id=agence_id, page=1, size=500
    )
    headers = ["Référence", "Date", "Agence", "Département", "Demandeur", "Statut", "Lignes"]
    data_rows = [
        [
            d.reference,
            d.date_demande.isoformat() if d.date_demande else "",
            d.agence_libelle_snapshot or str(d.agence_id),
            d.departement or "",
            d.demandeur_nom or "",
            d.statut,
            len(d.lignes or []),
        ]
        for d in rows
    ]
    from app.services.reporting_export import build_styled_pdf, build_styled_workbook

    title = "Demandes de fournitures — Stock & Fournitures"
    subtitle = f"{len(data_rows)} demande(s)"
    if format == "xlsx":
        content = build_styled_workbook(
            sheet_title="Demandes",
            report_title=title,
            headers=headers,
            rows=data_rows,
            subtitle=subtitle,
        )
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="demandes-stock.xlsx"'},
        )
    content = build_styled_pdf(
        report_title=title,
        headers=headers,
        rows=data_rows,
        subtitle=subtitle,
        landscape_mode=True,
    )
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="demandes-stock.pdf"'},
    )


@router.post("/demandes", response_model=DemandeOut, dependencies=_module)
async def create_demande(
    body: DemandeCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.stock.create")),
):
    demande = await MgStockService(db).create_demande(body, user)
    await audit_stock(
        db, user, "create", "mg_demande_fourniture", demande.id, request=request,
        after={"reference": demande.reference, "statut": demande.statut},
    )
    return demande


@router.get("/demandes/{demande_id}", response_model=DemandeOut, dependencies=_module)
async def get_demande(
    demande_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.view")),
):
    return await MgStockService(db).get_demande(demande_id)


@router.patch("/demandes/{demande_id}", response_model=DemandeOut, dependencies=_module)
async def update_demande(
    demande_id: UUID,
    body: DemandeUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.stock.create")),
):
    return await MgStockService(db).update_demande(demande_id, body, user)


@router.post("/demandes/{demande_id}/transition", response_model=DemandeOut, dependencies=_module)
async def transition_demande(
    demande_id: UUID,
    body: DemandeTransition,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.api.deps import load_user_permission_codes, user_has_permission_codes
    from fastapi import HTTPException

    have = await load_user_permission_codes(db, user)
    action = body.action.strip().lower()
    if action in {"visa_agence", "visa_mg", "rejeter", "archiver"}:
        if not user_has_permission_codes(have, "mg.stock.approve"):
            raise HTTPException(403, detail="Permission mg.stock.approve requise")
    elif action == "servir":
        if not (
            user_has_permission_codes(have, "mg.stock.exit")
            or user_has_permission_codes(have, "mg.stock.approve")
        ):
            raise HTTPException(403, detail="Permission mg.stock.exit ou mg.stock.approve requise")
    elif action in {"soumettre", "annuler"}:
        if not user_has_permission_codes(have, "mg.stock.create"):
            raise HTTPException(403, detail="Permission mg.stock.create requise")

    demande = await MgStockService(db).transition_demande(
        demande_id, body.action, user, body.lignes
    )
    await audit_stock(
        db, user, action, "mg_demande_fourniture", demande.id, request=request,
        after={"reference": demande.reference, "statut": demande.statut},
    )
    if demande.demandeur_id:
        await notify_stock_user(
            db,
            demande.demandeur_id,
            titre=f"Demande {demande.reference}",
            message=f"Statut mis à jour : {demande.statut}",
            entity="mg_demande_fourniture",
            entity_id=demande.id,
            actor=user,
        )
    if action == "servir":
        await notify_stock_roles(
            db,
            {"stock-fournitures.magasinier", "stock-fournitures.admin"},
            titre=f"Demande servie {demande.reference}",
            message=f"La demande {demande.reference} a été servie.",
            entity="mg_demande_fourniture",
            entity_id=demande.id,
            actor=user,
        )
    return demande


@router.get("/demandes/{demande_id}/pdf", dependencies=_module)
async def demande_pdf(
    demande_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.export")),
):
    demande = await MgStockService(db).get_demande(demande_id)
    data = pdf_demande_fourniture(demande)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{demande.reference}.pdf"'},
    )


@router.get("/dashboard", response_model=DashboardOut, dependencies=_module)
async def dashboard(
    agence_id: UUID | None = None,
    famille_id: UUID | None = None,
    period: str = Query("30j"),
    statut_niveau: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.view")),
):
    return await MgStockService(db).dashboard(
        agence_id=agence_id,
        famille_id=famille_id,
        period=period,
        statut_niveau=statut_niveau,
    )


@router.get("/alertes", response_model=list[AlerteOut], dependencies=_module)
async def list_alertes(
    agence_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.view")),
):
    return await MgStockService(db).list_alertes(agence_id=agence_id)


@router.get("/alertes/export", dependencies=_module)
async def export_alertes(
    agence_id: UUID | None = None,
    format: str = Query("xlsx", pattern="^(xlsx|pdf)$"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.export")),
):
    rows = await MgStockService(db).list_alertes(agence_id=agence_id)
    headers = ["Code", "Désignation", "Stock", "Min", "Niveau"]
    data_rows = [
        [
            a["code"],
            a["designation"],
            float(a["stock_actuel"] or 0),
            float(a["stock_min"] or 0),
            a["niveau"],
        ]
        for a in rows
    ]
    from app.services.reporting_export import build_styled_pdf, build_styled_workbook

    title = "Alertes stock — Stock & Fournitures"
    subtitle = f"{len(data_rows)} alerte(s)"
    if format == "xlsx":
        content = build_styled_workbook(
            sheet_title="Alertes",
            report_title=title,
            headers=headers,
            rows=data_rows,
            subtitle=subtitle,
        )
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="alertes-stock.xlsx"'},
        )
    content = build_styled_pdf(
        report_title=title,
        headers=headers,
        rows=data_rows,
        subtitle=subtitle,
        landscape_mode=True,
    )
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="alertes-stock.pdf"'},
    )


@router.get("/parametres", response_model=list[ParametreOut], dependencies=_module)
async def list_parametres(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.create")),
):
    return await MgStockService(db).list_parametres()


@router.post("/parametres", response_model=ParametreOut, dependencies=_module)
async def create_parametre(
    body: ParametreCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.create")),
):
    return await MgStockService(db).create_parametre(body)


@router.patch("/parametres/{cle}", response_model=ParametreOut, dependencies=_module)
async def update_parametre(
    cle: str,
    body: ParametreUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.create")),
):
    return await MgStockService(db).update_parametre(cle, body)


@router.delete("/parametres/{cle}", status_code=204, dependencies=_module)
async def delete_parametre(
    cle: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.create")),
):
    await MgStockService(db).delete_parametre(cle)


@router.get("/inventaires", response_model=list[InventaireOut], dependencies=_module)
async def list_inventaires(
    statut: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.view")),
):
    rows = await MgStockService(db).list_inventaires(statut=statut)
    return [_inventaire_out(r) for r in rows]


@router.get("/inventaires/export", dependencies=_module)
async def export_inventaires(
    statut: str | None = None,
    format: str = Query("xlsx", pattern="^(xlsx|pdf)$"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.export")),
):
    rows = await MgStockService(db).list_inventaires(statut=statut)
    headers = ["Référence", "Libellé", "Date début", "Date fin", "Statut", "Lignes"]
    data_rows = [
        [
            inv.reference,
            inv.libelle,
            inv.date_debut.isoformat() if inv.date_debut else "",
            inv.date_fin.isoformat() if inv.date_fin else "",
            inv.statut,
            len(inv.lignes or []),
        ]
        for inv in rows
    ]
    from app.services.reporting_export import build_styled_pdf, build_styled_workbook

    title = "Inventaires — Stock & Fournitures"
    subtitle = f"{len(data_rows)} inventaire(s)"
    if format == "xlsx":
        content = build_styled_workbook(
            sheet_title="Inventaires",
            report_title=title,
            headers=headers,
            rows=data_rows,
            subtitle=subtitle,
        )
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="inventaires-stock.xlsx"'},
        )
    content = build_styled_pdf(
        report_title=title,
        headers=headers,
        rows=data_rows,
        subtitle=subtitle,
        landscape_mode=True,
    )
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="inventaires-stock.pdf"'},
    )


@router.post("/inventaires", response_model=InventaireOut, dependencies=_module)
async def create_inventaire(
    body: InventaireCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.stock.inventory")),
):
    inv = await MgStockService(db).create_inventaire(body, user)
    await audit_stock(
        db, user, "create", "mg_inventaire", inv.id, request=request,
        after={"reference": inv.reference, "statut": inv.statut},
    )
    return _inventaire_out(inv)


@router.get("/inventaires/{inventaire_id}", response_model=InventaireOut, dependencies=_module)
async def get_inventaire(
    inventaire_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.view")),
):
    return _inventaire_out(await MgStockService(db).get_inventaire(inventaire_id))


@router.patch("/inventaires/{inventaire_id}/saisie", response_model=InventaireOut, dependencies=_module)
async def saisir_inventaire(
    inventaire_id: UUID,
    body: list[InventaireLigneIn],
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.inventory")),
):
    inv = await MgStockService(db).saisir_inventaire(inventaire_id, body)
    return _inventaire_out(inv)


@router.post("/inventaires/{inventaire_id}/cloturer", response_model=InventaireOut, dependencies=_module)
async def cloturer_inventaire(
    inventaire_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.stock.inventory")),
):
    inv = await MgStockService(db).cloturer_inventaire(inventaire_id, user)
    await audit_stock(
        db, user, "cloture", "mg_inventaire", inv.id, request=request,
        after={"reference": inv.reference, "statut": inv.statut},
    )
    return _inventaire_out(inv)


@router.post("/inventaires/{inventaire_id}/transition", response_model=InventaireOut, dependencies=_module)
async def transition_inventaire(
    inventaire_id: UUID,
    body: InventaireTransition,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.api.deps import load_user_permission_codes, user_has_permission_codes

    have = await load_user_permission_codes(db, user)
    action = body.action.strip().lower()
    if action in {"valider", "appliquer", "cloturer", "rejeter"}:
        needed = "mg.stock.inventory.validate"
        if not (
            user_has_permission_codes(have, needed)
            or user_has_permission_codes(have, "mg.stock.inventory")
        ):
            raise HTTPException(403, detail=f"Permission {needed} ou mg.stock.inventory requise")
    elif not user_has_permission_codes(have, "mg.stock.inventory"):
        raise HTTPException(403, detail="Permission mg.stock.inventory requise")
    inv = await MgStockService(db).transition_inventaire(
        inventaire_id, action, user, body.motif
    )
    await audit_stock(
        db, user, action, "mg_inventaire", inv.id, request=request,
        after={"reference": inv.reference, "statut": inv.statut},
    )
    return _inventaire_out(inv)


@router.get("/rapports/consommation", dependencies=_module)
async def rapport_consommation(
    year: int = Query(..., ge=2000, le=2100),
    month: int | None = Query(None, ge=1, le=12),
    agence_id: UUID | None = None,
    format: str = Query("json", pattern="^(json|csv|xlsx|pdf)$"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.export")),
):
    data = await MgStockService(db).rapport_conso(year=year, month=month, agence_id=agence_id)
    if format == "json":
        return data

    headers = ["Famille", "Code", "Désignation", "Quantité sortie"]
    rows = [
        [r["famille"], r["code"], r["designation"], float(r["quantite"])]
        for r in data["lignes"]
    ]
    title = f"Consommation stock — {data['periode']}"
    subtitle = f"Granularité {data['granularity']}"

    if format == "csv":
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=["famille", "code", "designation", "quantite"])
        writer.writeheader()
        for row in data["lignes"]:
            writer.writerow(row)
        return Response(
            content=buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="conso-{data["periode"]}.csv"'},
        )

    from app.services.reporting_export import build_styled_pdf, build_styled_workbook

    if format == "xlsx":
        content = build_styled_workbook(
            sheet_title="Consommation",
            report_title=title,
            headers=headers,
            rows=rows,
            subtitle=subtitle,
        )
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="conso-{data["periode"]}.xlsx"'},
        )

    content = build_styled_pdf(
        report_title=title,
        headers=headers,
        rows=rows,
        subtitle=subtitle,
        landscape_mode=True,
    )
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="conso-{data["periode"]}.pdf"'},
    )


@router.get("/periodes", dependencies=_module)
async def list_periodes(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.view")),
):
    from app.services.mg_stock_periodes import MgStockPeriodeService

    rows = await MgStockPeriodeService(db).list_periodes()
    return [PeriodeOut.model_validate(r) for r in rows]


@router.get("/periodes/active", dependencies=_module)
async def periode_active(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.stock.view")),
):
    from app.services.mg_stock_periodes import MgStockPeriodeService

    svc = MgStockPeriodeService(db)
    periode = await svc.ensure_open_periode(user)
    totaux = await svc.totaux_periode(periode)
    code, message = await svc.cloture_alerte(periode)
    await db.commit()
    return {**svc.serialize_periode(periode), **totaux, "cloture_statut": code, "cloture_message": message}


@router.get("/periodes/{periode_id}", dependencies=_module)
async def get_periode(
    periode_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.view")),
):
    from app.services.mg_stock_periodes import MgStockPeriodeService

    svc = MgStockPeriodeService(db)
    periode = await svc.get_periode(periode_id)
    totaux = await svc.totaux_periode(periode)
    return {**svc.serialize_periode(periode), **totaux}


@router.get("/periodes/{periode_id}/soldes", dependencies=_module)
async def list_soldes(
    periode_id: UUID,
    q: str | None = None,
    famille_id: UUID | None = None,
    agence_id: UUID | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.view")),
):
    from app.services.mg_stock_periodes import MgStockPeriodeService

    items, total = await MgStockPeriodeService(db).list_soldes(
        periode_id, q=q, famille_id=famille_id, agence_id=agence_id, page=page, size=size
    )
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/periodes/{periode_id}/preview-cloture", dependencies=_module)
async def preview_cloture(
    periode_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.view")),
):
    from app.services.mg_stock_periodes import MgStockPeriodeService

    return await MgStockPeriodeService(db).preview_cloture(periode_id)


@router.post("/periodes/{periode_id}/cloturer", dependencies=_module)
async def cloturer_periode(
    periode_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.stock.period.close")),
):
    from app.services.mg_stock_periodes import MgStockPeriodeService

    result = await MgStockPeriodeService(db).cloturer(periode_id, user)
    await audit_stock(
        db,
        user,
        "cloture_periode",
        "mg_stock_periode",
        periode_id,
        request=request,
        after={
            "libelle": result["periode"]["libelle"],
            "periode_suivante": result["periode_suivante"]["libelle"],
            "articles": result["articles"],
        },
    )
    await db.commit()
    return result


@router.post("/periodes/{periode_id}/rouvrir", dependencies=_module)
async def rouvrir_periode(
    periode_id: UUID,
    body: PeriodeReopenIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.stock.period.reopen")),
):
    from app.services.mg_stock_periodes import MgStockPeriodeService

    svc = MgStockPeriodeService(db)
    periode, locked = await svc.rouvrir(periode_id, user, body.motif)
    await audit_stock(
        db,
        user,
        "reouverture_periode",
        "mg_stock_periode",
        periode.id,
        request=request,
        after={"libelle": periode.libelle, "motif": body.motif, "verrouilee": locked},
    )
    await db.commit()
    return {**svc.serialize_periode(periode), "periode_verrouillee": locked}


@router.get("/rapports/catalog", dependencies=_module)
async def rapports_catalog(
    _: User = Depends(require_permission("mg.stock.view")),
):
    from app.services.mg_stock_reporting import catalog

    return catalog()


@router.get("/rapports/summary", dependencies=_module)
async def rapports_summary(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.export")),
):
    from app.services.mg_stock_reporting import MgStockReportingService

    return await MgStockReportingService(db).summary()


@router.post("/rapports/personnalise/preview", dependencies=_module)
async def rapport_custom_preview(
    body: RapportCustomPreviewIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.view")),
):
    from app.services.mg_stock_reporting import REPORTS, MgStockReportingService

    if body.dataset not in REPORTS or body.dataset == "personnalise":
        raise HTTPException(400, detail="Type de données inconnu")
    filters = dict(body.filters or {})
    if body.sort_by:
        filters["sort_by"] = body.sort_by
        filters["sort_dir"] = body.sort_dir
    return await MgStockReportingService(db).preview(
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
    user: User = Depends(require_permission("mg.stock.export")),
):
    from app.services.mg_stock_reporting import REPORTS, MgStockReportingService

    if body.dataset not in REPORTS or body.dataset == "personnalise":
        raise HTTPException(400, detail="Type de données inconnu")
    filters = dict(body.filters or {})
    content, media, filename, volume = await MgStockReportingService(db).export(
        body.dataset,
        fmt=body.format,
        scope=body.scope,
        ids=body.ids,
        filters=filters,
        columns=body.columns or None,
        user=user,
    )
    await audit_stock(
        db,
        user,
        "export",
        f"rapport_stock:personnalise:{body.dataset}",
        body.dataset,
        request=request,
        after={"format": body.format, "volume": volume},
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
    motif: str | None = None,
    type: str | None = None,
    departement: str | None = None,
    nature_ecart: str | None = None,
    agence_id: UUID | None = None,
    famille_id: UUID | None = None,
    annee: int | None = None,
    mois: int | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.view")),
):
    from app.services.mg_stock_reporting import MgStockReportingService

    return await MgStockReportingService(db).preview(
        report_key,
        filters={
            "q": q,
            "statut": statut,
            "motif": motif,
            "type": type,
            "departement": departement,
            "nature_ecart": nature_ecart,
            "agence_id": str(agence_id) if agence_id else None,
            "famille_id": str(famille_id) if famille_id else None,
            "annee": annee,
            "mois": mois,
        },
        page=page,
        size=size,
    )


@router.post("/rapports/{report_key}/export", dependencies=_module)
async def rapport_export(
    report_key: str,
    body: RapportExportIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.stock.export")),
):
    from app.services.mg_stock_reporting import MgStockReportingService

    content, media, filename, volume = await MgStockReportingService(db).export(
        report_key,
        fmt=body.format,
        scope=body.scope,
        ids=body.ids,
        filters=body.filters,
        columns=body.columns,
        user=user,
    )
    await audit_stock(
        db,
        user,
        "export",
        f"rapport_stock:{report_key}",
        report_key,
        request=request,
        after={"format": body.format, "volume": volume},
    )
    await db.commit()
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/imports/articles", dependencies=_module)
async def import_articles_protocol(
    _: User = Depends(require_permission("mg.stock.create")),
):
    from app.services.mg_stock_import import protocol

    return protocol()


@router.post("/imports/articles/analyze", dependencies=_module)
async def import_articles_analyze(
    file: UploadFile = File(...),
    _: User = Depends(require_permission("mg.stock.create")),
):
    from app.services.mg_stock_import import analyze_workbook

    raw = await file.read()
    return analyze_workbook(raw, file.filename or "articles.xlsx")
