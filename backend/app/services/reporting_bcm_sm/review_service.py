"""Synthèse préparation (étape 5) et vérification documentaire (étape 6).

Ne calcule aucune nouvelle règle comptable. Ne clôture pas D01/D02.
Ne déclare jamais un document réglementairement conforme tant que
``can_finalize_regulatory`` est faux ou qu’une porte métier est ouverte.
"""

from __future__ import annotations

import hashlib
from typing import Any

from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.reporting_bcm_sm import (
    RbcmCalculationRun,
    RbcmCampaign,
    RbcmCellResult,
    RbcmControlRun,
    RbcmDeliverable,
)
from app.services.reporting_bcm_sm.control_service import param_is_filled
from app.services.reporting_bcm_sm.document_access import resolve_deliverable_file
from app.services.reporting_bcm_sm.document_graph import load_gate_state
from app.services.reporting_bcm_sm.engine.rules_catalog import ADJUST_KEYS
from app.services.reporting_bcm_sm.parameter_service import (
    PARAM_CELL_HINTS,
    PARAM_DISPLAY_ORDER,
    PARAM_NATURE,
    PARAMETER_LABELS,
    current_values,
)

OFFICIAL_SHEETS = (
    "informations à fournir",
    "ETAT A",
    "ETAT B",
    "ETAT C",
    "CALCUL FPN",
    "RATIO COUVERTURE DE RISQUE",
    "RATIO DE LIQUIDITE",
    "RATIO FP ET AI",
)

GATE_LABELS = {
    "D01": "Correspondances (mapping A_VALIDER)",
    "D02": "ECART classes 1–8",
    "D06": "Rubriques sans correspondance",
    "D09": "Crédits / dépôts (ETAT B/C)",
    "D15": "TOTDEB / TOTCRE",
    "D16_D17": "Résidents / non-résidents",
    "D22": "Comptes multi-cellules",
}

VERDICT_PREP_LABELS = {
    "ready": "Prêt pour vérification",
    "complements": "Informations complémentaires attendues",
    "decision": "Décision métier nécessaire",
    "blocked": "Blocage technique",
}

VERDICT_DOC_LABELS = {
    "conforme": "Conforme",
    "a_corriger": "À corriger",
    "a_completer": "À compléter",
    "decision": "En attente d’une décision métier",
}


