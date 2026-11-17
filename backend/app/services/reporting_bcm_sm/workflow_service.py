"""Workflow 3 niveaux — séparation des tâches (pas d'auto-approbation)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import User
from app.models.reporting_bcm_sm import RbcmCampaign, RbcmControlResult
from app.services.reporting_bcm_sm import campaign_service


async def submit_for_control(
    db: AsyncSession, *, campaign: RbcmCampaign, user: User, comment: str | None
) -> RbcmCampaign:
    if campaign.status not in ("CALCULEE", "PARAMETREE", "RAPPROCHEE"):
        raise AppError(
            f"Transition interdite depuis {campaign.status}",
            code="WORKFLOW_INVALID",
        )
    blocking = await db.scalar(
        select(RbcmControlResult.id)
        .where(
            RbcmControlResult.campaign_id == campaign.id,
            RbcmControlResult.severity == "BLOCKING",
            RbcmControlResult.result == "FAIL",
        )
        .limit(1)
    )
    if blocking is not None:
        raise AppError(
            "Des contrôles bloquants empêchent la soumission (ex. ECART/D02, mapping).",
            status_code=409,
            code="CONTROLS_BLOCKING",
        )
    return await campaign_service.transition_status(
        db,
        campaign=campaign,
        user=user,
        action="SUBMIT_CONTROL",
        to_status="A_CONTROLER",
        comment=comment,
    )


async def control_ok(
    db: AsyncSession, *, campaign: RbcmCampaign, user: User, comment: str | None
) -> RbcmCampaign:
    if campaign.status != "A_CONTROLER":
        raise AppError("SM non en contrôle", code="WORKFLOW_INVALID")
    if campaign.preparer_id and campaign.preparer_id == user.id:
        raise AppError(
            "Séparation des tâches : le préparateur ne peut pas être contrôleur.",
            status_code=403,
            code="SOD_VIOLATION",
        )
    return await campaign_service.transition_status(
        db,
        campaign=campaign,
        user=user,
        action="CONTROL_OK",
        to_status="A_CONTROLER",  # reste en attente d'approbation — statut intermédiaire
        comment=comment,
    )


async def approve(
    db: AsyncSession, *, campaign: RbcmCampaign, user: User, comment: str | None
) -> RbcmCampaign:
    if campaign.status not in ("A_CONTROLER", "CALCULEE"):
        raise AppError("SM non soumise à approbation", code="WORKFLOW_INVALID")
    if campaign.preparer_id and campaign.preparer_id == user.id:
        raise AppError(
            "Séparation des tâches : auto-approbation interdite.",
            status_code=403,
            code="SOD_VIOLATION",
        )
    # Finalisation réglementaire bloquée si contrôles bloquants
    blocking = await db.scalar(
        select(RbcmControlResult.id)
        .where(
            RbcmControlResult.campaign_id == campaign.id,
            RbcmControlResult.severity == "BLOCKING",
            RbcmControlResult.result == "FAIL",
        )
        .limit(1)
    )
    if blocking is not None:
        raise AppError(
            "Approbation réglementaire impossible : contrôles bloquants ouverts "
            "(décisions métier D01/D02/D09 en attente).",
            status_code=409,
            code="REGULATORY_BLOCKED",
        )
    return await campaign_service.transition_status(
        db,
        campaign=campaign,
        user=user,
        action="APPROVE",
        to_status="APPROUVEE",
        comment=comment,
        require_other_user=True,
        compared_to_user_id=campaign.preparer_id,
    )


async def reject(
    db: AsyncSession, *, campaign: RbcmCampaign, user: User, comment: str | None
) -> RbcmCampaign:
    if not comment:
        raise AppError("Motif de rejet obligatoire", code="REJECT_REASON_REQUIRED")
    return await campaign_service.transition_status(
        db,
        campaign=campaign,
        user=user,
        action="CONTROL_REJECT",
        to_status="CALCULEE",
        comment=comment,
    )


async def close_campaign(
    db: AsyncSession, *, campaign: RbcmCampaign, user: User, comment: str | None
) -> RbcmCampaign:
    if campaign.status != "APPROUVEE":
        raise AppError("Seule une campagne approuvée peut être clôturée", code="WORKFLOW_INVALID")
    return await campaign_service.transition_status(
        db,
        campaign=campaign,
        user=user,
        action="CLOSE",
        to_status="CLOTUREE",
        comment=comment,
    )
