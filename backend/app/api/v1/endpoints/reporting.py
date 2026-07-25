from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.api.v1.endpoints.helpers import to_paginated
from app.db.session import get_db
from app.models import AuditLog, User
from app.schemas.common import PaginatedResponse
from app.schemas.reporting import (
    AuditLogRead,
    CompteNatureGroupeRead,
    CompteNatureLigneRead,
    CompteOptionRead,
    ComptesParNatureRead,
    DashboardCharts,
    DashboardKpi,
    RecapAmortissementDetailRead,
    RecapAmortissementLigneRead,
    RecapAmortissementRead,
)
from app.services.audit_query import list_audit_for_export
from app.services.audit_service import AuditService
from app.services.comptes_par_nature import build_comptes_par_nature
from app.services.immobilisation_service import DashboardService
from app.services.recap_amortissement import build_recap_amortissement
from app.services.reporting_export import (
    audit_logs_to_excel,
    comptes_par_nature_to_excel,
    comptes_par_nature_to_pdf,
    ecritures_to_excel,
    ecritures_to_pdf,
    format_period_label,
    immobilisations_to_excel,
    recap_amortissement_detail_to_excel,
    recap_amortissement_detail_to_pdf,
    recap_amortissement_to_excel,
    recap_amortissement_to_pdf,
)
from app.services.reporting_service import list_ecritures_for_export, list_immobilisations_for_export

router = APIRouter(tags=["reporting"])


def _audit_to_read(row: AuditLog) -> AuditLogRead:
    return AuditLogRead(
        id=row.id,
        user_id=row.user_id,
        user_email=row.user.email if row.user else None,
        action=row.action,
        entity=row.entity,
        entity_id=row.entity_id,
        ip_address=row.ip_address,
        created_at=row.created_at,
    )


@router.get("/dashboard/kpi", response_model=DashboardKpi)
async def dashboard_kpi(
    statut: str | None = None,
    famille: str | None = None,
    mois: int | None = Query(None, ge=1, le=12),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await DashboardService(db).kpi(statut=statut, famille=famille, mois=mois)
    return DashboardKpi(**data)


@router.get("/dashboard/charts", response_model=DashboardCharts)
async def dashboard_charts(
    statut: str | None = None,
    famille: str | None = None,
    mois: int | None = Query(None, ge=1, le=12),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await DashboardService(db).charts(statut=statut, famille=famille, mois=mois)
    return DashboardCharts(**data)


@router.get("/audit", response_model=PaginatedResponse[AuditLogRead])
async def list_audit(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    entity: str | None = None,
    action: str | None = None,
    search: str | None = None,
    date_debut: date | None = None,
    date_fin: date | None = None,
    _: User = Depends(require_roles("administrateur", "auditeur")),
    db: AsyncSession = Depends(get_db),
):
    items, total = await AuditService(db).list(
        page,
        size,
        entity=entity,
        action=action,
        search=search,
        date_debut=date_debut,
        date_fin=date_fin,
    )
    return to_paginated(items, total, page, size, _audit_to_read)


@router.get("/reporting/audit/export")
async def export_audit(
    entity: str | None = None,
    action: str | None = None,
    search: str | None = None,
    date_debut: date | None = None,
    date_fin: date | None = None,
    _: User = Depends(require_roles("administrateur", "auditeur")),
    db: AsyncSession = Depends(get_db),
):
    rows = await list_audit_for_export(
        db,
        entity=entity,
        action=action,
        search=search,
        date_debut=date_debut,
        date_fin=date_fin,
    )
    content = audit_logs_to_excel(rows, subtitle=format_period_label(date_debut, date_fin))
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="audit-el-amana.xlsx"'},
    )


@router.get("/reporting/ecritures/export")
async def export_ecritures(
    format: str = Query("xlsx", pattern="^(xlsx|pdf)$"),
    date_debut: date | None = None,
    date_fin: date | None = None,
    _: User = Depends(require_roles("administrateur", "comptable", "auditeur")),
    db: AsyncSession = Depends(get_db),
):
    rows = await list_ecritures_for_export(db, date_debut=date_debut, date_fin=date_fin)
    subtitle = format_period_label(date_debut, date_fin)
    if format == "pdf":
        content = ecritures_to_pdf(rows, subtitle=subtitle)
        media = "application/pdf"
        filename = "ecritures-el-amana.pdf"
    else:
        content = ecritures_to_excel(rows, subtitle=subtitle)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = "ecritures-el-amana.xlsx"
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/reporting/immobilisations/export")
async def export_immobilisations(
    _: User = Depends(require_roles("administrateur", "comptable", "auditeur")),
    db: AsyncSession = Depends(get_db),
):
    rows = await list_immobilisations_for_export(db)
    content = immobilisations_to_excel(rows, subtitle="Parc actif (hors biens supprimés)")
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="immobilisations-el-amana.xlsx"'},
    )


