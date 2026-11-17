"""API Reporting BCM SM — Login 2 + permissions granulaires."""

from __future__ import annotations

import csv
import io
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.exceptions import AppError
from app.db.session import get_db
from app.models import User
from app.models.reporting_bcm_sm import (
    RbcmCalculationRun,
    RbcmCampaign,
    RbcmCellResult,
    RbcmControlResult,
    RbcmDocumentDecision,
    RbcmImport,
    RbcmMappingRule,
    RbcmReconcileIssue,
    RbcmTemplate,
    RbcmTemplateCell,
)
from app.schemas.reporting_bcm_sm import (
    AccueilOut,
    CampaignCreate,
    CampaignListOut,
    CampaignOut,
    CampaignPatch,
    CampaignProgressOut,
    CellResultListOut,
    CellResultOut,
    CondLineListOut,
    CondLineOut,
    ControlResultOut,
    DocumentDecisionIn,
    DashboardOut,
    DeleteEligibilityOut,
    DetLineListOut,
    DetLineOut,
    DocumentDetailOut,
    DocumentListOut,
    DocumentOut,
    ImportConfirmIn,
    ImportListOut,
    ImportOut,
    MappingRuleListOut,
    MappingRuleOut,
    ParameterActionIn,
    ParameterValueIn,
    ParameterValueOut,
    ReconcileIssueListOut,
    ReconcileIssueOut,
    ReportingOwnerCandidateOut,
    ReportingOwnerChangeIn,
    ReportingOwnerHistoryOut,
    ValidationEventOut,
    WorkflowActionIn,
)
from app.services.audit_helpers import record_audit
from app.services.reporting_bcm_sm import (
    campaign_service,
    control_service,
    dashboard_service,
    excel_export,
    import_service,
    parameter_service,
    workflow_service,
)
from app.services.reporting_bcm_sm.document_access import (
    XLSX_TYPE,
    campaign_document_history,
    document_public_dict,
    get_document,
    list_documents,
    public_warnings,
    resolve_deliverable_file,
    safe_download_name,
    sm_period_filename,
)
from app.services.reporting_bcm_sm.access import (
    CONTROL_RUN_PERMS,
    IMPORT_PERMS,
    SAISIR_PARAM_PERMS,
)
from app.services.reporting_bcm_sm.constants import (
    MODULE_CODE,
    OPEN_CAMPAIGN_STATUSES,
    PERM_APPROVE,
    PERM_CONTROL,
    PERM_EXPORT,
    PERM_PREPARE,
    PERM_REOPEN,
    PERM_VIEW,
)
from app.services.reporting_bcm_sm.document_keys import decision_allowed
from app.services.reporting_bcm_sm.engine import runner as engine_runner
from app.services.reporting_bcm_sm.work_fill import generate_work

router = APIRouter(prefix="/reporting-bcm-sm", tags=["Reporting BCM SM"])


def _camp_out(c, names: dict | None = None) -> CampaignOut:  # noqa: ANN001
    out = CampaignOut.model_validate(c)
    names = names or {}
    return out.model_copy(
        update={
            "preparer_name": names.get(c.preparer_id) if c.preparer_id else None,
            "reporting_owner_name": names.get(c.reporting_owner_id)
            if c.reporting_owner_id
            else None,
        }
    )


async def _audit_doc(
    db: AsyncSession,
    *,
    user: User,
    request: Request,
    action: str,
    entity: str,
    entity_id: str,
    after: dict | None = None,
) -> None:
    await record_audit(
        db,
        user=user,
        action=action,
        entity=entity,
        entity_id=entity_id,
        request=request,
        after=after,
        module_code=MODULE_CODE,
        espace_code="comptabilite",
    )


async def _names_for(db: AsyncSession, *campaigns) -> dict:  # noqa: ANN001
    ids: list = []
    for c in campaigns:
        if c is None:
            continue
        ids.append(c.preparer_id)
        ids.append(getattr(c, "reporting_owner_id", None))
    return await campaign_service.display_names(db, ids)


@router.get("/accueil", response_model=AccueilOut)
async def accueil(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_VIEW)),
):
    rows, _ = await campaign_service.list_campaigns(db, page=1, page_size=1)
    open_n = int(
        await db.scalar(
            select(func.count())
            .select_from(RbcmCampaign)
            .where(RbcmCampaign.status.in_(OPEN_CAMPAIGN_STATUSES))
        )
        or 0
    )
    dash = await dashboard_service.dashboard_stats(db)
    last = rows[0] if rows else None
    names = await _names_for(db, last) if last else {}
    return AccueilOut(
        module_code=MODULE_CODE,
        open_campaigns=open_n,
        last_campaign=_camp_out(last, names) if last else None,
        pending_decisions=[
            "D01 mapping",
            "D02 ECART",
            "D06 / D04-D05 paramètres",
            "D09 crédits/dépôts",
            "D15 TOTDEB/TOTCRE",
            "D16/D17",
            "D22",
        ],
        ecart_policy="DESACTIVE jusqu'à validation D02 — aucune constante 2873223 dans le moteur",
        mapping_policy="Règles initiales A_VALIDER uniquement — pas d'activation automatique",
        dashboard=dash,
    )


@router.get("/dashboard", response_model=DashboardOut)
async def dashboard(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_VIEW)),
):
    data = await dashboard_service.dashboard_stats(db)
    return DashboardOut.model_validate(data)


