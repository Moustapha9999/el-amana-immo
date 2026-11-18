"""Workflow 3 niveaux — séparation des tâches (pas d'auto-approbation).

Étape 7 : soumission, contrôle, approbation, rejet, téléchargement final.
Ne clôture jamais D01/D02. Ne déclare jamais un livrable réglementaire tant que
``can_finalize_regulatory`` est faux ou qu’une porte métier est ouverte.
Le statut Excel ``VALIDATED`` n’existe pas en base (contrainte WORK/SUPERSEDED/
GENERATED) : le document final est le canevas figé au moment de l’approbation.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.exceptions import AppError
from app.models import User
from app.models.reporting_bcm_sm import (
    RbcmCalculationRun,
    RbcmCampaign,
    RbcmControlResult,
    RbcmControlRun,
    RbcmDeliverable,
    RbcmValidationEvent,
)
from app.services.reporting_bcm_sm import campaign_service
from app.services.reporting_bcm_sm.document_access import sm_period_filename
from app.services.reporting_bcm_sm.document_graph import load_gate_state
from app.services.reporting_bcm_sm.review_service import GATE_LABELS, _fp

SUBMIT_FROM = ("CALCULEE", "PARAMETREE", "RAPPROCHEE")
LOCKED_STATUSES = ("APPROUVEE", "CLOTUREE")
SUBMITTED_STATUS = "A_CONTROLER"


def _blocker(code: str, title: str, message: str) -> dict[str, str]:
    return {"code": code, "title": title, "message": message}


def _raise_blockers(
    blockers: list[dict[str, str]], *, code: str, status_code: int = 409
) -> None:
    if not blockers:
        return
    detail = " | ".join(b["message"] for b in blockers)
    raise AppError(detail, status_code=status_code, code=code)


def submit_blockers(facts: dict[str, Any]) -> list[dict[str, str]]:
    """Conditions de soumission — pures, sans I/O. Ne ferme aucune porte métier."""
    out: list[dict[str, str]] = []
    status = facts.get("status")
    if status in LOCKED_STATUSES:
        out.append(
            _blocker(
                "LOCKED",
                "SM figée",
                "Une SM approuvée ou clôturée ne peut pas être soumise. Réouvrir pour une nouvelle version.",
            )
        )
        return out
    if status == SUBMITTED_STATUS:
        out.append(
            _blocker(
                "ALREADY_SUBMITTED",
                "Déjà soumise",
                "La SM est déjà soumise. Attendre le contrôle / l’approbation, ou renvoyer en correction.",
            )
        )
        return out
    if status not in SUBMIT_FROM:
        out.append(
            _blocker(
                "STATUS",
                "Statut inadapté",
                f"Soumission interdite depuis {status}. Alimenter et vérifier le document d’abord.",
            )
        )
    if not facts.get("det_ok"):
        out.append(_blocker("DET", "BAL DET", "Aucune BAL DET confirmée."))
    if not facts.get("control_ok"):
        out.append(_blocker("CONTROLES", "Contrôles", "Aucun contrôle enregistré, ou échec technique."))
    if facts.get("blocking_controls"):
        out.append(
            _blocker(
                "CONTROLS_BLOCKING",
                "Contrôles bloquants",
                "Des contrôles bloquants sont en échec. La soumission est refusée.",
            )
        )
    if not facts.get("calc_ok"):
        out.append(_blocker("ALIMENTATION", "Alimentation", "Aucun calcul enregistré."))
    if facts.get("missing_params"):
        out.append(
            _blocker(
                "PARAMETRES",
                "Informations manuelles",
                f"{facts['missing_params']} paramètre(s) encore à saisir (un zéro n’est pas une saisie).",
            )
        )
    pending = list(facts.get("pending_manual") or [])
    if pending:
        out.append(
            _blocker(
                "MANUELLES",
                "Cellules manuelles",
                "Cellules encore vides : " + ", ".join(pending) + ".",
            )
        )
    if not facts.get("work_id"):
        out.append(_blocker("CANEVAS", "Canevas", "Aucun document de travail à soumettre."))
    if facts.get("work_stale") or facts.get("params_stale"):
        out.append(
            _blocker(
                "STALE",
                "Vérification périmée",
                "Les données ont changé depuis le dernier canevas. Relancer l’alimentation puis revérifier.",
            )
        )
    for gate in facts.get("open_gates") or []:
        out.append(
            _blocker(
                f"GATE_{gate}",
                GATE_LABELS.get(gate, gate),
                f"Décision métier {gate} encore ouverte — aucune règle n’a été inventée. "
                "La soumission réglementaire reste bloquée.",
            )
        )
    if not facts.get("can_finalize"):
        out.append(
            _blocker(
                "FINALIZE",
                "Finalisation réglementaire",
                "can_finalize_regulatory est faux : le moteur n’autorise pas un document officiel.",
            )
        )
    return out


def approve_blockers(facts: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    status = facts.get("status")
    if status in LOCKED_STATUSES:
        out.append(
            _blocker(
                "ALREADY_APPROVED",
                "Déjà approuvée",
                "La SM est déjà approuvée ou clôturée.",
            )
        )
        return out
    if status != SUBMITTED_STATUS:
        out.append(
            _blocker(
                "NOT_SUBMITTED",
                "Non soumise",
                "L’approbation exige une SM d’abord soumise au contrôle (A_CONTROLER).",
            )
        )
    user_id = facts.get("user_id")
    preparer_id = facts.get("preparer_id")
    if user_id and preparer_id and str(user_id) == str(preparer_id):
        out.append(
            _blocker(
                "SOD_PREPARER",
                "Séparation des tâches",
                "Le préparateur ne peut pas approuver sa propre SM.",
            )
        )
    owner_id = facts.get("reporting_owner_id")
    if user_id and owner_id and str(user_id) == str(owner_id):
        out.append(
            _blocker(
                "SOD_OWNER",
                "Séparation des tâches",
                "Le responsable du reporting ne peut pas approuver sa propre SM.",
            )
        )
    if facts.get("blocking_controls"):
        out.append(
            _blocker(
                "CONTROLS_BLOCKING",
                "Contrôles bloquants",
                "Approbation impossible : contrôles bloquants ouverts.",
            )
        )
    if facts.get("work_stale") or facts.get("params_stale"):
        out.append(
            _blocker(
                "STALE",
                "Vérification périmée",
                "Le canevas soumis n’est plus aligné. Renvoyer en correction.",
            )
        )
    for gate in facts.get("open_gates") or []:
        out.append(
            _blocker(
                f"GATE_{gate}",
                GATE_LABELS.get(gate, gate),
                f"Décision métier {gate} encore ouverte. L’approbation réglementaire reste bloquée.",
            )
        )
    if not facts.get("can_finalize"):
        out.append(
            _blocker(
                "FINALIZE",
                "Finalisation réglementaire",
                "can_finalize_regulatory est faux : pas de document officiel.",
            )
        )
    return out


def reject_blockers(facts: dict[str, Any], *, comment: str | None) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if facts.get("status") != SUBMITTED_STATUS:
        out.append(
            _blocker(
                "NOT_SUBMITTED",
                "Non soumise",
                "Seul un dossier soumis (A_CONTROLER) peut être renvoyé en correction.",
            )
        )
    if not (comment or "").strip():
        out.append(
            _blocker(
                "REJECT_REASON_REQUIRED",
                "Motif obligatoire",
                "Le motif de rejet est obligatoire.",
            )
        )
    return out


def control_ok_blockers(facts: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if facts.get("status") != SUBMITTED_STATUS:
        out.append(_blocker("NOT_SUBMITTED", "Non soumise", "SM non en contrôle."))
    user_id = facts.get("user_id")
    preparer_id = facts.get("preparer_id")
    if user_id and preparer_id and str(user_id) == str(preparer_id):
        out.append(
            _blocker(
                "SOD_PREPARER",
                "Séparation des tâches",
                "Le préparateur ne peut pas être contrôleur.",
            )
        )
    return out


def final_download_blockers(facts: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if facts.get("status") not in LOCKED_STATUSES:
        out.append(
            _blocker(
                "NOT_APPROVED",
                "Document final",
                "Le téléchargement réglementaire n’est disponible qu’après approbation. "
                "Le canevas actuel reste un document de travail.",
            )
        )
    if not facts.get("approved_work_id"):
        out.append(
            _blocker(
                "NO_FINAL",
                "Document figé absent",
                "Aucun canevas n’a été figé à l’approbation.",
            )
        )
    return out


def assert_campaign_editable(campaign: RbcmCampaign) -> None:
    """Interdit une modification silencieuse d’un dossier soumis ou figé."""
    if campaign.status in LOCKED_STATUSES:
        raise AppError(
            "SM approuvée ou clôturée : toute correction passe par une réouverture (nouvelle version).",
            status_code=409,
            code="CAMPAIGN_LOCKED",
        )
    if campaign.status == SUBMITTED_STATUS:
        raise AppError(
            "SM soumise : renvoyer le dossier en correction avant toute modification. "
            "Le document soumis ne doit pas être altéré silencieusement.",
            status_code=409,
            code="CAMPAIGN_SUBMITTED",
        )


async def _blocking_control_fail(db: AsyncSession, campaign_id) -> bool:
    row = await db.scalar(
        select(RbcmControlResult.id)
        .where(
            RbcmControlResult.campaign_id == campaign_id,
            RbcmControlResult.severity == "BLOCKING",
            RbcmControlResult.result == "FAIL",
        )
        .limit(1)
    )
    return row is not None


async def _last_event(db: AsyncSession, campaign_id, action: str) -> RbcmValidationEvent | None:
    return await db.scalar(
        select(RbcmValidationEvent)
        .where(
            RbcmValidationEvent.campaign_id == campaign_id,
            RbcmValidationEvent.action == action,
        )
        .order_by(RbcmValidationEvent.created_at.desc())
        .limit(1)
    )


async def _current_work(db: AsyncSession, campaign_id) -> RbcmDeliverable | None:
    return await db.scalar(
        select(RbcmDeliverable).where(
            RbcmDeliverable.campaign_id == campaign_id,
            RbcmDeliverable.kind == "EXCEL",
            RbcmDeliverable.status == "WORK",
        )
    )


def _workflow_meta(work: RbcmDeliverable | None) -> dict[str, Any]:
    if work is None or not work.warnings:
        return {}
    raw = work.warnings.get("workflow")
    return dict(raw) if isinstance(raw, dict) else {}


async def collect_facts(
    db: AsyncSession, campaign: RbcmCampaign, *, user: User | None = None
) -> dict[str, Any]:
    from app.services.reporting_bcm_sm.control_service import param_is_filled
    from app.services.reporting_bcm_sm.parameter_service import PARAM_DISPLAY_ORDER, current_values

    progress = await campaign_service.campaign_progress(db, campaign.id)
    params = await current_values(db, campaign.id)
    param_by = {p.parameter_code: p for p in params}
    missing = [
        code
        for code in PARAM_DISPLAY_ORDER
        if not param_is_filled(
            param_by[code].value if code in param_by else None,
            param_by[code].status if code in param_by else None,
        )
    ]
    calc = await db.scalar(
        select(RbcmCalculationRun)
        .where(
            RbcmCalculationRun.campaign_id == campaign.id,
            RbcmCalculationRun.status == "DONE",
        )
        .order_by(RbcmCalculationRun.created_at.desc())
        .limit(1)
    )
    work = await _current_work(db, campaign.id)
    live_fp = _fp(*[f"{p.parameter_code}:{p.value}:{p.status}" for p in params])
    params_stale = bool(calc and calc.fingerprint_params and calc.fingerprint_params != live_fp)
    work_stale = bool(
        work is not None and calc is not None and (work.run_id != calc.id or params_stale)
    )
    report = dict(calc.report or {}) if calc else {}
    last_control = await db.scalar(
        select(RbcmControlRun)
        .where(RbcmControlRun.campaign_id == campaign.id)
        .order_by(RbcmControlRun.created_at.desc(), RbcmControlRun.id.desc())
        .limit(1)
    )
    technical = bool(last_control and last_control.result == "FAILED")
    gates = await load_gate_state(db)
    open_gates = [k for k, v in gates.as_dict().items() if v]
    meta = _workflow_meta(work)
    submitted_ev = await _last_event(db, campaign.id, "SUBMIT_CONTROL")
    approved_ev = await _last_event(db, campaign.id, "APPROVE")
    rejected_ev = await _last_event(db, campaign.id, "CONTROL_REJECT")
    control_ev = await _last_event(db, campaign.id, "CONTROL_OK")
    return {
        "status": campaign.status,
        "det_ok": bool(progress.get("det_validated")),
        "control_ok": bool(progress.get("last_control_run_id")) and not technical,
        "calc_ok": calc is not None,
        "missing_params": len(missing),
        "pending_manual": list(report.get("pending_manual") or []),
        "work_id": str(work.id) if work else None,
        "work_filename": work.filename if work else None,
        "work_sha256": work.sha256 if work else None,
        "work_stale": work_stale,
        "params_stale": params_stale,
        "open_gates": open_gates,
        "gates": gates.as_dict(),
        "can_finalize": bool(report.get("can_finalize_regulatory")),
        "blocking_controls": await _blocking_control_fail(db, campaign.id),
        "preparer_id": str(campaign.preparer_id) if campaign.preparer_id else None,
        "reporting_owner_id": str(campaign.reporting_owner_id) if campaign.reporting_owner_id else None,
        "controller_id": str(campaign.controller_id) if campaign.controller_id else None,
        "approver_id": str(campaign.approver_id) if campaign.approver_id else None,
        "approved_at": campaign.approved_at.isoformat() if campaign.approved_at else None,
        "user_id": str(user.id) if user else None,
        "submitted_at": submitted_ev.created_at.isoformat() if submitted_ev else meta.get("submitted_at"),
        "submitted_by": str(submitted_ev.actor_id) if submitted_ev and submitted_ev.actor_id else meta.get("submitted_by"),
        "submitted_work_id": meta.get("submitted_work_id"),
        "approved_work_id": meta.get("approved_work_id"),
        "approved_sha256": meta.get("approved_sha256"),
        "control_ok_at": control_ev.created_at.isoformat() if control_ev else None,
        "rejected_at": rejected_ev.created_at.isoformat() if rejected_ev else None,
        "calc_run_id": str(calc.id) if calc else None,
        "period_filename": sm_period_filename(campaign.period_year, campaign.period_month),
    }


async def workflow_state(
    db: AsyncSession, campaign: RbcmCampaign, *, user: User | None = None
) -> dict[str, Any]:
    facts = await collect_facts(db, campaign, user=user)
    s_block = submit_blockers(facts)
    a_block = approve_blockers(facts)
    c_block = control_ok_blockers(facts)
    r_block = reject_blockers(facts, comment="motif")  # motif fourni à l’action
    r_need = reject_blockers(facts, comment=None)
    f_block = final_download_blockers(facts)
    return {
        "campaign_id": str(campaign.id),
        "status": campaign.status,
        "gates": facts["gates"],
        "open_gates": [
            {"code": g, "label": GATE_LABELS.get(g, g)} for g in facts["open_gates"]
        ],
        "can_finalize_regulatory": bool(facts["can_finalize"]),
        "work_stale": facts["work_stale"],
        "params_stale": facts["params_stale"],
        "submitted": {
            "at": facts["submitted_at"],
            "actor_id": facts["submitted_by"],
            "work_id": facts["submitted_work_id"],
        },
        "control_visa": {
            "at": facts["control_ok_at"],
            "actor_id": facts["controller_id"],
        },
        "approved": {
            "at": facts["approved_at"],
            "actor_id": facts["approver_id"],
            "work_id": facts["approved_work_id"],
        },
        "rejected": {"at": facts["rejected_at"]},
        "sod": {
            "preparer_id": facts["preparer_id"],
            "reporting_owner_id": facts["reporting_owner_id"],
            "current_user_id": facts["user_id"],
            "same_as_preparer": bool(
                facts["user_id"] and facts["preparer_id"] and facts["user_id"] == facts["preparer_id"]
            ),
            "same_as_owner": bool(
                facts["user_id"]
                and facts["reporting_owner_id"]
                and facts["user_id"] == facts["reporting_owner_id"]
            ),
        },
        "submit": {"allowed": not s_block, "blockers": s_block},
        "control_ok": {"allowed": not c_block, "blockers": c_block},
        "approve": {"allowed": not a_block, "blockers": a_block},
        "reject": {
            "allowed": not r_block,
            "blockers": r_need if facts["status"] != SUBMITTED_STATUS else [],
            "reason_required": True,
        },
        "work_download": {
            "allowed": bool(facts["work_id"]),
            "deliverable_id": facts["work_id"],
            "filename": facts["period_filename"],
            "disclaimer": "Document de travail non validé — ne constitue pas une validation réglementaire.",
        },
        "final_download": {
            "allowed": not f_block,
            "blockers": f_block,
            "deliverable_id": facts["approved_work_id"],
            "filename": facts["period_filename"],
        },
        "editable": facts["status"] not in (*LOCKED_STATUSES, SUBMITTED_STATUS),
    }


async def _stamp_work(
    db: AsyncSession, campaign: RbcmCampaign, *, user: User, phase: str
) -> RbcmDeliverable | None:
    work = await _current_work(db, campaign.id)
    if work is None:
        return None
    warnings = dict(work.warnings or {})
    wf = dict(warnings.get("workflow") or {})
    now = datetime.now(timezone.utc).isoformat()
    if phase == "submit":
        wf.update(
            {
                "submitted_at": now,
                "submitted_by": str(user.id),
                "submitted_work_id": str(work.id),
                "submitted_sha256": work.sha256,
                "submitted_run_id": str(work.run_id) if work.run_id else None,
            }
        )
        warnings["regulatory_validation"] = False
    elif phase == "approve":
        wf.update(
            {
                "approved_at": now,
                "approved_by": str(user.id),
                "approved_work_id": str(work.id),
                "approved_sha256": work.sha256,
                "approved_run_id": str(work.run_id) if work.run_id else None,
            }
        )
        warnings["regulatory_validation"] = True
        warnings["final"] = True
    elif phase == "reject":
        wf["rejected_at"] = now
        wf["rejected_by"] = str(user.id)
        warnings["regulatory_validation"] = False
        warnings.pop("final", None)
    warnings["workflow"] = wf
    work.warnings = warnings
    flag_modified(work, "warnings")
    await db.flush()
    return work


async def resolve_final_deliverable(
    db: AsyncSession, campaign: RbcmCampaign
) -> RbcmDeliverable:
    facts = await collect_facts(db, campaign)
    _raise_blockers(final_download_blockers(facts), code="FINAL_DOWNLOAD_BLOCKED")
    did = facts.get("approved_work_id")
    d = await db.get(RbcmDeliverable, uuid.UUID(str(did))) if did else None
    if d is None or d.campaign_id != campaign.id:
        raise AppError(
            "Document final introuvable. Le canevas de travail n’est pas le livrable réglementaire.",
            status_code=404,
            code="FINAL_NOT_FOUND",
        )
    return d


async def submit_for_control(
    db: AsyncSession, *, campaign: RbcmCampaign, user: User, comment: str | None
) -> RbcmCampaign:
    facts = await collect_facts(db, campaign, user=user)
    _raise_blockers(submit_blockers(facts), code="SUBMIT_BLOCKED")
    await _stamp_work(db, campaign, user=user, phase="submit")
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
    facts = await collect_facts(db, campaign, user=user)
    blockers = control_ok_blockers(facts)
    sod = [b for b in blockers if b["code"].startswith("SOD")]
    other = [b for b in blockers if not b["code"].startswith("SOD")]
    _raise_blockers(other, code="WORKFLOW_INVALID")
    _raise_blockers(sod, code="SOD_VIOLATION", status_code=403)
    return await campaign_service.transition_status(
        db,
        campaign=campaign,
        user=user,
        action="CONTROL_OK",
        to_status="A_CONTROLER",
        comment=comment,
    )


async def approve(
    db: AsyncSession, *, campaign: RbcmCampaign, user: User, comment: str | None
) -> RbcmCampaign:
    facts = await collect_facts(db, campaign, user=user)
    blockers = approve_blockers(facts)
    sod = [b for b in blockers if b["code"].startswith("SOD")]
    other = [b for b in blockers if not b["code"].startswith("SOD")]
    _raise_blockers(other, code="REGULATORY_BLOCKED")
    _raise_blockers(sod, code="SOD_VIOLATION", status_code=403)
    await _stamp_work(db, campaign, user=user, phase="approve")
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
    facts = await collect_facts(db, campaign, user=user)
    _raise_blockers(reject_blockers(facts, comment=comment), code="REJECT_INVALID")
    await _stamp_work(db, campaign, user=user, phase="reject")
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
