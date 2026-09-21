"""API Stock & Fournitures — Moyens Généraux."""

from __future__ import annotations

import csv
import io
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_module_access, require_permission
from app.models.auth import User
from app.schemas.mg_stock import (
    AlerteOut,
    ArticleCreate,
    ArticleOut,
    ArticleUpdate,
    DashboardOut,
    DemandeCreate,
    DemandeOut,
    DemandeTransition,
    DemandeUpdate,
    FamilleOut,
    InventaireCreate,
    InventaireLigneIn,
    InventaireOut,
    InventaireLigneOut,
    MouvementCreate,
    MouvementOut,
    ParametreOut,
    ParametreUpdate,
    RapportConsoOut,
)
from app.services.mg_stock_service import MgStockService
from app.services.mg_pdf_service import pdf_demande_fourniture

router = APIRouter(prefix="/mg/stock", tags=["mg-stock"])

_module = [Depends(require_module_access("stock-fournitures"))]


def _article_out(svc: MgStockService, article) -> ArticleOut:
    data = ArticleOut.model_validate(article)
    data.niveau = svc.niveau_stock(article)
    return data


def _inventaire_out(inv) -> InventaireOut:
    lignes = []
    for row in inv.lignes:
        item = InventaireLigneOut.model_validate(row)
        if row.article is not None:
            item.article_code = row.article.code
            item.article_designation = row.article.designation
        lignes.append(item)
    data = InventaireOut.model_validate(inv)
    data.lignes = lignes
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


@router.get("/articles", response_model=list[ArticleOut], dependencies=_module)
async def list_articles(
    q: str | None = None,
    famille_id: UUID | None = None,
    agence_id: UUID | None = None,
    bas_stock: bool = False,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.view")),
):
    svc = MgStockService(db)
    rows = await svc.list_articles(
        q=q, famille_id=famille_id, agence_id=agence_id, bas_stock=bas_stock
    )
    return [_article_out(svc, a) for a in rows]


@router.post("/articles", response_model=ArticleOut, dependencies=_module)
async def create_article(
    body: ArticleCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.stock.create")),
):
    svc = MgStockService(db)
    article = await svc.create_article(body, user)
    return _article_out(svc, article)


@router.patch("/articles/{article_id}", response_model=ArticleOut, dependencies=_module)
async def update_article(
    article_id: UUID,
    body: ArticleUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.create")),
):
    svc = MgStockService(db)
    article = await svc.update_article(article_id, body)
    return _article_out(svc, article)


@router.get("/mouvements", response_model=list[MouvementOut], dependencies=_module)
async def list_mouvements(
    article_id: UUID | None = None,
    type_mouvement: str | None = None,
    agence_id: UUID | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.view")),
):
    return await MgStockService(db).list_mouvements(
        article_id=article_id,
        type_mouvement=type_mouvement,
        agence_id=agence_id,
        limit=limit,
    )


@router.post("/mouvements", response_model=MouvementOut, dependencies=_module)
async def create_mouvement(
    body: MouvementCreate,
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
        from fastapi import HTTPException

        raise HTTPException(403, detail=f"Permission requise : {needed}")
    return await MgStockService(db).create_mouvement(body, user)


@router.get("/demandes", response_model=list[DemandeOut], dependencies=_module)
async def list_demandes(
    statut: str | None = None,
    agence_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.view")),
):
    return await MgStockService(db).list_demandes(statut=statut, agence_id=agence_id)


@router.post("/demandes", response_model=DemandeOut, dependencies=_module)
async def create_demande(
    body: DemandeCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.stock.create")),
):
    return await MgStockService(db).create_demande(body, user)


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
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.api.deps import load_user_permission_codes, user_has_permission_codes
    from fastapi import HTTPException

    have = await load_user_permission_codes(db, user)
    if body.action in {"visa_agence", "visa_mg", "rejeter"}:
        if not user_has_permission_codes(have, "mg.stock.approve"):
            raise HTTPException(403, detail="Permission mg.stock.approve requise")
    elif body.action in {"soumettre", "annuler"}:
        if not user_has_permission_codes(have, "mg.stock.create"):
            raise HTTPException(403, detail="Permission mg.stock.create requise")
    return await MgStockService(db).transition_demande(
        demande_id, body.action, user, body.lignes
    )


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
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.view")),
):
    return await MgStockService(db).dashboard(agence_id=agence_id, famille_id=famille_id)


@router.get("/alertes", response_model=list[AlerteOut], dependencies=_module)
async def list_alertes(
    agence_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.view")),
):
    return await MgStockService(db).list_alertes(agence_id=agence_id)


@router.get("/parametres", response_model=list[ParametreOut], dependencies=_module)
async def list_parametres(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.create")),
):
    return await MgStockService(db).list_parametres()


@router.patch("/parametres/{cle}", response_model=ParametreOut, dependencies=_module)
async def update_parametre(
    cle: str,
    body: ParametreUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.create")),
):
    return await MgStockService(db).update_parametre(cle, body)


@router.get("/inventaires", response_model=list[InventaireOut], dependencies=_module)
async def list_inventaires(
    statut: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("mg.stock.view")),
):
    rows = await MgStockService(db).list_inventaires(statut=statut)
    return [_inventaire_out(r) for r in rows]


@router.post("/inventaires", response_model=InventaireOut, dependencies=_module)
async def create_inventaire(
    body: InventaireCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.stock.inventory")),
):
    inv = await MgStockService(db).create_inventaire(body, user)
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
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("mg.stock.inventory")),
):
    inv = await MgStockService(db).cloturer_inventaire(inventaire_id, user)
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