@router.get("/campaigns", response_model=CampaignListOut)
async def list_campaigns(
    year: int | None = None,
    month: int | None = None,
    status: str | None = None,
    bank_code: str | None = None,
    search: str | None = None,
    sort_by: str = Query("period"),
    sort_order: str = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_VIEW)),
):
    rows, total = await campaign_service.list_campaigns(
        db,
        year=year,
        month=month,
        status=status,
        bank_code=bank_code,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    names = await _names_for(db, *rows)
    return CampaignListOut(
        items=[_camp_out(r, names) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/campaigns", response_model=CampaignOut, status_code=201)
async def create_campaign(
    body: CampaignCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_PREPARE)),
):
    camp = await campaign_service.create_campaign(
        db,
        user=user,
        period_year=body.period_year,
        period_month=body.period_month,
        bank_code=body.bank_code,
        closing_date=body.closing_date,
        notes=body.notes,
        label=body.label,
        reporting_owner_id=body.reporting_owner_id,
    )
    await record_audit(
        db,
        user=user,
        action="rbcm.campaign.create",
        entity="rbcm_campaign",
        entity_id=str(camp.id),
        request=request,
        after={
            "period_year": camp.period_year,
            "period_month": camp.period_month,
            "version": camp.campaign_version,
            "preparer_id": str(camp.preparer_id) if camp.preparer_id else None,
            "reporting_owner_id": str(camp.reporting_owner_id)
            if camp.reporting_owner_id
            else None,
        },
        module_code=MODULE_CODE,
        espace_code="comptabilite",
    )
    await db.commit()
    await db.refresh(camp)
    names = await _names_for(db, camp)
    return _camp_out(camp, names)


@router.get("/campaigns/{campaign_id}", response_model=CampaignOut)
async def get_campaign(
    campaign_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_VIEW)),
):
    camp = await campaign_service.get_campaign(db, campaign_id)
    await record_audit(
        db,
        user=user,
        action="rbcm.campaign.view",
        entity="rbcm_campaign",
        entity_id=str(camp.id),
        request=request,
        module_code=MODULE_CODE,
        espace_code="comptabilite",
    )
    await db.commit()
    names = await _names_for(db, camp)
    return _camp_out(camp, names)


@router.get("/preparateurs", response_model=list[ReportingOwnerCandidateOut])
async def list_preparateurs(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_PREPARE)),
):
    rows = await campaign_service.list_reporting_owners(db)
    return [
        ReportingOwnerCandidateOut(id=u.id, full_name=u.full_name, email=u.email)
        for u in rows
    ]


@router.get(
    "/campaigns/{campaign_id}/reporting-owner/history",
    response_model=list[ReportingOwnerHistoryOut],
)
async def reporting_owner_history(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_VIEW)),
):
    await campaign_service.get_campaign(db, campaign_id)
    rows = await campaign_service.list_owner_history(db, campaign_id)
    names = await campaign_service.display_names(
        db,
        [r.from_owner_id for r in rows]
        + [r.to_owner_id for r in rows]
        + [r.actor_id for r in rows],
    )
    return [
        ReportingOwnerHistoryOut.model_validate(r).model_copy(
            update={
                "from_owner_name": names.get(r.from_owner_id) if r.from_owner_id else None,
                "to_owner_name": names.get(r.to_owner_id) if r.to_owner_id else None,
                "actor_name": names.get(r.actor_id) if r.actor_id else None,
            }
        )
        for r in rows
    ]


@router.post(
    "/campaigns/{campaign_id}/reporting-owner",
    response_model=CampaignOut,
)
async def change_reporting_owner(
    campaign_id: uuid.UUID,
    body: ReportingOwnerChangeIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_PREPARE)),
):
    camp = await campaign_service.get_campaign(db, campaign_id)
    before = str(camp.reporting_owner_id) if camp.reporting_owner_id else None
    camp = await campaign_service.assign_reporting_owner(
        db,
        campaign=camp,
        owner_id=body.reporting_owner_id,
        actor=user,
        motif=body.motif,
    )
    await record_audit(
        db,
        user=user,
        action="rbcm.campaign.owner_change",
        entity="rbcm_campaign",
        entity_id=str(camp.id),
        request=request,
        before={"reporting_owner_id": before},
        after={
            "reporting_owner_id": str(camp.reporting_owner_id)
            if camp.reporting_owner_id
            else None,
            "motif": body.motif.strip(),
        },
        module_code=MODULE_CODE,
        espace_code="comptabilite",
    )
    await db.commit()
    await db.refresh(camp)
    names = await _names_for(db, camp)
    return _camp_out(camp, names)


@router.get("/campaigns/{campaign_id}/progress", response_model=CampaignProgressOut)
async def campaign_progress(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_VIEW)),
):
    await campaign_service.get_campaign(db, campaign_id)
    return CampaignProgressOut.model_validate(
        await campaign_service.campaign_progress(db, campaign_id)
    )


@router.get("/campaigns/{campaign_id}/history", response_model=list[ValidationEventOut])
async def campaign_history(
    campaign_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_VIEW)),
):
    await campaign_service.get_campaign(db, campaign_id)
    rows, _ = await campaign_service.list_history(
        db, campaign_id, page=page, page_size=page_size
    )
    return [ValidationEventOut.model_validate(r) for r in rows]


@router.patch("/campaigns/{campaign_id}", response_model=CampaignOut)
async def patch_campaign(
    campaign_id: uuid.UUID,
    body: CampaignPatch,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_PREPARE)),
):
    camp = await campaign_service.get_campaign(db, campaign_id)
    camp = await campaign_service.patch_campaign(
        db, camp, closing_date=body.closing_date, notes=body.notes, user=user
    )
    await record_audit(
        db,
        user=user,
        action="rbcm.campaign.patch",
        entity="rbcm_campaign",
        entity_id=str(camp.id),
        request=request,
        module_code=MODULE_CODE,
        espace_code="comptabilite",
    )
    await db.commit()
    await db.refresh(camp)
    names = await _names_for(db, camp)
    return _camp_out(camp, names)


@router.get("/campaigns/{campaign_id}/delete-check", response_model=DeleteEligibilityOut)
async def delete_check(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_VIEW)),
):
    camp = await campaign_service.get_campaign(db, campaign_id)
    return DeleteEligibilityOut.model_validate(
        await campaign_service.delete_eligibility(db, camp)
    )


@router.delete("/campaigns/{campaign_id}", status_code=204)
async def delete_campaign(
    campaign_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_PREPARE)),
):
    camp = await campaign_service.get_campaign(db, campaign_id)
    meta = {
        "period_year": camp.period_year,
        "period_month": camp.period_month,
        "version": camp.campaign_version,
        "status": camp.status,
    }
    await campaign_service.delete_campaign(db, campaign=camp, user=user)
    await record_audit(
        db,
        user=user,
        action="rbcm.campaign.delete",
        entity="rbcm_campaign",
        entity_id=str(campaign_id),
        request=request,
        before=meta,
        module_code=MODULE_CODE,
        espace_code="comptabilite",
    )
    await db.commit()
    return None


