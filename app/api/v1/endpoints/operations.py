from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status

from sqlalchemy import select

from sqlalchemy.ext.asyncio import AsyncSession



from app.api.deps import get_current_user, require_roles

from app.core.exceptions import AppError, raise_http_from_app

from app.db.session import get_db

from app.models import Ajustement, Cession, Immobilisation, Rebut, Reevaluation, User

from app.schemas.common import PaginatedResponse

from app.schemas.operations import (

    AjustementCreate,

    AjustementCreateResponse,

    AjustementListRead,

    AjustementRead,

    CessionCreate,

    CessionDetailRead,

    CessionListRead,

    CessionPreviewRequest,

    CessionPreviewResponse,

    CessionRead,

    CessionSortieResponse,

    RebutCreate,

    RebutDetailRead,

    RebutListRead,

    RebutRead,

    RebutSortieResponse,

    ReevaluationCreate,

    ReevaluationCreateResponse,

    ReevaluationDetailRead,

    ReevaluationListRead,

    ReevaluationRead,

)

from app.services.operations_query import (
    get_cession,
    get_rebut,
    get_reevaluation,
    list_ajustements,
    list_cessions,
    list_rebuts,
    list_reevaluations,
)

from app.services.operations_service import CessionService, RebutService

from app.services.reevaluation_service import AjustementService, ReevaluationService

from app.services.audit_helpers import record_audit



router = APIRouter(tags=["operations"])





def _cession_list_read(cession: Cession, immo: Immobilisation | None) -> CessionListRead:
    base = CessionRead.model_validate(cession)
    return CessionListRead(
        **base.model_dump(),
        code_inventaire=immo.code_inventaire if immo else None,
        designation=immo.designation if immo else None,
    )


def _cession_detail_read(cession: Cession, immo: Immobilisation | None) -> CessionDetailRead:
    from decimal import Decimal

    base = _cession_list_read(cession, immo)
    resultat = (cession.prix_cession - cession.vnc).quantize(Decimal("0.01"))
    if cession.plus_value and cession.plus_value > 0:
        cas = "plus_value"
    elif cession.moins_value and cession.moins_value > 0:
        cas = "moins_value"
    else:
        cas = "equilibre"
    return CessionDetailRead(
        **base.model_dump(),
        valeur_brute=immo.valeur_brute if immo else None,
        date_acquisition=immo.date_acquisition if immo else None,
        compte_immobilisation=immo.compte_immobilisation if immo else None,
        statut_immobilisation=immo.statut.value if immo and hasattr(immo.statut, "value") else (
            str(immo.statut) if immo else None
        ),
        resultat=resultat,
        cas=cas,
    )


def _cession_export_payload(cession: Cession, immo: Immobilisation | None) -> dict:
    detail = _cession_detail_read(cession, immo)
    cas_labels = {
        "plus_value": "Plus-value",
        "moins_value": "Moins-value",
        "equilibre": "Équilibre",
    }
    return {
        "reference": detail.reference or detail.libelle,
        "date_cession_fmt": detail.date_cession.strftime("%d/%m/%Y"),
        "code_inventaire": detail.code_inventaire,
        "designation": detail.designation,
        "date_acquisition_fmt": detail.date_acquisition.strftime("%d/%m/%Y") if detail.date_acquisition else None,
        "compte_immobilisation": detail.compte_immobilisation,
        "valeur_brute": float(detail.valeur_brute) if detail.valeur_brute is not None else "",
        "vnc": float(detail.vnc),
        "prix_cession": float(detail.prix_cession),
        "resultat": float(detail.resultat),
        "plus_value": float(detail.plus_value),
        "moins_value": float(detail.moins_value),
        "cas_label": cas_labels.get(detail.cas, detail.cas),
        "observations": detail.observations,
        "subtitle": f"Réf. {detail.reference or detail.id} — {detail.code_inventaire or ''}",
    }





def _rebut_list_read(rebut: Rebut, immo: Immobilisation | None) -> RebutListRead:

    base = RebutRead.model_validate(rebut)

    return RebutListRead(

        **base.model_dump(),

        code_inventaire=immo.code_inventaire if immo else None,

        designation=immo.designation if immo else None,

    )


def _rebut_detail_read(rebut: Rebut, immo: Immobilisation | None) -> RebutDetailRead:
    from decimal import Decimal

    base = _rebut_list_read(rebut, immo)
    cumul = None
    if immo is not None and immo.valeur_brute is not None:
        cumul = (immo.valeur_brute - rebut.vnc).quantize(Decimal("0.01"))
        if cumul < 0:
            cumul = Decimal("0.00")
    return RebutDetailRead(
        **base.model_dump(),
        valeur_brute=immo.valeur_brute if immo else None,
        date_acquisition=immo.date_acquisition if immo else None,
        compte_immobilisation=immo.compte_immobilisation if immo else None,
        statut_immobilisation=immo.statut.value if immo and hasattr(immo.statut, "value") else (
            str(immo.statut) if immo else None
        ),
        cumul_amortissement=cumul,
    )


