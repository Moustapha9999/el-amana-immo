from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.api.v1.endpoints.helpers import to_paginated
from app.core.exceptions import AppError, NotFoundError, raise_http_from_app
from app.core.pagination import page_offset
from app.db.session import get_db
from app.models import EcritureComptable, Immobilisation, User
from app.schemas.comptabilite import (
    AmortissementCalculerLigneRead,
    AmortissementCalculerRequest,
    AmortissementCalculerResponse,
    AmortissementComptabiliserRequest,
    AmortissementComptabiliserResponse,
    AmortissementGenererPlanRequest,
    AmortissementRead,
    AmortissementSimulateRequest,
    ComptePlanCreateLinked,
    ComptePlanRead,
    ComptePlanUpdate,
    EcritureCreate,
    EcritureDetailRead,
    EcritureRead,
    JournalCreate,
    JournalRead,
    ParametrageAmortissementRead,
    ParametrageAmortissementUpdate,
)
from app.schemas.common import MessageResponse, PaginatedResponse
from app.services.amortissement_batch import AmortissementBatchService, CalculAmortLigne
from app.services.amortissement_service import AmortissementService
from app.services.audit_helpers import record_audit
from app.services.immobilisation_service import ParametrageService
from app.services.compte_nature_service import CompteNatureService
from app.services.organisation_service import ComptePlanService, JournalService


def _calcul_ligne_read(ligne: CalculAmortLigne) -> AmortissementCalculerLigneRead:
    return AmortissementCalculerLigneRead(
        immobilisation_id=ligne.immobilisation_id,
        code_inventaire=ligne.code_inventaire,
        designation=ligne.designation,
        statut=ligne.statut,
        vnc_avant=ligne.vnc_avant,
        dotation=ligne.dotation,
        vnc_apres=ligne.vnc_apres,
        cumul_avant=ligne.cumul_avant,
        cumul_apres=ligne.cumul_apres,
        valeur_brute=ligne.valeur_brute,
        nature=ligne.nature,
        compte_dotation=ligne.compte_dotation,
        compte_amortissement=ligne.compte_amortissement,
        taux=ligne.taux,
        message=ligne.message,
    )

router = APIRouter(tags=["comptabilite"])


@router.get("/journaux", response_model=PaginatedResponse[JournalRead])
async def list_journaux(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), search: str | None = None, _: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    items, total = await JournalService(db).list(page, size, search)
    return to_paginated(items, total, page, size, JournalRead.model_validate)


@router.post("/journaux", response_model=JournalRead, status_code=status.HTTP_201_CREATED)
async def create_journal(payload: JournalCreate, _: User = Depends(require_roles("administrateur", "comptable")), db: AsyncSession = Depends(get_db)):
    return await JournalService(db).create(payload)