@router.post("/campaigns/{campaign_id}/archive", response_model=CampaignOut)
async def archive_campaign(
    campaign_id: uuid.UUID,
    body: WorkflowActionIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_PREPARE)),
):
    camp = await campaign_service.get_campaign(db, campaign_id)
    camp = await campaign_service.archive_campaign(
        db, campaign=camp, user=user, comment=body.comment
    )
    await record_audit(
        db,
        user=user,
        action="rbcm.campaign.archive",
        entity="rbcm_campaign",
        entity_id=str(camp.id),
        request=request,
        after={"status": camp.status},
        module_code=MODULE_CODE,
        espace_code="comptabilite",
    )
    await db.commit()
    await db.refresh(camp)
    names = await _names_for(db, camp)
    return _camp_out(camp, names)


@router.post("/campaigns/{campaign_id}/reopen", response_model=CampaignOut, status_code=201)
async def reopen_campaign(
    campaign_id: uuid.UUID,
    body: WorkflowActionIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_REOPEN)),
):
    source = await campaign_service.get_campaign(db, campaign_id)
    camp = await campaign_service.reopen_campaign(
        db, user=user, source=source, comment=body.comment
    )
    await record_audit(
        db,
        user=user,
        action="rbcm.campaign.reopen",
        entity="rbcm_campaign",
        entity_id=str(camp.id),
        request=request,
        after={"from": str(source.id), "version": camp.campaign_version},
        module_code=MODULE_CODE,
        espace_code="comptabilite",
    )
    await db.commit()
    await db.refresh(camp)
    names = await _names_for(db, camp)
    return _camp_out(camp, names)


# --- Imports ---


@router.post("/campaigns/{campaign_id}/imports", response_model=ImportOut, status_code=201)
async def upload_import(
    campaign_id: uuid.UUID,
    request: Request,
    file_type: Annotated[str, Form()],
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(*IMPORT_PERMS)),
):
    camp = await campaign_service.get_campaign(db, campaign_id)
    if camp.status in ("CLOTUREE", "APPROUVEE"):
        raise AppError("Campagne figée : import interdit.", status_code=409, code="CAMPAIGN_LOCKED")
    data = await file.read()
    if len(data) > 100 * 1024 * 1024:
        raise AppError("Fichier trop volumineux", code="FILE_TOO_LARGE")
    imp, _ = await import_service.upload_and_analyze(
        db,
        campaign=camp,
        user=user,
        file_type=file_type,
        filename=file.filename or "balance.xlsx",
        data=data,
    )
    await record_audit(
        db,
        user=user,
        action="rbcm.import.upload",
        entity="rbcm_import",
        entity_id=str(imp.id),
        request=request,
        after={"file_type": imp.file_type, "sha256": imp.sha256, "status": imp.status},
        module_code=MODULE_CODE,
        espace_code="comptabilite",
    )
    await db.commit()
    await db.refresh(imp)
    return ImportOut.model_validate(imp)


@router.post("/campaigns/{campaign_id}/imports/{import_id}/confirm", response_model=ImportOut)
async def confirm_import(
    campaign_id: uuid.UUID,
    import_id: uuid.UUID,
    body: ImportConfirmIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(*IMPORT_PERMS)),
):
    camp = await campaign_service.get_campaign(db, campaign_id)
    imp = await import_service.confirm_import(
        db,
        campaign=camp,
        user=user,
        import_id=import_id,
        replace_validated=body.replace_validated,
    )
    await record_audit(
        db,
        user=user,
        action="rbcm.import.confirm",
        entity="rbcm_import",
        entity_id=str(imp.id),
        request=request,
        after={"status": imp.status, "file_type": imp.file_type, "replace": body.replace_validated},
        module_code=MODULE_CODE,
        espace_code="comptabilite",
    )
    await db.commit()
    await db.refresh(imp)
    return ImportOut.model_validate(imp)


@router.delete("/campaigns/{campaign_id}/imports/{import_id}", status_code=204)
async def discard_import(
    campaign_id: uuid.UUID,
    import_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(*IMPORT_PERMS)),
):
    """Supprime un import non confirmé. VALIDATED / SUPERSEDED : 409."""
    camp = await campaign_service.get_campaign(db, campaign_id)
    meta = await import_service.discard_unconfirmed_import(
        db, campaign=camp, import_id=import_id
    )
    await record_audit(
        db,
        user=user,
        action="rbcm.import.discard",
        entity="rbcm_import",
        entity_id=str(import_id),
        request=request,
        before=meta,
        module_code=MODULE_CODE,
        espace_code="comptabilite",
    )
    await db.commit()
    return None


@router.get("/imports", response_model=ImportListOut)
async def list_imports_global(
    campaign_id: uuid.UUID | None = None,
    file_type: str | None = None,
    status: str | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_VIEW)),
):
    rows, total = await import_service.list_imports_global(
        db,
        campaign_id=campaign_id,
        file_type=file_type,
        status=status,
        search=search,
        page=page,
        page_size=page_size,
    )
    return ImportListOut(
        items=[ImportOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/campaigns/{campaign_id}/imports", response_model=list[ImportOut])
async def list_imports(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_VIEW)),
):
    await campaign_service.get_campaign(db, campaign_id)
    rows = (
        await db.scalars(
            select(RbcmImport)
            .where(RbcmImport.campaign_id == campaign_id)
            .order_by(RbcmImport.created_at.desc())
        )
    ).all()
    return [ImportOut.model_validate(r) for r in rows]


@router.get("/campaigns/{campaign_id}/imports/{import_id}", response_model=ImportOut)
async def get_import(
    campaign_id: uuid.UUID,
    import_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_VIEW)),
):
    await campaign_service.get_campaign(db, campaign_id)
    imp = await db.get(RbcmImport, import_id)
    if imp is None or imp.campaign_id != campaign_id:
        raise AppError("Import introuvable", status_code=404, code="IMPORT_NOT_FOUND")
    await record_audit(
        db,
        user=user,
        action="rbcm.import.view",
        entity="rbcm_import",
        entity_id=str(imp.id),
        request=request,
        module_code=MODULE_CODE,
        espace_code="comptabilite",
    )
    await db.commit()
    return ImportOut.model_validate(imp)


