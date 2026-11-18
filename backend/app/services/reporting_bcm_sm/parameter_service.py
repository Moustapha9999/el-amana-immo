"""Paramètres mensuels — pas de reconduction N−1 ; absence ≠ zéro."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import User
from app.models.reporting_bcm_sm import (
    RbcmCampaign,
    RbcmImport,
    RbcmImportLineDet,
    RbcmParameterDefinition,
    RbcmParameterValue,
)
from app.services.reporting_bcm_sm.constants import PARAMETER_CODES


PARAMETER_LABELS = {
    "caisse_devises": "Caisse devises",
    "publics_mru": "Publics MRU",
    "publics_dev": "Publics devises",
    "prives_dev": "Privés devises",
    "projets": "Projets",
    "dat_public": "DAT public",
    "amort_frais_immo": "Amortissement frais immobiliers",
    "cautions_dev": "Cautions devises",
}

# Ordre métier de l’étape 4 — les cinq codes demandés d’abord.
PARAM_DISPLAY_ORDER = (
    "amort_frais_immo",
    "dat_public",
    "publics_mru",
    "publics_dev",
    "projets",
    "caisse_devises",
    "prives_dev",
    "cautions_dev",
)

PARAM_CELL_HINTS = {
    "amort_frais_immo": "A:234:C",
    "dat_public": "A:327:D",
    "publics_mru": "A:322:D",
    "publics_dev": "A:322:F",
    "projets": "A:323:D (−) / A:403:D (+)",
    "caisse_devises": "Proposition BAL DET",
    "prives_dev": "Saisie mensuelle — cellule à confirmer (D05)",
    "cautions_dev": "Saisie mensuelle — cellule à confirmer (D05)",
}

PARAM_NATURE = {
    "amort_frais_immo": "manuel",
    "dat_public": "manuel",
    "publics_mru": "manuel",
    "publics_dev": "manuel",
    "projets": "ajustement",
    "caisse_devises": "calculable",
    "prives_dev": "manuel",
    "cautions_dev": "manuel",
}

_PARAM_FILLED_STATUSES = ("SAISI", "CALCULE", "VALIDE")

# Proposition dérivable caisse_devises — règle provisoire documentée (D04/D05 ouverts).
# NCG classe caisse (préfixe 101) + devise EUR. Ne pas appliquer comme vérité définitive.
CAISSE_DEVISES_NCG_PREFIX = "101"
CAISSE_DEVISES_DEVISE = "EUR"


async def ensure_definitions(db: AsyncSession) -> None:
    existing = {
        r.code
        for r in (await db.scalars(select(RbcmParameterDefinition))).all()
    }
    for code in PARAMETER_CODES:
        if code in existing:
            continue
        db.add(
            RbcmParameterDefinition(
                code=code,
                label=PARAMETER_LABELS.get(code, code),
                calculable=(code == "caisse_devises"),
            )
        )
    await db.flush()


async def current_values(db: AsyncSession, campaign_id: uuid.UUID) -> list[RbcmParameterValue]:
    """Dernière valeur par code (append-only)."""
    rows = (
        await db.scalars(
            select(RbcmParameterValue)
            .where(RbcmParameterValue.campaign_id == campaign_id)
            .order_by(RbcmParameterValue.created_at.desc())
        )
    ).all()
    seen: set[str] = set()
    out: list[RbcmParameterValue] = []
    for r in rows:
        if r.parameter_code in seen:
            continue
        seen.add(r.parameter_code)
        out.append(r)
    return out


def _param_rank(code: str) -> int:
    try:
        return PARAM_DISPLAY_ORDER.index(code)
    except ValueError:
        return 99


async def parameter_catalog(db: AsyncSession, campaign_id: uuid.UUID) -> list[dict]:
    await ensure_definitions(db)
    defs = (await db.scalars(select(RbcmParameterDefinition))).all()
    current = {v.parameter_code: v for v in await current_values(db, campaign_id)}
    out = []
    for d in sorted(defs, key=lambda row: (_param_rank(row.code), row.code)):
        v = current.get(d.code)
        status = v.status if v else "EN_ATTENTE"
        out.append(
            {
                "code": d.code,
                "label": d.label,
                "calculable": d.calculable,
                "nature": PARAM_NATURE.get(d.code, "manuel"),
                "cell_hint": PARAM_CELL_HINTS.get(d.code),
                "value": str(v.value) if v and v.value is not None else None,
                "value_id": str(v.id) if v else None,
                "source": v.source if v else None,
                "justification": v.justification if v else None,
                "justificatif_ref": v.justificatif_ref if v else None,
                "status": status,
                "filled": status in _PARAM_FILLED_STATUSES,
                "authored_by_id": str(v.authored_by_id) if v and v.authored_by_id else None,
                "validated_by_id": str(v.validated_by_id) if v and v.validated_by_id else None,
                "created_at": v.created_at.isoformat() if v else None,
            }
        )
    return out


async def set_parameter(
    db: AsyncSession,
    *,
    campaign: RbcmCampaign,
    user: User,
    parameter_code: str,
    value: Decimal | None,
    source: str | None,
    justification: str | None,
    status: str | None = None,
    justificatif_ref: str | None = None,
    expected_value_id: uuid.UUID | None = None,
) -> RbcmParameterValue:
    from app.services.reporting_bcm_sm.workflow_service import assert_campaign_editable

    assert_campaign_editable(campaign)
    if parameter_code not in PARAMETER_CODES:
        raise AppError(f"Paramètre inconnu : {parameter_code}", code="UNKNOWN_PARAMETER")
    if value is None and not (source or justification):
        raise AppError(
            "Une valeur absente ne peut pas être enregistrée sans source/justification "
            "(interdiction de zéro silencieux).",
            code="PARAM_MISSING_JUSTIFICATION",
        )
    if value is not None and not source and not justification:
        raise AppError(
            "Chaque paramètre doit avoir une source ou une justification.",
            code="PARAM_SOURCE_REQUIRED",
        )

    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
        {"k": f"rbcm-param:{campaign.id}:{parameter_code}"},
    )
    prev = await db.scalar(
        select(RbcmParameterValue)
        .where(
            RbcmParameterValue.campaign_id == campaign.id,
            RbcmParameterValue.parameter_code == parameter_code,
        )
        .order_by(RbcmParameterValue.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    if prev is None and expected_value_id is not None:
        raise AppError(
            "Ce paramètre a changé. Rechargez puis réessayez.",
            status_code=409,
            code="PARAM_CONFLICT",
        )
    if prev is not None and expected_value_id is None:
        raise AppError(
            "La version actuelle du paramètre est requise (expected_value_id).",
            status_code=409,
            code="PARAM_VERSION_REQUIRED",
        )
    if prev is not None and expected_value_id != prev.id:
        raise AppError(
            "Ce paramètre a été modifié par un autre utilisateur. Rechargez puis réessayez.",
            status_code=409,
            code="PARAM_CONFLICT",
        )
    if prev and prev.status == "VALIDE":
        # Révision : nouvel enregistrement ; l'ancien reste en historique
        pass

    row = RbcmParameterValue(
        campaign_id=campaign.id,
        parameter_code=parameter_code,
        value=value,
        source=source,
        justification=justification,
        justificatif_ref=justificatif_ref,
        status=status or ("SAISI" if value is not None else "EN_ATTENTE"),
        authored_by_id=user.id,
        supersedes_value_id=prev.id if prev else None,
    )
    db.add(row)
    await db.flush()

    # Progression campagne
    filled = await current_values(db, campaign.id)
    codes_filled = {
        p.parameter_code
        for p in filled
        if p.status in _PARAM_FILLED_STATUSES
    }
    if len(codes_filled) >= len(PARAMETER_CODES) and campaign.status in (
        "IMPORTS",
        "RAPPROCHEE",
        "BROUILLON",
    ):
        campaign.status = "PARAMETREE"
        await db.flush()
    return row


async def validate_parameter(
    db: AsyncSession,
    *,
    campaign: RbcmCampaign,
    user: User,
    value_id: uuid.UUID,
    comment: str | None = None,
) -> RbcmParameterValue:
    row = await db.get(RbcmParameterValue, value_id)
    if row is None or row.campaign_id != campaign.id:
        raise AppError("Paramètre introuvable", status_code=404, code="PARAM_NOT_FOUND")
    if row.status not in ("SAISI", "CALCULE"):
        raise AppError(
            f"Validation impossible depuis le statut {row.status}.",
            status_code=409,
            code="PARAM_VALIDATE_INVALID",
        )
    if row.authored_by_id == user.id:
        raise AppError(
            "Séparation des tâches : l'auteur ne peut pas valider sa propre saisie.",
            status_code=403,
            code="SOD_VIOLATION",
        )
    row.status = "VALIDE"
    row.validated_by_id = user.id
    row.validated_at = datetime.now(timezone.utc)
    if comment:
        row.justification = (row.justification or "") + f"\n[validation] {comment}"
    await db.flush()
    return row


async def reject_parameter(
    db: AsyncSession,
    *,
    campaign: RbcmCampaign,
    user: User,
    value_id: uuid.UUID,
    comment: str | None = None,
) -> RbcmParameterValue:
    row = await db.get(RbcmParameterValue, value_id)
    if row is None or row.campaign_id != campaign.id:
        raise AppError("Paramètre introuvable", status_code=404, code="PARAM_NOT_FOUND")
    if row.status not in ("SAISI", "CALCULE", "VALIDE"):
        raise AppError(
            f"Rejet impossible depuis le statut {row.status}.",
            status_code=409,
            code="PARAM_REJECT_INVALID",
        )
    if not comment or not comment.strip():
        raise AppError("Le rejet exige une justification.", code="PARAM_REJECT_REASON")
    row.status = "REJETE"
    row.validated_by_id = user.id
    row.validated_at = datetime.now(timezone.utc)
    row.justification = (row.justification or "") + f"\n[rejet] {comment.strip()}"
    await db.flush()
    return row


async def history(
    db: AsyncSession,
    *,
    campaign_id: uuid.UUID,
    parameter_code: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[RbcmParameterValue], int]:
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    q = select(RbcmParameterValue).where(RbcmParameterValue.campaign_id == campaign_id)
    cq = select(func.count()).select_from(RbcmParameterValue).where(
        RbcmParameterValue.campaign_id == campaign_id
    )
    if parameter_code:
        q = q.where(RbcmParameterValue.parameter_code == parameter_code)
        cq = cq.where(RbcmParameterValue.parameter_code == parameter_code)
    total = int(await db.scalar(cq) or 0)
    rows = (
        await db.scalars(
            q.order_by(RbcmParameterValue.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return list(rows), total


async def propose_caisse_devises(db: AsyncSession, campaign: RbcmCampaign) -> dict:
    """Proposition traçable — ne sauvegarde pas ; confirmation via set_parameter."""
    det = await db.scalar(
        select(RbcmImport).where(
            RbcmImport.campaign_id == campaign.id,
            RbcmImport.file_type == "BAL_DET",
            RbcmImport.status == "VALIDATED",
        )
    )
    if det is None:
        raise AppError(
            "BAL DET validé requis pour dériver caisse_devises.",
            status_code=409,
            code="DET_REQUIRED",
        )

    rows = (
        await db.scalars(
            select(RbcmImportLineDet).where(
                RbcmImportLineDet.import_id == det.id,
                RbcmImportLineDet.devise == CAISSE_DEVISES_DEVISE,
                RbcmImportLineDet.ncg.like(f"{CAISSE_DEVISES_NCG_PREFIX}%"),
            )
        )
    ).all()

    total = Decimal("0")
    comptes: list[dict] = []
    for r in rows:
        # Solde signé débit − crédit (observation F9 = montant EUR)
        signed = (r.debit or Decimal("0")) - (r.credit or Decimal("0"))
        total += signed
        comptes.append(
            {
                "line_no": r.line_no,
                "ncg": r.ncg,
                "compte": r.compte,
                "libelle": r.libelle,
                "devise": r.devise,
                "debit": str(r.debit),
                "credit": str(r.credit),
                "signed": str(signed),
            }
        )

    total = total.quantize(Decimal("0.01"))
    return {
        "parameter_code": "caisse_devises",
        "proposed_value": str(total),
        "devise": CAISSE_DEVISES_DEVISE,
        "unit": CAISSE_DEVISES_DEVISE,
        "method": (
            f"Somme (DEB−CRE) des lignes BAL DET devise={CAISSE_DEVISES_DEVISE} "
            f"et NCG préfixe {CAISSE_DEVISES_NCG_PREFIX}* — règle provisoire T3.3 ; "
            "validation métier requise (D04/D05 ouverts). Observation oct.2026 F9=20 254,50 EUR "
            "est une référence de contrôle, pas une constante."
        ),
        "source_import_id": str(det.id),
        "source_sha256": det.sha256,
        "source_filename": det.filename,
        "accounts_count": len(comptes),
        "accounts_sample": comptes[:100],
        "auto_saved": False,
        "note": "Confirmer via POST parameters avec source=BAL_DET_DERIVE",
    }