def _rebut_export_payload(rebut: Rebut, immo: Immobilisation | None) -> dict:
    detail = _rebut_detail_read(rebut, immo)
    return {
        "date_rebut_fmt": detail.date_rebut.strftime("%d/%m/%Y"),
        "code_inventaire": detail.code_inventaire,
        "designation": detail.designation,
        "date_acquisition_fmt": detail.date_acquisition.strftime("%d/%m/%Y") if detail.date_acquisition else None,
        "compte_immobilisation": detail.compte_immobilisation,
        "valeur_brute": float(detail.valeur_brute) if detail.valeur_brute is not None else "",
        "cumul_amortissement": float(detail.cumul_amortissement) if detail.cumul_amortissement is not None else "",
        "vnc": float(detail.vnc),
        "motif": detail.motif,
        "statut_immobilisation": detail.statut_immobilisation,
        "subtitle": f"{detail.code_inventaire or ''} — {detail.date_rebut.strftime('%d/%m/%Y')}",
    }





def _reevaluation_list_read(row: Reevaluation, immo: Immobilisation | None) -> ReevaluationListRead:

    base = ReevaluationRead.model_validate(row)

    return ReevaluationListRead(

        **base.model_dump(),

        code_inventaire=immo.code_inventaire if immo else None,

        designation=immo.designation if immo else None,

    )


def _reevaluation_detail_read(row: Reevaluation, immo: Immobilisation | None) -> ReevaluationDetailRead:
    from decimal import Decimal

    base = _reevaluation_list_read(row, immo)
    ecart = (row.nouvelle_valeur - row.ancienne_valeur).quantize(Decimal("0.01"))
    if ecart > 0:
        sens = "hausse"
    elif ecart < 0:
        sens = "baisse"
    else:
        sens = "neutre"
    return ReevaluationDetailRead(
        **base.model_dump(),
        valeur_brute=immo.valeur_brute if immo else None,
        date_acquisition=immo.date_acquisition if immo else None,
        compte_immobilisation=immo.compte_immobilisation if immo else None,
        statut_immobilisation=immo.statut.value if immo and hasattr(immo.statut, "value") else (
            str(immo.statut) if immo else None
        ),
        ecart=ecart,
        sens=sens,
    )


def _reevaluation_export_payload(row: Reevaluation, immo: Immobilisation | None) -> dict:
    detail = _reevaluation_detail_read(row, immo)
    sens_labels = {
        "hausse": "Hausse",
        "baisse": "Baisse",
        "neutre": "Neutre",
    }
    return {
        "date_reevaluation_fmt": detail.date_reevaluation.strftime("%d/%m/%Y"),
        "code_inventaire": detail.code_inventaire,
        "designation": detail.designation,
        "date_acquisition_fmt": detail.date_acquisition.strftime("%d/%m/%Y") if detail.date_acquisition else None,
        "compte_immobilisation": detail.compte_immobilisation,
        "valeur_brute_actuelle": float(detail.valeur_brute) if detail.valeur_brute is not None else "",
        "ancienne_valeur": float(detail.ancienne_valeur),
        "nouvelle_valeur": float(detail.nouvelle_valeur),
        "ecart": float(detail.ecart),
        "sens_label": sens_labels.get(detail.sens, detail.sens),
        "justificatif": detail.justificatif,
        "statut_immobilisation": detail.statut_immobilisation,
        "subtitle": f"{detail.code_inventaire or ''} — {detail.date_reevaluation.strftime('%d/%m/%Y')}",
    }





def _ajustement_list_read(row: Ajustement, immo: Immobilisation | None) -> AjustementListRead:

    base = AjustementRead.model_validate(row)

    return AjustementListRead(

        **base.model_dump(),

        code_inventaire=immo.code_inventaire if immo else None,

        designation=immo.designation if immo else None,

    )