@router.get("/campaigns/{campaign_id}/imports/{import_id}/download")
async def download_import_file(
    campaign_id: uuid.UUID,
    import_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_VIEW)),
):
    """Télécharge le fichier Excel original stocké (permission view / import)."""
    from pathlib import Path

    await campaign_service.get_campaign(db, campaign_id)
    imp = await db.get(RbcmImport, import_id)
    if imp is None or imp.campaign_id != campaign_id or not imp.stored_path:
        raise AppError("Fichier d'import introuvable", status_code=404, code="IMPORT_FILE_NOT_FOUND")
    path = Path(imp.stored_path)
    if not path.is_file():
        raise AppError("Fichier source absent du stockage", status_code=404, code="IMPORT_FILE_MISSING")
    return FileResponse(
        path,
        filename=imp.filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/campaigns/{campaign_id}/cond-lines", response_model=CondLineListOut)
async def list_cond_lines(
    campaign_id: uuid.UUID,
    search: str | None = None,
    ncg: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort_by: str = Query("ncg"),
    sort_order: str = Query("asc"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_VIEW)),
):
    await campaign_service.get_campaign(db, campaign_id)
    rows, total = await import_service.list_cond_lines(
        db,
        campaign_id=campaign_id,
        search=search,
        ncg=ncg,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    items = []
    for r in rows:
        item = CondLineOut.model_validate(r)
        item.var = r.tot_debit - r.tot_credit
        items.append(item)
    return CondLineListOut(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/campaigns/{campaign_id}/det-lines", response_model=DetLineListOut)
async def list_det_lines(
    campaign_id: uuid.UUID,
    import_id: uuid.UUID | None = None,
    search: str | None = None,
    ncg: str | None = None,
    devise: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_VIEW)),
):
    await campaign_service.get_campaign(db, campaign_id)
    rows, total = await import_service.list_det_lines(
        db,
        campaign_id=campaign_id,
        import_id=import_id,
        search=search,
        ncg=ncg,
        devise=devise,
        page=page,
        page_size=page_size,
    )
    return DetLineListOut(
        items=[DetLineOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


# --- Réconciliation ---


@router.get("/campaigns/{campaign_id}/reconcile")
async def get_reconcile(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_VIEW)),
):
    await campaign_service.get_campaign(db, campaign_id)
    return await control_service.reconcile_view(db, campaign_id)


@router.get(
    "/campaigns/{campaign_id}/reconcile/issues",
    response_model=ReconcileIssueListOut,
)
async def list_reconcile_issues(
    campaign_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    search: str | None = None,
    severity: str | None = None,
    code: str | None = None,
    resolved: bool | None = None,
    run_id: uuid.UUID | None = None,
    all_runs: bool = Query(False),
    sort: str = Query("severity"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_VIEW)),
):
    await campaign_service.get_campaign(db, campaign_id)
    filters = [
        RbcmReconcileIssue.campaign_id == campaign_id,
        RbcmReconcileIssue.code != "SUMMARY",
    ]
    if not all_runs:
        rid = run_id
        if rid is None:
            last = await control_service.latest_run(db, campaign_id)
            rid = last.id if last else None
        if rid is not None:
            filters.append(RbcmReconcileIssue.run_id == rid)
        else:
            filters.append(RbcmReconcileIssue.run_id.is_(None))
    if severity:
        filters.append(RbcmReconcileIssue.severity == severity.upper())
    if code:
        filters.append(RbcmReconcileIssue.code.ilike(f"%{code.strip()}%"))
    if resolved is not None:
        filters.append(RbcmReconcileIssue.resolved.is_(resolved))
    if search:
        q = f"%{search.strip()}%"
        filters.append(
            or_(
                RbcmReconcileIssue.message.ilike(q),
                RbcmReconcileIssue.ncg.ilike(q),
                RbcmReconcileIssue.code.ilike(q),
            )
        )

    total = int(
        await db.scalar(select(func.count()).select_from(RbcmReconcileIssue).where(*filters))
        or 0
    )
    order = RbcmReconcileIssue.severity.desc()
    if sort == "ncg":
        order = RbcmReconcileIssue.ncg.asc().nulls_last()
    elif sort == "code":
        order = RbcmReconcileIssue.code.asc()
    elif sort == "created_at":
        order = RbcmReconcileIssue.created_at.desc()

    rows = (
        await db.scalars(
            select(RbcmReconcileIssue)
            .where(*filters)
            .order_by(order, RbcmReconcileIssue.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return ReconcileIssueListOut(
        items=[ReconcileIssueOut.model_validate(i) for i in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/campaigns/{campaign_id}/reconcile")
async def run_reconcile(
    campaign_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(*CONTROL_RUN_PERMS)),
):
    camp = await campaign_service.get_campaign(db, campaign_id)
    result = await import_service.reconcile_campaign(db, camp, user=user)
    await record_audit(
        db,
        user=user,
        action="rbcm.control.run",
        entity="rbcm_control_run",
        entity_id=result.get("id"),
        request=request,
        after={
            "campaign_id": str(camp.id),
            "result": result.get("result"),
            "previous_run_id": result.get("previous_run_id"),
            "actor_id": str(user.id),
        },
        module_code=MODULE_CODE,
        espace_code="comptabilite",
    )
    await db.commit()
    return result


@router.get("/campaigns/{campaign_id}/controls/runs")
async def list_control_runs(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_VIEW)),
):
    await campaign_service.get_campaign(db, campaign_id)
    runs = await control_service.list_runs(db, campaign_id)
    names = await campaign_service.display_names(db, [r.actor_id for r in runs])
    out = []
    for r in runs:
        payload = control_service.serialize_run(
            r, [], actor_name=names.get(r.actor_id) if r.actor_id else None
        )
        payload.pop("issues", None)
        out.append(payload)
    return {"items": out, "total": len(out)}


@router.get("/campaigns/{campaign_id}/controls/runs/{run_id}")
async def get_control_run(
    campaign_id: uuid.UUID,
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_VIEW)),
):
    await campaign_service.get_campaign(db, campaign_id)
    run = await control_service.get_run(db, campaign_id, run_id)
    issues = await control_service.issues_for_run(db, run.id)
    names = await campaign_service.display_names(db, [run.actor_id])
    return control_service.serialize_run(
        run, issues, actor_name=names.get(run.actor_id) if run.actor_id else None
    )


@router.post("/campaigns/{campaign_id}/controls/runs")
async def post_control_run(
    campaign_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(*CONTROL_RUN_PERMS)),
):
    return await run_reconcile(campaign_id, request, db, user)


