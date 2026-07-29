from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
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
    SoldeNatureLigneRead,
    Soldes14868Read,
    VentilationAmortAgenceGroupeRead,
    VentilationAmortAgenceLigneRead,
    VentilationAmortissementsAgenceRead,
)
from app.services.audit_query import list_audit_for_export
from app.services.audit_service import AuditService
from app.services.immobilisation_service import DashboardService
from app.services.reporting_snapshot import resolve_comptes, resolve_recap, resolve_soldes
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
    ventilation_amortissements_agence_to_excel,
    ventilation_amortissements_agence_to_pdf,
)
from app.services.reporting_service import list_ecritures_for_export, list_immobilisations_for_export
from app.services.ventilation_amortissements_agence import build_ventilation_amortissements_agence

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
    result = await resolve_recap(db, annee)
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
    result = await resolve_recap(db, annee)
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
    result = await resolve_comptes(db, annee, compte=compte)
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
    result = await resolve_comptes(db, annee, compte=compte)
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


@router.get("/reporting/soldes-148-68", response_model=Soldes14868Read)
async def get_soldes_148_68(
    annee: int = Query(..., ge=2000, le=2100),
    _: User = Depends(require_roles("administrateur", "comptable", "auditeur")),
    db: AsyncSession = Depends(get_db),
):
    """Soldes des comptes 148 (amort.) et 68 (dotations) par nature d'immobilisation."""
    result = await resolve_soldes(db, annee)
    return Soldes14868Read(
        annee=result.annee,
        date_arrete=result.date_arrete.isoformat(),
        lignes=[
            SoldeNatureLigneRead(
                nature_code=ligne.nature_code,
                nature=ligne.nature,
                compte_immobilisation=ligne.compte_immobilisation,
                compte_amortissement=ligne.compte_amortissement,
                libelle_amortissement=ligne.libelle_amortissement,
                solde_148=float(ligne.solde_148),
                solde_148_n1=float(ligne.solde_148_n1),
                compte_dotation=ligne.compte_dotation,
                libelle_dotation=ligne.libelle_dotation,
                solde_68=float(ligne.solde_68),
                valeur_brute=float(ligne.valeur_brute),
                vnc=float(ligne.vnc),
                nb_biens=ligne.nb_biens,
            )
            for ligne in result.lignes
        ],
        total_148=float(result.total_148),
        total_148_n1=float(result.total_148_n1),
        total_68=float(result.total_68),
        total_valeur_brute=float(result.total_valeur_brute),
        total_vnc=float(result.total_vnc),
        nb_biens=result.nb_biens,
    )


def _ventilation_ligne_read(line) -> VentilationAmortAgenceLigneRead:
    return VentilationAmortAgenceLigneRead(
        immobilisation_id=line.immobilisation_id,
        code_inventaire=line.code_inventaire,
        designation=line.designation,
        date_acquisition=line.date_acquisition.isoformat() if line.date_acquisition else None,
        valeur_brute=float(line.valeur_brute),
        taux=float(line.taux) if line.taux is not None else None,
        amortissement_cumule=float(line.amortissement_cumule),
        dotation_periode=float(line.dotation_periode),
        vnc=float(line.vnc),
        agence_id=line.agence_id,
        agence_code=line.agence_code,
        agence_libelle=line.agence_libelle,
    )


def _ventilation_to_read(result) -> VentilationAmortissementsAgenceRead:
    return VentilationAmortissementsAgenceRead(
        annee=result.annee,
        periodicite=result.periodicite,
        periode_index=result.periode_index,
        periode_label=result.periode_label,
        date_arrete=result.date_arrete.isoformat(),
        agence_filtre_id=result.agence_filtre_id,
        categorie_filtre_id=result.categorie_filtre_id,
        total_compte_68=float(result.total_compte_68),
        nb_immobilisations=result.nb_immobilisations,
        total_dotations=float(result.total_dotations),
        groupes=[
            VentilationAmortAgenceGroupeRead(
                agence_id=g.agence_id,
                agence_code=g.agence_code,
                agence_libelle=g.agence_libelle,
                total_dotations=float(g.total_dotations),
                nb_immobilisations=g.nb_immobilisations,
                lignes=[_ventilation_ligne_read(ligne) for ligne in g.lignes],
            )
            for g in result.groupes
        ],
        exercices_disponibles=result.exercices_disponibles,
    )


