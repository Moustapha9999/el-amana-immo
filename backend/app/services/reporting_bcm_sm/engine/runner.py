"""Orchestration du calcul — catalogue Cellules SM + BAL DET."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import User
from app.models.reporting_bcm_sm import (
    RbcmCalculationRun,
    RbcmCampaign,
    RbcmCellResult,
    RbcmControlResult,
    RbcmDocumentDecision,
    RbcmEcartSnapshot,
    RbcmImport,
    RbcmImportLineDet,
    RbcmMappingVersion,
)
from app.services.reporting_bcm_sm.constants import ENGINE_VERSION
from app.services.reporting_bcm_sm.engine.det_basis import DetLine, canonical_ncg
from app.services.reporting_bcm_sm.engine.evaluate import classes_1_8_gap, evaluate_sm, mapping_coverage
from app.services.reporting_bcm_sm.engine.rules_catalog import (
    ADJUST_KEYS,
    MANUAL_KEYS,
    catalog_stats,
)
from app.services.reporting_bcm_sm.parameter_service import current_values

_PARAM_OK = frozenset({"SAISI", "CALCULE", "VALIDE"})


def _fp(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update((p or "").encode("utf-8"))
        h.update(b"|")
    return h.hexdigest()


def _current_decisions(rows: list[RbcmDocumentDecision]) -> dict:
    by_key: dict[str, RbcmDocumentDecision] = {}
    for row in sorted(rows, key=lambda r: r.decided_at):
        by_key[row.document_cell_key] = row
    return {k: v for k, v in by_key.items() if v.decision_type != "RETRAIT"}


async def run_calculation(
    db: AsyncSession,
    *,
    campaign: RbcmCampaign,
    user: User,
    allow_provisional: bool = True,
) -> RbcmCalculationRun:
    """Alimente les cellules du catalogue depuis la BAL DET. Les manuels sont préservés."""
    del allow_provisional  # conservé pour compatibilité d'appel
    det = await db.scalar(
        select(RbcmImport).where(
            RbcmImport.campaign_id == campaign.id,
            RbcmImport.file_type == "BAL_DET",
            RbcmImport.status == "VALIDATED",
        )
    )
    if det is None:
        raise AppError(
            "Import BAL DET validé requis avant calcul (source comptable unique).",
            code="CALC_MISSING_IMPORTS",
        )

    det_rows = list(
        (
            await db.scalars(
                select(RbcmImportLineDet).where(
                    RbcmImportLineDet.campaign_id == campaign.id,
                    RbcmImportLineDet.import_id == det.id,
                )
            )
        ).all()
    )
    lines = [
        DetLine(
            ncg=canonical_ncg(r.ncg or ""),
            compte=r.compte or "",
            libelle=r.libelle or "",
            devise=r.devise,
            debit=r.debit,
            credit=r.credit,
        )
        for r in det_rows
        if r.ncg
    ]

    mapping_version = None
    if campaign.mapping_version_id:
        mapping_version = await db.get(RbcmMappingVersion, campaign.mapping_version_id)
    if mapping_version is None:
        mapping_version = await db.scalar(
            select(RbcmMappingVersion).where(RbcmMappingVersion.is_current.is_(True)).limit(1)
        )

    params = await current_values(db, campaign.id)
    param_fp = _fp(*[f"{p.parameter_code}:{p.value}:{p.status}" for p in params])
    param_map = {
        p.parameter_code: p.value
        for p in params
        if p.value is not None and p.status in _PARAM_OK
    }

    dec_rows = list(
        (await db.scalars(select(RbcmDocumentDecision).where(RbcmDocumentDecision.campaign_id == campaign.id))).all()
    )
    current_dec = _current_decisions(dec_rows)
    decisions = {
        k: v.decided_value
        for k, v in current_dec.items()
        if v.decided_value is not None
    }

    from app.services.reporting_bcm_sm.ncg_orientation_service import (
        list_active_orientations,
        merge_active_orientations,
    )

    stats = catalog_stats()
    active_oris = await list_active_orientations(db)
    catalog = merge_active_orientations(orientations=active_oris)
    ori_fp = _fp(
        *[
            f"{o.ncg}:{o.cell_ref}:{o.operation}:{o.currency_scope}:{o.id}"
            for o in sorted(active_oris, key=lambda r: str(r.id))
        ]
    )
    run = RbcmCalculationRun(
        campaign_id=campaign.id,
        engine_version=ENGINE_VERSION,
        status="RUNNING",
        fingerprint_imports=_fp(det.sha256),
        fingerprint_mapping=_fp("CELLULES_SM", str(stats), f"ORI:{ori_fp}"),
        fingerprint_params=param_fp,
        started_by_id=user.id,
    )
    db.add(run)
    await db.flush()

    evaluated = evaluate_sm(lines, params=param_map, decisions=decisions, rules=catalog)
    coverage = mapping_coverage(evaluated)
    ecart_amount = classes_1_8_gap(lines)

    db.add(
        RbcmEcartSnapshot(
            campaign_id=campaign.id,
            run_id=run.id,
            amount=ecart_amount,
            formula_key="SUM_SIGNED_CLASSES_1_8_DET",
            source_description=(
                "Σ(DEB−CRE) NCG classes 1–8 sur BAL DET. Présenté en contrôle, "
                "jamais appliqué comme constante de calcul."
            ),
            is_active_in_run=False,
            state="EN_ATTENTE_D02",
            historical_ref_2873223=True,
            historical_ref_2873218=False,
        )
    )

    for key, cell in evaluated.items():
        db.add(
            RbcmCellResult(
                run_id=run.id,
                campaign_id=campaign.id,
                cell_ref=key,
                calculated_value=cell.calculated,
                retained_value=cell.retained,
                value_status=cell.status,
                traces={"origin": cell.origin, "steps": cell.traces},
            )
        )

    pending_manual = [
        k
        for k in MANUAL_KEYS
        if k not in evaluated or evaluated[k].retained is None
    ]
    pending_adjust = list(ADJUST_KEYS)

    controls = [
        ("IMP_DET", "Import BAL DET validé (source unique)", "BLOCKING", "OK", None),
        (
            "MAP_CATALOG",
            "Catalogue Cellules SM (règles BAL DET, identiques pour chaque mois)",
            "INFO",
            "OK",
            f"{stats['auto']} AUTO / {stats['manual']} manuelles / {stats['adjust']} à ajuster",
        ),
        (
            "NCG_ABSENTS",
            "Rubriques du mapping absentes de cette BAL DET",
            "INFO",
            "OK",
            (
                "Aucune. Une rubrique absente vaut 0 pour ce mois ; "
                "les autres termes de la cellule restent calculés."
                if not coverage["absent"]
                else (
                    f"{len(coverage['absent'])} rubrique(s) absente(s), contribution nulle : "
                    + ", ".join(
                        f"{row['ncg']}→{row['cell']}" for row in coverage["absent"][:40]
                    )
                )
            ),
        ),
        (
            "ECART_DET",
            "Écart classes 1–8 (DET)",
            "WARNING",
            "FAIL" if ecart_amount else "OK",
            f"{ecart_amount} — à justifier, non forcé dans ETAT A",
        ),
        (
            "MANUELLES",
            "Cellules hors BAL DET à compléter",
            "WARNING",
            "FAIL" if pending_manual else "OK",
            ", ".join(pending_manual) if pending_manual else "toutes renseignées",
        ),
        (
            "AJUSTEMENTS",
            "Cellules calculées à ajuster manuellement",
            "WARNING",
            "FAIL",
            ", ".join(pending_adjust),
        ),
        (
            "ETAT_C_L50",
            "Alerte double comptage ligne 208 / 209 / TOTAL 220",
            "WARNING",
            "FAIL",
            "Canevas officiel conservé — 208 recopie 209 et le TOTAL additionne les deux",
        ),
        (
            "RCR_INFO_C",
            "RCR D14/D15 : référence INFO C7/C8 (pas B7/B8)",
            "INFO",
            "OK",
            "Formule corrigée à la génération du canevas de travail",
        ),
    ]
    blocking_fail = False
    for code, desc, sev, result, just in controls:
        if sev == "BLOCKING" and result == "FAIL":
            blocking_fail = True
        db.add(
            RbcmControlResult(
                campaign_id=campaign.id,
                run_id=run.id,
                control_code=code,
                description=desc,
                severity=sev,
                result=result,
                justification=just,
            )
        )

    auto_n = sum(1 for c in evaluated.values() if c.status == "AUTOMATIQUE" and c.retained is not None)
    run.status = "DONE"
    run.finished_at = datetime.now(timezone.utc)
    run.report = {
        "catalog": stats,
        "cells": len(evaluated),
        "auto_filled": auto_n,
        "pending_manual": pending_manual,
        "pending_adjust": pending_adjust,
        "blocking_fail": blocking_fail,
        "ecart_amount": str(ecart_amount),
        "ecart_active": False,
        "mapping_version_id": str(mapping_version.id) if mapping_version else None,
        "can_finalize_regulatory": False,
        "can_download_work": True,
        "engine": "CELLULES_SM",
        "mapping_coverage": coverage,
    }
    campaign.status = "CALCULEE"
    await db.flush()
    return run