@router.get("/campaigns/{campaign_id}/complements")
async def get_complements(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_VIEW)),
):
    camp = await campaign_service.get_campaign(db, campaign_id)
    data = await control_service.build_complements(db, campaign=camp, user=user)
    run = data.get("run")
    if run and run.get("actor_id"):
        names = await campaign_service.display_names(db, [uuid.UUID(run["actor_id"])])
        run["actor_name"] = names.get(uuid.UUID(run["actor_id"]))
    return data


@router.get("/campaigns/{campaign_id}/reconcile/export")
async def export_reconcile(
    campaign_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_EXPORT)),
):
    await campaign_service.get_campaign(db, campaign_id)
    last = await control_service.latest_run(db, campaign_id)
    filters = [
        RbcmReconcileIssue.campaign_id == campaign_id,
        RbcmReconcileIssue.code != "SUMMARY",
    ]
    if last is not None:
        filters.append(RbcmReconcileIssue.run_id == last.id)
    issues = (
        await db.scalars(
            select(RbcmReconcileIssue)
            .where(*filters)
            .order_by(RbcmReconcileIssue.code, RbcmReconcileIssue.ncg)
        )
    ).all()
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["run_id", "category", "ncg", "severity", "code", "resolution_state", "message", "details"])
    for i in issues:
        w.writerow(
            [
                str(i.run_id or ""),
                i.category or "",
                i.ncg or "",
                i.severity,
                i.code,
                i.resolution_state,
                i.message,
                str(i.details or ""),
            ]
        )
    await record_audit(
        db,
        user=user,
        action="rbcm.reconcile.export",
        entity="rbcm_campaign",
        entity_id=str(campaign_id),
        request=request,
        module_code=MODULE_CODE,
        espace_code="comptabilite",
    )
    await db.commit()
    data = buf.getvalue().encode("utf-8-sig")
    return StreamingResponse(
        io.BytesIO(data),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="rbcm_reconcile_{campaign_id}.csv"'},
    )


# --- Paramètres ---


@router.get("/campaigns/{campaign_id}/parameters")
async def list_parameters(
    campaign_id: uuid.UUID,
    catalog: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_VIEW)),
):
    await campaign_service.get_campaign(db, campaign_id)
    await parameter_service.ensure_definitions(db)
    if catalog:
        rows = await parameter_service.parameter_catalog(db, campaign_id)
        await db.commit()
        return rows
    rows = await parameter_service.current_values(db, campaign_id)
    await db.commit()
    return [ParameterValueOut.model_validate(r) for r in rows]


@router.post("/campaigns/{campaign_id}/parameters", response_model=ParameterValueOut, status_code=201)
async def set_parameter(
    campaign_id: uuid.UUID,
    body: ParameterValueIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(*SAISIR_PARAM_PERMS)),
):
    camp = await campaign_service.get_campaign(db, campaign_id)
    await parameter_service.ensure_definitions(db)
    current = {p.parameter_code: p for p in await parameter_service.current_values(db, campaign_id)}
    prev = current.get(body.parameter_code)
    row = await parameter_service.set_parameter(
        db,
        campaign=camp,
        user=user,
        parameter_code=body.parameter_code,
        value=body.value,
        source=body.source,
        justification=body.justification,
        justificatif_ref=body.justificatif_ref,
        expected_value_id=body.expected_value_id,
    )
    await record_audit(
        db,
        user=user,
        action="rbcm.parameter.set",
        entity="rbcm_parameter_value",
        entity_id=str(row.id),
        request=request,
        before={
            "value_id": str(prev.id) if prev else None,
            "value": str(prev.value) if prev and prev.value is not None else None,
            "authored_by_id": str(prev.authored_by_id) if prev and prev.authored_by_id else None,
            "status": prev.status if prev else None,
        },
        after={
            "code": row.parameter_code,
            "status": row.status,
            "value": str(row.value) if row.value is not None else None,
            "authored_by_id": str(user.id),
            "justification": row.justification,
            "justificatif_ref": row.justificatif_ref,
            "reporting_owner_id": str(camp.reporting_owner_id) if camp.reporting_owner_id else None,
        },
        module_code=MODULE_CODE,
        espace_code="comptabilite",
    )
    await db.commit()
    await db.refresh(row)
    return ParameterValueOut.model_validate(row)


@router.get("/campaigns/{campaign_id}/parameters/history", response_model=list[ParameterValueOut])
async def parameters_history(
    campaign_id: uuid.UUID,
    parameter_code: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_VIEW)),
):
    await campaign_service.get_campaign(db, campaign_id)
    rows, _ = await parameter_service.history(
        db,
        campaign_id=campaign_id,
        parameter_code=parameter_code,
        page=page,
        page_size=page_size,
    )
    return [ParameterValueOut.model_validate(r) for r in rows]


@router.post(
    "/campaigns/{campaign_id}/parameters/{value_id}/validate",
    response_model=ParameterValueOut,
)
async def validate_parameter(
    campaign_id: uuid.UUID,
    value_id: uuid.UUID,
    body: ParameterActionIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_CONTROL)),
):
    camp = await campaign_service.get_campaign(db, campaign_id)
    row = await parameter_service.validate_parameter(
        db, campaign=camp, user=user, value_id=value_id, comment=body.comment
    )
    await record_audit(
        db,
        user=user,
        action="rbcm.parameter.validate",
        entity="rbcm_parameter_value",
        entity_id=str(row.id),
        request=request,
        module_code=MODULE_CODE,
        espace_code="comptabilite",
    )
    await db.commit()
    await db.refresh(row)
    return ParameterValueOut.model_validate(row)


@router.post(
    "/campaigns/{campaign_id}/parameters/{value_id}/reject",
    response_model=ParameterValueOut,
)
async def reject_parameter(
    campaign_id: uuid.UUID,
    value_id: uuid.UUID,
    body: ParameterActionIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_CONTROL)),
):
    camp = await campaign_service.get_campaign(db, campaign_id)
    row = await parameter_service.reject_parameter(
        db, campaign=camp, user=user, value_id=value_id, comment=body.comment
    )
    await record_audit(
        db,
        user=user,
        action="rbcm.parameter.reject",
        entity="rbcm_parameter_value",
        entity_id=str(row.id),
        request=request,
        module_code=MODULE_CODE,
        espace_code="comptabilite",
    )
    await db.commit()
    await db.refresh(row)
    return ParameterValueOut.model_validate(row)


