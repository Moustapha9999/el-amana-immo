"""Export Excel — openpyxl écrit les cellules calculées ; Python = vérité.

Ne prétend pas recalculer les formules Excel. PDF : bloqué sans solution DSI.
"""

from __future__ import annotations

import hashlib
import uuid
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import User
from app.models.reporting_bcm_sm import (
    RbcmCalculationRun,
    RbcmCampaign,
    RbcmCellResult,
    RbcmDeliverable,
)
from app.services.platform_backup_engine import upload_root
from app.services.reporting_bcm_sm.constants import MODULE_CODE
from app.services.reporting_bcm_sm.document_access import sm_period_filename


async def generate_excel(
    db: AsyncSession,
    *,
    campaign: RbcmCampaign,
    user: User,
    run_id: uuid.UUID | None = None,
) -> RbcmDeliverable:
    run: RbcmCalculationRun | None
    if run_id:
        run = await db.get(RbcmCalculationRun, run_id)
    else:
        run = await db.scalar(
            select(RbcmCalculationRun)
            .where(
                RbcmCalculationRun.campaign_id == campaign.id,
                RbcmCalculationRun.status == "DONE",
            )
            .order_by(RbcmCalculationRun.created_at.desc())
            .limit(1)
        )
    if run is None:
        raise AppError("Aucun run de calcul disponible", code="EXPORT_NO_RUN")

    results = (
        await db.scalars(
            select(RbcmCellResult).where(RbcmCellResult.run_id == run.id)
        )
    ).all()

    wb = Workbook()
    # Huit feuilles cibles du modèle officiel — structure minimale tant que canevas
    # n'est pas injecté en template versionné.
    sheet_names = [
        "ETAT A",
        "ETAT B",
        "ETAT C",
        "Informations",
        "FPN",
        "Ratios",
        "Controles",
        "Alertes",
    ]
    ws0 = wb.active
    ws0.title = sheet_names[0]
    for name in sheet_names[1:]:
        wb.create_sheet(name)

    ws = wb["ETAT A"]
    ws["A1"] = "Reporting BCM SM — export moteur Python"
    ws["A2"] = f"Campagne {campaign.period_month:02d}/{campaign.period_year} v{campaign.campaign_version}"
    ws["A3"] = f"Engine {run.engine_version}"
    ws["A4"] = "ATTENTION : les formules Excel du canevas officiel ne sont pas recalculées par openpyxl."
    ws["A5"] = "Valeurs ci-dessous = moteur BEA DIGITAL (source de vérité)."
    ws["A6"] = "ECART et ETAT B/C : voir alertes (D02/D09)."

    ws.append([])
    ws.append(["cell_ref", "calculated_value", "retained_value", "value_status"])
    for r in results:
        def _s(v: Decimal | None) -> str | None:
            return None if v is None else str(v)

        ws.append([r.cell_ref, _s(r.calculated_value), _s(r.retained_value), r.value_status])

    alertes = wb["Alertes"]
    alertes["A1"] = "Données provisoires / blocages"
    alertes["A2"] = "ECART désactivé (D02)"
    alertes["A3"] = "ETAT B/C provisoires (D09)"
    alertes["A4"] = "Mapping : seules les règles ACTIVE sont retenues ; A_VALIDER ignorées pour le livrable"
    alertes["A5"] = "PDF : non généré — solution DSI non validée"
    report = run.report or {}
    alertes["A6"] = f"can_finalize_regulatory={report.get('can_finalize_regulatory', False)}"

    buf = BytesIO()
    wb.save(buf)
    payload = buf.getvalue()
    sha = hashlib.sha256(payload).hexdigest()

    root = upload_root() / MODULE_CODE / str(campaign.id) / "exports"
    root.mkdir(parents=True, exist_ok=True)
    filename = sm_period_filename(campaign.period_year, campaign.period_month)
    stored_name = (
        f"SM-{campaign.period_month:02d}-{campaign.period_year}"
        f"_v{campaign.campaign_version}_{sha[:16]}.xlsx"
    )
    path = root / stored_name
    path.write_bytes(payload)

    deliverable = RbcmDeliverable(
        campaign_id=campaign.id,
        run_id=run.id,
        kind="EXCEL",
        filename=filename,
        stored_path=str(path),
        sha256=sha,
        status="GENERATED",
        warnings={
            "formulas_not_recalculated": True,
            "provisional": True,
            "pdf_unavailable": True,
            "ecart_inactive": True,
        },
        created_by_id=user.id,
    )
    db.add(deliverable)
    await db.flush()
    return deliverable


def pdf_status() -> dict:
    return {
        "available": False,
        "reason": (
            "Aucune conversion PDF DSI-approuvée n'est configurée (DSI-PDF / LibreOffice). "
            "Excel généré uniquement ; ne pas présenter un PDF avec caches formules obsolètes."
        ),
        "dsi_action_required": True,
    }
