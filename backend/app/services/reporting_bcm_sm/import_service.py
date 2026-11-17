"""Import BAL DET (source unique T3.4-A2) — Decimal, idempotence SHA-256.

Colonnes officielles oct. 2026 :
- DET : NCG, COMPTE, LIBELLE, DEVISE, DEB, CRE

BAL COND : parsers / tables conservés pour historique ; upload refusé (IMPORT_COND_DEPRECATED).
"""

from __future__ import annotations

import hashlib
import re
import uuid
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import User
from app.models.reporting_bcm_sm import (
    RbcmBalanceNcg,
    RbcmCampaign,
    RbcmImport,
    RbcmImportLineDet,
    RbcmReconcileIssue,
)
from app.services.platform_backup_engine import upload_root
from app.services.reporting_bcm_sm.constants import (
    IMPORT_STATUSES_UNCONFIRMED,
    MODULE_CODE,
)

KNOWN_DEVISES = frozenset({"MRU", "MRO", "EUR", "USD", "GBP"})
DET_HEADERS = ("NCG", "COMPTE", "LIBELLE", "DEVISE", "DEB", "CRE")
COND_HEADERS = ("CLAS", "NCG", "LIBELLE", "TOTDEB", "TOTCRE", "VAR")


def _dec(value, *, allow_empty_zero: bool = True) -> Decimal:  # noqa: ANN001
    if value is None or value == "":
        if allow_empty_zero:
            return Decimal("0")
        raise AppError("Montant manquant", code="INVALID_AMOUNT")
    if isinstance(value, float):
        return Decimal(str(value))
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as exc:
        raise AppError(f"Montant invalide : {value!r}", code="INVALID_AMOUNT") from exc


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _norm_str(v) -> str | None:  # noqa: ANN001
    if v is None or v == "":
        return None
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    if isinstance(v, int):
        return str(v)
    return str(v).strip() or None


def detect_period_from_filename(name: str) -> tuple[int | None, int | None]:
    m = re.search(r"(20\d{2})[-_./]?(\d{1,2})", name)
    if not m:
        m = re.search(r"(\d{1,2})[-_./](20\d{2})", name)
        if m:
            return int(m.group(2)), int(m.group(1))
        return None, None
    return int(m.group(1)), int(m.group(2))


def _check_headers(actual: list, expected: tuple[str, ...]) -> list[str]:
    errors = []
    for i, name in enumerate(expected):
        got = _norm_str(actual[i]).upper() if i < len(actual) and actual[i] is not None else None
        if got != name:
            errors.append(f"Colonne {i + 1} attendue {name}, trouvée {got!r}")
    return errors