@router.get("/campaigns/{campaign_id}/parameters/caisse-devises/propose")
async def propose_caisse(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(*SAISIR_PARAM_PERMS)),
):
    camp = await campaign_service.get_campaign(db, campaign_id)
    return await parameter_service.propose_caisse_devises(db, camp)


@router.post(
    "/campaigns/{campaign_id}/parameters/caisse-devises/apply",
    response_model=ParameterValueOut,
)
async def apply_caisse(
    campaign_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(*SAISIR_PARAM_PERMS)),
):
    camp = await campaign_service.get_campaign(db, campaign_id)
    proposal = await parameter_service.propose_caisse_devises(db, camp)
    from decimal import Decimal

    current = {p.parameter_code: p for p in await parameter_service.current_values(db, campaign_id)}
    prev = current.get("caisse_devises")
    row = await parameter_service.set_parameter(
        db,
        campaign=camp,
        user=user,
        parameter_code="caisse_devises",
        value=Decimal(proposal["proposed_value"]),
        source="BAL_DET_DERIVE",
        expected_value_id=prev.id if prev else None,
        justification=proposal["method"],
        status="CALCULE",
    )
    await record_audit(
        db,
        user=user,
        action="rbcm.parameter.caisse_derive",
        entity="rbcm_parameter_value",
        entity_id=str(row.id),
        request=request,
        after={"value": proposal["proposed_value"], "sha256": proposal["source_sha256"]},
        module_code=MODULE_CODE,
        espace_code="comptabilite",
    )
    await db.commit()
    await db.refresh(row)
    return ParameterValueOut.model_validate(row)


# --- Mapping ---


@router.get("/mapping/summary")
async def mapping_summary(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_VIEW)),
):
    rows = (
        await db.execute(
            select(RbcmMappingRule.lifecycle_status, func.count()).group_by(
                RbcmMappingRule.lifecycle_status
            )
        )
    ).all()
    by_life = {s: int(c) for s, c in rows}
    total = sum(by_life.values())
    return {
        "total": total,
        "by_lifecycle": by_life,
        "a_valider": by_life.get("A_VALIDER", 0),
        "active": by_life.get("ACTIVE", 0),
        "rejected": by_life.get("REJECTED", 0),
        "superseded": by_life.get("SUPERSEDED", 0),
        "activation_policy": "Aucune activation automatique — D01 ouvert",
    }


_MAPPING_SORT_COLUMNS = {
    "cell_ref": RbcmMappingRule.cell_ref,
    "pattern": RbcmMappingRule.pattern,
    "match_type": RbcmMappingRule.match_type,
    "amount_basis": RbcmMappingRule.amount_basis,
    "lifecycle_status": RbcmMappingRule.lifecycle_status,
    "provenance": RbcmMappingRule.provenance,
    "priority": RbcmMappingRule.priority,
}


@router.get("/mapping/rules", response_model=MappingRuleListOut)
async def list_mapping_rules(
    cell_ref: str | None = None,
    lifecycle_status: str | None = None,
    match_type: str | None = None,
    search: str | None = None,
    sort_by: str = Query("cell_ref"),
    sort_order: str = Query("asc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_VIEW)),
):
    """Liste paginée en lecture seule. Ne change aucun statut de règle."""
    filters = []
    if cell_ref:
        filters.append(RbcmMappingRule.cell_ref == cell_ref)
    if lifecycle_status:
        filters.append(RbcmMappingRule.lifecycle_status == lifecycle_status)
    if match_type:
        filters.append(RbcmMappingRule.match_type == match_type)
    if search:
        like = f"%{search.strip()}%"
        filters.append(
            or_(
                RbcmMappingRule.cell_ref.ilike(like),
                RbcmMappingRule.pattern.ilike(like),
                RbcmMappingRule.match_type.ilike(like),
                RbcmMappingRule.provenance.ilike(like),
            )
        )
    total = int(
        await db.scalar(select(func.count()).select_from(RbcmMappingRule).where(*filters)) or 0
    )
    column = _MAPPING_SORT_COLUMNS.get(sort_by, RbcmMappingRule.cell_ref)
    ordered = column.desc() if sort_order.lower() == "desc" else column.asc()
    order = [ordered]
    if column is not RbcmMappingRule.cell_ref:
        order.append(RbcmMappingRule.cell_ref.asc())
    if column is not RbcmMappingRule.priority:
        order.append(RbcmMappingRule.priority.asc())
    rows = (
        await db.scalars(
            select(RbcmMappingRule)
            .where(*filters)
            .order_by(*order)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return MappingRuleListOut(
        items=[MappingRuleOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


# --- Calcul / contrôles / workflow / export ---


@router.post("/campaigns/{campaign_id}/calculate")
async def calculate(
    campaign_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_PREPARE)),
):
    camp = await campaign_service.get_campaign(db, campaign_id)
    run = await engine_runner.run_calculation(db, campaign=camp, user=user)
    work = None
    try:
        work = await generate_work(db, campaign=camp, user=user)
    except AppError as exc:
        if exc.code != "TEMPLATE_NOT_FOUND":
            raise
    await record_audit(
        db,
        user=user,
        action="rbcm.calculate",
        entity="rbcm_calculation_run",
        entity_id=str(run.id),
        request=request,
        after=run.report,
        module_code=MODULE_CODE,
        espace_code="comptabilite",
    )
    await db.commit()
    return {
        "run_id": str(run.id),
        "status": run.status,
        "report": run.report,
        "work": work,
    }


@router.get("/campaigns/{campaign_id}/cells", response_model=CellResultListOut)
async def list_cells(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_VIEW)),
):
    await campaign_service.get_campaign(db, campaign_id)
    run = await db.scalar(
        select(RbcmCalculationRun)
        .where(
            RbcmCalculationRun.campaign_id == campaign_id,
            RbcmCalculationRun.status == "DONE",
        )
        .order_by(RbcmCalculationRun.created_at.desc())
        .limit(1)
    )
    if run is None:
        return CellResultListOut(items=[], total=0, run_id=None, report=None)
    rows = list(
        (
            await db.scalars(
                select(RbcmCellResult)
                .where(RbcmCellResult.run_id == run.id)
                .order_by(RbcmCellResult.cell_ref)
            )
        ).all()
    )
    items = [
        CellResultOut(
            cell_ref=r.cell_ref,
            calculated_value=r.calculated_value,
            retained_value=r.retained_value,
            value_status=r.value_status,
            origin=(r.traces or {}).get("origin") if isinstance(r.traces, dict) else None,
        )
        for r in rows
    ]
    return CellResultListOut(items=items, total=len(items), run_id=run.id, report=run.report)


@router.post("/campaigns/{campaign_id}/documents/work")
async def generate_campaign_work(
    campaign_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_PREPARE)),
):
    camp = await campaign_service.get_campaign(db, campaign_id)
    out = await generate_work(db, campaign=camp, user=user)
    await record_audit(
        db,
        user=user,
        action="rbcm.document.work",
        entity="rbcm_deliverable",
        entity_id=out["id"],
        request=request,
        after={"document_seq": out.get("document_seq")},
        module_code=MODULE_CODE,
        espace_code="comptabilite",
    )
    await db.commit()
    return out