def _ventilation_export_payload(result) -> dict:
    return {
        "annee": result.annee,
        "subtitle": (
            f"{result.periode_label} — Compte 68 ventilé par agence "
            f"(total {float(result.total_compte_68):,.2f} MRU)".replace(",", " ")
        ),
        "total_compte_68": float(result.total_compte_68),
        "nb_immobilisations": result.nb_immobilisations,
        "total_dotations": float(result.total_dotations),
        "groupes": [
            {
                "agence_libelle": g.agence_libelle,
                "agence_code": g.agence_code,
                "total_dotations": float(g.total_dotations),
                "nb_immobilisations": g.nb_immobilisations,
                "lignes": [
                    {
                        "designation": ligne.designation,
                        "code_inventaire": ligne.code_inventaire,
                        "date_acquisition_fmt": ligne.date_acquisition.strftime("%d/%m/%Y")
                        if ligne.date_acquisition
                        else "",
                        "valeur_brute": float(ligne.valeur_brute),
                        "taux": float(ligne.taux) if ligne.taux is not None else None,
                        "amortissement_cumule": float(ligne.amortissement_cumule),
                        "dotation_periode": float(ligne.dotation_periode),
                        "vnc": float(ligne.vnc),
                        "agence": ligne.agence_libelle,
                    }
                    for ligne in g.lignes
                ],
            }
            for g in result.groupes
        ],
    }


async def _build_ventilation(
    db: AsyncSession,
    *,
    annee: int,
    periodicite: str,
    periode_index: int | None,
    agence_id: UUID | None,
    categorie_id: UUID | None,
):
    try:
        return await build_ventilation_amortissements_agence(
            db,
            annee=annee,
            periodicite=periodicite,
            periode_index=periode_index,
            agence_id=agence_id,
            categorie_id=categorie_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/reporting/amortissements-agence",
    response_model=VentilationAmortissementsAgenceRead,
)
@router.get(
    "/rapports/amortissements-agence",
    response_model=VentilationAmortissementsAgenceRead,
    include_in_schema=False,
)
async def get_amortissements_agence(
    annee: int = Query(..., ge=2000, le=2100),
    periodicite: str = Query("trimestriel", pattern="^(mensuel|trimestriel|annuel)$"),
    periode_index: int | None = Query(
        None,
        ge=1,
        le=12,
        description="1–4 (trimestriel) ou 1–12 (mensuel). Ignoré si annuel.",
    ),
    agence_id: UUID | None = Query(None, description="Filtrer une agence (vide = toutes)"),
    categorie_id: UUID | None = Query(None, description="Filtrer une catégorie (optionnel)"),
    _: User = Depends(require_roles("administrateur", "comptable", "auditeur")),
    db: AsyncSession = Depends(get_db),
):
    """Ventilation des dotations (compte 68) par agence."""
    result = await _build_ventilation(
        db,
        annee=annee,
        periodicite=periodicite,
        periode_index=periode_index,
        agence_id=agence_id,
        categorie_id=categorie_id,
    )
    return _ventilation_to_read(result)


@router.get("/reporting/amortissements-agence/export")
@router.get("/rapports/amortissements-agence/export", include_in_schema=False)
async def export_amortissements_agence(
    annee: int = Query(..., ge=2000, le=2100),
    format: str = Query("xlsx", pattern="^(xlsx|pdf)$"),
    periodicite: str = Query("trimestriel", pattern="^(mensuel|trimestriel|annuel)$"),
    periode_index: int | None = Query(None, ge=1, le=12),
    agence_id: UUID | None = Query(None),
    categorie_id: UUID | None = Query(None),
    _: User = Depends(require_roles("administrateur", "comptable", "auditeur")),
    db: AsyncSession = Depends(get_db),
):
    result = await _build_ventilation(
        db,
        annee=annee,
        periodicite=periodicite,
        periode_index=periode_index,
        agence_id=agence_id,
        categorie_id=categorie_id,
    )
    payload = _ventilation_export_payload(result)
    suffix = f"-{result.agence_filtre_id[:8]}" if result.agence_filtre_id else ""
    if format == "pdf":
        content = ventilation_amortissements_agence_to_pdf(payload)
        media = "application/pdf"
        filename = f"amortissements-agence-{annee}{suffix}.pdf"
    else:
        content = ventilation_amortissements_agence_to_excel(payload)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = f"amortissements-agence-{annee}{suffix}.xlsx"
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
