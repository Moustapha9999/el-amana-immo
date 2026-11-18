"""Feuille explicative « À LIRE » — documentaire, hors canevas officiel.

Ne calcule aucune règle comptable. Ne modifie aucune feuille officielle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.reporting_bcm_sm import (
    RbcmCalculationRun,
    RbcmCampaign,
    RbcmCellResult,
    RbcmControlRun,
    RbcmImport,
    RbcmReconcileIssue,
    RbcmTemplate,
)
from app.services.reporting_bcm_sm.control_service import GAP_STATES, latest_run
from app.services.reporting_bcm_sm.engine.evaluate import STATUS_MISSING
from app.services.reporting_bcm_sm.engine.rules_catalog import (
    ADJUST_KEYS,
    MANUAL_KEYS,
    RULES_BY_KEY,
)
from app.services.reporting_bcm_sm.parameter_service import PARAMETER_LABELS
from app.services.reporting_export import format_montant

# Libellés des portes — recopie locale pour éviter un import circulaire avec review_service.
_GATE_LABELS = {
    "D01": "Correspondances (mapping A_VALIDER)",
    "D02": "ECART classes 1–8",
    "D06": "Rubriques sans correspondance",
    "D09": "Crédits / dépôts (ETAT B/C)",
    "D15": "TOTDEB / TOTCRE",
    "D16_D17": "Résidents / non-résidents",
    "D22": "Comptes multi-cellules",
}

COVER_SHEET_NAME = "À LIRE"
EXPLANATORY_SHEETS = (COVER_SHEET_NAME, "AVERTISSEMENT")
DOCUMENT_STATUS = "DOCUMENT DE TRAVAIL — NON VALIDÉ"
NONE_MANUAL_MSG = (
    "Aucune cellule nécessitant une saisie manuelle n'a été détectée lors de cette génération."
)
NONE_ISSUE_MSG = (
    "Aucun problème particulier n'a été détecté lors de l'import et des contrôles exécutés."
)

_SHEET_FROM_PREFIX = {
    "A": "ETAT A",
    "B": "ETAT B",
    "C": "ETAT C",
    "INFO": "informations à fournir",
    "RCR": "RATIO COUVERTURE DE RISQUE",
    "FPN": "CALCUL FPN",
    "RL": "RATIO DE LIQUIDITE",
    "RFP": "RATIO FP ET AI",
}

_IMPORT_STATUS_LABELS = {
    "UPLOADED": "Déposé",
    "ANALYZED": "Analysé",
    "VALIDATED": "Confirmé",
    "REJECTED": "Rejeté",
    "SUPERSEDED": "Remplacé",
}

_CONTROL_RESULT_LABELS = {
    "OK": "Contrôles aboutis",
    "WARNINGS": "Avertissements",
    "INCOMPLETE": "Informations incomplètes",
    "DECISIONS_PENDING": "Décisions métier en attente",
    "BLOCKING": "Anomalie bloquante",
    "FAILED": "Échec technique",
}

_MONTHS_FR = (
    "",
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)

_NAVY = "0B3A5B"
_NAVY2 = "1A5278"
_WHITE = "FFFFFF"
_BG = "F7F9FC"
_ALT = "EEF3F8"
_FILL_OK = "E8F5E9"
_FILL_WAIT = "FFF8E1"
_FILL_WARN = "FFF4E5"
_FILL_BLOCK = "FCE8E6"
_FILL_DEC = "E8F1F8"
_FILL_ECART = "FFF8E1"
_FILL_BANNER = "FDECEA"
_THIN = Border(
    left=Side(style="thin", color="D0D7DE"),
    right=Side(style="thin", color="D0D7DE"),
    top=Side(style="thin", color="D0D7DE"),
    bottom=Side(style="thin", color="D0D7DE"),
)
_ALIGN = Alignment(vertical="center", wrap_text=True)
_ALIGN_L = Alignment(vertical="center", wrap_text=True, horizontal="left")


@dataclass
class ManualCellRow:
    sheet: str
    excel_address: str
    label: str
    nature: str
    current_display: str
    action: str
    filled: bool
    pending: bool


@dataclass
class IssueRow:
    nature: str
    location: str
    explanation: str
    action: str
    kind: str  # blocking | warning | ecart | decision


@dataclass
class CoverPayload:
    period_label: str
    generated_at: str
    campaign_ref: str
    campaign_id: str
    document_status: str
    canvas_ref: str
    det_filename: str | None
    det_period: str | None
    det_imported_at: str | None
    det_row_count: str | None
    det_compte_count: str | None
    det_ncg_count: str | None
    det_analysis: str | None
    det_controls: str | None
    det_import_id: str | None
    calc_run_id: str | None
    manual_rows: list[ManualCellRow] = field(default_factory=list)
    issue_rows: list[IssueRow] = field(default_factory=list)
    decision_rows: list[IssueRow] = field(default_factory=list)


def parse_engine_cell_ref(key: str) -> tuple[str | None, str | None]:
    """A:114:D → (ETAT A, D114). INFO:C9 → (informations à fournir, C9)."""
    if not key or ":" not in key:
        return None, None
    parts = key.split(":")
    if len(parts) == 3:
        prefix, row, col = parts
        sheet = _SHEET_FROM_PREFIX.get(prefix)
        if sheet and row.isdigit() and col:
            return sheet, f"{col}{row}"
        return None, None
    if len(parts) == 2:
        prefix, addr = parts
        sheet = _SHEET_FROM_PREFIX.get(prefix)
        if sheet and addr:
            return sheet, addr
    return None, None


def _fmt_dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")


def _fmt_amount(value: Decimal | int | float | str | None) -> str:
    if value is None or value == "":
        return "—"
    return format_montant(value)


def _row_label_from_wb(wb, sheet: str, excel_address: str) -> str | None:
    if sheet not in getattr(wb, "sheetnames", []):
        return None
    digits = "".join(ch for ch in excel_address if ch.isdigit())
    if not digits:
        return None
    ws = wb[sheet]
    for col in ("B", "A"):
        raw = ws[f"{col}{digits}"].value
        if raw is None:
            continue
        text = str(raw).strip()
        if text and not text.startswith("="):
            return text[:180]
    return None


def _looks_like_code(text: str | None) -> bool:
    if not text:
        return True
    t = text.strip()
    compact = t.replace(".", "").replace(" ", "")
    return compact.isdigit() and len(compact) <= 6


def _cell_label(key: str, *, wb=None, bcm_by_key: dict[str, str] | None = None) -> str:
    rule = RULES_BY_KEY.get(key)
    if rule and rule.param_code:
        named = PARAMETER_LABELS.get(rule.param_code)
        if named:
            return named
    bcm = (bcm_by_key or {}).get(key)
    sheet, addr = parse_engine_cell_ref(key)
    row_lib = _row_label_from_wb(wb, sheet, addr) if wb is not None and sheet and addr else None
    if row_lib and not _looks_like_code(row_lib):
        if bcm and str(bcm) not in row_lib:
            return f"{bcm} — {row_lib}"
        return row_lib
    if bcm and not _looks_like_code(str(bcm)):
        return str(bcm)
    if addr:
        return f"Rubrique {addr}"
    return key


def _manual_rows_from_run(
    *,
    cell_by_ref: dict[str, RbcmCellResult],
    pending_manual: list[str],
    wb=None,
    bcm_by_key: dict[str, str] | None = None,
) -> list[ManualCellRow]:
    pending_set = set(pending_manual)
    rows: list[ManualCellRow] = []
    for key in MANUAL_KEYS:
        sheet, addr = parse_engine_cell_ref(key)
        result = cell_by_ref.get(key)
        retained = None if result is None else result.retained_value
        status = None if result is None else result.value_status
        missing = key in pending_set or retained is None or status == STATUS_MISSING
        if missing:
            current = "—"
            action = "Compléter la valeur"
            filled = False
            pending = True
        else:
            current = _fmt_amount(retained)
            action = "Valeur déjà saisie dans BEA DIGITAL — conservée à la génération"
            filled = True
            pending = False
        rows.append(
            ManualCellRow(
                sheet=sheet or "—",
                excel_address=addr or key,
                label=_cell_label(key, wb=wb, bcm_by_key=bcm_by_key),
                nature="Saisie manuelle",
                current_display=current,
                action=action,
                filled=filled,
                pending=pending,
            )
        )
    for key in ADJUST_KEYS:
        sheet, addr = parse_engine_cell_ref(key)
        result = cell_by_ref.get(key)
        retained = None if result is None else result.retained_value
        calculated = None if result is None else result.calculated_value
        shown = retained if retained is not None else calculated
        if shown is None:
            current = "—"
            action = "Vérifier et ajuster"
            filled = False
        else:
            current = _fmt_amount(shown)
            action = "Vérifier et ajuster — valeur calculée conservée, non forcée"
            filled = True
        rows.append(
            ManualCellRow(
                sheet=sheet or "—",
                excel_address=addr or key,
                label=_cell_label(key, wb=wb, bcm_by_key=bcm_by_key),
                nature="Ajustement",
                current_display=current,
                action=action,
                filled=filled,
                pending=True,
            )
        )
    return rows


def classify_issue(
    *,
    severity: str | None,
    resolution: str | None,
    code: str | None,
    category: str | None,
) -> str:
    sev = (severity or "").upper()
    res = (resolution or "").upper()
    code_u = (code or "").upper()
    cat = (category or "").upper()
    if res == "PENDING_DECISION" or cat == "D":
        return "Décision métier encore attendue"
    if code_u in {"DET_CLASSES_1_8", "ECART", "ECART_DET"} or code_u.startswith("ECART"):
        return "Écart constaté à examiner"
    if sev == "BLOCKING" or res == "STILL_BLOCKING":
        return "Anomalie bloquante"
    return "Avertissement"


def _kind_from_nature(nature: str) -> str:
    if nature == "Anomalie bloquante":
        return "blocking"
    if nature == "Écart constaté à examiner":
        return "ecart"
    if nature == "Décision métier encore attendue":
        return "decision"
    return "warning"


def _issue_from_control(
    issue: RbcmReconcileIssue,
) -> IssueRow | None:
    if issue.resolved or issue.resolution_state not in GAP_STATES:
        return None
    if (issue.severity or "").upper() == "INFO" and issue.resolution_state == "OK":
        return None
    nature = classify_issue(
        severity=issue.severity,
        resolution=issue.resolution_state,
        code=issue.code,
        category=issue.category,
    )
    details = issue.details or {}
    loc_parts = []
    if details.get("sheet"):
        loc_parts.append(str(details["sheet"]))
    if details.get("cell"):
        loc_parts.append(str(details["cell"]))
    if issue.ncg:
        loc_parts.append(f"NCG {issue.ncg}")
    explanation = issue.message or issue.title or issue.code
    action = details.get("recommended_action") or details.get("consequence") or "—"
    return IssueRow(
        nature=nature,
        location=" · ".join(loc_parts) if loc_parts else "—",
        explanation=str(explanation),
        action=str(action),
        kind=_kind_from_nature(nature),
    )


def _ecart_row(report: dict | None) -> IssueRow | None:
    if not report:
        return None
    raw = report.get("ecart_amount")
    if raw is None or raw == "" or str(raw) in ("0", "0.0", "0.00"):
        return None
    try:
        if Decimal(str(raw)) == 0:
            return None
    except Exception:
        pass
    return IssueRow(
        nature="Écart constaté à examiner",
        location="ETAT A",
        explanation=(
            f"Écart classes 1 à 8 constaté : {_fmt_amount(raw)}. "
            "Présenté en contrôle, jamais forcé dans le canevas."
        ),
        action="Laisser ECART inactif jusqu’à l’arbitrage D02.",
        kind="ecart",
    )


def _det_analysis_text(det: RbcmImport | None) -> str | None:
    if det is None:
        return None
    report = det.control_report or {}
    blocking = [str(x) for x in (report.get("blocking_reasons") or []) if x]
    error_count = report.get("error_count")
    ready = report.get("ready_to_confirm")
    status = _IMPORT_STATUS_LABELS.get(det.status, det.status)
    parts = [f"Statut de l’import : {status}"]
    if ready is True:
        parts.append("Analyse aboutie — import confirmable.")
    elif ready is False:
        parts.append("Analyse incomplète ou non confirmable.")
    if blocking:
        parts.append("Motifs bloquants : " + " ; ".join(blocking[:5]))
    elif error_count not in (None, 0, "0"):
        parts.append(f"Signalements d’analyse : {error_count}.")
    return " ".join(parts)


def _det_counts(det: RbcmImport | None) -> tuple[str | None, str | None, str | None]:
    if det is None:
        return None, None, None
    report = det.control_report or {}
    rows = det.row_count if det.row_count is not None else report.get("row_count")
    ncg = report.get("confirmed_ncg_count")
    if ncg is None:
        ncg = report.get("ncg_count")
    comptes = report.get("compte_count")
    return (
        None if rows is None else str(rows),
        None if comptes is None else str(comptes),
        None if ncg is None else str(ncg),
    )


def build_cover_payload(
    *,
    campaign: RbcmCampaign,
    template: RbcmTemplate | None,
    run: RbcmCalculationRun | None,
    det: RbcmImport | None,
    control_run: RbcmControlRun | None,
    issues: list[RbcmReconcileIssue],
    gates_open: dict[str, bool],
    cell_results: list[RbcmCellResult],
    generated_at: datetime,
    wb=None,
    bcm_by_key: dict[str, str] | None = None,
) -> CoverPayload:
    month = campaign.period_month
    year = campaign.period_year
    month_name = _MONTHS_FR[month] if 1 <= month <= 12 else str(month)
    period_label = f"{month_name} {year} ({month:02d}/{year})"
    campaign_ref = f"SM-{month:02d}-{year} v{campaign.campaign_version}"
    canvas_ref = "—"
    if template is not None:
        bits = [f"{template.template_code} v{template.version}"]
        if template.filename:
            bits.append(template.filename)
        if template.sha256:
            bits.append(f"SHA {template.sha256[:16]}")
        canvas_ref = " · ".join(bits)

    report = (run.report if run is not None else None) or {}
    pending_manual = list(report.get("pending_manual") or [])
    cell_by_ref = {r.cell_ref: r for r in cell_results}
    manual_rows = _manual_rows_from_run(
        cell_by_ref=cell_by_ref,
        pending_manual=pending_manual,
        wb=wb,
        bcm_by_key=bcm_by_key,
    )

    det_period = None
    if det is not None and det.period_year_detected and det.period_month_detected:
        det_period = f"{det.period_month_detected:02d}/{det.period_year_detected}"
    row_count, compte_count, ncg_count = _det_counts(det)

    ctrl_label = None
    if control_run is not None:
        label = _CONTROL_RESULT_LABELS.get(control_run.result, control_run.result)
        when = _fmt_dt(control_run.created_at)
        ctrl_label = label if when is None else f"{label} ({when})"
        if control_run.id:
            ctrl_label += f" — run {control_run.id}"

    issue_rows: list[IssueRow] = []
    ecart = _ecart_row(report)
    if ecart is not None:
        issue_rows.append(ecart)

    seen_ecart = ecart is not None
    decision_from_issues: list[IssueRow] = []
    collapsed: dict[tuple[str, str, str], IssueRow] = {}
    covered_gates: set[str] = set()
    for issue in issues:
        row = _issue_from_control(issue)
        if row is None:
            continue
        code_u = (issue.code or "").upper()
        if seen_ecart and (code_u in {"DET_CLASSES_1_8", "ECART", "ECART_DET"} or code_u.startswith("ECART")):
            continue
        if code_u in {"MANUAL", "MANUELLES", "ADJUST", "AJUSTEMENTS"}:
            continue
        key = (row.nature, row.explanation, row.kind)
        prev = collapsed.get(key)
        if prev is not None:
            marker = " (plusieurs occurrences)"
            if marker not in (prev.explanation or ""):
                prev.explanation = f"{prev.explanation}{marker}"
            continue
        collapsed[key] = row
        if row.kind == "decision":
            decision_from_issues.append(row)
            for gate in (gates_open or {}):
                if code_u.startswith(gate.replace("_", "")) or code_u.startswith(gate):
                    covered_gates.add(gate)
            continue
        issue_rows.append(row)

    if det is not None:
        report_imp = det.control_report or {}
        for err in (report_imp.get("errors") or [])[:8]:
            if isinstance(err, dict):
                msg = err.get("error") or err.get("message") or str(err)
                line = err.get("line")
                loc = f"Ligne {line}" if line else "BAL DET"
            else:
                msg = str(err)
                loc = "BAL DET"
            issue_rows.append(
                IssueRow(
                    nature="Avertissement",
                    location=str(loc),
                    explanation=str(msg),
                    action="Examiner la ligne concernée dans l’import, sans forcer une correction.",
                    kind="warning",
                )
            )
        extra_err = int(report_imp.get("error_count") or 0) - min(8, len(report_imp.get("errors") or []))
        if extra_err > 0:
            issue_rows.append(
                IssueRow(
                    nature="Avertissement",
                    location="BAL DET",
                    explanation=f"{extra_err} autre(s) signalement(s) d’analyse non listés ici.",
                    action="Consulter le rapport d’import dans BEA DIGITAL.",
                    kind="warning",
                )
            )
        for reason in report_imp.get("blocking_reasons") or []:
            issue_rows.append(
                IssueRow(
                    nature="Anomalie bloquante",
                    location="BAL DET",
                    explanation=str(reason),
                    action="Corriger l’import avant de s’appuyer sur ce document.",
                    kind="blocking",
                )
            )

    decision_rows: list[IssueRow] = list(decision_from_issues)
    for code, opened in (gates_open or {}).items():
        if not opened or code in covered_gates:
            continue
        decision_rows.append(
            IssueRow(
                nature="Décision métier encore attendue",
                location="—",
                explanation=_GATE_LABELS.get(code, code),
                action=f"Porte {code} ouverte — non tranchée par cette génération.",
                kind="decision",
            )
        )

    return CoverPayload(
        period_label=period_label,
        generated_at=_fmt_dt(generated_at) or "—",
        campaign_ref=campaign_ref,
        campaign_id=str(campaign.id),
        document_status=DOCUMENT_STATUS,
        canvas_ref=canvas_ref,
        det_filename=None if det is None else det.filename,
        det_period=det_period,
        det_imported_at=_fmt_dt(None if det is None else (det.validated_at or det.created_at)),
        det_row_count=row_count,
        det_compte_count=compte_count,
        det_ncg_count=ncg_count,
        det_analysis=_det_analysis_text(det),
        det_controls=ctrl_label,
        det_import_id=None if det is None else str(det.id),
        calc_run_id=None if run is None else str(run.id),
        manual_rows=manual_rows,
        issue_rows=issue_rows,
        decision_rows=decision_rows,
    )


def _fill(hex_color: str) -> PatternFill:
    return PatternFill("solid", fgColor=hex_color)


def _font(*, size=11, bold=False, color=_NAVY, italic=False) -> Font:
    return Font(name="Calibri", size=size, bold=bold, color=color, italic=italic)


def _merge_row(ws, row: int, value: str, *, fill: str, font: Font, height: int = 22) -> None:
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
    cell = ws.cell(row=row, column=1, value=value)
    cell.fill = _fill(fill)
    cell.font = font
    cell.alignment = Alignment(vertical="center", wrap_text=True, indent=1)
    for col in range(1, 7):
        ws.cell(row=row, column=col).fill = _fill(fill)
        ws.cell(row=row, column=col).border = _THIN
    ws.row_dimensions[row].height = height


def _kv(ws, row: int, label: str, value: str | None, *, alt: bool = False) -> int:
    bg = _ALT if alt else _BG
    ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=6)
    c1 = ws.cell(row=row, column=1, value=label)
    c1.font = _font(bold=True, size=11, color=_NAVY)
    c1.fill = _fill(bg)
    c1.alignment = _ALIGN_L
    c1.border = _THIN
    text = value if value not in (None, "") else "—"
    c2 = ws.cell(row=row, column=2, value=text)
    c2.font = _font(size=11, color="1F2A37")
    c2.alignment = _ALIGN_L
    c2.fill = _fill(bg)
    c2.border = _THIN
    for col in range(3, 7):
        ws.cell(row=row, column=col).fill = _fill(bg)
        ws.cell(row=row, column=col).border = _THIN
    ws.row_dimensions[row].height = 22 if len(str(text)) < 90 else 36
    return row + 1


def _headers(ws, row: int, titles: list[str]) -> int:
    for i, title in enumerate(titles, start=1):
        cell = ws.cell(row=row, column=i, value=title)
        cell.fill = _fill(_NAVY)
        cell.font = _font(bold=True, size=10, color=_WHITE)
        cell.alignment = Alignment(vertical="center", wrap_text=True, horizontal="center")
        cell.border = _THIN
    ws.row_dimensions[row].height = 22
    return row + 1


def _note(ws, row: int, text: str, *, fill: str = _BG) -> int:
    _merge_row(ws, row, text, fill=fill, font=_font(size=11, italic=True, color="334155"), height=32)
    return row + 1


def write_a_lire_sheet(wb, payload: CoverPayload) -> None:
    if COVER_SHEET_NAME in wb.sheetnames:
        del wb[COVER_SHEET_NAME]
    ws = wb.create_sheet(COVER_SHEET_NAME, 0)
    ws.sheet_properties.tabColor = _NAVY
    ws.sheet_view.showGridLines = False
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_margins.left = 0.5
    ws.page_margins.right = 0.5
    ws.page_margins.top = 0.6
    ws.page_margins.bottom = 0.6
    ws.print_title_rows = "1:4"
    ws.freeze_panes = "A5"

    widths = {"A": 28, "B": 16, "C": 42, "D": 18, "E": 22, "F": 48}
    for col, width in widths.items():
        ws.column_dimensions[col].width = width

    r = 1
    _merge_row(
        ws,
        r,
        "Reporting BCM — Situation Mensuelle",
        fill=_NAVY,
        font=_font(size=16, bold=True, color=_WHITE),
        height=28,
    )
    r = 2
    _merge_row(
        ws,
        r,
        "À LIRE — notice de lecture du canevas de travail",
        fill=_NAVY2,
        font=_font(size=13, bold=True, color=_WHITE),
        height=24,
    )
    r = 3
    _merge_row(
        ws,
        r,
        payload.document_status,
        fill=_FILL_BANNER,
        font=_font(size=12, bold=True, color="9B1C1C"),
        height=24,
    )
    r = 4
    _merge_row(
        ws,
        r,
        (
            "Feuille explicative générée automatiquement. Elle n’altère pas les feuilles officielles, "
            "ni les formules, ni les mappings. Ce fichier n’est pas une validation réglementaire."
        ),
        fill=_BG,
        font=_font(size=10, italic=True, color="475569"),
        height=28,
    )
    r = 5

    r += 1
    _merge_row(
        ws,
        r,
        "A. Informations générales sur la Situation Mensuelle",
        fill=_NAVY,
        font=_font(size=12, bold=True, color=_WHITE),
        height=24,
    )
    r += 1
    r = _kv(ws, r, "Mois / année", payload.period_label, alt=True)
    r = _kv(ws, r, "Date de génération", payload.generated_at)
    r = _kv(ws, r, "Référence de campagne", payload.campaign_ref, alt=True)
    r = _kv(ws, r, "Identifiant campagne", payload.campaign_id)
    r = _kv(ws, r, "Statut du document", payload.document_status, alt=True)
    r = _kv(ws, r, "Canevas", payload.canvas_ref)
    if payload.calc_run_id:
        r = _kv(ws, r, "Exécution moteur", payload.calc_run_id, alt=True)

    r += 1
    _merge_row(
        ws,
        r,
        "B. Informations sur la BAL DET utilisée",
        fill=_NAVY,
        font=_font(size=12, bold=True, color=_WHITE),
        height=24,
    )
    r += 1
    if payload.det_filename is None:
        r = _note(
            ws,
            r,
            "Aucune BAL DET validée n’était liée à cette SM au moment de la génération. "
            "Les feuilles officielles n’ont pas été alimentées depuis une balance confirmée.",
        )
    else:
        r = _kv(ws, r, "Fichier importé", payload.det_filename, alt=True)
        r = _kv(ws, r, "Période de la balance", payload.det_period)
        r = _kv(ws, r, "Date d’import / confirmation", payload.det_imported_at, alt=True)
        r = _kv(ws, r, "Lignes importées", payload.det_row_count)
        r = _kv(ws, r, "Comptes détectés", payload.det_compte_count, alt=True)
        r = _kv(ws, r, "NCG détectés", payload.det_ncg_count)
        r = _kv(ws, r, "Résultat de l’analyse", payload.det_analysis, alt=True)
        r = _kv(ws, r, "Résultat des contrôles", payload.det_controls)
        r = _kv(ws, r, "Référence d’import", payload.det_import_id, alt=True)

    r += 1
    _merge_row(
        ws,
        r,
        "C. Cellules nécessitant une saisie manuelle ou un ajustement",
        fill=_NAVY,
        font=_font(size=12, bold=True, color=_WHITE),
        height=24,
    )
    r += 1
    pending = [row for row in payload.manual_rows if row.pending and not row.filled]
    if not pending and not any(row.nature == "Ajustement" for row in payload.manual_rows):
        r = _note(ws, r, NONE_MANUAL_MSG, fill=_FILL_OK)
    elif not any(row.nature == "Saisie manuelle" and row.pending for row in payload.manual_rows):
        r = _note(ws, r, NONE_MANUAL_MSG, fill=_FILL_OK)

    r = _headers(ws, r, ["Feuille", "Cellule", "Rubrique", "Nature", "Valeur actuelle", "Action attendue"])
    if not payload.manual_rows:
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=6)
        cell = ws.cell(row=r, column=1, value=NONE_MANUAL_MSG)
        cell.font = _font(italic=True, color="334155")
        cell.alignment = _ALIGN_L
        r += 1
    else:
        for i, row in enumerate(payload.manual_rows):
            bg = _FILL_OK if row.filled and not (row.nature == "Ajustement") else (
                _FILL_WAIT if row.pending else _ALT if i % 2 else _BG
            )
            values = [
                row.sheet,
                row.excel_address,
                row.label,
                row.nature,
                row.current_display,
                row.action,
            ]
            for col, val in enumerate(values, start=1):
                cell = ws.cell(row=r, column=col, value=val)
                cell.fill = _fill(bg)
                cell.font = _font(size=10, color="1F2A37")
                cell.alignment = _ALIGN
                cell.border = _THIN
            ws.row_dimensions[r].height = 28
            r += 1

    r += 1
    _merge_row(
        ws,
        r,
        "D. Écarts, anomalies et avertissements",
        fill=_NAVY,
        font=_font(size=12, bold=True, color=_WHITE),
        height=24,
    )
    r += 1
    if not payload.issue_rows:
        r = _note(ws, r, NONE_ISSUE_MSG, fill=_FILL_OK)
    else:
        r = _headers(
            ws,
            r,
            ["Nature", "Feuille / cellule", "Explication", "", "Action attendue", ""],
        )
        ws.merge_cells(start_row=r - 1, start_column=3, end_row=r - 1, end_column=4)
        ws.merge_cells(start_row=r - 1, start_column=5, end_row=r - 1, end_column=6)
        for row in payload.issue_rows:
            bg = {
                "blocking": _FILL_BLOCK,
                "warning": _FILL_WARN,
                "ecart": _FILL_ECART,
                "decision": _FILL_DEC,
            }.get(row.kind, _FILL_WARN)
            ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=4)
            ws.merge_cells(start_row=r, start_column=5, end_row=r, end_column=6)
            for col in range(1, 7):
                cell = ws.cell(row=r, column=col)
                cell.fill = _fill(bg)
                cell.border = _THIN
                cell.alignment = _ALIGN
                cell.font = _font(size=10, color="1F2A37")
            ws.cell(row=r, column=1).value = row.nature
            ws.cell(row=r, column=2).value = row.location
            ws.cell(row=r, column=3).value = row.explanation
            ws.cell(row=r, column=5).value = row.action
            ws.row_dimensions[r].height = 32 if len(row.explanation) > 80 else 24
            r += 1

    if payload.decision_rows:
        r += 1
        _merge_row(
            ws,
            r,
            "Décisions métier encore ouvertes (non tranchées par cette génération)",
            fill=_NAVY2,
            font=_font(size=11, bold=True, color=_WHITE),
            height=22,
        )
        r += 1
        r = _headers(ws, r, ["Nature", "Porte / sujet", "Explication", "", "Action attendue", ""])
        ws.merge_cells(start_row=r - 1, start_column=3, end_row=r - 1, end_column=4)
        ws.merge_cells(start_row=r - 1, start_column=5, end_row=r - 1, end_column=6)
        for row in payload.decision_rows:
            ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=4)
            ws.merge_cells(start_row=r, start_column=5, end_row=r, end_column=6)
            for col in range(1, 7):
                cell = ws.cell(row=r, column=col)
                cell.fill = _fill(_FILL_DEC)
                cell.border = _THIN
                cell.alignment = _ALIGN
                cell.font = _font(size=10, color="1F2A37")
            ws.cell(row=r, column=1).value = row.nature
            ws.cell(row=r, column=2).value = row.location
            ws.cell(row=r, column=3).value = row.explanation
            ws.cell(row=r, column=5).value = row.action
            ws.row_dimensions[r].height = 24
            r += 1

    r += 1
    _merge_row(
        ws,
        r,
        (
            "Précautions : ne pas traiter un 0 Excel comme un zéro métier ; ne pas forcer D01/D02 ; "
            "conserver les formules des feuilles officielles ; n’utiliser ce fichier que comme document de travail."
        ),
        fill=_BG,
        font=_font(size=10, italic=True, color="475569"),
        height=32,
    )


async def attach_a_lire(
    wb,
    db: AsyncSession,
    *,
    campaign: RbcmCampaign,
    template: RbcmTemplate | None,
    run: RbcmCalculationRun | None,
    gates_open: dict[str, bool],
    cell_results: list[RbcmCellResult],
    bcm_by_key: dict[str, str] | None = None,
    generated_at: datetime | None = None,
) -> None:
    det = await db.scalar(
        select(RbcmImport).where(
            RbcmImport.campaign_id == campaign.id,
            RbcmImport.file_type == "BAL_DET",
            RbcmImport.status == "VALIDATED",
        )
    )
    control_run = await latest_run(db, campaign.id)
    issues: list[RbcmReconcileIssue] = []
    if control_run is not None:
        issues = list(
            (
                await db.scalars(
                    select(RbcmReconcileIssue).where(RbcmReconcileIssue.run_id == control_run.id)
                )
            ).all()
        )
    payload = build_cover_payload(
        campaign=campaign,
        template=template,
        run=run,
        det=det,
        control_run=control_run,
        issues=issues,
        gates_open=gates_open,
        cell_results=cell_results,
        generated_at=generated_at or datetime.now(timezone.utc),
        wb=wb,
        bcm_by_key=bcm_by_key,
    )
    write_a_lire_sheet(wb, payload    )