@router.post("/campaigns/{campaign_id}/document-decisions")
async def create_document_decision(
    campaign_id: uuid.UUID,
    body: DocumentDecisionIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_PREPARE)),
):
    camp = await campaign_service.get_campaign(db, campaign_id)
    template = None
    if camp.template_version_id:
        template = await db.get(RbcmTemplate, camp.template_version_id)
    if template is None:
        template = await db.scalar(select(RbcmTemplate).where(RbcmTemplate.status == "CURRENT"))
    if template is None:
        raise AppError("canevas documentaire introuvable", status_code=404, code="TEMPLATE_NOT_FOUND")
    cell = await db.scalar(
        select(RbcmTemplateCell).where(
            RbcmTemplateCell.template_id == template.id,
            RbcmTemplateCell.document_cell_key == body.document_cell_key,
        )
    )
    if cell is None or not decision_allowed(cell):
        raise AppError("cellule non saisissable", status_code=409, code="CELL_NOT_WRITABLE")
    prev = await db.scalar(
        select(RbcmDocumentDecision)
        .where(
            RbcmDocumentDecision.campaign_id == campaign_id,
            RbcmDocumentDecision.document_cell_key == body.document_cell_key,
        )
        .order_by(RbcmDocumentDecision.decided_at.desc())
        .limit(1)
    )
    row = RbcmDocumentDecision(
        campaign_id=campaign_id,
        template_cell_id=cell.id,
        document_cell_key=body.document_cell_key,
        decided_value=body.decided_value,
        decision_type=body.decision_type,
        reason=body.reason,
        justificatif_ref=body.justificatif_ref,
        decided_by_id=user.id,
        supersedes_decision_id=None if prev is None else prev.id,
    )
    db.add(row)
    await db.flush()
    await record_audit(
        db,
        user=user,
        action="rbcm.document.decision",
        entity="rbcm_document_decision",
        entity_id=str(row.id),
        request=request,
        after={"key": body.document_cell_key, "type": body.decision_type},
        module_code=MODULE_CODE,
        espace_code="comptabilite",
    )
    await db.commit()
    return {"id": str(row.id), "document_cell_key": body.document_cell_key}


@router.get("/campaigns/{campaign_id}/controls", response_model=list[ControlResultOut])
async def list_controls(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_VIEW)),
):
    await campaign_service.get_campaign(db, campaign_id)
    rows = (
        await db.scalars(
            select(RbcmControlResult)
            .where(RbcmControlResult.campaign_id == campaign_id)
            .order_by(RbcmControlResult.executed_at.desc())
        )
    ).all()
    return [ControlResultOut.model_validate(r) for r in rows]


@router.post("/campaigns/{campaign_id}/workflow/submit-control", response_model=CampaignOut)
async def wf_submit(
    campaign_id: uuid.UUID,
    body: WorkflowActionIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_PREPARE)),
):
    camp = await campaign_service.get_campaign(db, campaign_id)
    camp = await workflow_service.submit_for_control(
        db, campaign=camp, user=user, comment=body.comment
    )
    await record_audit(
        db,
        user=user,
        action="rbcm.workflow.submit",
        entity="rbcm_campaign",
        entity_id=str(camp.id),
        request=request,
        module_code=MODULE_CODE,
        espace_code="comptabilite",
    )
    await db.commit()
    await db.refresh(camp)
    return _camp_out(camp)


@router.post("/campaigns/{campaign_id}/workflow/control-ok", response_model=CampaignOut)
async def wf_control(
    campaign_id: uuid.UUID,
    body: WorkflowActionIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_CONTROL)),
):
    camp = await campaign_service.get_campaign(db, campaign_id)
    camp = await workflow_service.control_ok(db, campaign=camp, user=user, comment=body.comment)
    await record_audit(
        db,
        user=user,
        action="rbcm.workflow.control_ok",
        entity="rbcm_campaign",
        entity_id=str(camp.id),
        request=request,
        module_code=MODULE_CODE,
        espace_code="comptabilite",
    )
    await db.commit()
    await db.refresh(camp)
    return _camp_out(camp)


@router.post("/campaigns/{campaign_id}/workflow/approve", response_model=CampaignOut)
async def wf_approve(
    campaign_id: uuid.UUID,
    body: WorkflowActionIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_APPROVE)),
):
    camp = await campaign_service.get_campaign(db, campaign_id)
    camp = await workflow_service.approve(db, campaign=camp, user=user, comment=body.comment)
    await record_audit(
        db,
        user=user,
        action="rbcm.workflow.approve",
        entity="rbcm_campaign",
        entity_id=str(camp.id),
        request=request,
        module_code=MODULE_CODE,
        espace_code="comptabilite",
    )
    await db.commit()
    await db.refresh(camp)
    return _camp_out(camp)


@router.post("/campaigns/{campaign_id}/workflow/reject", response_model=CampaignOut)
async def wf_reject(
    campaign_id: uuid.UUID,
    body: WorkflowActionIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_CONTROL)),
):
    camp = await campaign_service.get_campaign(db, campaign_id)
    camp = await workflow_service.reject(db, campaign=camp, user=user, comment=body.comment)
    await record_audit(
        db,
        user=user,
        action="rbcm.workflow.reject",
        entity="rbcm_campaign",
        entity_id=str(camp.id),
        request=request,
        module_code=MODULE_CODE,
        espace_code="comptabilite",
    )
    await db.commit()
    await db.refresh(camp)
    return _camp_out(camp)