def _fp(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update((p or "").encode("utf-8"))
        h.update(b"|")
    return h.hexdigest()


def _check(
    code: str,
    title: str,
    *,
    state: str,
    detail: str,
    action: str | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "title": title,
        "state": state,
        "detail": detail,
        "action": action,
    }


def _finding(
    *,
    code: str,
    title: str,
    category: str,
    severity: str,
    status: str,
    message: str,
    sheet: str | None = None,
    cell: str | None = None,
    action: str | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "title": title,
        "category": category,
        "severity": severity,
        "status": status,
        "message": message,
        "sheet": sheet,
        "cell": cell,
        "action": action,
    }


def preparation_verdict(
    *,
    det_ok: bool,
    control_ok: bool,
    calc_ok: bool,
    missing_params: int,
    decisions_open: int,
    technical: bool,
) -> str:
    if technical or not det_ok or not control_ok:
        return "blocked"
    if not calc_ok or missing_params:
        return "complements"
    if decisions_open:
        return "decision"
    return "ready"


def document_verdict(
    *,
    blocking: bool,
    to_complete: bool,
    decisions: bool,
    can_finalize: bool,
) -> str:
    if blocking:
        return "a_corriger"
    if to_complete:
        return "a_completer"
    if decisions or not can_finalize:
        return "decision"
    return "conforme"


async def build_review(db: AsyncSession, campaign: RbcmCampaign) -> dict[str, Any]:
    from app.services.reporting_bcm_sm.campaign_service import campaign_progress

    progress = await campaign_progress(db, campaign.id)
    params = await current_values(db, campaign.id)
    param_by = {p.parameter_code: p for p in params}
    missing_params = [
        {
            "code": code,
            "label": PARAMETER_LABELS.get(code, code),
            "cell_hint": PARAM_CELL_HINTS.get(code),
            "nature": PARAM_NATURE.get(code, "manuel"),
        }
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
    work = await db.scalar(
        select(RbcmDeliverable).where(
            RbcmDeliverable.campaign_id == campaign.id,
            RbcmDeliverable.kind == "EXCEL",
            RbcmDeliverable.status == "WORK",
        )
    )
    live_fp = _fp(*[f"{p.parameter_code}:{p.value}:{p.status}" for p in params])
    params_stale = bool(calc and calc.fingerprint_params and calc.fingerprint_params != live_fp)
    work_stale = bool(
        work is not None
        and calc is not None
        and (work.run_id != calc.id or params_stale)
    )
    report = dict(calc.report or {}) if calc else {}
    pending_manual = list(report.get("pending_manual") or [])
    pending_adjust = list(report.get("pending_adjust") or ADJUST_KEYS)
    can_finalize = bool(report.get("can_finalize_regulatory"))

    last_control = await db.scalar(
        select(RbcmControlRun)
        .where(RbcmControlRun.campaign_id == campaign.id)
        .order_by(RbcmControlRun.created_at.desc(), RbcmControlRun.id.desc())
        .limit(1)
    )
    technical = bool(last_control and last_control.result == "FAILED")
    det_ok = bool(progress.get("det_validated"))
    control_ok = bool(progress.get("last_control_run_id")) and not technical
    calc_ok = calc is not None

    gates = await load_gate_state(db)
    gates_dict = gates.as_dict()
    open_gates = [k for k, v in gates_dict.items() if v]
    decisions_open = len(open_gates)

    checks = [
        _check(
            "INFOS",
            "Informations générales",
            state="ok" if campaign.period_year and campaign.period_month else "fail",
            detail=f"{campaign.period_month:02d}/{campaign.period_year} · v{campaign.campaign_version} · {campaign.bank_code}",
        ),
        _check(
            "DET",
            "BAL DET importée",
            state="ok" if det_ok else "fail",
            detail="BAL DET confirmée." if det_ok else "Aucune BAL DET validée.",
            action=None if det_ok else "Importer et confirmer la BAL DET.",
        ),
        _check(
            "CONTROLES",
            "Contrôles effectués",
            state="fail" if technical else ("ok" if control_ok else "fail"),
            detail=(
                "Échec technique du dernier contrôle."
                if technical
                else (
                    f"Dernier résultat : {progress.get('last_control_result') or '—'}"
                    if control_ok
                    else "Aucun contrôle enregistré."
                )
            ),
            action="Relancer les contrôles." if technical or not control_ok else None,
        ),
        _check(
            "ALIMENTATION",
            "Alimentation depuis la BAL DET",
            state="ok" if calc_ok else "missing",
            detail=(
                f"{report.get('auto_filled') or 0} cellule(s) calculée(s)."
                if calc_ok
                else "Aucun calcul enregistré."
            ),
            action=None if calc_ok else "Alimenter depuis la BAL DET.",
        ),
        _check(
            "PARAMETRES",
            "Informations manuelles",
            state="ok" if not missing_params else "missing",
            detail=(
                "Les huit paramètres mensuels sont renseignés."
                if not missing_params
                else f"{len(missing_params)} paramètre(s) encore à saisir (zéro ≠ complété)."
            ),
            action=None if not missing_params else "Compléter l’étape Informations à compléter.",
        ),
        _check(
            "MANUELLES",
            "Cellules encore vides",
            state="ok" if calc_ok and not pending_manual else ("missing" if calc_ok else "wait"),
            detail=(
                "Toutes les cellules manuelles du moteur sont renseignées."
                if calc_ok and not pending_manual
                else (", ".join(pending_manual) if pending_manual else "En attente d’alimentation.")
            ),
        ),
        _check(
            "AJUSTEMENTS",
            "Cellules à ajuster",
            state="wait" if pending_adjust else "ok",
            detail=(
                ", ".join(pending_adjust)
                if pending_adjust
                else "Aucune cellule AUTO_THEN_ADJUST."
            ),
            action="Lecture seule jusqu’aux décisions D01/D02 — ne pas forcer une valeur.",
        ),
        _check(
            "DECISIONS",
            "Décisions métier",
            state="wait" if open_gates else "ok",
            detail=(
                ", ".join(GATE_LABELS.get(g, g) for g in open_gates)
                if open_gates
                else "Aucune porte ouverte."
            ),
            action="Ne pas inventer de règle. Consulter le détail ci-dessous.",
        ),
        _check(
            "CANEVAS",
            "Canevas de travail",
            state="ok" if work and not work_stale else ("stale" if work else "missing"),
            detail=(
                "Canevas à régénérer : les données ont changé."
                if work_stale
                else (work.filename if work else "Aucun document de travail.")
            ),
            action=(
                "Relancer l’alimentation pour actualiser le canevas."
                if work_stale
                else (None if work else "Générer le canevas depuis Documents.")
            ),
        ),
    ]

    verdict = preparation_verdict(
        det_ok=det_ok,
        control_ok=control_ok,
        calc_ok=calc_ok,
        missing_params=len(missing_params),
        decisions_open=decisions_open,
        technical=technical,
    )
    can_verify = det_ok and control_ok and calc_ok

    decisions = [
        {
            "code": code,
            "label": GATE_LABELS.get(code, code),
            "open": True,
            "needed_for": "conformité du document, pas pour consulter la préparation",
        }
        for code in open_gates
    ]

    preparation = {
        "verdict": verdict,
        "verdict_label": VERDICT_PREP_LABELS[verdict],
        "can_verify": can_verify,
        "checks": checks,
        "missing_params": missing_params,
        "pending_manual": pending_manual,
        "pending_adjust": pending_adjust,
        "decisions": decisions,
        "work_stale": work_stale,
        "params_stale": params_stale,
    }

    verification = await _build_verification(
        db,
        campaign=campaign,
        calc=calc,
        work=work,
        report=report,
        pending_manual=pending_manual,
        pending_adjust=pending_adjust,
        missing_params=missing_params,
        open_gates=open_gates,
        gates_dict=gates_dict,
        can_finalize=can_finalize,
        work_stale=work_stale,
        params_stale=params_stale,
        can_verify=can_verify,
    )
    return {
        "campaign_id": str(campaign.id),
        "preparation": preparation,
        "verification": verification,
        "progress": {
            "last_calc_run_id": str(calc.id) if calc else None,
            "work_document_id": str(work.id) if work else None,
            "work_stale": work_stale,
        },
    }


async def _build_verification(
    db: AsyncSession,
    *,
    campaign: RbcmCampaign,
    calc: RbcmCalculationRun | None,
    work: RbcmDeliverable | None,
    report: dict[str, Any],
    pending_manual: list[str],
    pending_adjust: list[str],
    missing_params: list[dict[str, Any]],
    open_gates: list[str],
    gates_dict: dict[str, bool],
    can_finalize: bool,
    work_stale: bool,
    params_stale: bool,
    can_verify: bool,
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    warnings = dict(work.warnings or {}) if work else {}

    if not can_verify:
        findings.append(
            _finding(
                code="PRECOND",
                title="Préconditions de vérification",
                category="structure",
                severity="blocking",
                status="fail",
                message="La vérification exige une BAL DET confirmée, des contrôles et une alimentation.",
                action="Revenir aux étapes 2 à 4, puis alimenter.",
            )
        )

    sheet_names: list[str] = []
    missing_sheets: list[str] = []
    if work is not None:
        try:
            path = resolve_deliverable_file(work)
            wb = load_workbook(path, read_only=True, data_only=False)
            try:
                sheet_names = list(wb.sheetnames)
            finally:
                wb.close()
        except Exception:
            findings.append(
                _finding(
                    code="FILE",
                    title="Fichier du canevas",
                    category="structure",
                    severity="blocking",
                    status="fail",
                    message="Le fichier de travail est illisible ou son empreinte ne correspond pas.",
                    action="Régénérer le canevas.",
                )
            )
        else:
            missing_sheets = [s for s in OFFICIAL_SHEETS if s not in sheet_names]
            if missing_sheets:
                findings.append(
                    _finding(
                        code="SHEETS",
                        title="Feuilles officielles",
                        category="structure",
                        severity="blocking",
                        status="fail",
                        message="Feuilles absentes : " + ", ".join(missing_sheets),
                        action="Régénérer le canevas officiel — ne pas utiliser l’export technique.",
                    )
                )
            else:
                findings.append(
                    _finding(
                        code="SHEETS",
                        title="Feuilles officielles",
                        category="structure",
                        severity="info",
                        status="ok",
                        message="Les huit feuilles du canevas BCM sont présentes.",
                    )
                )
            extra = [
                s
                for s in sheet_names
                if s not in OFFICIAL_SHEETS and s not in ("AVERTISSEMENT", "À LIRE")
            ]
            if extra:
                findings.append(
                    _finding(
                        code="SHEETS_EXTRA",
                        title="Feuilles additionnelles",
                        category="structure",
                        severity="info",
                        status="ok",
                        message="Feuilles hors canevas métier : " + ", ".join(extra[:8]),
                    )
                )
            findings.append(
                _finding(
                    code="FORMULAS",
                    title="Formules du canevas",
                    category="structure",
                    severity="info",
                    status="ok",
                    message="La génération documentaire conserve les formules structurelles et les totaux Excel.",
                )
            )
    else:
        findings.append(
            _finding(
                code="WORK",
                title="Canevas de travail",
                category="structure",
                severity="warning",
                status="fail",
                message="Aucun document de travail à vérifier.",
                action="Générer le canevas après l’alimentation.",
            )
        )

    parse_err = list(warnings.get("graph_parse_errors") or [])
    if parse_err:
        findings.append(
            _finding(
                code="PARSE",
                title="Formules non interprétées",
                category="structure",
                severity="warning",
                status="fail",
                message=f"{len(parse_err)} formule(s) du canevas n’ont pas pu être lues.",
                action="Signaler à l’expertise — ne pas réécrire la formule dans Excel.",
            )
        )

    if work_stale or params_stale:
        findings.append(
            _finding(
                code="STALE",
                title="Canevas non aligné",
                category="donnees",
                severity="warning",
                status="fail",
                message="Les données ont changé depuis la dernière génération. La vérification porte sur une version antérieure.",
                action="Relancer l’alimentation pour actualiser le document.",
            )
        )

    if calc is not None:
        cells = list(
            (
                await db.scalars(
                    select(RbcmCellResult).where(RbcmCellResult.run_id == calc.id)
                )
            ).all()
        )
        auto_n = sum(
            1
            for c in cells
            if c.value_status == "AUTOMATIQUE" and c.retained_value is not None
        )
        findings.append(
            _finding(
                code="DET_CELLS",
                title="Données issues de la BAL DET",
                category="donnees",
                severity="info",
                status="ok",
                message=f"{auto_n} cellule(s) calculée(s) automatiquement (ETAT A).",
                sheet="ETAT A",
            )
        )
        findings.append(
            _finding(
                code="REPRISES",
                title="Reprises ETAT A → B / C",
                category="donnees",
                severity="info",
                status="pending" if gates_dict.get("D09") else "ok",
                message=(
                    "Les copies Excel A→B/C sont conservées. ETAT B/C restent incomplets tant que D09 n’est pas tranchée."
                ),
                sheet="ETAT B / ETAT C",
                action="Ne pas forcer 70/30 ni une source absente.",
            )
        )

    fillable_pending = [p["code"] for p in missing_params]
    if fillable_pending or pending_manual:
        cells_txt = ", ".join(pending_manual or [p.get("cell_hint") or p["code"] for p in missing_params])
        findings.append(
            _finding(
                code="MANUAL",
                title="Valeurs manuelles",
                category="donnees",
                severity="warning",
                status="fail",
                message=f"Encore à renseigner : {cells_txt}.",
                action="Saisir à l’étape 4 puis relancer l’alimentation.",
            )
        )
    elif calc is not None:
        findings.append(
            _finding(
                code="MANUAL",
                title="Valeurs manuelles",
                category="donnees",
                severity="info",
                status="ok",
                message="Les cellules manuelles du moteur liées aux paramètres sont renseignées. A:114:D reste D01.",
                cell="A:114:D",
                sheet="ETAT A",
            )
        )

    if pending_adjust:
        findings.append(
            _finding(
                code="ADJUST",
                title="Ajustements",
                category="donnees",
                severity="info",
                status="pending",
                message="Cellules AUTO_THEN_ADJUST : " + ", ".join(pending_adjust),
                sheet="ETAT A",
                action="Aucun ajustement Excel n’est appliqué tant que D01/D02 ne sont pas validés.",
            )
        )

    ecart = report.get("ecart_amount")
    if calc is not None:
        findings.append(
            _finding(
                code="ECART",
                title="Écart classes 1–8",
                category="anomalie",
                severity="warning",
                status="fail" if ecart and str(ecart) not in ("0", "0.00") else "ok",
                message=(
                    f"Écart constaté {ecart} — présenté en contrôle, jamais forcé dans ETAT A (D02)."
                    if ecart and str(ecart) not in ("0", "0.00")
                    else "Pas d’écart classes 1–8 sur la BAL DET."
                ),
                sheet="ETAT A",
                action="Laisser ECART inactif jusqu’à l’arbitrage D02.",
            )
        )

    findings.append(
        _finding(
            code="ETAT_C_208",
            title="Anomalie ETAT C 208 / 209",
            category="anomalie",
            severity="warning",
            status="fail",
            message="Le canevas officiel recopie 208 depuis 209 et le TOTAL 220 additionne les deux (double comptage).",
            sheet="ETAT C",
            cell="C:208 / C:209 / C:220",
            action="Conserver le canevas — ne pas corriger la formule sans décision métier.",
        )
    )
    findings.append(
        _finding(
            code="RCR_INFO",
            title="Références RCR INFO C7 / C8",
            category="anomalie",
            severity="info",
            status="ok",
            message="À la génération du canevas de travail, D14/D15 pointent vers informations à fournir!C7 et C8 (montants), pas B7/B8.",
            sheet="RATIO COUVERTURE DE RISQUE",
            cell="D14 / D15",
        )
    )

    for code in open_gates:
        findings.append(
            _finding(
                code=f"GATE_{code}",
                title=GATE_LABELS.get(code, code),
                category="anomalie",
                severity="warning",
                status="pending",
                message=f"Porte {code} ouverte — aucune règle de calcul n’a été inventée.",
                action="Attendre la décision métier. La vérification ne peut pas être « conforme ».",
            )
        )

    blocking = any(f["severity"] == "blocking" and f["status"] == "fail" for f in findings)
    to_complete = bool(fillable_pending or pending_manual or work_stale or params_stale)
    decisions = bool(open_gates) or not can_finalize
    verdict = document_verdict(
        blocking=blocking,
        to_complete=to_complete,
        decisions=decisions,
        can_finalize=can_finalize,
    )

    return {
        "verdict": verdict,
        "verdict_label": VERDICT_DOC_LABELS[verdict],
        "can_finalize_regulatory": False,
        "stale": work_stale or params_stale,
        "work_id": str(work.id) if work else None,
        "work_filename": work.filename if work else None,
        "calc_run_id": str(calc.id) if calc else None,
        "sheets": sheet_names,
        "missing_sheets": missing_sheets,
        "findings": findings,
        "counts": {
            "blocking": sum(1 for f in findings if f["severity"] == "blocking" and f["status"] == "fail"),
            "warning": sum(1 for f in findings if f["severity"] == "warning"),
            "info": sum(1 for f in findings if f["severity"] == "info"),
            "pending": sum(1 for f in findings if f["status"] == "pending"),
        },
    }
