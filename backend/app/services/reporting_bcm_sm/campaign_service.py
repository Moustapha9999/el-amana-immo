"""Gestion des campagnes mensuelles — règle P2 versionnée."""

from __future__ import annotations

import uuid
from calendar import monthrange
from datetime import date, datetime, timezone
from typing import Iterable

from sqlalchemy import Select, delete as sa_delete, exists, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, NotFoundError
from app.models import Permission, User
from app.models.associations import role_permissions_table, user_roles_table
from app.models.reporting_bcm_sm import (
    RbcmBalanceNcg,
    RbcmCalculationRun,
    RbcmCampaign,
    RbcmCellDecision,
    RbcmCellResult,
    RbcmControlResult,
    RbcmControlRun,
    RbcmDeliverable,
    RbcmDocumentDecision,
    RbcmEcartSnapshot,
    RbcmImport,
    RbcmImportLineDet,
    RbcmParameterValue,
    RbcmReconcileIssue,
    RbcmReportingOwnerHistory,
    RbcmValidationEvent,
)
from app.services.auth_service import module_access_clause
from app.services.permission_service import load_user_permission_codes, user_has_permission_codes
from app.services.reporting_bcm_sm.constants import (
    BANK_CODE_DEFAULT,
    IMPORT_STATUSES_CONFIRMED,
    MODULE_CODE,
    OPEN_CAMPAIGN_STATUSES,
    PERM_ADMIN,
    PERM_PREPARE,
)


async def get_campaign(db: AsyncSession, campaign_id: uuid.UUID) -> RbcmCampaign:
    row = await db.get(RbcmCampaign, campaign_id)
    if row is None:
        raise NotFoundError("SM", str(campaign_id))
    return row