@router.post("/campaigns/{campaign_id}/workflow/close", response_model=CampaignOut)
async def wf_close(
    campaign_id: uuid.UUID,
    body: WorkflowActionIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_APPROVE)),
):
    camp = await campaign_service.get_campaign(db, campaign_id)
    if camp.status != "APPROUVEE":
        raise AppError(
            "Seule une campagne APPROUVEE peut être clôturée.",
            status_code=409,
            code="CLOSE_INVALID",
        )
    camp = await campaign_service.transition_status(
        db,
        campaign=camp,
        user=user,
        action="CLOSE",
        to_status="CLOTUREE",
        comment=body.comment,
    )
    await record_audit(
        db,
        user=user,
        action="rbcm.workflow.close",
        entity="rbcm_campaign",
        entity_id=str(camp.id),
        request=request,
        module_code=MODULE_CODE,
        espace_code="comptabilite",
    )
    await db.commit()
    await db.refresh(camp)
    return _camp_out(camp)


@router.get("/campaigns/{campaign_id}/documents", response_model=DocumentListOut)
async def list_campaign_documents(
    campaign_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_VIEW)),
):
    camp = await campaign_service.get_campaign(db, campaign_id)
    rows = await list_documents(db, campaign_id)
    names = await campaign_service.display_names(db, [d.created_by_id for d in rows])
    items = [
        DocumentOut.model_validate(
            {
                **document_public_dict(
                    d, period_year=camp.period_year, period_month=camp.period_month
                ),
                "created_by_name": names.get(d.created_by_id) if d.created_by_id else None,
            }
        )
        for d in rows
    ]
    await _audit_doc(
        db,
        user=user,
        request=request,
        action="rbcm.document.list",
        entity="rbcm_campaign",
        entity_id=str(campaign_id),
        after={"result": "ok", "count": len(items)},
    )
    return DocumentListOut(items=items, total=len(items))


@router.get(
    "/campaigns/{campaign_id}/documents/{deliverable_id}",
    response_model=DocumentDetailOut,
)
async def get_campaign_document(
    campaign_id: uuid.UUID,
    deliverable_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_VIEW)),
):
    camp = await campaign_service.get_campaign(db, campaign_id)
    d = await get_document(db, campaign_id=campaign_id, deliverable_id=deliverable_id)
    payload = document_public_dict(
        d, period_year=camp.period_year, period_month=camp.period_month
    )
    names = await campaign_service.display_names(db, [d.created_by_id])
    payload["created_by_name"] = names.get(d.created_by_id) if d.created_by_id else None
    history = await campaign_document_history(db, campaign_id)
    await _audit_doc(
        db,
        user=user,
        request=request,
        action="rbcm.document.get",
        entity="rbcm_deliverable",
        entity_id=str(d.id),
        after={
            "result": "ok",
            "campaign_id": str(campaign_id),
            "status": d.status,
            "document_seq": d.document_seq,
        },
    )
    return DocumentDetailOut.model_validate(
        {
            **payload,
            "warnings": public_warnings(d.warnings),
            "history": history,
        }
    )


@router.get("/campaigns/{campaign_id}/documents/{deliverable_id}/download")
async def download_campaign_document(
    campaign_id: uuid.UUID,
    deliverable_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_EXPORT)),
):
    camp = await campaign_service.get_campaign(db, campaign_id)
    download_name = sm_period_filename(camp.period_year, camp.period_month)
    try:
        d = await get_document(db, campaign_id=campaign_id, deliverable_id=deliverable_id)
        path = resolve_deliverable_file(d)
    except AppError as exc:
        await _audit_doc(
            db,
            user=user,
            request=request,
            action="rbcm.document.download_denied",
            entity="rbcm_deliverable",
            entity_id=str(deliverable_id),
            after={
                "result": "denied",
                "campaign_id": str(campaign_id),
                "code": exc.code,
            },
        )
        await db.commit()
        raise
    await _audit_doc(
        db,
        user=user,
        request=request,
        action="rbcm.document.download",
        entity="rbcm_deliverable",
        entity_id=str(d.id),
        after={
            "result": "ok",
            "campaign_id": str(campaign_id),
            "status": d.status,
            "document_seq": d.document_seq,
            "sha256": d.sha256,
            "filename": download_name,
        },
    )
    return FileResponse(
        path,
        filename=download_name,
        media_type=XLSX_TYPE,
    )


@router.post("/campaigns/{campaign_id}/exports/excel")
async def export_excel(
    campaign_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_EXPORT)),
):
    camp = await campaign_service.get_campaign(db, campaign_id)
    d = await excel_export.generate_excel(db, campaign=camp, user=user)
    await record_audit(
        db,
        user=user,
        action="rbcm.export.excel",
        entity="rbcm_deliverable",
        entity_id=str(d.id),
        request=request,
        module_code=MODULE_CODE,
        espace_code="comptabilite",
    )
    await db.commit()
    return {
        "id": str(d.id),
        "filename": d.filename,
        "sha256": d.sha256,
        "warnings": d.warnings,
        "pdf": excel_export.pdf_status(),
    }


@router.get("/campaigns/{campaign_id}/exports/{deliverable_id}/download")
async def download_export(
    campaign_id: uuid.UUID,
    deliverable_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(PERM_EXPORT)),
):
    from pathlib import Path

    from app.models.reporting_bcm_sm import RbcmDeliverable

    camp = await campaign_service.get_campaign(db, campaign_id)
    d = await db.get(RbcmDeliverable, deliverable_id)
    if d is None or d.campaign_id != campaign_id or not d.stored_path:
        raise AppError("Livrable introuvable", status_code=404, code="DELIVERABLE_NOT_FOUND")
    path = Path(d.stored_path)
    if not path.is_file():
        raise AppError("Fichier livrable absent", status_code=404, code="DELIVERABLE_FILE_MISSING")
    return FileResponse(
        path,
        filename=sm_period_filename(camp.period_year, camp.period_month),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/pdf-status")
async def pdf_status(user: User = Depends(require_permission(PERM_VIEW))):
    return excel_export.pdf_status()