@router.get("/reporting/immobilisations/import-template")
async def download_import_template(_: User = Depends(require_roles("administrateur", "comptable"))):
    from app.services.immobilisation_import import immobilisations_import_template_bytes

    return Response(
        content=immobilisations_import_template_bytes(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="modele-import-immobilisations.xlsx"'},
    )


def _recap_ligne_read(line) -> RecapAmortissementLigneRead:
    return RecapAmortissementLigneRead(
        compte_immobilisation=line.compte_immobilisation,
        intitule=line.intitule,
        valeur_brute=float(line.valeur_brute),
        compte_amortissement=line.compte_amortissement,
        amorts_cumules_n1=float(line.amorts_cumules_n1),
        cessions_annee=float(line.cessions_annee),
        dotations_annee=float(line.dotations_annee),
        amorts_cumules_n=float(line.amorts_cumules_n),
        vnc=float(line.vnc),
    )


def _recap_detail_read(detail) -> RecapAmortissementDetailRead:
    return RecapAmortissementDetailRead(
        immobilisation_id=detail.immobilisation_id,
        code_inventaire=detail.code_inventaire,
        designation=detail.designation,
        compte_immobilisation=detail.compte_immobilisation,
        valeur_brute=float(detail.valeur_brute),
        amorts_cumules_n1=float(detail.amorts_cumules_n1),
        cessions_annee=float(detail.cessions_annee),
        dotations_annee=float(detail.dotations_annee),
        amorts_cumules_n=float(detail.amorts_cumules_n),
        vnc=float(detail.vnc),
    )


@router.get("/reporting/recap-amortissement", response_model=RecapAmortissementRead)
async def get_recap_amortissement(
    annee: int = Query(..., ge=2000, le=2100),
    _: User = Depends(require_roles("administrateur", "comptable", "auditeur")),
    db: AsyncSession = Depends(get_db),
):
    result = await build_recap_amortissement(db, annee)
    return RecapAmortissementRead(
        annee=result.annee,
        date_arrete=result.date_arrete.isoformat(),
        lignes=[_recap_ligne_read(ligne) for ligne in result.lignes],
        details=[_recap_detail_read(d) for d in result.details],
        totaux=_recap_ligne_read(result.totaux),
    )


@router.get("/reporting/recap-amortissement/export")
async def export_recap_amortissement(
    annee: int = Query(..., ge=2000, le=2100),
    format: str = Query("xlsx", pattern="^(xlsx|pdf)$"),
    vue: str = Query("synthese", pattern="^(synthese|detail)$"),
    _: User = Depends(require_roles("administrateur", "comptable", "auditeur")),
    db: AsyncSession = Depends(get_db),
):
    result = await build_recap_amortissement(db, annee)
    if vue == "detail":
        payload = {
            "annee": result.annee,
            "subtitle": f"Détail des dotations comptabilisées — Arrêté au 31/12/{result.annee}",
            "details": [
                {
                    "code_inventaire": d.code_inventaire,
                    "designation": d.designation,
                    "compte_immobilisation": d.compte_immobilisation,
                    "dotations_annee": float(d.dotations_annee),
                    "amorts_cumules_n": float(d.amorts_cumules_n),
                    "vnc": float(d.vnc),
                }
                for d in result.details
            ],
            "totaux": {
                "dotations_annee": float(result.totaux.dotations_annee),
                "amorts_cumules_n": float(result.totaux.amorts_cumules_n),
                "vnc": float(result.totaux.vnc),
            },
        }
        if format == "pdf":
            content = recap_amortissement_detail_to_pdf(payload)
            media = "application/pdf"
            filename = f"detail-dotations-amortissement-{annee}.pdf"
        else:
            content = recap_amortissement_detail_to_excel(payload)
            media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            filename = f"detail-dotations-amortissement-{annee}.xlsx"
    else:
        payload = {
            "annee": result.annee,
            "subtitle": f"Arrêté au 31/12/{result.annee} — Comptes 142000 à 147030",
            "lignes": [
                {
                    "compte_immobilisation": ligne.compte_immobilisation,
                    "intitule": ligne.intitule,
                    "valeur_brute": float(ligne.valeur_brute),
                    "compte_amortissement": ligne.compte_amortissement,
                    "amorts_cumules_n1": float(ligne.amorts_cumules_n1),
                    "cessions_annee": float(ligne.cessions_annee),
                    "dotations_annee": float(ligne.dotations_annee),
                    "amorts_cumules_n": float(ligne.amorts_cumules_n),
                    "vnc": float(ligne.vnc),
                }
                for ligne in result.lignes
            ],
            "totaux": {
                "valeur_brute": float(result.totaux.valeur_brute),
                "amorts_cumules_n1": float(result.totaux.amorts_cumules_n1),
                "cessions_annee": float(result.totaux.cessions_annee),
                "dotations_annee": float(result.totaux.dotations_annee),
                "amorts_cumules_n": float(result.totaux.amorts_cumules_n),
                "vnc": float(result.totaux.vnc),
            },
        }
        if format == "pdf":
            content = recap_amortissement_to_pdf(payload)
            media = "application/pdf"
            filename = f"recap-amortissement-{annee}.pdf"
        else:
            content = recap_amortissement_to_excel(payload)
            media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            filename = f"recap-amortissement-{annee}.xlsx"
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _compte_nature_ligne_read(line) -> CompteNatureLigneRead:
    return CompteNatureLigneRead(
        immobilisation_id=line.immobilisation_id,
        code_inventaire=line.code_inventaire,
        date_acquisition=line.date_acquisition.isoformat() if line.date_acquisition else None,
        quantite=line.quantite,
        designation=line.designation,
        valeur_acquisition=float(line.valeur_acquisition),
        taux=float(line.taux) if line.taux is not None else None,
        amorts_cumules_n1=float(line.amorts_cumules_n1),
        dotations_annee=float(line.dotations_annee),
        amorts_cumules_n=float(line.amorts_cumules_n),
        vnc=float(line.vnc),
        agence_code=line.agence_code,
        agence_libelle=line.agence_libelle,
    )


def _comptes_par_nature_payload(result) -> dict:
    def _line_export(line) -> dict:
        return {
            "date_acquisition_fmt": line.date_acquisition.strftime("%d/%m/%Y")
            if line.date_acquisition
            else "",
            "quantite": line.quantite,
            "designation": line.designation,
            "valeur_acquisition": float(line.valeur_acquisition),
            "taux": float(line.taux) if line.taux is not None else None,
            "amorts_cumules_n1": float(line.amorts_cumules_n1),
            "dotations_annee": float(line.dotations_annee),
            "amorts_cumules_n": float(line.amorts_cumules_n),
            "vnc": float(line.vnc),
            "agence": line.agence_libelle or line.agence_code or "",
        }

    def _totaux_export(line) -> dict:
        return {
            "quantite": line.quantite,
            "designation": line.designation,
            "valeur_acquisition": float(line.valeur_acquisition),
            "amorts_cumules_n1": float(line.amorts_cumules_n1),
            "dotations_annee": float(line.dotations_annee),
            "amorts_cumules_n": float(line.amorts_cumules_n),
            "vnc": float(line.vnc),
        }

    if result.compte_filtre:
        lib = next(
            (g.intitule for g in result.groupes if g.compte_immobilisation == result.compte_filtre),
            result.compte_filtre,
        )
        subtitle = f"Arrêté au 31/12/{result.annee} — Compte {result.compte_filtre} ({lib})"
    else:
        subtitle = f"Arrêté au 31/12/{result.annee} — Comptes 142000 à 147030"

    return {
        "annee": result.annee,
        "subtitle": subtitle,
        "groupes": [
            {
                "compte_immobilisation": g.compte_immobilisation,
                "intitule": g.intitule,
                "lignes": [_line_export(ligne) for ligne in g.lignes],
                "totaux": _totaux_export(g.totaux),
            }
            for g in result.groupes
        ],
        "totaux": _totaux_export(result.totaux),
    }


@router.get("/reporting/comptes-par-nature", response_model=ComptesParNatureRead)
async def get_comptes_par_nature(
    annee: int = Query(..., ge=2000, le=2100),
    compte: str | None = Query(None, description="Compte immobilisation (ex. 142010). Vide = tous."),
    _: User = Depends(require_roles("administrateur", "comptable", "auditeur")),
    db: AsyncSession = Depends(get_db),
):
    result = await build_comptes_par_nature(db, annee, compte=compte)
    return ComptesParNatureRead(
        annee=result.annee,
        date_arrete=result.date_arrete.isoformat(),
        groupes=[
            CompteNatureGroupeRead(
                compte_immobilisation=g.compte_immobilisation,
                intitule=g.intitule,
                lignes=[_compte_nature_ligne_read(ligne) for ligne in g.lignes],
                totaux=_compte_nature_ligne_read(g.totaux),
            )
            for g in result.groupes
        ],
        totaux=_compte_nature_ligne_read(result.totaux),
        compte_filtre=result.compte_filtre,
        comptes_disponibles=[
            CompteOptionRead(numero=c.numero, libelle=c.libelle) for c in result.comptes_disponibles
        ],
    )


@router.get("/reporting/comptes-par-nature/export")
async def export_comptes_par_nature(
    annee: int = Query(..., ge=2000, le=2100),
    format: str = Query("xlsx", pattern="^(xlsx|pdf)$"),
    compte: str | None = Query(None),
    _: User = Depends(require_roles("administrateur", "comptable", "auditeur")),
    db: AsyncSession = Depends(get_db),
):
    result = await build_comptes_par_nature(db, annee, compte=compte)
    payload = _comptes_par_nature_payload(result)
    suffix = f"-{result.compte_filtre}" if result.compte_filtre else ""
    if format == "pdf":
        content = comptes_par_nature_to_pdf(payload)
        media = "application/pdf"
        filename = f"comptes-par-nature-{annee}{suffix}.pdf"
    else:
        content = comptes_par_nature_to_excel(payload)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = f"comptes-par-nature-{annee}{suffix}.xlsx"
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
