"""Génération WORK documentaire — phase C. N'appelle pas runner.py ni excel_export."""

from __future__ import annotations

import uuid
from calendar import monthrange
from datetime import date
from pathlib import Path

from openpyxl import load_workbook
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import User
from app.models.reporting_bcm_sm import (
    RbcmCalculationRun,
    RbcmCampaign,
    RbcmCellResult,
    RbcmDeliverable,
    RbcmDocumentDecision,
    RbcmTemplate,
    RbcmTemplateCell,
)
from app.services.reporting_bcm_sm.document_access import sm_period_filename
from app.services.reporting_bcm_sm.document_graph import (
    GateState,
    evaluate_for_campaign,
    load_gate_state,
)
from app.services.reporting_bcm_sm.document_keys import decision_allowed
from app.services.reporting_bcm_sm.template_seed import apply_struct_key_convention
from app.services.reporting_bcm_sm.template_storage import (
    file_sha256,
    resolved_upload_root,
    verify_stored_template,
)

WORK_BANNER = (
    "VERSION DE TRAVAIL BEA DIGITAL — montants et totaux éventuellement incomplets "
    "— ne constitue pas une validation réglementaire"
)

_CLEAR_NATURES = ("OCTOBER_LEAF", "OCTOBER_CONSTANT_FORMULA")
_WRITE_NATURES = frozenset({"OCTOBER_LEAF", "OCTOBER_CONSTANT_FORMULA", "LEAF"})
_RCR_REF_FIXES = (("D14", "!B7", "!C7"), ("D15", "!B8", "!C8"))


def work_dest_dir(campaign_id: uuid.UUID) -> Path:
    if not isinstance(campaign_id, uuid.UUID):
        try:
            campaign_id = uuid.UUID(str(campaign_id))
        except (ValueError, TypeError) as exc:
            raise AppError("campaign_id n'est pas un UUID", status_code=500, code="TEMPLATE_PATH_UNSAFE") from exc
    root = resolved_upload_root()
    dest = (root / "reporting-bcm-sm" / str(campaign_id) / "work").resolve()
    try:
        dest.relative_to(root)
    except ValueError as exc:
        raise AppError("chemin WORK hors upload_root", status_code=500, code="TEMPLATE_PATH_UNSAFE") from exc
    return dest


def _closing_iso(campaign: RbcmCampaign) -> str:
    if campaign.closing_date:
        return campaign.closing_date.isoformat()
    last = monthrange(campaign.period_year, campaign.period_month)[1]
    return date(campaign.period_year, campaign.period_month, last).isoformat()


def _apply_header_footer(ws) -> None:
    try:
        ws.oddHeader.center.text = WORK_BANNER
        ws.oddFooter.center.text = WORK_BANNER
    except Exception:
        try:
            ws.oddHeader.center = WORK_BANNER
            ws.oddFooter.center = WORK_BANNER
        except Exception:
            pass


def _write_avertissement(
    wb,
    *,
    campaign: RbcmCampaign,
    gates: GateState,
    sha: str,
    filled: int = 0,
    pending_manual: list[str] | None = None,
) -> None:
    ws = wb.create_sheet("AVERTISSEMENT", 0)
    pending = pending_manual or []
    lines = [
        WORK_BANNER,
        f"Situation Mensuelle {campaign.bank_code} {campaign.period_month:02d}/{campaign.period_year} v{campaign.campaign_version}",
        "Ce fichier n'est pas une validation réglementaire.",
        "Les formules Excel du canevas officiel sont conservées ; la vérité métier est le graphe Decimal BEA DIGITAL.",
        "Un 0 ou TRUE affiché par Excel n'est pas un zéro métier ni un contrôle OK.",
        "D9 (ETAT A!D9) reste D9 — aucune ligne n'a été insérée sur les feuilles officielles.",
        f"SHA template : {sha}",
        "Portes métier ouvertes (non fermées par cette génération) : "
        + ", ".join(k for k, v in gates.as_dict().items() if v),
        f"Moteur Cellules SM : {filled} cellule(s) alimentée(s) depuis la BAL DET.",
        "À compléter manuellement après téléchargement : "
        + (", ".join(pending) if pending else "aucune si les paramètres / saisies sont renseignés"),
        "Les totaux (Somme codes, D+E+F+G) restent des formules Excel.",
        "Alerte double comptage ETAT C : la ligne 208 recopie la 209, et le TOTAL (220) additionne les deux. "
        "Canevas officiel conservé — ne pas modifier ces formules.",
        "RATIO COUVERTURE DE RISQUE D14/D15 : références « informations à fournir »!C7 et C8 (pas B7/B8).",
    ]
    for i, line in enumerate(lines, start=1):
        ws.cell(row=i, column=1, value=line)
    ws.column_dimensions["A"].width = 120
    _apply_header_footer(ws)


def _current_decisions(rows: list[RbcmDocumentDecision]) -> dict[str, RbcmDocumentDecision]:
    by_key: dict[str, RbcmDocumentDecision] = {}
    for row in sorted(rows, key=lambda r: r.decided_at):
        by_key[row.document_cell_key] = row
    return {k: v for k, v in by_key.items() if v.decision_type != "RETRAIT"}


async def _lock_work_gen(db: AsyncSession, campaign_id: uuid.UUID) -> None:
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
        {"k": f"rbcm-work-gen:{campaign_id}"},
    )


async def generate_work(
    db: AsyncSession,
    *,
    campaign: RbcmCampaign,
    user: User | None = None,
) -> dict:
    """Génère un livrable WORK immuable. Concurrent : seq n puis n+1, pas 409."""
    await apply_struct_key_convention(db)
    await _lock_work_gen(db, campaign.id)

    if campaign.template_version_id:
        template = await db.get(RbcmTemplate, campaign.template_version_id)
    else:
        template = await db.scalar(select(RbcmTemplate).where(RbcmTemplate.status == "CURRENT"))
    if template is None:
        raise AppError("canevas documentaire introuvable", status_code=404, code="TEMPLATE_NOT_FOUND")

    src = verify_stored_template(template.stored_path, template.sha256)

    cells = list(
        (await db.scalars(select(RbcmTemplateCell).where(RbcmTemplateCell.template_id == template.id))).all()
    )
    by_addr = {(c.sheet_name, c.excel_address): c for c in cells}

    seq = int(
        await db.scalar(
            select(func.coalesce(func.max(RbcmDeliverable.document_seq), 0)).where(
                RbcmDeliverable.campaign_id == campaign.id,
                RbcmDeliverable.document_seq.is_not(None),
            )
        )
        or 0
    ) + 1

    current_work = await db.scalar(
        select(RbcmDeliverable)
        .where(
            RbcmDeliverable.campaign_id == campaign.id,
            RbcmDeliverable.kind == "EXCEL",
            RbcmDeliverable.status == "WORK",
        )
        .with_for_update()
    )

    decisions_rows = list(
        (
            await db.scalars(
                select(RbcmDocumentDecision).where(RbcmDocumentDecision.campaign_id == campaign.id)
            )
        ).all()
    )
    current_dec = _current_decisions(decisions_rows)
    gates = await load_gate_state(db)
    graph = await evaluate_for_campaign(db, campaign_id=campaign.id, template=template, gates=gates)

    run = await db.scalar(
        select(RbcmCalculationRun)
        .where(
            RbcmCalculationRun.campaign_id == campaign.id,
            RbcmCalculationRun.status == "DONE",
        )
        .order_by(RbcmCalculationRun.created_at.desc())
        .limit(1)
    )
    engine_values: dict[str, object] = {}
    pending_manual: list[str] = []
    if run is not None:
        for r in (
            await db.scalars(select(RbcmCellResult).where(RbcmCellResult.run_id == run.id))
        ).all():
            if r.retained_value is not None:
                engine_values[r.cell_ref] = r.retained_value
        pending_manual = list((run.report or {}).get("pending_manual") or [])

    dest_dir = work_dest_dir(campaign.id)
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise AppError(f"répertoire WORK inaccessible: {exc}", status_code=503, code="STORAGE_UNAVAILABLE") from exc

    tmp_path = dest_dir / f".tmp-{uuid.uuid4()}.xlsx"
    final_path: Path | None = None
    inserted = False
    try:
        wb = load_workbook(src)
        official = list(wb.sheetnames)
        filled = 0
        b2 = _closing_iso(campaign)
        b3 = campaign.bank_code
        for name in official:
            if name not in wb.sheetnames:
                continue
            ws = wb[name]
            _apply_header_footer(ws)
            ws["B2"] = b2
            ws["B3"] = b3
            for (sheet, addr), cell in by_addr.items():
                if sheet != name:
                    continue
                if cell.nature in _CLEAR_NATURES:
                    ws[addr].value = None
                if cell.nature in _WRITE_NATURES and cell.document_cell_key in engine_values:
                    ws[addr].value = float(engine_values[cell.document_cell_key])  # type: ignore[arg-type]
                    filled += 1
                if decision_allowed(cell) and cell.document_cell_key in current_dec:
                    dec = current_dec[cell.document_cell_key]
                    if dec.decided_value is not None:
                        ws[addr].value = float(dec.decided_value)
            if name == "RATIO COUVERTURE DE RISQUE":
                for addr, old, new in _RCR_REF_FIXES:
                    val = ws[addr].value
                    if isinstance(val, str) and old in val:
                        ws[addr].value = val.replace(old, new)
        _write_avertissement(
            wb,
            campaign=campaign,
            gates=gates,
            sha=template.sha256,
            filled=filled,
            pending_manual=pending_manual,
        )

        wb.save(tmp_path)
        wb.close()
        sha = file_sha256(tmp_path)
        filename = sm_period_filename(campaign.period_year, campaign.period_month)
        stored_name = (
            f"SM-{campaign.period_month:02d}-{campaign.period_year}"
            f"_w{seq}_{sha[:16]}.xlsx"
        )
        if ".." in stored_name:
            raise AppError("nom WORK refusé", status_code=500, code="TEMPLATE_PATH_UNSAFE")
        final_path = dest_dir / stored_name
        tmp_path.replace(final_path)
        stored = str(final_path)

        deliverable = RbcmDeliverable(
            campaign_id=campaign.id,
            run_id=None if run is None else run.id,
            kind="EXCEL",
            filename=filename,
            stored_path=stored,
            sha256=sha,
            status="WORK",
            warnings={
                "work": True,
                "regulatory_validation": False,
                "template_sha256": template.sha256,
                "gates_open": gates.as_dict(),
                "div_zero_possible": True,
                "concordance_true_if_empty": True,
                "graph_parse_errors": graph.parse_errors[:20],
                "engine_filled": filled,
                "pending_manual": pending_manual,
            },
            created_by_id=None if user is None else user.id,
            template_id=template.id,
            document_seq=seq,
        )
        if current_work is not None:
            current_work.status = "SUPERSEDED"
            await db.flush()
        db.add(deliverable)
        await db.flush()
        if current_work is not None:
            current_work.superseded_by_id = deliverable.id
        if campaign.template_version_id is None:
            campaign.template_version_id = template.id
        await db.flush()
        inserted = True
        return {
            "id": str(deliverable.id),
            "document_seq": seq,
            "filename": filename,
            "stored_path": stored,
            "sha256": sha,
            "template_id": str(template.id),
            "superseded_id": None if current_work is None else str(current_work.id),
            "graph_status": {
                "A:CTRL:I147": None if graph.get("A:CTRL:I147") is None else graph.get("A:CTRL:I147").status,
                "RCR:H31": None if graph.get("RCR:H31") is None else graph.get("RCR:H31").status,
            },
        }
    except AppError:
        if not inserted:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            if final_path is not None and final_path.exists():
                final_path.unlink(missing_ok=True)
        raise
    except OSError as exc:
        if not inserted:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            if final_path is not None and final_path.exists():
                final_path.unlink(missing_ok=True)
        raise AppError(f"écriture WORK impossible: {exc}", status_code=503, code="STORAGE_UNAVAILABLE") from exc
    except Exception:
        if not inserted:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            if final_path is not None and final_path.exists():
                final_path.unlink(missing_ok=True)
        raise