@router.get("/plan-comptable", response_model=PaginatedResponse[ComptePlanRead])
async def list_plan(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models import CategorieImmobilisation

    items, total = await ComptePlanService(db).list(page, size, search)
    categories = list(
        (
            await db.execute(
                select(CategorieImmobilisation).where(CategorieImmobilisation.deleted_at.is_(None))
            )
        )
        .scalars()
        .all()
    )
    natures = {c.compte_immobilisation: c for c in categories if c.compte_immobilisation}
    by_amort = {c.compte_amortissement: c for c in categories if c.compte_amortissement}
    by_dot = {c.compte_dotation: c for c in categories if c.compte_dotation}

    def to_read(row) -> ComptePlanRead:
        nat = natures.get(row.numero) or by_amort.get(row.numero) or by_dot.get(row.numero)
        data = ComptePlanRead.model_validate(row)
        if nat is None:
            return data
        return data.model_copy(
            update={
                "nature_code": nat.code,
                "nature_libelle": nat.famille,
                "nature_taux": nat.taux_lineaire_defaut,
                "nature_duree_annees": nat.duree_annees_defaut,
                "nature_compte_amortissement": nat.compte_amortissement,
                "nature_compte_dotation": nat.compte_dotation,
            }
        )

    return to_paginated(items, total, page, size, to_read)


@router.post("/plan-comptable", response_model=ComptePlanRead, status_code=status.HTTP_201_CREATED)
async def create_compte(
    payload: ComptePlanCreateLinked,
    _: User = Depends(require_roles("administrateur", "comptable")),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await CompteNatureService(db).create_linked(payload)
    except AppError as exc:
        raise_http_from_app(exc)


@router.get("/plan-comptable/{entity_id}", response_model=ComptePlanRead)
async def get_compte(
    entity_id: UUID,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await ComptePlanService(db).get(entity_id)
    except AppError as exc:
        raise_http_from_app(exc)


@router.patch("/plan-comptable/{entity_id}", response_model=ComptePlanRead)
async def update_compte(
    entity_id: UUID,
    payload: ComptePlanUpdate,
    _: User = Depends(require_roles("administrateur", "comptable")),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await ComptePlanService(db).update(entity_id, payload)
    except AppError as exc:
        raise_http_from_app(exc)


@router.delete("/plan-comptable/{entity_id}", response_model=MessageResponse)
async def delete_compte(
    entity_id: UUID,
    _: User = Depends(require_roles("administrateur")),
    db: AsyncSession = Depends(get_db),
):
    try:
        await ComptePlanService(db).soft_delete(entity_id)
        return MessageResponse(message="Compte désactivé")
    except AppError as exc:
        raise_http_from_app(exc)


@router.get("/parametrage/amortissement", response_model=ParametrageAmortissementRead)
async def get_parametrage(_: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await ParametrageService(db).get_or_create()


@router.patch("/parametrage/amortissement", response_model=ParametrageAmortissementRead)
async def update_parametrage(payload: ParametrageAmortissementUpdate, _: User = Depends(require_roles("administrateur")), db: AsyncSession = Depends(get_db)):
    return await ParametrageService(db).update(payload.model_dump(exclude_unset=True))


@router.get("/amortissements/immobilisation/{immobilisation_id}", response_model=list[AmortissementRead])
async def list_amortissements(immobilisation_id: UUID, _: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = await AmortissementService(db).list_for_immobilisation(immobilisation_id)
    return [AmortissementRead.model_validate(r) for r in rows]


@router.get("/amortissements/immobilisation/{immobilisation_id}/export")
async def export_amortissement_fiche(
    immobilisation_id: UUID,
    format: str = Query("xlsx", pattern="^(xlsx|pdf)$"),
    annee: int | None = Query(None, ge=2000, le=2100),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export fiche amortissement (exercice courant par défaut)."""
    from datetime import date as date_cls

    from fastapi.responses import Response

    from app.services.immobilisation_service import ImmobilisationService
    from app.services.reporting_export import (
        _format_periode_export,
        amortissement_fiche_to_excel,
        amortissement_fiche_to_pdf,
    )

    try:
        immo = await ImmobilisationService(db).get(immobilisation_id)
        rows = await AmortissementService(db).list_for_immobilisation(immobilisation_id)
        year = annee or date_cls.today().year
        prefix = f"{year}-"
        plan = [r for r in rows if not r.simule and not r.annule and r.periode.startswith(prefix)]
        lignes = [
            [
                _format_periode_export(r.periode),
                float(r.montant),
                float(r.cumul),
                float(r.vnc),
                "Comptabilisée" if r.valide else "À comptabiliser",
            ]
            for r in plan
        ]
        meta = {
            "subtitle": (
                f"{immo.code_inventaire} — {immo.designation} — "
                f"Exercice {year} — VB {immo.valeur_brute}"
            ),
        }
        code = immo.code_inventaire.replace(" ", "_")
        if format == "pdf":
            content = amortissement_fiche_to_pdf(meta=meta, lignes=lignes)
            media = "application/pdf"
            filename = f"fiche-amortissement-{code}-{year}.pdf"
        else:
            content = amortissement_fiche_to_excel(meta=meta, lignes=lignes)
            media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            filename = f"fiche-amortissement-{code}-{year}.xlsx"
        return Response(
            content=content,
            media_type=media,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except AppError as exc:
        raise_http_from_app(exc)


@router.post("/amortissements/simuler", response_model=AmortissementRead, status_code=status.HTTP_201_CREATED)
async def simuler_amortissement(payload: AmortissementSimulateRequest, _: User = Depends(require_roles("administrateur", "comptable")), db: AsyncSession = Depends(get_db)):
    try:
        row = await AmortissementService(db).simulate(payload.immobilisation_id, payload.periode)
        return row
    except AppError as exc:
        raise_http_from_app(exc)


@router.post("/amortissements/generer-plan", response_model=list[AmortissementRead], status_code=status.HTTP_201_CREATED)
async def generer_plan_amortissement(
    payload: AmortissementGenererPlanRequest,
    _: User = Depends(require_roles("administrateur", "comptable")),
    db: AsyncSession = Depends(get_db),
):
    try:
        rows = await AmortissementService(db).generer_plan(payload.immobilisation_id)
        return [AmortissementRead.model_validate(r) for r in rows]
    except AppError as exc:
        raise_http_from_app(exc)


@router.post("/amortissements/comptabiliser", response_model=AmortissementComptabiliserResponse)
async def comptabiliser_amortissement(
    payload: AmortissementComptabiliserRequest,
    request: Request,
    user: User = Depends(require_roles("administrateur", "comptable")),
    db: AsyncSession = Depends(get_db),
):
    try:
        row, ecriture = await AmortissementService(db).comptabiliser(
            payload.immobilisation_id,
            payload.periode,
            payload.date_ecriture,
        )
        await record_audit(
            db,
            user=user,
            action="comptabiliser_amortissement",
            entity="ecriture_comptable",
            entity_id=str(ecriture.id),
            request=request,
            after={"periode": payload.periode, "montant": str(ecriture.montant)},
        )
        return AmortissementComptabiliserResponse(
            amortissement=AmortissementRead.model_validate(row),
            ecriture=EcritureRead.model_validate(ecriture),
        )
    except AppError as exc:
        raise_http_from_app(exc)


@router.post("/amortissements/calculer", response_model=AmortissementCalculerResponse)
async def calculer_amortissements(
    payload: AmortissementCalculerRequest,
    request: Request,
    user: User = Depends(require_roles("administrateur", "comptable")),
    db: AsyncSession = Depends(get_db),
):
    """Campagne batch : simulation (aperçu) ou validation (écritures de dotation)."""
    try:
        result = await AmortissementBatchService(db).calculer(
            periodicite=payload.periodicite,
            annee=payload.annee,
            periode_index=payload.periode_index,
            mode=payload.mode,
            categorie_ids=payload.categorie_ids,
            date_ecriture=payload.date_ecriture,
            user=user,
        )
        if result.mode == "validation" and result.nb_calcules > 0:
            await record_audit(
                db,
                user=user,
                action="calculer_amortissements",
                entity="amortissement",
                entity_id=result.periode,
                request=request,
                after={
                    "periode": result.periode,
                    "periodicite": result.periodicite,
                    "nb_calcules": result.nb_calcules,
                    "total_dotations": str(result.total_dotations),
                },
            )
        return AmortissementCalculerResponse(
            periodicite=result.periodicite,
            annee=result.annee,
            periode_index=result.periode_index,
            periode=result.periode,
            date_debut=result.date_debut,
            date_arrete=result.date_arrete,
            date_ecriture=result.date_ecriture,
            mode=result.mode,
            periode_statut=result.periode_statut,
            nb_calcules=result.nb_calcules,
            nb_ignores_vnc=result.nb_ignores_vnc,
            nb_deja_comptabilises=result.nb_deja_comptabilises,
            nb_erreurs=result.nb_erreurs,
            total_dotations=result.total_dotations,
            lignes=[_calcul_ligne_read(x) for x in result.lignes],
            ignores=[_calcul_ligne_read(x) for x in result.ignores],
            deja_comptabilises=[_calcul_ligne_read(x) for x in result.deja_comptabilises],
            erreurs=[_calcul_ligne_read(x) for x in result.erreurs],
        )
    except AppError as exc:
        raise_http_from_app(exc)


@router.get("/ecritures", response_model=PaginatedResponse[EcritureRead])
async def list_ecritures(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    date_debut: date | None = None,
    date_fin: date | None = None,
    search: str | None = None,
    journal_code: str | None = None,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import String, cast, or_

    filters = []
    if date_debut is not None:
        filters.append(EcritureComptable.date_ecriture >= date_debut)
    if date_fin is not None:
        filters.append(EcritureComptable.date_ecriture <= date_fin)
    if journal_code and journal_code.strip():
        filters.append(EcritureComptable.journal_code.ilike(journal_code.strip()))
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        filters.append(
            or_(
                EcritureComptable.libelle.ilike(pattern),
                EcritureComptable.journal_code.ilike(pattern),
                EcritureComptable.compte_debit.ilike(pattern),
                EcritureComptable.compte_credit.ilike(pattern),
                EcritureComptable.reference.ilike(pattern),
                cast(EcritureComptable.montant, String).ilike(pattern),
            )
        )

    count = await db.execute(select(func.count()).select_from(EcritureComptable).where(*filters))
    total = int(count.scalar_one())
    result = await db.execute(
        select(EcritureComptable)
        .where(*filters)
        .order_by(EcritureComptable.date_ecriture.desc())
        .offset(page_offset(page, size))
        .limit(size)
    )
    items = list(result.scalars().all())
    return to_paginated(items, total, page, size, EcritureRead.model_validate)


def _type_mouvement_ecriture(ecriture: EcritureComptable) -> str:
    ref = (ecriture.reference or "").upper()
    lib = (ecriture.libelle or "").lower()
    if ref.startswith("AMORT") or "amortissement" in lib or "dotation" in lib:
        return "amortissement"
    if ref.startswith("CESS") or "cession" in lib:
        return "cession"
    if ref.startswith("REBUT") or "rebut" in lib:
        return "rebut"
    if ref.startswith("REEVAL") or "réévalu" in lib or "reeval" in lib:
        return "reevaluation"
    if not ecriture.generee_auto:
        return "manuel"
    return "autre"


async def _ecriture_detail(db: AsyncSession, ecriture_id: UUID) -> EcritureDetailRead:
    row = await db.get(EcritureComptable, ecriture_id)
    if row is None:
        raise NotFoundError("Écriture comptable", str(ecriture_id))
    code = designation = None
    if row.immobilisation_id:
        immo = await db.get(Immobilisation, row.immobilisation_id)
        if immo is not None:
            code = immo.code_inventaire
            designation = immo.designation
    base = EcritureRead.model_validate(row)
    return EcritureDetailRead(
        **base.model_dump(),
        code_inventaire=code,
        designation=designation,
        type_mouvement=_type_mouvement_ecriture(row),
    )


@router.get("/ecritures/{ecriture_id}", response_model=EcritureDetailRead)
async def get_ecriture(
    ecriture_id: UUID,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await _ecriture_detail(db, ecriture_id)
    except AppError as exc:
        raise_http_from_app(exc)


@router.get("/ecritures/{ecriture_id}/export")
async def export_ecriture_fiche(
    ecriture_id: UUID,
    format: str = Query("xlsx", pattern="^(xlsx|pdf)$"),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import Response

    from app.services.reporting_export import ecriture_fiche_to_excel, ecriture_fiche_to_pdf

    try:
        detail = await _ecriture_detail(db, ecriture_id)
        type_labels = {
            "amortissement": "Dotation / amortissement",
            "cession": "Cession",
            "rebut": "Mise au rebut",
            "reevaluation": "Réévaluation",
            "manuel": "Saisie manuelle",
            "autre": "Autre",
        }
        payload = {
            "date_ecriture_fmt": detail.date_ecriture.strftime("%d/%m/%Y"),
            "journal_code": detail.journal_code,
            "libelle": detail.libelle,
            "compte_debit": detail.compte_debit,
            "compte_credit": detail.compte_credit,
            "montant": float(detail.montant),
            "reference": detail.reference or "—",
            "origine": "Automatique" if detail.generee_auto else "Manuelle",
            "validee": "Oui" if detail.validee else "Non",
            "code_inventaire": detail.code_inventaire or "—",
            "designation": detail.designation or "—",
            "type_mouvement": type_labels.get(detail.type_mouvement or "", detail.type_mouvement or "—"),
            "subtitle": f"{detail.reference or detail.id} — {detail.libelle[:60]}",
        }
        ref = (detail.reference or str(detail.id)[:8]).replace(" ", "_")
        if format == "pdf":
            content = ecriture_fiche_to_pdf(payload)
            media = "application/pdf"
            filename = f"fiche-ecriture-{ref}.pdf"
        else:
            content = ecriture_fiche_to_excel(payload)
            media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            filename = f"fiche-ecriture-{ref}.xlsx"
        return Response(
            content=content,
            media_type=media,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except AppError as exc:
        raise_http_from_app(exc)


@router.post("/ecritures", response_model=EcritureRead, status_code=status.HTTP_201_CREATED)
async def create_ecriture(payload: EcritureCreate, _: User = Depends(require_roles("administrateur", "comptable")), db: AsyncSession = Depends(get_db)):
    from app.core.exceptions import AppError, raise_http_from_app
    from app.services.exercice_guard import ensure_exercice_ouvert_pour_date

    try:
        await ensure_exercice_ouvert_pour_date(
            db, payload.date_ecriture, contexte="Écriture comptable"
        )
    except AppError as exc:
        raise_http_from_app(exc)
    row = EcritureComptable(**payload.model_dump(), generee_auto=False)
    db.add(row)
    await db.flush()
    return row
