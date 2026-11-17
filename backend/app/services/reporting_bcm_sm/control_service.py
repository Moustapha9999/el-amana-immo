"""Contrôles métier SM — exécutions append-only, classification A/B/C/D.

Ne supprime jamais les ``rbcm_reconcile_issue`` précédentes.
Ne modifie pas le mapping (A_VALIDER) ni ECART ni le moteur.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import User
from app.models.reporting_bcm_sm import (
    RbcmBalanceNcg,
    RbcmCampaign,
    RbcmControlRun,
    RbcmImport,
    RbcmMappingRule,
    RbcmMappingVersion,
    RbcmReconcileIssue,
    RbcmUnmappedRubric,
)
from app.services.permission_service import load_user_permission_codes
from app.services.reporting_bcm_sm import access as rbcm_access
from app.services.reporting_bcm_sm import parameter_service
from app.services.reporting_bcm_sm.constants import PARAMETER_CODES
from app.services.reporting_bcm_sm.parameter_service import PARAMETER_LABELS

GAP_STATES = ("OPEN", "STILL_BLOCKING", "PENDING_DECISION", "IN_PROGRESS")
OK_STATES = ("OK", "RESOLVED")


def display_amount(value: Decimal | None) -> str | None:
    """NULL métier ≠ « 0,00 »."""
    if value is None:
        return None
    return format(value, "f")


def param_is_filled(value: Decimal | None, status: str | None) -> bool:
    if status in ("SAISI", "CALCULE", "VALIDE"):
        return True
    return value is not None


def global_result(issues: list[RbcmReconcileIssue]) -> str:
    blocking_file = any(
        i.severity == "BLOCKING" and (i.category or "") == "A" and i.resolution_state != "OK"
        for i in issues
    )
    if blocking_file:
        return "BLOCKING"
    gaps_c_b = [
        i
        for i in issues
        if i.resolution_state in ("OPEN", "STILL_BLOCKING") and (i.category or "") in ("B", "C")
    ]
    if gaps_c_b:
        return "INCOMPLETE"
    decisions = [
        i
        for i in issues
        if i.resolution_state == "PENDING_DECISION" or (i.category == "D" and i.resolution_state != "OK")
    ]
    if decisions:
        return "DECISIONS_PENDING"
    warnings = [i for i in issues if i.severity == "WARNING" and i.resolution_state != "OK"]
    if warnings:
        return "WARNINGS"
    return "OK"


def _item(
    *,
    campaign_id: uuid.UUID,
    run_id: uuid.UUID,
    category: str,
    item_key: str,
    code: str,
    title: str,
    message: str,
    severity: str,
    resolution_state: str,
    observed: str | None = None,
    expected: str | None = None,
    source: str | None = None,
    expected_source: str | None = None,
    consequence: str | None = None,
    recommended_action: str | None = None,
    action_code: str | None = None,
    ncg: str | None = None,
    extra: dict | None = None,
) -> RbcmReconcileIssue:
    kind = "SUCCESS" if resolution_state == "OK" else "GAP"
    details: dict[str, Any] = {
        "kind": kind,
        "observed": observed,
        "expected": expected,
        "source": source,
        "expected_source": expected_source,
        "consequence": consequence,
        "recommended_action": recommended_action,
        "action_code": action_code,
    }
    if extra:
        details.update(extra)
    return RbcmReconcileIssue(
        campaign_id=campaign_id,
        run_id=run_id,
        category=category,
        item_key=item_key,
        code=code,
        title=title,
        message=message,
        severity=severity,
        resolution_state=resolution_state,
        resolved=resolution_state in ("OK", "RESOLVED"),
        ncg=ncg,
        details=details,
    )


async def latest_run(db: AsyncSession, campaign_id: uuid.UUID) -> RbcmControlRun | None:
    return await db.scalar(
        select(RbcmControlRun)
        .where(RbcmControlRun.campaign_id == campaign_id)
        .order_by(RbcmControlRun.created_at.desc(), RbcmControlRun.id.desc())
        .limit(1)
    )


async def list_runs(db: AsyncSession, campaign_id: uuid.UUID) -> list[RbcmControlRun]:
    rows = (
        await db.scalars(
            select(RbcmControlRun)
            .where(RbcmControlRun.campaign_id == campaign_id)
            .order_by(RbcmControlRun.created_at.desc(), RbcmControlRun.id.desc())
        )
    ).all()
    return list(rows)


async def get_run(db: AsyncSession, campaign_id: uuid.UUID, run_id: uuid.UUID) -> RbcmControlRun:
    run = await db.get(RbcmControlRun, run_id)
    if run is None or run.campaign_id != campaign_id:
        raise AppError("Rapport de contrôle introuvable.", status_code=404, code="CONTROL_RUN_NOT_FOUND")
    return run


async def issues_for_run(
    db: AsyncSession, run_id: uuid.UUID
) -> list[RbcmReconcileIssue]:
    rows = (
        await db.scalars(
            select(RbcmReconcileIssue)
            .where(RbcmReconcileIssue.run_id == run_id)
            .order_by(RbcmReconcileIssue.category.nulls_last(), RbcmReconcileIssue.code)
        )
    ).all()
    return list(rows)


async def _mapping_snapshot(db: AsyncSession) -> dict[str, Any]:
    ver = await db.scalar(
        select(RbcmMappingVersion).where(RbcmMappingVersion.is_current.is_(True)).limit(1)
    )
    if ver is None:
        return {
            "a_valider": 0,
            "active": 0,
            "multi_cell": [],
            "unmapped": 0,
            "version_id": None,
        }
    rules = list(
        (
            await db.scalars(
                select(RbcmMappingRule).where(RbcmMappingRule.mapping_version_id == ver.id)
            )
        ).all()
    )
    a_valider = sum(1 for r in rules if r.lifecycle_status == "A_VALIDER")
    active = sum(1 for r in rules if r.lifecycle_status == "ACTIVE")
    by_pat: dict[str, set[str]] = defaultdict(set)
    for r in rules:
        by_pat[r.pattern].add(r.cell_ref)
    multi = [
        {"pattern": p, "cells": sorted(cells)}
        for p, cells in by_pat.items()
        if len(cells) > 1
    ]
    unmapped = int(
        await db.scalar(select(func.count()).select_from(RbcmUnmappedRubric)) or 0
    )
    return {
        "a_valider": a_valider,
        "active": active,
        "multi_cell": multi[:20],
        "multi_cell_count": len(multi),
        "unmapped": unmapped,
        "version_id": str(ver.id),
        "rules_total": len(rules),
    }


async def persist_failed_run(
    db: AsyncSession,
    *,
    campaign_id: uuid.UUID,
    user: User | None,
    error: BaseException,
) -> None:
    """Enregistre un run FAILED après rollback du travail partiel, puis commit.

    ``get_db`` annule la transaction appelante en cas d'exception : le commit
    ici est indispensable pour que l'échec survive. Le rollback préalable
    libère le ``FOR UPDATE`` campagne (sinon l'INSERT FK resterait bloqué).
    """
    from app.services.audit_helpers import record_audit

    previous = await latest_run(db, campaign_id)
    run = RbcmControlRun(
        campaign_id=campaign_id,
        actor_id=user.id if user is not None else None,
        result="FAILED",
        previous_run_id=previous.id if previous else None,
        summary={
            "technical_failure": True,
            "error_type": type(error).__name__,
            "result": "FAILED",
        },
    )
    db.add(run)
    await db.flush()
    try:
        await record_audit(
            db,
            user=user,
            action="rbcm.control.technical_failure",
            entity="rbcm_control_run",
            entity_id=str(run.id),
            after={
                "campaign_id": str(campaign_id),
                "result": "FAILED",
                "error_type": type(error).__name__,
                "previous_run_id": str(previous.id) if previous else None,
            },
            module_code="reporting-bcm-sm",
            espace_code="comptabilite",
        )
    except Exception:
        pass
    await db.commit()


async def run_sm_controls(
    db: AsyncSession,
    *,
    campaign: RbcmCampaign,
    user: User | None,
) -> dict[str, Any]:
    """Nouvelle exécution. Ne supprime aucun rapport précédent."""
    try:
        return await _run_sm_controls_body(db, campaign=campaign, user=user)
    except AppError:
        raise
    except Exception as exc:
        campaign_id = campaign.id
        actor_id = user.id if user is not None else None
        try:
            await db.rollback()
        except Exception:
            pass
        actor = await db.get(User, actor_id) if actor_id is not None else None
        try:
            await persist_failed_run(db, campaign_id=campaign_id, user=actor, error=exc)
        except Exception:
            raise AppError(
                "Le contrôle a échoué techniquement et le rapport d’échec n’a pas pu être conservé. Relancez.",
                status_code=500,
                code="CONTROL_TECHNICAL_FAILURE",
            ) from exc
        raise AppError(
            "Le contrôle a échoué techniquement. Le rapport d’échec a été conservé. Relancez.",
            status_code=500,
            code="CONTROL_TECHNICAL_FAILURE",
        ) from exc


async def _run_sm_controls_body(
    db: AsyncSession,
    *,
    campaign: RbcmCampaign,
    user: User | None,
) -> dict[str, Any]:
    locked = await db.scalar(
        select(RbcmCampaign).where(RbcmCampaign.id == campaign.id).with_for_update()
    )
    if locked is None:
        raise AppError("SM introuvable", status_code=404, code="NOT_FOUND")

    previous = await latest_run(db, campaign.id)
    run = RbcmControlRun(
        campaign_id=campaign.id,
        actor_id=user.id if user is not None else None,
        result="OK",
        previous_run_id=previous.id if previous else None,
        summary=None,
    )
    db.add(run)
    await db.flush()

    prev_gap_keys: set[str] = set()
    if previous:
        prev_gap_keys = {
            k
            for k in (
                await db.scalars(
                    select(RbcmReconcileIssue.item_key).where(
                        RbcmReconcileIssue.run_id == previous.id,
                        RbcmReconcileIssue.item_key.is_not(None),
                        RbcmReconcileIssue.resolution_state.in_(GAP_STATES),
                    )
                )
            ).all()
            if k
        }

    issues: list[RbcmReconcileIssue] = []
    cid, rid = campaign.id, run.id

    det = await db.scalar(
        select(RbcmImport).where(
            RbcmImport.campaign_id == campaign.id,
            RbcmImport.file_type == "BAL_DET",
            RbcmImport.status == "VALIDATED",
        )
    )
    if det is None:
        issues.append(
            _item(
                campaign_id=cid,
                run_id=rid,
                category="A",
                item_key="DET:REQUIRED",
                code="DET_REQUIRED",
                title="BAL DET manquante",
                message="Importez et confirmez la BAL DET avant de contrôler la SM.",
                severity="BLOCKING",
                resolution_state="STILL_BLOCKING",
                expected="BAL DET confirmée",
                observed="Aucune BAL DET confirmée",
                source="SM",
                expected_source="Fichier BAL DET",
                consequence="Impossible de préparer la SM.",
                recommended_action="Importer BAL DET",
                action_code="IMPORTER",
            )
        )
    else:
        issues.extend(await _det_category_a(db, campaign=locked, det=det, run_id=rid))
        issues.extend(await _category_c_params(db, campaign=locked, run_id=rid))

    issues.extend(_category_b_other_sources(cid, rid))
    mapping = await _mapping_snapshot(db)
    issues.extend(_category_d_decisions(cid, rid, mapping))

    current_gap_keys = {
        i.item_key for i in issues if i.item_key and i.resolution_state in GAP_STATES
    }
    resolved_keys = sorted(prev_gap_keys - current_gap_keys)

    for iss in issues:
        db.add(iss)

    result = global_result(issues)
    run.result = result
    run.summary = {
        "result": result,
        "actor_id": str(user.id) if user else None,
        "previous_run_id": str(previous.id) if previous else None,
        "counts": _counts(issues),
        "resolved_since_previous": resolved_keys,
        "new_since_previous": sorted(current_gap_keys - prev_gap_keys),
        "still_open": sorted(current_gap_keys & prev_gap_keys),
        "det_import_id": str(det.id) if det else None,
        "mapping": {
            "a_valider": mapping["a_valider"],
            "active": mapping["active"],
            "multi_cell_count": mapping.get("multi_cell_count", 0),
        },
    }
    if locked.status in ("BROUILLON", "IMPORTS"):
        locked.status = "RAPPROCHEE"
    await db.flush()
    return serialize_run(run, issues, actor_name=None)


def _counts(issues: list[RbcmReconcileIssue]) -> dict[str, int]:
    return {
        "total": len(issues),
        "ok": sum(1 for i in issues if i.resolution_state == "OK"),
        "open": sum(1 for i in issues if i.resolution_state == "OPEN"),
        "blocking": sum(1 for i in issues if i.severity == "BLOCKING" and i.resolution_state != "OK"),
        "pending_decision": sum(1 for i in issues if i.resolution_state == "PENDING_DECISION"),
        "by_category": {
            cat: sum(1 for i in issues if i.category == cat and i.resolution_state != "OK")
            for cat in ("A", "B", "C", "D")
        },
    }


async def _det_category_a(
    db: AsyncSession, *, campaign: RbcmCampaign, det: RbcmImport, run_id: uuid.UUID
) -> list[RbcmReconcileIssue]:
    cid = campaign.id
    balances = list(
        (
            await db.scalars(
                select(RbcmBalanceNcg).where(
                    RbcmBalanceNcg.import_id == det.id,
                    RbcmBalanceNcg.source == "BAL_DET",
                )
            )
        ).all()
    )
    report = det.control_report or {}
    missing_ncg = int(report.get("missing_ncg_count") or report.get("skipped_no_ncg") or 0)
    error_count = int(report.get("error_count") or 0)
    ncg_count = len(balances)
    sum_deb = det.sum_debit
    sum_cre = det.sum_credit
    signed_1_8 = Decimal("0")
    for b in balances:
        if b.ncg and str(b.ncg)[:1] in "12345678":
            signed_1_8 += (b.tot_debit or Decimal("0")) - (b.tot_credit or Decimal("0"))
    signed_1_8 = signed_1_8.quantize(Decimal("0.01"))
    devises = report.get("devises") or {}
    out: list[RbcmReconcileIssue] = []

    out.append(
        _item(
            campaign_id=cid,
            run_id=run_id,
            category="A",
            item_key="OK:DET_CONFIRMED",
            code="DET_CONFIRMED",
            title="BAL DET confirmée",
            message=f"Fichier {det.filename} — {ncg_count} NCG.",
            severity="INFO",
            resolution_state="OK",
            observed=f"{ncg_count} NCG · {det.row_count or 0} lignes",
            source="BAL DET",
            extra={"filename": det.filename, "row_count": det.row_count},
        )
    )
    out.append(
        _item(
            campaign_id=cid,
            run_id=run_id,
            category="A",
            item_key="OK:DET_CLASSES_1_8",
            code="DET_CLASSES_1_8",
            title="Total signé classes 1 à 8",
            message="Agrégation DET (débiteur − créditeur) des NCG de classes 1–8.",
            severity="INFO",
            resolution_state="OK",
            observed=display_amount(signed_1_8),
            source="BAL DET",
            extra={"classes_1_8_signed_det": str(signed_1_8)},
        )
    )
    if devises:
        parts = ", ".join(f"{k}: {v}" for k, v in sorted(devises.items()))
        out.append(
            _item(
                campaign_id=cid,
                run_id=run_id,
                category="A",
                item_key="OK:DET_DEVISES",
                code="DET_DEVISES",
                title="Répartition par devise",
                message=parts,
                severity="INFO",
                resolution_state="OK",
                observed=parts,
                source="BAL DET",
            )
        )
    else:
        out.append(
            _item(
                campaign_id=cid,
                run_id=run_id,
                category="A",
                item_key="DET:NO_DEVISE",
                code="DET_NO_DEVISE",
                title="Devises non renseignées",
                message="Aucune devise n’est présente sur les lignes DET.",
                severity="INFO",
                resolution_state="OPEN",
                observed="Aucune",
                expected="Au moins une devise",
                source="BAL DET",
                consequence="Les colonnes devises de la SM ne pourront pas être proposées.",
                recommended_action="Vérifier le fichier importé.",
                action_code="CONSULTER",
            )
        )
    if missing_ncg > 0:
        out.append(
            _item(
                campaign_id=cid,
                run_id=run_id,
                category="A",
                item_key="DET:MISSING_NCG",
                code="DET_MISSING_NCG",
                title="Lignes sans NCG",
                message=f"{missing_ncg} ligne(s) exclue(s) des soldes agrégés.",
                severity="WARNING",
                resolution_state="OPEN",
                observed=str(missing_ncg),
                expected="Toutes les lignes portent un NCG",
                source="BAL DET",
                consequence="Ces lignes n’entrent pas dans les totaux NCG.",
                recommended_action="Contrôler le fichier si le volume est anormal.",
                action_code="CONSULTER",
            )
        )
    if error_count > 0:
        out.append(
            _item(
                campaign_id=cid,
                run_id=run_id,
                category="A",
                item_key="DET:ANALYSIS_WARNINGS",
                code="DET_ANALYSIS_WARNINGS",
                title="Anomalies d’analyse",
                message=f"{error_count} anomalie(s) signalée(s) à l’analyse du fichier.",
                severity="WARNING",
                resolution_state="OPEN",
                observed=str(error_count),
                source="BAL DET",
                action_code="CONSULTER",
                extra={"errors_sample": (report.get("errors") or [])[:20]},
            )
        )
    if ncg_count == 0:
        out.append(
            _item(
                campaign_id=cid,
                run_id=run_id,
                category="A",
                item_key="DET:NO_NCG",
                code="DET_NO_NCG",
                title="Aucun NCG agrégé",
                message="La confirmation n’a produit aucun solde NCG.",
                severity="BLOCKING",
                resolution_state="STILL_BLOCKING",
                observed="0",
                expected="Au moins un NCG",
                source="BAL DET",
                consequence="La SM ne peut pas être préparée.",
                recommended_action="Corriger et réimporter la BAL DET.",
                action_code="IMPORTER",
            )
        )

    # Proposition caisse devises — jamais enregistrée automatiquement.
    current = {p.parameter_code: p for p in await parameter_service.current_values(db, campaign.id)}
    caisse = current.get("caisse_devises")
    caisse_filled = param_is_filled(
        caisse.value if caisse else None, caisse.status if caisse else None
    )
    try:
        prop = await parameter_service.propose_caisse_devises(db, campaign)
        proposed = prop.get("proposed_value")
        out.append(
            _item(
                campaign_id=cid,
                run_id=run_id,
                category="A",
                item_key="PARAM:caisse_devises",
                code="PARAM_CAISSE_PROPOSAL",
                title="Caisse devises (proposition DET)",
                message=(
                    "Proposition déjà rattachée au paramètre."
                    if caisse_filled
                    else "Valeur calculable depuis la BAL DET — confirmation manuelle requise."
                ),
                severity="INFO",
                resolution_state="OK" if caisse_filled else "OPEN",
                observed=proposed,
                expected="Confirmation du comptable (D04/D05 ouverts)",
                source="BAL DET (NCG 101* · EUR, DEB−CRE)",
                expected_source="Paramètre caisse_devises",
                consequence="Sans confirmation, le paramètre reste à compléter.",
                recommended_action=(
                    "Consulter le paramètre."
                    if caisse_filled
                    else "Enregistrer la proposition avec justification."
                ),
                action_code=None if caisse_filled else "SAISIR",
                extra={
                    "parameter_code": "caisse_devises",
                    "proposed_value": proposed,
                    "unit": prop.get("unit"),
                    "method": prop.get("method"),
                    "auto_saved": False,
                },
            )
        )
    except AppError:
        pass

    out.append(
        _item(
            campaign_id=cid,
            run_id=run_id,
            category="A",
            item_key="OK:DET_SUMS",
            code="DET_SUMS",
            title="Totaux débit / crédit",
            message="Sommes DET confirmées (Decimal).",
            severity="INFO",
            resolution_state="OK",
            observed=f"D {display_amount(sum_deb)} · C {display_amount(sum_cre)}",
            source="BAL DET",
        )
    )
    return out


async def _category_c_params(
    db: AsyncSession, *, campaign: RbcmCampaign, run_id: uuid.UUID
) -> list[RbcmReconcileIssue]:
    current = {p.parameter_code: p for p in await parameter_service.current_values(db, campaign.id)}
    out: list[RbcmReconcileIssue] = []
    for code in PARAMETER_CODES:
        if code == "caisse_devises":
            # Classé en A (calculable DET) — une seule demande de saisie.
            continue
        label = PARAMETER_LABELS.get(code, code)
        row = current.get(code)
        filled = param_is_filled(row.value if row else None, row.status if row else None)
        if filled:
            observed = display_amount(row.value) if row else None
            out.append(
                _item(
                    campaign_id=campaign.id,
                    run_id=run_id,
                    category="C",
                    item_key=f"PARAM:{code}",
                    code="PARAM_FILLED",
                    title=label,
                    message="Paramètre renseigné (historique conservé).",
                    severity="INFO",
                    resolution_state="OK",
                    observed=observed,
                    source=row.source if row else None,
                    extra={
                        "parameter_code": code,
                        "status": row.status if row else None,
                        "authored_by_id": str(row.authored_by_id) if row and row.authored_by_id else None,
                    },
                )
            )
        else:
            out.append(
                _item(
                    campaign_id=campaign.id,
                    run_id=run_id,
                    category="C",
                    item_key=f"PARAM:{code}",
                    code="PARAM_MISSING",
                    title=label,
                    message="Information mensuelle à saisir — l’absence n’est pas un zéro.",
                    severity="WARNING",
                    resolution_state="OPEN",
                    observed=None,
                    expected="Valeur saisie avec source et justification",
                    source=None,
                    expected_source="Saisie comptable du mois",
                    consequence="La préparation officielle de la SM restera incomplète pour cette rubrique.",
                    recommended_action="Saisir la valeur (ou justifier l’absence).",
                    action_code="SAISIR",
                    extra={"parameter_code": code, "status": "EN_ATTENTE"},
                )
            )
    out.append(
        _item(
            campaign_id=campaign.id,
            run_id=run_id,
            category="C",
            item_key="FPN:ANNEXES",
            code="FPN_ANNEXES",
            title="Informations FPN",
            message=(
                "Annexes « informations à fournir » du canevas SM "
                "(bénéfice hors dividendes, créances radiées, etc.)."
            ),
            severity="INFO",
            resolution_state="OPEN",
            observed=None,
            expected="Saisie lors de la préparation du canevas (T3.5-3)",
            expected_source="Comptabilité / canevas officiel",
            consequence="Les feuilles FPN et ratios resteront incomplètes.",
            recommended_action="Attendre le canevas officiel — ne pas inventer de montants.",
            action_code="CONSULTER",
        )
    )
    return out


def _category_b_other_sources(campaign_id: uuid.UUID, run_id: uuid.UUID) -> list[RbcmReconcileIssue]:
    specs = [
        (
            "D09:CREDITS",
            "D09_CREDITS",
            "Crédits à l’économie (ETAT B)",
            "Les concours par contrepartie (EPA, EPC, privé…) ne figurent pas dans la BAL DET.",
            "Fichier crédits / extraction D09",
        ),
        (
            "D09:DEPOTS",
            "D09_DEPOTS",
            "Dépôts",
            "La ventilation des dépôts n’est pas portée par la BAL DET.",
            "Fichier dépôts / extraction D09",
        ),
        (
            "D09:MATURITES",
            "D09_MATURITES",
            "Échéances et maturités (ETAT C)",
            "Les ventilations < 3 mois / 3 mois–2 ans / > 2 ans sont hors BAL DET.",
            "Fichier crédits-dépôts par maturité (D09)",
        ),
    ]
    out = []
    for key, code, title, msg, src in specs:
        out.append(
            _item(
                campaign_id=campaign_id,
                run_id=run_id,
                category="B",
                item_key=key,
                code=code,
                title=title,
                message=msg,
                severity="WARNING",
                resolution_state="OPEN",
                observed=None,
                expected="Données de la source métier — pas de répartition forfaitaire",
                source="Absente de la BAL DET",
                expected_source=src,
                consequence="ETAT B/C resteront provisoires ou vides tant que D09 n’est pas tranchée.",
                recommended_action="Fournir le fichier source lorsque disponible. Ne pas forcer 70/30.",
                action_code="CONSULTER",
            )
        )
    return out


def _category_d_decisions(
    campaign_id: uuid.UUID, run_id: uuid.UUID, mapping: dict[str, Any]
) -> list[RbcmReconcileIssue]:
    a_valider = int(mapping.get("a_valider") or 0)
    active = int(mapping.get("active") or 0)
    multi_n = int(mapping.get("multi_cell_count") or 0)
    unmapped = int(mapping.get("unmapped") or 0)
    out = [
        _item(
            campaign_id=campaign_id,
            run_id=run_id,
            category="D",
            item_key="DEC:D01",
            code="D01_MAPPING",
            title="Correspondances non validées (D01)",
            message=(
                f"{a_valider} règle(s) A_VALIDER, {active} ACTIVE. "
                "Aucune activation automatique."
            ),
            severity="BLOCKING",
            resolution_state="PENDING_DECISION",
            observed=f"{a_valider} A_VALIDER / {active} ACTIVE",
            expected="Arbitrage métier D01",
            source="Référentiel de correspondances",
            consequence="Pas d’état réglementaire définitif.",
            recommended_action="Consulter les correspondances (accès expert). Ne pas activer.",
            action_code="CONSULTER",
            extra={"a_valider": a_valider, "active": active},
        ),
        _item(
            campaign_id=campaign_id,
            run_id=run_id,
            category="D",
            item_key="DEC:D02",
            code="D02_ECART",
            title="ECART non formalisé (D02)",
            message="L’ECART reste désactivé. Aucune constante n’est appliquée au livrable.",
            severity="BLOCKING",
            resolution_state="PENDING_DECISION",
            observed="DESACTIVE",
            expected="Décision D02",
            source="Politique ECART",
            consequence="L’ECART n’est pas reporté sur la SM officielle.",
            recommended_action="Laisser ECART inactif jusqu’à arbitrage.",
            action_code="CONSULTER",
        ),
        _item(
            campaign_id=campaign_id,
            run_id=run_id,
            category="D",
            item_key="DEC:D06",
            code="D06_UNMAPPED",
            title="Rubriques sans correspondance (D06)",
            message=(
                f"{unmapped} rubrique(s) tracée(s) dans le référentiel. "
                "Jamais de zéro automatique."
            ),
            severity="WARNING",
            resolution_state="PENDING_DECISION",
            observed=str(unmapped) if unmapped else "Table encore vide — 67 rubriques documentaires T1",
            expected="Décision D06, jamais 0,00 fictif",
            source="Canevas / mapping",
            consequence="Cellules NON_MAPPEE jusqu’à arbitrage.",
            recommended_action="Ne pas saisir de zéro de substitution.",
            action_code="CONSULTER",
        ),
        _item(
            campaign_id=campaign_id,
            run_id=run_id,
            category="D",
            item_key="DEC:D16_D17",
            code="D16_D17_RESIDENCE",
            title="Résidents / non-résidents (D16/D17)",
            message="La BAL DET ne distingue pas la résidence. Colonnes 2–5 de l’ETAT A non calculables.",
            severity="BLOCKING",
            resolution_state="PENDING_DECISION",
            observed="Absent de la BAL DET",
            expected="Décision D16/D17 ou source complémentaire",
            source="BAL DET",
            expected_source="Paramètre résidence / fichier complémentaire",
            consequence="Pas de ventilation résidents / non-résidents.",
            recommended_action="Attendre l’arbitrage. Ne pas inventer la ventilation.",
            action_code="CONSULTER",
        ),
        _item(
            campaign_id=campaign_id,
            run_id=run_id,
            category="D",
            item_key="DEC:D22",
            code="D22_CONFLICTS",
            title="Comptes multi-cellules (D22)",
            message=f"{multi_n} compte(s) liés à plusieurs cellules BCM.",
            severity="WARNING" if multi_n else "INFO",
            resolution_state="PENDING_DECISION" if multi_n else "OK",
            observed=str(multi_n),
            expected="Une décision par conflit",
            source="Correspondances",
            consequence="Deux propositions possibles, une seule décision.",
            recommended_action="Consulter les conflits (accès expert). Pas d’activation.",
            action_code="CONSULTER",
            extra={"conflicts_sample": mapping.get("multi_cell") or []},
        ),
    ]
    return out


def serialize_issue(i: RbcmReconcileIssue, *, live: dict | None = None) -> dict[str, Any]:
    d = i.details or {}
    observed = d.get("observed")
    live_state = None
    available = list(
        filter(
            None,
            ["CONSULTER", d.get("action_code") if d.get("action_code") != "CONSULTER" else None],
        )
    )
    current_value_id = d.get("current_value_id")
    if live:
        live_state = live.get("live_state")
        observed = live.get("observed", observed)
        if live.get("available_actions") is not None:
            available = live["available_actions"]
        current_value_id = live.get("current_value_id", current_value_id)
    return {
        "id": str(i.id),
        "campaign_id": str(i.campaign_id),
        "run_id": str(i.run_id) if i.run_id else None,
        "category": i.category,
        "item_key": i.item_key,
        "code": i.code,
        "title": i.title or i.message,
        "message": i.message,
        "severity": i.severity,
        "resolution_state": i.resolution_state,
        "resolved": i.resolved,
        "ncg": i.ncg,
        "observed": observed,
        "expected": d.get("expected"),
        "source": d.get("source"),
        "expected_source": d.get("expected_source"),
        "consequence": d.get("consequence"),
        "recommended_action": d.get("recommended_action"),
        "action_code": d.get("action_code"),
        "available_actions": available,
        "live_state": live_state,
        "parameter_code": d.get("parameter_code"),
        "proposed_value": d.get("proposed_value"),
        "current_value_id": current_value_id,
        "unit": d.get("unit"),
        "details": d,
        "created_at": i.created_at.isoformat() if i.created_at else None,
    }


def serialize_run(
    run: RbcmControlRun,
    issues: list[RbcmReconcileIssue],
    *,
    actor_name: str | None,
) -> dict[str, Any]:
    return {
        "id": str(run.id),
        "campaign_id": str(run.campaign_id),
        "actor_id": str(run.actor_id) if run.actor_id else None,
        "actor_name": actor_name,
        "result": run.result,
        "previous_run_id": str(run.previous_run_id) if run.previous_run_id else None,
        "summary": run.summary,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "counts": (run.summary or {}).get("counts") or _counts(issues),
        "issues": [serialize_issue(i) for i in issues],
    }


async def build_complements(
    db: AsyncSession,
    *,
    campaign: RbcmCampaign,
    user: User | None,
) -> dict[str, Any]:
    """File A/B/C/D à partir du dernier run + état live des paramètres."""
    run = await latest_run(db, campaign.id)
    if run is None:
        return {
            "run": None,
            "items": [],
            "by_category": {"A": [], "B": [], "C": [], "D": []},
            "counts": {"A": 0, "B": 0, "C": 0, "D": 0, "open": 0},
            "technical_failure": False,
        }
    issues = await issues_for_run(db, run.id)
    current = {p.parameter_code: p for p in await parameter_service.current_values(db, campaign.id)}
    have: set[str] = set()
    if user is not None:
        have = await load_user_permission_codes(db, user)

    def can_saisir() -> bool:
        return rbcm_access.can_saisir_parametre(have)

    def can_control() -> bool:
        return rbcm_access.can_lancer_controles(have)

    items: list[dict] = []
    for i in issues:
        d = i.details or {}
        if d.get("kind") == "SUCCESS" or i.resolution_state in OK_STATES:
            continue
        live: dict[str, Any] = {}
        code = d.get("parameter_code")
        if i.category == "C" and code:
            row = current.get(code)
            live["current_value_id"] = str(row.id) if row else None
            if row and param_is_filled(row.value, row.status):
                live = {
                    **live,
                    "live_state": "SAISIE_A_RECONTROLER",
                    "observed": display_amount(row.value),
                    "available_actions": ["CONSULTER", "RELANCER"] if can_control() else ["CONSULTER"],
                }
            elif can_saisir():
                live["available_actions"] = ["CONSULTER", "SAISIR"]
            else:
                live["available_actions"] = ["CONSULTER"]
        elif i.category == "A" and d.get("action_code") == "SAISIR":
            acts = ["CONSULTER"]
            if can_saisir():
                acts.append("SAISIR")
            live["available_actions"] = acts
            pcode = d.get("parameter_code")
            prow = current.get(pcode) if pcode else None
            live["current_value_id"] = str(prow.id) if prow else None
        elif d.get("action_code") == "IMPORTER":
            live["available_actions"] = (
                ["CONSULTER", "IMPORTER"] if rbcm_access.can_importer(have) else ["CONSULTER"]
            )
        else:
            live["available_actions"] = ["CONSULTER"]
        items.append(serialize_issue(i, live=live))

    by_cat = {c: [x for x in items if x.get("category") == c] for c in ("A", "B", "C", "D")}
    return {
        "run": serialize_run(run, issues, actor_name=None),
        "items": items,
        "by_category": by_cat,
        "counts": {c: len(by_cat[c]) for c in ("A", "B", "C", "D")} | {"open": len(items)},
        "can_saisir": can_saisir(),
        "can_control": can_control(),
        "can_importer": rbcm_access.can_importer(have),
        "technical_failure": run.result == "FAILED",
    }


async def reconcile_view(db: AsyncSession, campaign_id: uuid.UUID) -> dict[str, Any]:
    """Vue expert : dernier rapport, sans mélanger les exécutions précédentes."""
    run = await latest_run(db, campaign_id)
    if run is None:
        return {
            "campaign_id": str(campaign_id),
            "ready": False,
            "summary": None,
            "summary_message": None,
            "issues": [],
            "issues_count": 0,
            "run_id": None,
            "result": None,
        }
    issues = await issues_for_run(db, run.id)
    summary = dict(run.summary or {})
    for i in issues:
        d = i.details or {}
        if i.code == "DET_CONFIRMED":
            summary.setdefault("row_count", d.get("row_count"))
            summary.setdefault("filename", d.get("filename"))
        if i.code == "DET_CLASSES_1_8":
            summary.setdefault("classes_1_8_signed_det", d.get("classes_1_8_signed_det"))
        if i.code == "DET_SUMS":
            summary.setdefault("observed_sums", d.get("observed"))
        if i.item_key == "OK:DET_CONFIRMED" and i.message:
            summary.setdefault("ncg_count", None)
    ncg_issue = next((i for i in issues if i.code == "DET_CONFIRMED"), None)
    if ncg_issue and ncg_issue.message:
        # « Fichier X — N NCG. »
        parts = ncg_issue.message.rsplit("—", 1)
        if len(parts) == 2 and "NCG" in parts[1]:
            digits = "".join(ch for ch in parts[1] if ch.isdigit())
            if digits:
                summary.setdefault("ncg_count", int(digits))
    gaps = [i for i in issues if i.resolution_state in GAP_STATES]
    return {
        "campaign_id": str(campaign_id),
        "ready": True,
        "summary": summary,
        "summary_message": f"Contrôles SM — {run.result}",
        "issues": [serialize_issue(i) for i in gaps[:50]],
        "issues_count": len(gaps),
        "run_id": str(run.id),
        "result": run.result,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }
