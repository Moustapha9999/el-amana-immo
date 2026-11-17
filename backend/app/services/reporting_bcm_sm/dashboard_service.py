"""KPIs dashboard Reporting BCM SM — données réelles uniquement."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.reporting_bcm_sm import (
    RbcmCampaign,
    RbcmImport,
    RbcmParameterValue,
    RbcmReconcileIssue,
)
from app.services.reporting_bcm_sm.constants import (
    PARAMETER_CODES,
    SM_APPROVED_STATUSES,
    SM_CALCULATED_STATUSES,
    SM_CLOSED_STATUSES,
    SM_IN_PROGRESS_STATUSES,
    SM_OPEN_STATUSES,
    SM_PENDING_VALIDATION_STATUSES,
)


async def _count_status(db: AsyncSession, statuses: tuple[str, ...]) -> int:
    if not statuses:
        return 0
    return int(
        await db.scalar(
            select(func.count())
            .select_from(RbcmCampaign)
            .where(RbcmCampaign.status.in_(statuses))
        )
        or 0
    )


async def dashboard_stats(db: AsyncSession) -> dict:
    total = int(await db.scalar(select(func.count()).select_from(RbcmCampaign)) or 0)
    open_n = await _count_status(db, SM_OPEN_STATUSES)
    in_progress_n = await _count_status(db, SM_IN_PROGRESS_STATUSES)
    pending_n = await _count_status(db, SM_PENDING_VALIDATION_STATUSES)
    calculated_n = await _count_status(db, SM_CALCULATED_STATUSES)
    approved_n = await _count_status(db, SM_APPROVED_STATUSES)
    closed_n = await _count_status(db, SM_CLOSED_STATUSES)

    by_status_rows = (
        await db.execute(
            select(RbcmCampaign.status, func.count())
            .group_by(RbcmCampaign.status)
            .order_by(func.count().desc())
        )
    ).all()
    by_status = [{"label": s, "value": int(c)} for s, c in by_status_rows]

    # T3.4-A2/B — KPI workflow = BAL DET uniquement (COND = archives).
    imports_ok = int(
        await db.scalar(
            select(func.count())
            .select_from(RbcmImport)
            .where(RbcmImport.status == "VALIDATED", RbcmImport.file_type == "BAL_DET")
        )
        or 0
    )
    imports_anomaly = int(
        await db.scalar(
            select(func.count())
            .select_from(RbcmImport)
            .where(
                RbcmImport.file_type == "BAL_DET",
                RbcmImport.status.in_(("ANALYZED", "REJECTED")),
            )
        )
        or 0
    )

    by_type_rows = (
        await db.execute(
            select(RbcmImport.file_type, func.count())
            .where(RbcmImport.status == "VALIDATED")
            .group_by(RbcmImport.file_type)
        )
    ).all()
    imports_by_type = [{"label": t, "value": int(c)} for t, c in by_type_rows]

    monthly_rows = (
        await db.execute(
            select(
                RbcmCampaign.period_year,
                RbcmCampaign.period_month,
                func.count(RbcmImport.id),
            )
            .join(RbcmImport, RbcmImport.campaign_id == RbcmCampaign.id)
            .where(
                RbcmImport.status == "VALIDATED",
                RbcmImport.file_type == "BAL_DET",
            )
            .group_by(RbcmCampaign.period_year, RbcmCampaign.period_month)
            .order_by(RbcmCampaign.period_year.desc(), RbcmCampaign.period_month.desc())
            .limit(12)
        )
    ).all()
    imports_monthly = [
        {
            "label": f"{int(m):02d}/{int(y)}",
            "value": int(c),
            "year": int(y),
            "month": int(m),
        }
        for y, m, c in reversed(monthly_rows)
    ]

    anomaly_rows = (
        await db.execute(
            select(RbcmReconcileIssue.code, func.count())
            .where(RbcmReconcileIssue.code != "SUMMARY")
            .group_by(RbcmReconcileIssue.code)
            .order_by(func.count().desc())
            .limit(10)
        )
    ).all()
    anomalies_by_code = [{"label": code, "value": int(c)} for code, c in anomaly_rows]

    # Progression moyenne sur SM ouvertes (définition T3.4-C)
    open_camps = (
        await db.scalars(select(RbcmCampaign).where(RbcmCampaign.status.in_(SM_OPEN_STATUSES)))
    ).all()
    params_missing = 0
    for camp in open_camps:
        vals = (
            await db.scalars(
                select(RbcmParameterValue)
                .where(RbcmParameterValue.campaign_id == camp.id)
                .order_by(RbcmParameterValue.created_at.desc())
            )
        ).all()
        seen: set[str] = set()
        filled: set[str] = set()
        for v in vals:
            if v.parameter_code in seen:
                continue
            seen.add(v.parameter_code)
            if v.value is not None or v.status in ("SAISI", "CALCULE", "VALIDE"):
                filled.add(v.parameter_code)
        params_missing += len(PARAMETER_CODES) - len(filled)

    progress_samples = []
    for camp in open_camps[:50]:
        from app.services.reporting_bcm_sm import campaign_service

        p = await campaign_service.campaign_progress(db, camp.id)
        progress_samples.append(p["pct"])
    avg_progress = int(round(sum(progress_samples) / len(progress_samples))) if progress_samples else 0

    recent_camps = (
        await db.scalars(select(RbcmCampaign).order_by(RbcmCampaign.created_at.desc()).limit(5))
    ).all()
    recent_imports = (
        await db.scalars(
            select(RbcmImport)
            .where(RbcmImport.file_type == "BAL_DET")
            .order_by(RbcmImport.created_at.desc())
            .limit(5)
        )
    ).all()

    from app.models.reporting_bcm_sm import RbcmMappingRule

    mapping_stats = (
        await db.execute(
            select(RbcmMappingRule.lifecycle_status, func.count()).group_by(
                RbcmMappingRule.lifecycle_status
            )
        )
    ).all()

    params_filled_total = 0
    for camp in open_camps:
        vals = (
            await db.scalars(
                select(RbcmParameterValue)
                .where(RbcmParameterValue.campaign_id == camp.id)
                .order_by(RbcmParameterValue.created_at.desc())
            )
        ).all()
        seen: set[str] = set()
        for v in vals:
            if v.parameter_code in seen:
                continue
            seen.add(v.parameter_code)
            if v.value is not None or v.status in ("SAISI", "CALCULE", "VALIDE"):
                params_filled_total += 1

    return {
        "campaigns_total": total,
        "campaigns_open": open_n,
        "campaigns_in_progress": in_progress_n,
        "campaigns_pending": pending_n,
        "campaigns_calculated": calculated_n,
        "campaigns_approved": approved_n,
        "campaigns_closed": closed_n,
        "campaigns_archived": closed_n,  # archivage = CLOTUREE (pas de statut distinct)
        "imports_validated": imports_ok,
        "imports_anomaly": imports_anomaly,
        "parameters_missing": params_missing,
        "parameters_filled": params_filled_total,
        "avg_progress_pct": avg_progress,
        "by_status": by_status,
        "imports_by_type": imports_by_type,
        "imports_monthly": imports_monthly,
        "anomalies_by_code": anomalies_by_code,
        "status_groups": {
            "open": list(SM_OPEN_STATUSES),
            "in_progress": list(SM_IN_PROGRESS_STATUSES),
            "pending_validation": list(SM_PENDING_VALIDATION_STATUSES),
            "calculated": list(SM_CALCULATED_STATUSES),
            "approved": list(SM_APPROVED_STATUSES),
            "closed_archived": list(SM_CLOSED_STATUSES),
        },
        "mapping_by_lifecycle": [{"label": s, "value": int(c)} for s, c in mapping_stats],
        "recent_campaigns": [
            {
                "id": str(c.id),
                "label": f"{c.period_month:02d}/{c.period_year} v{c.campaign_version}",
                "status": c.status,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in recent_camps
        ],
        "recent_imports": [
            {
                "id": str(i.id),
                "campaign_id": str(i.campaign_id),
                "file_type": i.file_type,
                "filename": i.filename,
                "status": i.status,
                "created_at": i.created_at.isoformat() if i.created_at else None,
            }
            for i in recent_imports
        ],
    }