def analyze_bal_det(data: bytes) -> dict:
    wb = load_workbook(BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    rows_out: list[dict] = []
    errors: list[dict] = []
    sum_d = Decimal("0")
    sum_c = Decimal("0")
    devises: Counter[str] = Counter()
    ncgs: set[str] = set()
    comptes: set[str] = set()
    header_errors: list[str] = []

    for i, row in enumerate(ws.iter_rows(values_only=True)):
        cells = list(row)
        if i == 0:
            header_errors = _check_headers(cells, DET_HEADERS)
            continue
        if not cells or all(c is None or c == "" for c in cells[:6]):
            continue
        try:
            ncg = _norm_str(cells[0] if len(cells) > 0 else None)
            compte = _norm_str(cells[1] if len(cells) > 1 else None)
            libelle = _norm_str(cells[2] if len(cells) > 2 else None)
            devise = (_norm_str(cells[3] if len(cells) > 3 else None) or "").upper() or None
            debit = _dec(cells[4] if len(cells) > 4 else 0)
            credit = _dec(cells[5] if len(cells) > 5 else 0)
        except AppError as e:
            errors.append({"line": i + 1, "error": e.message})
            continue
        line_errs = []
        if not ncg:
            line_errs.append("NCG manquant")
        if not compte:
            line_errs.append("COMPTE manquant")
        if devise and devise not in KNOWN_DEVISES:
            line_errs.append(f"Devise inattendue: {devise}")
        if line_errs:
            errors.append({"line": i + 1, "error": "; ".join(line_errs), "ncg": ncg, "compte": compte})
            # on conserve quand même la ligne pour preview si montants OK
        if ncg:
            ncgs.add(ncg)
        if compte:
            comptes.add(compte)
        if devise:
            devises[devise] += 1
        sum_d += debit
        sum_c += credit
        rows_out.append(
            {
                "line_no": i + 1,
                "ncg": ncg,
                "compte": compte,
                "libelle": libelle,
                "devise": devise,
                "debit": debit,
                "credit": credit,
            }
        )
    wb.close()
    missing_ncg = sum(1 for r in rows_out if not r.get("ncg"))
    missing_compte = sum(1 for r in rows_out if not r.get("compte"))
    rejected_lines = len(errors)
    valid_lines = max(0, len(rows_out) - rejected_lines)
    columns_recognized = [h for h in DET_HEADERS]
    columns_missing = list(header_errors)
    blocking = bool(header_errors) or len(ncgs) == 0
    return {
        "file_type": "BAL_DET",
        "header_ok": not header_errors,
        "header_errors": header_errors,
        "columns_recognized": columns_recognized,
        "columns_missing": columns_missing,
        "column_types": {
            "NCG": "texte",
            "COMPTE": "texte",
            "LIBELLE": "texte",
            "DEVISE": "texte",
            "DEB": "decimal",
            "CRE": "decimal",
        },
        "row_count": len(rows_out),
        "valid_lines": valid_lines,
        "rejected_lines": rejected_lines,
        "valid_hint": valid_lines,
        "error_count": len(errors) + len(header_errors),
        "errors": ([{"line": 1, "error": h} for h in header_errors] + errors)[:200],
        "sum_debit": sum_d,
        "sum_credit": sum_c,
        "ncg_count": len(ncgs),
        "compte_count": len(comptes),
        "devises": dict(devises),
        "preview": rows_out[:50],
        "preview_limit": 50,
        "rows": rows_out,
        "missing_ncg_count": missing_ncg,
        "missing_compte_count": missing_compte,
        "duplicate_hint": None,
        "ready_to_confirm": not blocking,
        "blocking_reasons": (
            (["En-têtes incorrects"] if header_errors else [])
            + (["Aucun NCG reconnu"] if len(ncgs) == 0 else [])
        ),
    }


def aggregate_det_balances(
    rows: list[dict],
) -> tuple[dict[str, tuple[Decimal, Decimal, str | None]], int]:
    """Agrège DET par NCG. Retourne (agg, skipped_no_ncg). Jamais de placeholder '?'."""
    agg: dict[str, tuple[Decimal, Decimal, str | None]] = {}
    skipped = 0
    for r in rows:
        ncg = r.get("ncg")
        if not ncg:
            skipped += 1
            continue
        d, c, lib = agg.get(ncg, (Decimal("0"), Decimal("0"), r.get("libelle")))
        agg[ncg] = (d + r["debit"], c + r["credit"], r.get("libelle") or lib)
    return agg, skipped


def aggregate_cond_balances(
    rows: list[dict],
) -> tuple[dict[str, tuple[Decimal, Decimal, str | None, str | None]], int]:
    """Agrège COND par NCG. Exclut les NCG vides (évite collision uq_rbcm_balance_ncg)."""
    agg: dict[str, tuple[Decimal, Decimal, str | None, str | None]] = {}
    skipped = 0
    for r in rows:
        ncg = r.get("ncg")
        if not ncg:
            skipped += 1
            continue
        d, c, lib, clas = agg.get(
            ncg, (Decimal("0"), Decimal("0"), r.get("libelle"), r.get("clas"))
        )
        agg[ncg] = (
            d + r["debit"],
            c + r["credit"],
            r.get("libelle") or lib,
            r.get("clas") or clas,
        )
    return agg, skipped


def analyze_bal_cond(data: bytes) -> dict:
    wb = load_workbook(BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    rows_out: list[dict] = []
    errors: list[dict] = []
    sum_d = Decimal("0")
    sum_c = Decimal("0")
    ncgs: set[str] = set()
    ncg_seen: Counter[str] = Counter()
    header_errors: list[str] = []
    var_mismatch = 0
    missing_ncg = 0

    for i, row in enumerate(ws.iter_rows(values_only=True)):
        cells = list(row)
        if i == 0:
            header_errors = _check_headers(cells, COND_HEADERS)
            continue
        if not cells or all(c is None or c == "" for c in cells[:5]):
            continue
        try:
            clas = _norm_str(cells[0] if len(cells) > 0 else None)
            ncg = _norm_str(cells[1] if len(cells) > 1 else None)
            libelle = _norm_str(cells[2] if len(cells) > 2 else None)
            debit = _dec(cells[3] if len(cells) > 3 else 0)
            credit = _dec(cells[4] if len(cells) > 4 else 0)
            var = _dec(cells[5] if len(cells) > 5 else debit - credit)
        except AppError as e:
            errors.append({"line": i + 1, "error": e.message})
            continue
        if not ncg:
            missing_ncg += 1
            errors.append(
                {
                    "line": i + 1,
                    "error": "NCG manquant — ligne ignorée à la confirmation (évite conflit UNIQUE)",
                }
            )
        else:
            ncg_seen[ncg] += 1
            if ncg_seen[ncg] == 2:
                errors.append(
                    {
                        "line": i + 1,
                        "error": f"NCG dupliqué {ncg} — agrégation à la confirmation",
                        "ncg": ncg,
                    }
                )
            ncgs.add(ncg)
        expected_var = debit - credit
        if abs(var - expected_var) > Decimal("0.01"):
            var_mismatch += 1
            errors.append(
                {
                    "line": i + 1,
                    "error": f"VAR incohérent ({var} ≠ TOTDEB−TOTCRE={expected_var})",
                    "ncg": ncg,
                }
            )
        sum_d += debit
        sum_c += credit
        rows_out.append(
            {
                "line_no": i + 1,
                "clas": clas,
                "ncg": ncg,
                "libelle": libelle,
                "debit": debit,
                "credit": credit,
                "var": var,
            }
        )
    wb.close()
    dup_ncg = sum(1 for _n, cnt in ncg_seen.items() if cnt > 1)
    return {
        "file_type": "BAL_COND",
        "header_ok": not header_errors,
        "header_errors": header_errors,
        "row_count": len(rows_out),
        "error_count": len(errors) + len(header_errors),
        "errors": ([{"line": 1, "error": h} for h in header_errors] + errors)[:200],
        "sum_debit": sum_d,
        "sum_credit": sum_c,
        "ncg_count": len(ncgs),
        "missing_ncg_count": missing_ncg,
        "duplicate_ncg_count": dup_ncg,
        "var_mismatch_count": var_mismatch,
        "preview": rows_out[:50],
        "rows": rows_out,
        # Confirmation possible même avec NCG manquants : ils seront exclus des soldes.
        "ready_to_confirm": not header_errors and len(ncgs) > 0,
    }


def _jsonable(obj):  # noqa: ANN001
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, list):
        return [_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    return obj


async def upload_and_analyze(
    db: AsyncSession,
    *,
    campaign: RbcmCampaign,
    user: User,
    file_type: str,
    filename: str,
    data: bytes,
) -> tuple[RbcmImport, dict]:
    if file_type not in ("BAL_DET", "BAL_COND"):
        raise AppError("Type de fichier invalide", code="INVALID_FILE_TYPE")
    if file_type == "BAL_COND":
        # T3.4-A2 — source unique BAL DET ; tables/historique COND conservés.
        raise AppError(
            "BAL COND n’est plus accepté dans le workflow. "
            "Importez uniquement la BAL DET (source comptable unique).",
            status_code=410,
            code="IMPORT_COND_DEPRECATED",
        )
    if not filename.lower().endswith((".xlsx", ".xlsm")):
        raise AppError("Format attendu : Excel (.xlsx)", code="INVALID_FORMAT")
    if len(data) > 100 * 1024 * 1024:
        raise AppError("Fichier trop volumineux (max 100 Mo)", code="FILE_TOO_LARGE")

    sha = _sha256(data)
    existing = await db.scalar(
        select(RbcmImport).where(
            RbcmImport.campaign_id == campaign.id,
            RbcmImport.file_type == file_type,
            RbcmImport.sha256 == sha,
        )
    )
    if existing is not None:
        report = existing.control_report or {"idempotent": True}
        report = {**report, "idempotent": True, "existing_import_id": str(existing.id)}
        return existing, report

    analysis = analyze_bal_det(data) if file_type == "BAL_DET" else analyze_bal_cond(data)
    if not analysis.get("header_ok", True):
        raise AppError(
            "En-têtes de colonnes incorrects : " + "; ".join(analysis.get("header_errors") or []),
            code="INVALID_HEADERS",
        )

    py, pm = detect_period_from_filename(filename)
    root = upload_root() / MODULE_CODE / str(campaign.id)
    root.mkdir(parents=True, exist_ok=True)
    dest = root / f"{file_type}_{sha[:16]}_{Path(filename).name}"
    dest.write_bytes(data)

    control = {
        "row_count": analysis["row_count"],
        "sum_debit": str(analysis["sum_debit"]),
        "sum_credit": str(analysis["sum_credit"]),
        "error_count": analysis.get("error_count", 0),
        "errors": analysis.get("errors", [])[:100],
        "preview": _jsonable(analysis["preview"]),
        "preview_limit": analysis.get("preview_limit", 50),
        "ncg_count": analysis.get("ncg_count"),
        "compte_count": analysis.get("compte_count"),
        "devises": analysis.get("devises"),
        "var_mismatch_count": analysis.get("var_mismatch_count"),
        "missing_ncg_count": analysis.get("missing_ncg_count", 0),
        "missing_compte_count": analysis.get("missing_compte_count", 0),
        "duplicate_ncg_count": analysis.get("duplicate_ncg_count", 0),
        "valid_lines": analysis.get("valid_lines"),
        "rejected_lines": analysis.get("rejected_lines"),
        "columns_recognized": analysis.get("columns_recognized"),
        "columns_missing": analysis.get("columns_missing"),
        "column_types": analysis.get("column_types"),
        "blocking_reasons": analysis.get("blocking_reasons") or [],
        "ready_to_confirm": bool(analysis.get("ready_to_confirm", True)),
        "header_ok": True,
    }

    imp = RbcmImport(
        campaign_id=campaign.id,
        file_type=file_type,
        filename=filename[:255],
        stored_path=str(dest),
        sha256=sha,
        size_bytes=len(data),
        status="ANALYZED",
        period_year_detected=py,
        period_month_detected=pm,
        control_report=control,
        uploaded_by_id=user.id,
        row_count=analysis["row_count"],
        sum_debit=analysis["sum_debit"],
        sum_credit=analysis["sum_credit"],
    )
    db.add(imp)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise AppError(
            "Import déjà présent (empreinte SHA-256).",
            status_code=409,
            code="IMPORT_DUPLICATE",
        ) from exc
    return imp, control


async def confirm_import(
    db: AsyncSession,
    *,
    campaign: RbcmCampaign,
    user: User,
    import_id: uuid.UUID,
    data: bytes | None = None,
    replace_validated: bool = False,
) -> RbcmImport:
    # Verrouillage ligne pour éviter double confirmation concurrente.
    imp = await db.scalar(
        select(RbcmImport).where(RbcmImport.id == import_id).with_for_update()
    )
    if imp is None or imp.campaign_id != campaign.id:
        raise AppError("Import introuvable", status_code=404, code="IMPORT_NOT_FOUND")
    if imp.status == "VALIDATED" and not replace_validated:
        raise AppError(
            "Import déjà validé — confirmez le remplacement contrôlé.",
            status_code=409,
            code="IMPORT_VALIDATED",
        )

    prev = await db.scalar(
        select(RbcmImport).where(
            RbcmImport.campaign_id == campaign.id,
            RbcmImport.file_type == imp.file_type,
            RbcmImport.status == "VALIDATED",
            RbcmImport.id != imp.id,
        )
    )
    if prev is not None:
        if not replace_validated:
            raise AppError(
                "Un import validé existe déjà pour ce type. Confirmez le remplacement.",
                status_code=409,
                code="IMPORT_VALIDATED_EXISTS",
            )
        prev.status = "SUPERSEDED"
        imp.supersedes_import_id = prev.id

    raw = data
    if raw is None and imp.stored_path:
        raw = Path(imp.stored_path).read_bytes()
    if raw is None:
        raise AppError("Fichier source indisponible pour confirmation", code="IMPORT_FILE_MISSING")

    analysis = analyze_bal_det(raw) if imp.file_type == "BAL_DET" else analyze_bal_cond(raw)
    if not analysis.get("header_ok", True):
        raise AppError("En-têtes invalides au moment de la confirmation", code="INVALID_HEADERS")

    # Nettoyer anciennes lignes/balances de cet import si re-confirm
    for model in (RbcmImportLineDet, RbcmBalanceNcg):
        old = (
            await db.scalars(select(model).where(model.import_id == imp.id))  # type: ignore[attr-defined]
        ).all()
        for row in old:
            await db.delete(row)
    await db.flush()

    confirmed_ncg_count = 0
    skipped_no_ncg = 0
    if imp.file_type == "BAL_DET":
        batch: list[RbcmImportLineDet] = []
        for r in analysis["rows"]:
            batch.append(
                RbcmImportLineDet(
                    campaign_id=campaign.id,
                    import_id=imp.id,
                    line_no=r["line_no"],
                    ncg=r.get("ncg"),
                    compte=r.get("compte"),
                    libelle=r.get("libelle"),
                    devise=r.get("devise"),
                    debit=r["debit"],
                    credit=r["credit"],
                )
            )
            if len(batch) >= 1000:
                db.add_all(batch)
                await db.flush()
                batch.clear()
        if batch:
            db.add_all(batch)
            await db.flush()
        agg, skipped_no_ncg = aggregate_det_balances(analysis["rows"])
        confirmed_ncg_count = len(agg)
        for ncg, (d, c, lib) in agg.items():
            db.add(
                RbcmBalanceNcg(
                    campaign_id=campaign.id,
                    import_id=imp.id,
                    source="BAL_DET",
                    ncg=ncg,
                    libelle=lib,
                    tot_debit=d,
                    tot_credit=c,
                )
            )
    else:
        # Agrégation obligatoire par NCG : uq_rbcm_balance_ncg (import_id, ncg).
        # Les lignes sans NCG sont exclues (ne jamais forcer "?" → collision UNIQUE).
        agg_c, skipped_no_ncg = aggregate_cond_balances(analysis["rows"])
        if not agg_c:
            raise AppError(
                "Confirmation impossible — aucune ligne BAL COND avec NCG valide.",
                status_code=422,
                code="IMPORT_NO_VALID_NCG",
            )
        confirmed_ncg_count = len(agg_c)
        for ncg, (d, c, lib, _clas) in agg_c.items():
            db.add(
                RbcmBalanceNcg(
                    campaign_id=campaign.id,
                    import_id=imp.id,
                    source="BAL_COND",
                    ncg=ncg,
                    libelle=lib,
                    tot_debit=d,
                    tot_credit=c,
                )
            )

    report = dict(imp.control_report or {})
    report.update(
        {
            "confirmed_ncg_count": confirmed_ncg_count,
            "skipped_no_ncg": skipped_no_ncg,
            "missing_ncg_count": analysis.get("missing_ncg_count", skipped_no_ncg),
            "duplicate_ncg_count": analysis.get("duplicate_ncg_count", 0),
        }
    )
    imp.control_report = report
    imp.status = "VALIDATED"
    imp.validated_by_id = user.id
    imp.validated_at = datetime.now(timezone.utc)
    imp.row_count = analysis["row_count"]
    imp.sum_debit = analysis["sum_debit"]
    imp.sum_credit = analysis["sum_credit"]
    if campaign.status == "BROUILLON":
        campaign.status = "IMPORTS"
    try:
        await db.flush()
    except IntegrityError as exc:
        # Message générique DUPLICATE (api_errors) masquait uq_rbcm_balance_ncg.
        raise AppError(
            "Confirmation impossible — conflit d'unicité sur les soldes NCG "
            "(doublons non agrégés ou import concurrent). Réessayez ou contactez le support.",
            status_code=409,
            code="IMPORT_BALANCE_CONFLICT",
        ) from exc
    # T3.5-2 : contrôles métier append-only (plus de suppression des anciennes anomalies).
    if imp.file_type == "BAL_DET":
        await run_det_coherence_controls(db, campaign, user=user)
    return imp


def _unlink_stored_import(stored_path: str | None) -> None:
    """Retire le fichier sous upload_root uniquement — jamais hors racine de stockage."""
    if not stored_path:
        return
    try:
        root = upload_root().resolve()
        path = Path(stored_path).resolve()
        path.relative_to(root)
    except (OSError, ValueError):
        return
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass


async def discard_unconfirmed_import(
    db: AsyncSession,
    *,
    campaign: RbcmCampaign,
    import_id: uuid.UUID,
) -> dict:
    """Suppression physique d'un import non confirmé (ANALYZED / REJECTED / UPLOADED).

    Un import VALIDATED ou SUPERSEDED n'est jamais détruit : remplacement contrôlé
    ou archivage de la SM. Ne contourne pas les FK : lignes et soldes d'abord.
    """
    if campaign.status in ("CLOTUREE", "APPROUVEE"):
        raise AppError(
            "SM figée : suppression d'import interdite.",
            status_code=409,
            code="CAMPAIGN_LOCKED",
        )
    imp = await db.scalar(
        select(RbcmImport).where(RbcmImport.id == import_id).with_for_update()
    )
    if imp is None or imp.campaign_id != campaign.id:
        raise AppError("Import introuvable", status_code=404, code="IMPORT_NOT_FOUND")
    if imp.status not in IMPORT_STATUSES_UNCONFIRMED:
        raise AppError(
            "Seul un import non confirmé (analysé ou rejeté) peut être supprimé. "
            "Un import validé se remplace ; une SM déjà calculée s'archive.",
            status_code=409,
            code="IMPORT_DELETE_FORBIDDEN",
        )
    meta = {
        "id": str(imp.id),
        "filename": imp.filename,
        "status": imp.status,
        "sha256": imp.sha256,
        "file_type": imp.file_type,
    }
    stored = imp.stored_path
    for model in (RbcmImportLineDet, RbcmBalanceNcg):
        old = (await db.scalars(select(model).where(model.import_id == imp.id))).all()
        for row in old:
            await db.delete(row)
    await db.flush()
    await db.delete(imp)
    await db.flush()
    _unlink_stored_import(stored)
    return meta


async def purge_unconfirmed_imports(
    db: AsyncSession,
    *,
    campaign: RbcmCampaign,
) -> int:
    """Cascade des analyses non confirmées (SM BROUILLON éligible à la suppression)."""
    rows = (
        await db.scalars(
            select(RbcmImport).where(
                RbcmImport.campaign_id == campaign.id,
                RbcmImport.status.in_(IMPORT_STATUSES_UNCONFIRMED),
            )
        )
    ).all()
    n = 0
    for imp in rows:
        await discard_unconfirmed_import(db, campaign=campaign, import_id=imp.id)
        n += 1
    return n


async def run_det_coherence_controls(
    db: AsyncSession,
    campaign: RbcmCampaign,
    user=None,  # noqa: ANN001
) -> dict:
    """Contrôles internes sur BAL DET validée — délègue au service T3.5-2 (append-only)."""
    from app.services.reporting_bcm_sm.control_service import run_sm_controls

    return await run_sm_controls(db, campaign=campaign, user=user)


async def reconcile_campaign(
    db: AsyncSession,
    campaign: RbcmCampaign,
    *,
    user=None,  # noqa: ANN001
    debit_warn_threshold: Decimal = Decimal("1"),
    credit_warn_threshold: Decimal = Decimal("1"),
) -> dict:
    """Point d’entrée contrôles campagne — exécution append-only T3.5-2."""
    return await run_det_coherence_controls(db, campaign, user=user)


async def reconcile_det_cond_legacy(
    db: AsyncSession,
    campaign: RbcmCampaign,
    *,
    debit_warn_threshold: Decimal = Decimal("1"),
    credit_warn_threshold: Decimal = Decimal("1"),
) -> dict:
    """DEPRECATED — rapprochement DET/COND (historique T3.3/T3.4). Ne pas utiliser en workflow."""
    det = await db.scalar(
        select(RbcmImport).where(
            RbcmImport.campaign_id == campaign.id,
            RbcmImport.file_type == "BAL_DET",
            RbcmImport.status == "VALIDATED",
        )
    )
    cond = await db.scalar(
        select(RbcmImport).where(
            RbcmImport.campaign_id == campaign.id,
            RbcmImport.file_type == "BAL_COND",
            RbcmImport.status == "VALIDATED",
        )
    )
    if not det or not cond:
        return {"ready": False, "reason": "DET et COND validés requis (legacy)", "deprecated": True}

    # T3.5-2 : ne plus purger ni écrire rbcm_reconcile_issue. Diagnostic hors workflow uniquement.
    return {
        "ready": False,
        "deprecated": True,
        "reason": "Rapprochement DET/COND hors workflow (T3.4-A2). Aucune anomalie écrite.",
        "det_import_id": str(det.id),
        "cond_import_id": str(cond.id),
    }

    det_ncgs = {
        r.ncg: r
        for r in (
            await db.scalars(
                select(RbcmBalanceNcg).where(
                    RbcmBalanceNcg.import_id == det.id, RbcmBalanceNcg.source == "BAL_DET"
                )
            )
        ).all()
    }
    cond_ncgs = {
        r.ncg: r
        for r in (
            await db.scalars(
                select(RbcmBalanceNcg).where(
                    RbcmBalanceNcg.import_id == cond.id, RbcmBalanceNcg.source == "BAL_COND"
                )
            )
        ).all()
    }

    only_det = sorted(set(det_ncgs) - set(cond_ncgs))
    only_cond = sorted(set(cond_ncgs) - set(det_ncgs))
    common = sorted(set(det_ncgs) & set(cond_ncgs))

    abs_deb = Decimal("0")
    abs_cre = Decimal("0")
    credit_gt1 = 0
    debit_gt1 = 0
    max_credit_gap = Decimal("0")
    max_credit_ncg = None
    details = []

    for ncg in common:
        d = det_ncgs[ncg]
        c = cond_ncgs[ncg]
        gap_d = abs(d.tot_debit - c.tot_debit)
        gap_c = abs(d.tot_credit - c.tot_credit)
        abs_deb += gap_d
        abs_cre += gap_c
        if gap_c > credit_warn_threshold:
            credit_gt1 += 1
            if gap_c > max_credit_gap:
                max_credit_gap = gap_c
                max_credit_ncg = ncg
            db.add(
                RbcmReconcileIssue(
                    campaign_id=campaign.id,
                    ncg=ncg,
                    severity="WARNING",
                    code="CREDIT_GAP",
                    message=f"Écart crédit DET/COND = {gap_c}",
                    details={
                        "det_credit": str(d.tot_credit),
                        "cond_credit": str(c.tot_credit),
                        "gap": str(gap_c),
                    },
                )
            )
        if gap_d > debit_warn_threshold:
            debit_gt1 += 1
            db.add(
                RbcmReconcileIssue(
                    campaign_id=campaign.id,
                    ncg=ncg,
                    severity="WARNING",
                    code="DEBIT_GAP",
                    message=f"Écart débit DET/COND = {gap_d}",
                    details={
                        "det_debit": str(d.tot_debit),
                        "cond_debit": str(c.tot_debit),
                        "gap": str(gap_d),
                    },
                )
            )
        if gap_d > 0 or gap_c > 0:
            details.append(
                {
                    "ncg": ncg,
                    "libelle": c.libelle or d.libelle,
                    "det_debit": str(d.tot_debit),
                    "cond_debit": str(c.tot_debit),
                    "gap_debit": str(gap_d),
                    "det_credit": str(d.tot_credit),
                    "cond_credit": str(c.tot_credit),
                    "gap_credit": str(gap_c),
                }
            )

    for ncg in only_det[:500]:
        db.add(
            RbcmReconcileIssue(
                campaign_id=campaign.id,
                ncg=ncg,
                severity="WARNING",
                code="NCG_ONLY_DET",
                message=f"NCG {ncg} présent en DET uniquement",
            )
        )
    for ncg in only_cond[:500]:
        db.add(
            RbcmReconcileIssue(
                campaign_id=campaign.id,
                ncg=ncg,
                severity="WARNING",
                code="NCG_ONLY_COND",
                message=f"NCG {ncg} présent en COND uniquement",
            )
        )

    # Somme classes 1–8 COND (référence documentaire campagne — pas constante ECART)
    classes_1_8 = Decimal("0")
    for ncg, row in cond_ncgs.items():
        if ncg and ncg[:1] in "12345678":
            classes_1_8 += row.tot_debit - row.tot_credit

    db.add(
        RbcmReconcileIssue(
            campaign_id=campaign.id,
            ncg=None,
            severity="INFO",
            code="SUMMARY",
            message="Synthèse rapprochement DET/COND",
            details={
                "ncg_det": len(det_ncgs),
                "ncg_cond": len(cond_ncgs),
                "only_det": len(only_det),
                "only_cond": len(only_cond),
                "abs_debit_gap": str(abs_deb),
                "abs_credit_gap": str(abs_cre),
                "credit_gaps_gt_threshold": credit_gt1,
                "debit_gaps_gt_threshold": debit_gt1,
                "max_credit_gap": str(max_credit_gap),
                "max_credit_ncg": max_credit_ncg,
                "classes_1_8_signed_cond": str(classes_1_8.quantize(Decimal("0.01"))),
                "threshold_debit": str(debit_warn_threshold),
                "threshold_credit": str(credit_warn_threshold),
                "note": "Valeurs T1 oct.2026 = références de contrôle, pas constantes métier",
            },
        )
    )
    campaign.status = "RAPPROCHEE"
    await db.flush()
    return {
        "ready": True,
        "ncg_det": len(det_ncgs),
        "ncg_cond": len(cond_ncgs),
        "only_det": only_det[:100],
        "only_cond": only_cond[:100],
        "abs_debit_gap": str(abs_deb),
        "abs_credit_gap": str(abs_cre),
        "credit_gaps_gt_threshold": credit_gt1,
        "debit_gaps_gt_threshold": debit_gt1,
        "max_credit_gap": str(max_credit_gap),
        "max_credit_ncg": max_credit_ncg,
        "classes_1_8_signed_cond": str(classes_1_8.quantize(Decimal("0.01"))),
        "gaps_sample": sorted(details, key=lambda x: Decimal(x["gap_credit"]), reverse=True)[:50],
    }


async def list_cond_lines(
    db: AsyncSession,
    *,
    campaign_id: uuid.UUID,
    search: str | None = None,
    ncg: str | None = None,
    page: int = 1,
    page_size: int = 50,
    sort_by: str = "ncg",
    sort_order: str = "asc",
) -> tuple[list[RbcmBalanceNcg], int]:
    """Soldes BAL COND (agrégés NCG) — pagination serveur."""
    page = max(1, page)
    page_size = min(max(1, page_size), 200)
    base = [
        RbcmBalanceNcg.campaign_id == campaign_id,
        RbcmBalanceNcg.source == "BAL_COND",
    ]
    if ncg:
        base.append(RbcmBalanceNcg.ncg == ncg)
    if search:
        like = f"%{search.strip()}%"
        from sqlalchemy import or_

        base.append(
            or_(RbcmBalanceNcg.ncg.ilike(like), RbcmBalanceNcg.libelle.ilike(like))
        )
    cq = select(func.count()).select_from(RbcmBalanceNcg).where(*base)
    total = int(await db.scalar(cq) or 0)
    col = RbcmBalanceNcg.ncg
    if sort_by == "debit":
        col = RbcmBalanceNcg.tot_debit
    elif sort_by == "credit":
        col = RbcmBalanceNcg.tot_credit
    order = col.desc() if sort_order.lower() == "desc" else col.asc()
    rows = (
        await db.scalars(
            select(RbcmBalanceNcg)
            .where(*base)
            .order_by(order)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return list(rows), total


async def list_imports_global(
    db: AsyncSession,
    *,
    campaign_id: uuid.UUID | None = None,
    file_type: str | None = None,
    status: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[RbcmImport], int]:
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    filters = []
    if campaign_id:
        filters.append(RbcmImport.campaign_id == campaign_id)
    if file_type:
        filters.append(RbcmImport.file_type == file_type)
    if status:
        filters.append(RbcmImport.status == status)
    if search:
        like = f"%{search.strip()}%"
        filters.append(RbcmImport.filename.ilike(like))
    cq = select(func.count()).select_from(RbcmImport)
    q = select(RbcmImport)
    if filters:
        cq = cq.where(*filters)
        q = q.where(*filters)
    total = int(await db.scalar(cq) or 0)
    rows = (
        await db.scalars(
            q.order_by(RbcmImport.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return list(rows), total


async def list_det_lines(
    db: AsyncSession,
    *,
    campaign_id: uuid.UUID,
    import_id: uuid.UUID | None = None,
    search: str | None = None,
    ncg: str | None = None,
    devise: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[RbcmImportLineDet], int]:
    page = max(1, page)
    page_size = min(max(1, page_size), 200)
    q = select(RbcmImportLineDet).where(RbcmImportLineDet.campaign_id == campaign_id)
    cq = select(func.count()).select_from(RbcmImportLineDet).where(
        RbcmImportLineDet.campaign_id == campaign_id
    )
    if import_id:
        q = q.where(RbcmImportLineDet.import_id == import_id)
        cq = cq.where(RbcmImportLineDet.import_id == import_id)
    if ncg:
        q = q.where(RbcmImportLineDet.ncg == ncg)
        cq = cq.where(RbcmImportLineDet.ncg == ncg)
    if devise:
        q = q.where(RbcmImportLineDet.devise == devise.upper())
        cq = cq.where(RbcmImportLineDet.devise == devise.upper())
    if search:
        like = f"%{search.strip()}%"
        q = q.where(
            (RbcmImportLineDet.compte.ilike(like))
            | (RbcmImportLineDet.libelle.ilike(like))
            | (RbcmImportLineDet.ncg.ilike(like))
        )
        cq = cq.where(
            (RbcmImportLineDet.compte.ilike(like))
            | (RbcmImportLineDet.libelle.ilike(like))
            | (RbcmImportLineDet.ncg.ilike(like))
        )
    total = int(await db.scalar(cq) or 0)
    rows = (
        await db.scalars(
            q.order_by(RbcmImportLineDet.line_no).offset((page - 1) * page_size).limit(page_size)
        )
    ).all()
    return list(rows), total