@router.get("/cessions", response_model=PaginatedResponse[CessionListRead])
async def list_cessions_endpoint(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    date_debut: date | None = None,
    date_fin: date | None = None,
    search: str | None = None,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows, total = await list_cessions(
        db,
        page,
        size,
        date_debut=date_debut,
        date_fin=date_fin,
        search=search,
    )
    items = [_cession_list_read(c, immo) for c, immo in rows]
    return PaginatedResponse(items=items, total=total, page=page, size=size)


@router.get("/cessions/{cession_id}", response_model=CessionDetailRead)
async def get_cession_endpoint(
    cession_id: UUID,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        cession, immo = await get_cession(db, cession_id)
        return _cession_detail_read(cession, immo)
    except AppError as exc:
        raise_http_from_app(exc)


@router.get("/cessions/{cession_id}/export")
async def export_cession_fiche(
    cession_id: UUID,
    format: str = Query("xlsx", pattern="^(xlsx|pdf)$"),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import Response

    from app.services.reporting_export import cession_fiche_to_excel, cession_fiche_to_pdf

    try:
        cession, immo = await get_cession(db, cession_id)
        payload = _cession_export_payload(cession, immo)
        ref = (cession.reference or str(cession.id)[:8]).replace(" ", "_")
        if format == "pdf":
            content = cession_fiche_to_pdf(payload)
            media = "application/pdf"
            filename = f"fiche-cession-{ref}.pdf"
        else:
            content = cession_fiche_to_excel(payload)
            media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            filename = f"fiche-cession-{ref}.xlsx"
        return Response(
            content=content,
            media_type=media,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except AppError as exc:
        raise_http_from_app(exc)


@router.get("/rebuts", response_model=PaginatedResponse[RebutListRead])
async def list_rebuts_endpoint(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    date_debut: date | None = None,
    date_fin: date | None = None,
    search: str | None = None,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows, total = await list_rebuts(
        db,
        page,
        size,
        date_debut=date_debut,
        date_fin=date_fin,
        search=search,
    )
    items = [_rebut_list_read(r, immo) for r, immo in rows]
    return PaginatedResponse(items=items, total=total, page=page, size=size)


@router.get("/rebuts/{rebut_id}", response_model=RebutDetailRead)
async def get_rebut_endpoint(
    rebut_id: UUID,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        rebut, immo = await get_rebut(db, rebut_id)
        return _rebut_detail_read(rebut, immo)
    except AppError as exc:
        raise_http_from_app(exc)


@router.get("/rebuts/{rebut_id}/export")
async def export_rebut_fiche(
    rebut_id: UUID,
    format: str = Query("xlsx", pattern="^(xlsx|pdf)$"),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import Response

    from app.services.reporting_export import rebut_fiche_to_excel, rebut_fiche_to_pdf

    try:
        rebut, immo = await get_rebut(db, rebut_id)
        payload = _rebut_export_payload(rebut, immo)
        code = (payload.get("code_inventaire") or str(rebut.id)[:8]).replace(" ", "_")
        if format == "pdf":
            content = rebut_fiche_to_pdf(payload)
            media = "application/pdf"
            filename = f"fiche-rebut-{code}.pdf"
        else:
            content = rebut_fiche_to_excel(payload)
            media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            filename = f"fiche-rebut-{code}.xlsx"
        return Response(
            content=content,
            media_type=media,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except AppError as exc:
        raise_http_from_app(exc)





@router.get("/reevaluations", response_model=PaginatedResponse[ReevaluationListRead])
async def list_reevaluations_endpoint(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    date_debut: date | None = None,
    date_fin: date | None = None,
    search: str | None = None,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows, total = await list_reevaluations(
        db,
        page,
        size,
        date_debut=date_debut,
        date_fin=date_fin,
        search=search,
    )
    items = [_reevaluation_list_read(r, immo) for r, immo in rows]
    return PaginatedResponse(items=items, total=total, page=page, size=size)





@router.get("/ajustements", response_model=PaginatedResponse[AjustementListRead])

async def list_ajustements_endpoint(

    page: int = Query(1, ge=1),

    size: int = Query(20, ge=1, le=100),

    _: User = Depends(get_current_user),

    db: AsyncSession = Depends(get_db),

):

    rows, total = await list_ajustements(db, page, size)

    items = [_ajustement_list_read(a, immo) for a, immo in rows]

    return PaginatedResponse(items=items, total=total, page=page, size=size)





@router.post("/cessions/preview", response_model=CessionPreviewResponse)
async def preview_cession(
    payload: CessionPreviewRequest,
    _: User = Depends(require_roles("administrateur", "comptable")),
    db: AsyncSession = Depends(get_db),
):
    """Calcule VNC à la date de cession et le résultat (PV / MV / équilibre) sans enregistrer."""
    try:
        data = await CessionService(db).preview(
            payload.immobilisation_id,
            payload.date_cession,
            payload.prix_cession,
        )
        return CessionPreviewResponse(**data)
    except AppError as exc:
        raise_http_from_app(exc)


@router.post("/cessions", response_model=CessionSortieResponse, status_code=status.HTTP_201_CREATED)

async def create_cession(

    payload: CessionCreate,

    request: Request,

    user: User = Depends(require_roles("administrateur", "comptable")),

    db: AsyncSession = Depends(get_db),

):

    try:

        row, ecriture_ids = await CessionService(db).create(payload)

        await record_audit(

            db,

            user=user,

            action="cession",

            entity="immobilisation",

            entity_id=str(payload.immobilisation_id),

            request=request,

            after={"prix": str(payload.prix_cession), "ecritures": len(ecriture_ids)},

        )

        return CessionSortieResponse(cession=CessionRead.model_validate(row), ecriture_ids=ecriture_ids)

    except AppError as exc:

        raise_http_from_app(exc)





@router.post("/rebuts", response_model=RebutSortieResponse, status_code=status.HTTP_201_CREATED)

async def create_rebut(

    payload: RebutCreate,

    request: Request,

    user: User = Depends(require_roles("administrateur", "comptable")),

    db: AsyncSession = Depends(get_db),

):

    try:

        row, ecriture_ids = await RebutService(db).create(payload)

        await record_audit(

            db,

            user=user,

            action="rebut",

            entity="immobilisation",

            entity_id=str(payload.immobilisation_id),

            request=request,

            after={"vnc": str(row.vnc), "ecritures": len(ecriture_ids)},

        )

        return RebutSortieResponse(rebut=RebutRead.model_validate(row), ecriture_ids=ecriture_ids)

    except AppError as exc:

        raise_http_from_app(exc)





@router.post("/reevaluations", response_model=ReevaluationCreateResponse, status_code=status.HTTP_201_CREATED)

async def create_reevaluation(

    payload: ReevaluationCreate,

    request: Request,

    user: User = Depends(require_roles("administrateur", "comptable")),

    db: AsyncSession = Depends(get_db),

):

    try:

        row, plan_regenere, ecriture_ids = await ReevaluationService(db).create(payload)

        await record_audit(

            db,

            user=user,

            action="reevaluation",

            entity="immobilisation",

            entity_id=str(payload.immobilisation_id),

            request=request,

            after={

                "ancienne": str(row.ancienne_valeur),

                "nouvelle": str(row.nouvelle_valeur),

                "plan_regenere": plan_regenere,

                "ecritures": len(ecriture_ids),

            },

        )

        return ReevaluationCreateResponse(

            reevaluation=ReevaluationRead.model_validate(row),

            plan_regenere=plan_regenere,

            ecriture_ids=ecriture_ids,

        )

    except AppError as exc:

        raise_http_from_app(exc)





@router.post("/ajustements", response_model=AjustementCreateResponse, status_code=status.HTTP_201_CREATED)

async def create_ajustement(

    payload: AjustementCreate,

    request: Request,

    user: User = Depends(require_roles("administrateur", "comptable")),

    db: AsyncSession = Depends(get_db),

):

    try:

        row, ecriture_ids = await AjustementService(db).create(payload)

        await record_audit(

            db,

            user=user,

            action="ajustement",

            entity="immobilisation",

            entity_id=str(payload.immobilisation_id),

            request=request,

            after={

                "type": payload.type_ajustement.value,

                "montant": str(payload.montant),

                "ecritures": len(ecriture_ids),

            },

        )

        return AjustementCreateResponse(ajustement=AjustementRead.model_validate(row), ecriture_ids=ecriture_ids)

    except AppError as exc:

        raise_http_from_app(exc)





@router.get("/reevaluations/immobilisation/{immobilisation_id}", response_model=list[ReevaluationRead])

async def list_reevaluations_for_immo(

    immobilisation_id: UUID,

    _: User = Depends(get_current_user),

    db: AsyncSession = Depends(get_db),

):

    result = await db.execute(

        select(Reevaluation)

        .where(Reevaluation.immobilisation_id == immobilisation_id)

        .order_by(Reevaluation.date_reevaluation.desc())

    )

    return list(result.scalars().all())


@router.get("/reevaluations/{reevaluation_id}", response_model=ReevaluationDetailRead)
async def get_reevaluation_endpoint(
    reevaluation_id: UUID,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        row, immo = await get_reevaluation(db, reevaluation_id)
        return _reevaluation_detail_read(row, immo)
    except AppError as exc:
        raise_http_from_app(exc)


@router.get("/reevaluations/{reevaluation_id}/export")
async def export_reevaluation_fiche(
    reevaluation_id: UUID,
    format: str = Query("xlsx", pattern="^(xlsx|pdf)$"),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import Response

    from app.services.reporting_export import reevaluation_fiche_to_excel, reevaluation_fiche_to_pdf

    try:
        row, immo = await get_reevaluation(db, reevaluation_id)
        payload = _reevaluation_export_payload(row, immo)
        code = (payload.get("code_inventaire") or str(row.id)[:8]).replace(" ", "_")
        if format == "pdf":
            content = reevaluation_fiche_to_pdf(payload)
            media = "application/pdf"
            filename = f"fiche-reevaluation-{code}.pdf"
        else:
            content = reevaluation_fiche_to_excel(payload)
            media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            filename = f"fiche-reevaluation-{code}.xlsx"
        return Response(
            content=content,
            media_type=media,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except AppError as exc:
        raise_http_from_app(exc)


