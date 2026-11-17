"""Accès API aux livrables documentaires — lecture seule, pas de régénération."""

from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.reporting_bcm_sm import RbcmDeliverable
from app.services.reporting_bcm_sm.template_storage import file_sha256, resolved_upload_root

WORK_DISCLAIMER = (
    "Document de travail non validé — ne constitue pas une validation réglementaire."
)
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _raise(code: str, message: str, status_code: int) -> None:
    raise AppError(message, status_code=status_code, code=code)


def sm_period_filename(period_year: int, period_month: int) -> str:
    """Nom métier du canevas : SM-01-2026.xlsx (janvier 2026), SM-02-2026.xlsx, …"""
    month = int(period_month)
    year = int(period_year)
    if month < 1 or month > 12:
        _raise("TEMPLATE_PATH_UNSAFE", "mois de SM invalide pour le nom de fichier", 500)
    return safe_download_name(f"SM-{month:02d}-{year}.xlsx")


def safe_download_name(filename: str | None) -> str:
    raw = filename or ""
    if not raw or ".." in raw or "/" in raw or "\\" in raw:
        _raise("TEMPLATE_PATH_UNSAFE", "nom de fichier refusé", 500)
    name = Path(raw).name
    if name != raw:
        _raise("TEMPLATE_PATH_UNSAFE", "nom de fichier refusé", 500)
    return name


def document_public_dict(
    d: RbcmDeliverable,
    *,
    period_year: int | None = None,
    period_month: int | None = None,
) -> dict:
    documentary = d.status in ("WORK", "SUPERSEDED")
    filename = d.filename
    if period_year is not None and period_month is not None:
        filename = sm_period_filename(period_year, period_month)
    return {
        "id": d.id,
        "campaign_id": d.campaign_id,
        "kind": d.kind,
        "format": "xlsx" if d.kind == "EXCEL" else (d.kind or "").lower(),
        "status": d.status,
        "document_seq": d.document_seq,
        "filename": filename,
        "sha256": d.sha256,
        "sha256_available": bool(d.sha256),
        "created_at": d.created_at,
        "created_by_id": d.created_by_id,
        "template_id": d.template_id,
        "superseded_by_id": d.superseded_by_id,
        "is_current_work": d.status == "WORK",
        "regulatory_validated": False,
        "work_disclaimer": WORK_DISCLAIMER if documentary else None,
        "generation_kind": "documentary" if documentary else "technical_export",
    }


def public_warnings(warnings: dict | None) -> dict | None:
    if not warnings:
        return None
    out = {}
    for key, val in warnings.items():
        lk = str(key).lower()
        if "path" in lk or "dir" in lk or "stored" in lk:
            continue
        out[key] = val
    return out or None


def resolve_deliverable_file(d: RbcmDeliverable) -> Path:
    """Chemin sûr sous upload_root / campagne. Vérifie SHA si présent. Aucune régénération."""
    if not d.stored_path:
        _raise("DELIVERABLE_FILE_MISSING", "fichier livrable absent", 404)
    if ".." in d.stored_path:
        _raise("TEMPLATE_PATH_UNSAFE", "traversée refusée", 500)
    safe_download_name(d.filename)
    root = resolved_upload_root()
    resolved = Path(d.stored_path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        _raise("TEMPLATE_PATH_UNSAFE", "stored_path hors upload_root", 500)
    camp_root = (root / "reporting-bcm-sm" / str(d.campaign_id)).resolve()
    try:
        resolved.relative_to(camp_root)
    except ValueError:
        _raise("TEMPLATE_PATH_UNSAFE", "fichier hors répertoire de la SM", 500)
    if resolved.is_symlink():
        target = resolved.resolve()
        try:
            target.relative_to(camp_root)
        except ValueError:
            _raise("TEMPLATE_PATH_UNSAFE", "lien symbolique hors répertoire autorisé", 500)
    if not resolved.is_file():
        _raise("DELIVERABLE_FILE_MISSING", "fichier livrable absent du disque", 404)
    if d.sha256:
        sha = file_sha256(resolved)
        if sha.lower() != d.sha256.lower():
            _raise("WORK_SHA_MISMATCH", "SHA fichier ≠ SHA colonne", 409)
    return resolved


async def list_documents(db: AsyncSession, campaign_id: uuid.UUID) -> list[RbcmDeliverable]:
    rows = (
        await db.scalars(
            select(RbcmDeliverable)
            .where(RbcmDeliverable.campaign_id == campaign_id)
            .order_by(
                RbcmDeliverable.document_seq.desc().nulls_last(),
                RbcmDeliverable.created_at.desc(),
            )
        )
    ).all()
    return list(rows)


async def get_document(
    db: AsyncSession,
    *,
    campaign_id: uuid.UUID,
    deliverable_id: uuid.UUID,
) -> RbcmDeliverable:
    d = await db.get(RbcmDeliverable, deliverable_id)
    if d is None or d.campaign_id != campaign_id:
        _raise("DELIVERABLE_NOT_FOUND", "Livrable introuvable pour cette SM", 404)
    return d


async def campaign_document_history(
    db: AsyncSession,
    campaign_id: uuid.UUID,
) -> list[dict]:
    rows = await list_documents(db, campaign_id)
    return [
        {
            "id": r.id,
            "status": r.status,
            "document_seq": r.document_seq,
            "filename": r.filename,
            "created_at": r.created_at,
            "is_current_work": r.status == "WORK",
        }
        for r in rows
        if r.status in ("WORK", "SUPERSEDED", "GENERATED")
    ]