async def list_campaigns(
    db: AsyncSession,
    *,
    year: int | None = None,
    month: int | None = None,
    status: str | None = None,
    bank_code: str | None = None,
    search: str | None = None,
    sort_by: str = "period",
    sort_order: str = "desc",
    page: int = 1,
    page_size: int = 25,
    limit: int | None = None,
    offset: int | None = None,
) -> tuple[list[RbcmCampaign], int]:
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    if limit is not None:
        page_size = min(max(1, limit), 200)
    if offset is not None:
        page = (offset // page_size) + 1 if page_size else 1

    filters = []
    if year is not None:
        filters.append(RbcmCampaign.period_year == year)
    if month is not None:
        filters.append(RbcmCampaign.period_month == month)
    if status is not None:
        filters.append(RbcmCampaign.status == status)
    if bank_code:
        filters.append(RbcmCampaign.bank_code == bank_code.strip().upper())
    if search:
        like = f"%{search.strip()}%"
        filters.append(
            or_(
                RbcmCampaign.notes.ilike(like),
                RbcmCampaign.bank_code.ilike(like),
                RbcmCampaign.status.ilike(like),
            )
        )

    count_q: Select = select(func.count()).select_from(RbcmCampaign)
    list_q: Select = select(RbcmCampaign)
    if filters:
        count_q = count_q.where(*filters)
        list_q = list_q.where(*filters)

    desc = sort_order.lower() != "asc"
    if sort_by == "status":
        order_cols = [RbcmCampaign.status.desc() if desc else RbcmCampaign.status.asc()]
    elif sort_by == "created_at":
        order_cols = [RbcmCampaign.created_at.desc() if desc else RbcmCampaign.created_at.asc()]
    else:
        order_cols = [
            RbcmCampaign.period_year.desc() if desc else RbcmCampaign.period_year.asc(),
            RbcmCampaign.period_month.desc() if desc else RbcmCampaign.period_month.asc(),
            RbcmCampaign.campaign_version.desc() if desc else RbcmCampaign.campaign_version.asc(),
        ]
    list_q = list_q.order_by(*order_cols)

    total = int(await db.scalar(count_q) or 0)
    rows = (
        await db.scalars(list_q.offset((page - 1) * page_size).limit(page_size))
    ).all()
    return list(rows), total


async def _max_version(
    db: AsyncSession, *, bank_code: str, year: int, month: int
) -> int:
    q = select(func.max(RbcmCampaign.campaign_version)).where(
        RbcmCampaign.bank_code == bank_code,
        RbcmCampaign.period_year == year,
        RbcmCampaign.period_month == month,
    )
    return int(await db.scalar(q) or 0)


async def _has_open_campaign(
    db: AsyncSession, *, bank_code: str, year: int, month: int
) -> RbcmCampaign | None:
    q = (
        select(RbcmCampaign)
        .where(
            RbcmCampaign.bank_code == bank_code,
            RbcmCampaign.period_year == year,
            RbcmCampaign.period_month == month,
            RbcmCampaign.status.in_(OPEN_CAMPAIGN_STATUSES),
        )
        .limit(1)
    )
    return await db.scalar(q)


async def display_names(
    db: AsyncSession, user_ids: Iterable[uuid.UUID | None]
) -> dict[uuid.UUID, str]:
    ids = {i for i in user_ids if i}
    if not ids:
        return {}
    rows = (await db.execute(select(User.id, User.full_name).where(User.id.in_(ids)))).all()
    return {uid: name for uid, name in rows}


async def _load_preparer(db: AsyncSession, user_id: uuid.UUID) -> User:
    """Utilisateur actif autorisé à préparer une SM (permission Login 2)."""
    user = await db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise AppError("Responsable introuvable.", status_code=404, code="OWNER_NOT_FOUND")
    if not user.is_active:
        raise AppError(
            "Le responsable désigné n'est pas actif.",
            status_code=403,
            code="OWNER_INACTIVE",
        )
    codes = await load_user_permission_codes(db, user)
    if not user_has_permission_codes(codes, PERM_PREPARE):
        raise AppError(
            "Le responsable doit disposer de la permission de préparation "
            "(reporting-bcm-sm.prepare).",
            status_code=403,
            code="OWNER_NOT_PREPARER",
        )
    return user


async def list_reporting_owners(db: AsyncSession) -> list[User]:
    """Utilisateurs actifs pouvant être désignés responsables (PERM_PREPARE / admin / superuser)."""
    has_perm = exists().where(
        user_roles_table.c.user_id == User.id,
        user_roles_table.c.role_id == role_permissions_table.c.role_id,
        role_permissions_table.c.permission_id == Permission.id,
        Permission.code.in_((PERM_PREPARE, PERM_ADMIN)),
    )
    q = (
        select(User)
        .where(
            User.is_active.is_(True),
            User.deleted_at.is_(None),
            or_(User.is_superuser.is_(True), has_perm),
            or_(User.is_superuser.is_(True), module_access_clause(MODULE_CODE)),
        )
        .order_by(User.full_name.asc(), User.email.asc())
    )
    return list((await db.scalars(q)).all())


def _append_owner_history(
    db: AsyncSession,
    *,
    campaign: RbcmCampaign,
    from_owner_id: uuid.UUID | None,
    to_owner_id: uuid.UUID,
    actor_id: uuid.UUID,
    motif: str,
    action: str,
) -> None:
    db.add(
        RbcmReportingOwnerHistory(
            campaign_id=campaign.id,
            from_owner_id=from_owner_id,
            to_owner_id=to_owner_id,
            actor_id=actor_id,
            motif=motif,
        )
    )
    db.add(
        RbcmValidationEvent(
            campaign_id=campaign.id,
            action=action,
            from_status=campaign.status,
            to_status=campaign.status,
            comment=motif,
            actor_id=actor_id,
        )
    )


async def assign_reporting_owner(
    db: AsyncSession,
    *,
    campaign: RbcmCampaign,
    owner_id: uuid.UUID,
    actor: User,
    motif: str,
) -> RbcmCampaign:
    """Changement de responsable — motif obligatoire, historique append-only."""
    if campaign.status in ("CLOTUREE", "APPROUVEE"):
        raise AppError(
            "SM figée : modification du responsable interdite.",
            status_code=409,
            code="CAMPAIGN_LOCKED",
        )
    reason = (motif or "").strip()
    if not reason:
        raise AppError(
            "Le motif du changement de responsable est obligatoire.",
            code="OWNER_REASON_REQUIRED",
        )
    if campaign.reporting_owner_id == owner_id:
        raise AppError(
            "Ce responsable est déjà désigné.",
            code="OWNER_UNCHANGED",
        )
    owner = await _load_preparer(db, owner_id)
    previous = campaign.reporting_owner_id
    campaign.reporting_owner_id = owner.id
    campaign.reporting_owner_set_at = datetime.now(timezone.utc)
    _append_owner_history(
        db,
        campaign=campaign,
        from_owner_id=previous,
        to_owner_id=owner.id,
        actor_id=actor.id,
        motif=reason,
        action="OWNER_CHANGE",
    )
    await db.flush()
    return campaign


async def list_owner_history(
    db: AsyncSession, campaign_id: uuid.UUID
) -> list[RbcmReportingOwnerHistory]:
    rows = (
        await db.scalars(
            select(RbcmReportingOwnerHistory)
            .where(RbcmReportingOwnerHistory.campaign_id == campaign_id)
            .order_by(RbcmReportingOwnerHistory.created_at.asc())
        )
    ).all()
    return list(rows)


async def create_campaign(
    db: AsyncSession,
    *,
    user: User,
    period_year: int,
    period_month: int,
    bank_code: str = BANK_CODE_DEFAULT,
    closing_date=None,
    notes: str | None = None,
    label: str | None = None,
    reporting_owner_id: uuid.UUID | None = None,
) -> RbcmCampaign:
    bank = (bank_code or BANK_CODE_DEFAULT).strip().upper() or BANK_CODE_DEFAULT
    if period_month < 1 or period_month > 12:
        raise AppError("Mois invalide", code="INVALID_MONTH")
    if period_year < 2000 or period_year > 2100:
        raise AppError("Année invalide", code="INVALID_YEAR")

    open_row = await _has_open_campaign(db, bank_code=bank, year=period_year, month=period_month)
    if open_row is not None:
        raise AppError(
            f"Une SM ouverte existe déjà pour {period_month:02d}/{period_year} "
            f"(version {open_row.campaign_version}, statut {open_row.status}). "
            "Clôturez-la ou utilisez la réouverture contrôlée.",
            status_code=409,
            code="CAMPAIGN_OPEN_EXISTS",
        )

    prev_max = await _max_version(db, bank_code=bank, year=period_year, month=period_month)
    version = prev_max + 1 if prev_max else 1

    note_parts = []
    if label:
        note_parts.append(f"[libellé] {label.strip()}")
    if notes:
        note_parts.append(notes.strip())
    merged_notes = "\n".join(note_parts) if note_parts else None

    owner_id = reporting_owner_id or user.id
    if owner_id != user.id:
        await _load_preparer(db, owner_id)
    else:
        owner_id = user.id

    if closing_date is None:
        closing_date = date(period_year, period_month, monthrange(period_year, period_month)[1])

    now = datetime.now(timezone.utc)
    camp = RbcmCampaign(
        period_year=period_year,
        period_month=period_month,
        closing_date=closing_date,
        bank_code=bank,
        status="BROUILLON",
        campaign_version=version,
        preparer_id=user.id,
        reporting_owner_id=owner_id,
        reporting_owner_set_at=now,
        notes=merged_notes,
    )
    db.add(camp)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise AppError(
            "Conflit d'unicité de SM (période / version).",
            status_code=409,
            code="CAMPAIGN_DUPLICATE",
        ) from exc
    db.add(
        RbcmValidationEvent(
            campaign_id=camp.id,
            action="CREATE",
            from_status=None,
            to_status="BROUILLON",
            comment=label or notes,
            actor_id=user.id,
        )
    )
    _append_owner_history(
        db,
        campaign=camp,
        from_owner_id=None,
        to_owner_id=owner_id,
        actor_id=user.id,
        motif="Désignation initiale",
        action="OWNER_ASSIGN",
    )
    await db.flush()
    return camp


async def patch_campaign(
    db: AsyncSession,
    campaign: RbcmCampaign,
    *,
    closing_date=...,
    notes=...,
    user: User | None = None,
) -> RbcmCampaign:
    if campaign.status in ("CLOTUREE", "APPROUVEE"):
        raise AppError(
            "SM figée : modification interdite.",
            status_code=409,
            code="CAMPAIGN_LOCKED",
        )
    before_notes = campaign.notes
    before_date = campaign.closing_date
    if closing_date is not ...:
        campaign.closing_date = closing_date
    if notes is not ...:
        campaign.notes = notes
    if user and (before_notes != campaign.notes or before_date != campaign.closing_date):
        db.add(
            RbcmValidationEvent(
                campaign_id=campaign.id,
                action="PATCH",
                from_status=campaign.status,
                to_status=campaign.status,
                comment="Modification métadonnées",
                actor_id=user.id,
            )
        )
    await db.flush()
    return campaign


async def delete_eligibility(db: AsyncSession, campaign: RbcmCampaign) -> dict:
    """Suppression autorisée quel que soit le statut — les counts alimentent la confirmation."""
    n_imp = int(
        await db.scalar(
            select(func.count())
            .select_from(RbcmImport)
            .where(RbcmImport.campaign_id == campaign.id)
        )
        or 0
    )
    n_imp_confirmed = int(
        await db.scalar(
            select(func.count())
            .select_from(RbcmImport)
            .where(
                RbcmImport.campaign_id == campaign.id,
                RbcmImport.status.in_(IMPORT_STATUSES_CONFIRMED),
            )
        )
        or 0
    )
    n_imp_draft = n_imp - n_imp_confirmed
    n_par = int(
        await db.scalar(
            select(func.count())
            .select_from(RbcmParameterValue)
            .where(RbcmParameterValue.campaign_id == campaign.id)
        )
        or 0
    )
    n_hist = int(
        await db.scalar(
            select(func.count())
            .select_from(RbcmValidationEvent)
            .where(
                RbcmValidationEvent.campaign_id == campaign.id,
                RbcmValidationEvent.action != "CREATE",
            )
        )
        or 0
    )
    reasons: list[str] = []
    if n_imp:
        reasons.append(f"{n_imp} import(s) seront définitivement retirés.")
    if n_par:
        reasons.append(f"{n_par} paramètre(s) saisi(s) seront définitivement retirés.")
    if n_hist:
        reasons.append(f"{n_hist} événement(s) de workflow seront retirés.")
    can_archive = campaign.status not in ("CLOTUREE",)
    return {
        "can_delete": True,
        "can_archive": can_archive,
        "reasons": reasons,
        "dependencies": {
            "imports": n_imp,
            "imports_confirmed": n_imp_confirmed,
            "imports_draft": n_imp_draft,
            "parameters": n_par,
            "workflow_events": n_hist,
            "status": campaign.status,
        },
    }


async def archive_campaign(
    db: AsyncSession,
    *,
    campaign: RbcmCampaign,
    user: User,
    comment: str | None = None,
) -> RbcmCampaign:
    """Archivage = clôture conservatrice (données conservées, période libérée)."""
    if campaign.status == "CLOTUREE":
        raise AppError("SM déjà clôturée / archivée.", status_code=409, code="ALREADY_CLOSED")
    return await transition_status(
        db,
        campaign=campaign,
        user=user,
        action="ARCHIVE",
        to_status="CLOTUREE",
        comment=comment or "Archivage contrôlé — données conservées",
    )


async def _purge_campaign_children(db: AsyncSession, campaign: RbcmCampaign) -> None:
    """Retire les enfants rbcm_* dans l'ordre des FK RESTRICT, sans contourner l'intégrité."""
    from app.services.reporting_bcm_sm.import_service import _unlink_stored_import

    cid = campaign.id
    await db.execute(
        update(RbcmDocumentDecision)
        .where(RbcmDocumentDecision.campaign_id == cid)
        .values(supersedes_decision_id=None)
    )
    await db.execute(sa_delete(RbcmDocumentDecision).where(RbcmDocumentDecision.campaign_id == cid))

    deliverables = (
        await db.scalars(select(RbcmDeliverable).where(RbcmDeliverable.campaign_id == cid))
    ).all()
    deliverable_paths = [d.stored_path for d in deliverables]
    await db.execute(
        update(RbcmDeliverable)
        .where(RbcmDeliverable.campaign_id == cid)
        .values(superseded_by_id=None)
    )
    await db.execute(sa_delete(RbcmDeliverable).where(RbcmDeliverable.campaign_id == cid))

    await db.execute(
        update(RbcmCellDecision)
        .where(RbcmCellDecision.campaign_id == cid)
        .values(supersedes_decision_id=None)
    )
    await db.execute(sa_delete(RbcmCellDecision).where(RbcmCellDecision.campaign_id == cid))
    await db.execute(sa_delete(RbcmCellResult).where(RbcmCellResult.campaign_id == cid))
    await db.execute(sa_delete(RbcmControlResult).where(RbcmControlResult.campaign_id == cid))
    await db.execute(sa_delete(RbcmEcartSnapshot).where(RbcmEcartSnapshot.campaign_id == cid))
    await db.execute(sa_delete(RbcmCalculationRun).where(RbcmCalculationRun.campaign_id == cid))

    await db.execute(sa_delete(RbcmReconcileIssue).where(RbcmReconcileIssue.campaign_id == cid))
    await db.execute(
        update(RbcmControlRun)
        .where(RbcmControlRun.campaign_id == cid)
        .values(previous_run_id=None)
    )
    await db.execute(sa_delete(RbcmControlRun).where(RbcmControlRun.campaign_id == cid))

    await db.execute(
        update(RbcmParameterValue)
        .where(RbcmParameterValue.campaign_id == cid)
        .values(supersedes_value_id=None)
    )
    await db.execute(sa_delete(RbcmParameterValue).where(RbcmParameterValue.campaign_id == cid))

    await db.execute(sa_delete(RbcmImportLineDet).where(RbcmImportLineDet.campaign_id == cid))
    await db.execute(sa_delete(RbcmBalanceNcg).where(RbcmBalanceNcg.campaign_id == cid))
    imports = (await db.scalars(select(RbcmImport).where(RbcmImport.campaign_id == cid))).all()
    import_paths = [imp.stored_path for imp in imports]
    await db.execute(
        update(RbcmImport).where(RbcmImport.campaign_id == cid).values(supersedes_import_id=None)
    )
    await db.execute(sa_delete(RbcmImport).where(RbcmImport.campaign_id == cid))

    await db.execute(sa_delete(RbcmValidationEvent).where(RbcmValidationEvent.campaign_id == cid))
    await db.execute(
        sa_delete(RbcmReportingOwnerHistory).where(RbcmReportingOwnerHistory.campaign_id == cid)
    )
    await db.execute(
        update(RbcmCampaign)
        .where(RbcmCampaign.reopened_from_id == cid)
        .values(reopened_from_id=None)
    )
    await db.flush()
    for path in (*deliverable_paths, *import_paths):
        _unlink_stored_import(path)


async def delete_campaign(
    db: AsyncSession,
    *,
    campaign: RbcmCampaign,
    user: User,
) -> None:
    """Suppression d'une SM quel que soit son statut.

    Cascade ordonnée des enfants rbcm_* (FK RESTRICT respectées). Les fichiers
    d'import et de livrable sous upload_root sont retirés après flush.
    """
    _ = user
    await _purge_campaign_children(db, campaign)
    try:
        await db.delete(campaign)
        await db.flush()
    except IntegrityError as exc:
        raise AppError(
            "Suppression impossible : des données liées restent attachées à cette SM.",
            status_code=409,
            code="CAMPAIGN_DELETE_FORBIDDEN",
        ) from exc


async def reopen_campaign(
    db: AsyncSession,
    *,
    user: User,
    source: RbcmCampaign,
    comment: str | None = None,
) -> RbcmCampaign:
    if source.status != "CLOTUREE":
        raise AppError(
            "Seule une SM clôturée peut être rouverte.",
            status_code=409,
            code="CAMPAIGN_REOPEN_INVALID",
        )
    if not comment or not comment.strip():
        raise AppError(
            "La réouverture exige une raison documentée.",
            code="REOPEN_REASON_REQUIRED",
        )
    open_row = await _has_open_campaign(
        db,
        bank_code=source.bank_code,
        year=source.period_year,
        month=source.period_month,
    )
    if open_row is not None:
        raise AppError(
            "Une version ouverte existe déjà pour cette période.",
            status_code=409,
            code="CAMPAIGN_OPEN_EXISTS",
        )

    mx = await _max_version(
        db, bank_code=source.bank_code, year=source.period_year, month=source.period_month
    )
    new_version = max(source.campaign_version + 1, mx + 1)

    now = datetime.now(timezone.utc)
    owner_id = source.reporting_owner_id or user.id
    camp = RbcmCampaign(
        period_year=source.period_year,
        period_month=source.period_month,
        closing_date=source.closing_date,
        bank_code=source.bank_code,
        status="BROUILLON",
        campaign_version=new_version,
        reopened_from_id=source.id,
        preparer_id=user.id,
        reporting_owner_id=owner_id,
        reporting_owner_set_at=now,
        notes=f"Réouverture depuis v{source.campaign_version} — {comment.strip()}",
    )
    db.add(camp)
    db.add(
        RbcmValidationEvent(
            campaign_id=source.id,
            action="REOPEN",
            from_status=source.status,
            to_status="ROUVERTE",
            comment=comment,
            actor_id=user.id,
        )
    )
    try:
        await db.flush()
    except IntegrityError as exc:
        raise AppError(
            "Conflit d'unicité lors de la réouverture.",
            status_code=409,
            code="CAMPAIGN_DUPLICATE",
        ) from exc
    _append_owner_history(
        db,
        campaign=camp,
        from_owner_id=None,
        to_owner_id=owner_id,
        actor_id=user.id,
        motif=f"Reprise du responsable à la réouverture — {comment.strip()}",
        action="OWNER_ASSIGN",
    )
    await db.flush()
    return camp


async def list_history(
    db: AsyncSession, campaign_id: uuid.UUID, *, page: int = 1, page_size: int = 50
) -> tuple[list[RbcmValidationEvent], int]:
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    cq = select(func.count()).select_from(RbcmValidationEvent).where(
        RbcmValidationEvent.campaign_id == campaign_id
    )
    total = int(await db.scalar(cq) or 0)
    rows = (
        await db.scalars(
            select(RbcmValidationEvent)
            .where(RbcmValidationEvent.campaign_id == campaign_id)
            .order_by(RbcmValidationEvent.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return list(rows), total


async def transition_status(
    db: AsyncSession,
    *,
    campaign: RbcmCampaign,
    user: User,
    action: str,
    to_status: str,
    comment: str | None = None,
    require_other_user: bool = False,
    compared_to_user_id: uuid.UUID | None = None,
) -> RbcmCampaign:
    if require_other_user and compared_to_user_id and compared_to_user_id == user.id:
        raise AppError(
            "Séparation des tâches : un utilisateur ne peut pas approuver sa propre opération.",
            status_code=403,
            code="SOD_VIOLATION",
        )
    from_status = campaign.status
    campaign.status = to_status
    if to_status == "APPROUVEE":
        campaign.approver_id = user.id
        campaign.approved_at = datetime.now(timezone.utc)
    if to_status == "A_CONTROLER":
        campaign.controller_id = None
    if action == "CONTROL_OK":
        campaign.controller_id = user.id
    if to_status == "CLOTUREE":
        campaign.locked_at = datetime.now(timezone.utc)
    db.add(
        RbcmValidationEvent(
            campaign_id=campaign.id,
            action=action,
            from_status=from_status,
            to_status=to_status,
            comment=comment,
            actor_id=user.id,
        )
    )
    await db.flush()
    return campaign


async def campaign_progress(db: AsyncSession, campaign_id: uuid.UUID) -> dict:
    """Indicateurs de progression pour l'UI (pas un état réglementaire)."""
    from app.services.reporting_bcm_sm.constants import PARAMETER_CODES

    imports = (
        await db.scalars(select(RbcmImport).where(RbcmImport.campaign_id == campaign_id))
    ).all()
    det_ok = any(i.file_type == "BAL_DET" and i.status == "VALIDATED" for i in imports)
    # Historique seulement — plus requis dans le workflow (T3.4-A2).
    cond_ok = any(i.file_type == "BAL_COND" and i.status == "VALIDATED" for i in imports)
    # Les contrôles internes sont exécutés à la confirmation DET.
    coherence_ok = det_ok
    params = (
        await db.scalars(
            select(RbcmParameterValue)
            .where(RbcmParameterValue.campaign_id == campaign_id)
            .order_by(RbcmParameterValue.created_at.desc())
        )
    ).all()
    seen: set[str] = set()
    filled = 0
    validated = 0
    for p in params:
        if p.parameter_code in seen:
            continue
        seen.add(p.parameter_code)
        if p.status in ("SAISI", "CALCULE", "VALIDE"):
            filled += 1
        if p.status == "VALIDE":
            validated += 1
    # Workflow : DET → contrôles internes → paramètres (plus d’étape COND).
    steps = [
        ("imports_det", det_ok),
        ("controles_det", coherence_ok),
        ("parametres", filled >= len(PARAMETER_CODES)),
    ]
    done = sum(1 for _, ok in steps if ok)
    out = {
        "det_validated": det_ok,
        "cond_validated": cond_ok,  # deprecated flag — historique uniquement
        "parameters_filled": filled,
        "parameters_validated": validated,
        "parameters_total": len(PARAMETER_CODES),
        "steps_done": done,
        "steps_total": len(steps),
        "pct": int(round(100 * done / len(steps))) if steps else 0,
        "imports_count": len([i for i in imports if i.file_type == "BAL_DET"]),
        "imports_anomaly": sum(
            1
            for i in imports
            if i.file_type == "BAL_DET"
            and i.status == "REJECTED"
        ),
        "last_control_run_id": None,
        "last_control_result": None,
        "last_control_at": None,
        "complements_open": 0,
        "last_calc_run_id": None,
        "last_calc_at": None,
        "work_document_id": None,
        "work_stale": False,
    }

    calc = await db.scalar(
        select(RbcmCalculationRun)
        .where(
            RbcmCalculationRun.campaign_id == campaign_id,
            RbcmCalculationRun.status == "DONE",
        )
        .order_by(RbcmCalculationRun.created_at.desc())
        .limit(1)
    )
    work = await db.scalar(
        select(RbcmDeliverable).where(
            RbcmDeliverable.campaign_id == campaign_id,
            RbcmDeliverable.kind == "EXCEL",
            RbcmDeliverable.status == "WORK",
        )
    )
    if calc is not None:
        out["last_calc_run_id"] = str(calc.id)
        out["last_calc_at"] = calc.finished_at.isoformat() if calc.finished_at else (
            calc.created_at.isoformat() if calc.created_at else None
        )
    if work is not None:
        out["work_document_id"] = str(work.id)
        out["work_stale"] = bool(calc is None or work.run_id != calc.id)

    from app.services.reporting_bcm_sm.control_service import GAP_STATES

    last = await db.scalar(
        select(RbcmControlRun)
        .where(RbcmControlRun.campaign_id == campaign_id)
        .order_by(RbcmControlRun.created_at.desc(), RbcmControlRun.id.desc())
        .limit(1)
    )
    if last is None:
        return out
    open_n = int(
        await db.scalar(
            select(func.count())
            .select_from(RbcmReconcileIssue)
            .where(
                RbcmReconcileIssue.run_id == last.id,
                RbcmReconcileIssue.resolution_state.in_(GAP_STATES),
            )
        )
        or 0
    )
    out["last_control_run_id"] = str(last.id)
    out["last_control_result"] = last.result
    out["last_control_at"] = last.created_at.isoformat() if last.created_at else None
    out["complements_open"] = open_n
    return out
