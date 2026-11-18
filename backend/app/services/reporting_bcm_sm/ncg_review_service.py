"""Revue métier Comptabilité — NCG détectés × orientations (sans activation auto)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.reporting_bcm_sm import (
    RbcmBalanceNcg,
    RbcmCampaign,
    RbcmImport,
    RbcmImportLineDet,
    RbcmNcgOrientation,
)
from app.services.reporting_bcm_sm.constants import (
    NCG_ORIENTATION_CURRENCIES,
    NCG_ORIENTATION_OPERATIONS,
    NCG_ORIENTATION_RESIDENCES,
    NCG_ORIENTATION_SHEETS,
    NCG_ORIENTATION_STATUSES,
)
from app.services.reporting_bcm_sm.engine.det_basis import canonical_ncg
from app.services.reporting_bcm_sm.ncg_orientation_service import (
    STATUS_ACTIVE,
    STATUS_DISABLED,
    STATUS_DRAFT,
    STATUS_PENDING,
    STATUS_REJECTED,
    catalog_target_cells,
    list_orientations,
    static_catalog_hits,
    _ori_dict,
)
from app.services.reporting_bcm_sm.ncg_structure_service import (
    STATUS_CONNU_NON_ORIENTE,
    STATUS_NOUVEAU,
    load_structure_report,
)

_REVIEW_STRUCTURE = frozenset({STATUS_NOUVEAU, STATUS_CONNU_NON_ORIENTE})


def decision_timeline(o: RbcmNcgOrientation | dict[str, Any]) -> list[dict[str, Any]]:
    """Historique de décision lisible (sans suppression)."""
    if isinstance(o, dict):
        get = o.get
    else:

        def get(k: str, default=None):
            return getattr(o, k, default)

    events: list[dict[str, Any]] = []
    mapping = [
        ("prepared", "Préparation", get("prepared_by_id"), get("prepared_at"), STATUS_DRAFT),
        ("submitted", "Soumission", get("submitted_by_id"), get("submitted_at"), STATUS_PENDING),
        ("validated", "Validation", get("validated_by_id"), get("validated_at"), STATUS_ACTIVE),
        ("rejected", "Rejet", get("rejected_by_id"), get("rejected_at"), STATUS_REJECTED),
        ("deactivated", "Désactivation", get("deactivated_by_id"), get("deactivated_at"), STATUS_DISABLED),
    ]
    for kind, label, user_id, at, status_after in mapping:
        if at is None and user_id is None:
            continue
        events.append(
            {
                "kind": kind,
                "label": label,
                "user_id": None if user_id is None else str(user_id),
                "at": at.isoformat() if hasattr(at, "isoformat") else at,
                "status_after": status_after,
                "comment": get("decision_comment") if kind in {"validated", "rejected", "deactivated", "submitted"} else None,
                "cell_ref": get("cell_ref"),
                "operation": get("operation"),
            }
        )
    return events


async def _det_samples(
    db: AsyncSession,
    *,
    import_id: UUID | None,
    ncgs: set[str],
    limit_per_ncg: int = 8,
) -> dict[str, dict[str, Any]]:
    if import_id is None or not ncgs:
        return {}
    rows = list(
        (
            await db.scalars(
                select(RbcmImportLineDet).where(
                    RbcmImportLineDet.import_id == import_id,
                    RbcmImportLineDet.ncg.in_(tuple(ncgs)),
                )
            )
        ).all()
    )
    out: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"devises": set(), "comptes": [], "line_count": 0}
    )
    for row in rows:
        code = canonical_ncg(row.ncg or "")
        if not code:
            continue
        bucket = out[code]
        bucket["line_count"] += 1
        if row.devise:
            bucket["devises"].add(row.devise)
        if row.compte and len(bucket["comptes"]) < limit_per_ncg:
            entry = {
                "compte": row.compte,
                "devise": row.devise,
                "debit": str(row.debit),
                "credit": str(row.credit),
                "libelle": row.libelle,
            }
            if entry not in bucket["comptes"]:
                bucket["comptes"].append(entry)
    return {
        k: {
            "devises": sorted(v["devises"]),
            "comptes": v["comptes"],
            "line_count": v["line_count"],
        }
        for k, v in out.items()
    }


async def _balances_for_ncgs(
    db: AsyncSession,
    *,
    ncgs: set[str],
) -> dict[str, list[dict[str, Any]]]:
    """Soldes DEB/CRE par NCG × période (BAL DET validées)."""
    if not ncgs:
        return {}
    camps = list((await db.scalars(select(RbcmCampaign))).all())
    camps = sorted(camps, key=lambda c: (c.period_year, c.period_month))
    out: dict[str, list[dict[str, Any]]] = {n: [] for n in ncgs}
    for camp in camps:
        imp = await db.scalar(
            select(RbcmImport).where(
                RbcmImport.campaign_id == camp.id,
                RbcmImport.file_type == "BAL_DET",
                RbcmImport.status == "VALIDATED",
            )
        )
        if imp is None:
            continue
        rows = list(
            (
                await db.scalars(
                    select(RbcmBalanceNcg).where(
                        RbcmBalanceNcg.import_id == imp.id,
                        RbcmBalanceNcg.source == "BAL_DET",
                        RbcmBalanceNcg.ncg.in_(tuple(ncgs)),
                    )
                )
            ).all()
        )
        by = {r.ncg: r for r in rows}
        label = f"{camp.period_month:02d}/{camp.period_year}"
        for code in ncgs:
            row = by.get(code)
            out[code].append(
                {
                    "period_year": camp.period_year,
                    "period_month": camp.period_month,
                    "label": label,
                    "present": row is not None,
                    "tot_debit": None if row is None else str(row.tot_debit),
                    "tot_credit": None if row is None else str(row.tot_credit),
                    "libelle": None if row is None else row.libelle,
                }
            )
    return out


async def build_review_board(db: AsyncSession, *, campaign: RbcmCampaign) -> dict[str, Any]:
    """Tableau de revue Comptabilité pour une campagne (BAL DET de référence)."""
    structure = await load_structure_report(db, campaign=campaign)
    import_id = structure.get("import_id")
    if isinstance(import_id, str):
        try:
            import_uuid: UUID | None = UUID(import_id)
        except ValueError:
            import_uuid = None
    else:
        import_uuid = import_id

    focus_items = [
        i for i in (structure.get("items") or []) if i.get("status") in _REVIEW_STRUCTURE
    ]
    focus_ncgs = {i["ncg"] for i in focus_items}
    samples = await _det_samples(db, import_id=import_uuid, ncgs=focus_ncgs)
    balances_map = await _balances_for_ncgs(db, ncgs=focus_ncgs)

    all_oris = await list_orientations(db)
    by_ncg: dict[str, list[dict[str, Any]]] = defaultdict(list)
    status_counts = {
        "a_orienter": 0,
        "en_attente": 0,
        "actif": 0,
        "rejete": 0,
        "desactive": 0,
    }
    ori_out: list[dict[str, Any]] = []
    for o in all_oris:
        d = _ori_dict(o)
        d["timeline"] = decision_timeline(o)
        ori_out.append(d)
        by_ncg[o.ncg].append(d)
        if o.status == STATUS_DRAFT:
            status_counts["a_orienter"] += 1
        elif o.status == STATUS_PENDING:
            status_counts["en_attente"] += 1
        elif o.status == STATUS_ACTIVE:
            status_counts["actif"] += 1
        elif o.status == STATUS_REJECTED:
            status_counts["rejete"] += 1
        elif o.status == STATUS_DISABLED:
            status_counts["desactive"] += 1

    board_rows: list[dict[str, Any]] = []
    for item in focus_items:
        code = item["ncg"]
        oris = by_ncg.get(code, [])
        latest = oris[0] if oris else None
        sample = samples.get(code, {"devises": [], "comptes": [], "line_count": 0})
        board_rows.append(
            {
                "ncg": code,
                "libelle": item.get("libelle"),
                "structure_status": item.get("status"),
                "tot_debit": item.get("tot_debit"),
                "tot_credit": item.get("tot_credit"),
                "present_zero": bool(item.get("present_zero")),
                "reapparu": bool(item.get("reapparu")),
                "covered_by_class": bool(item.get("covered_by_class")),
                "first_seen_period": item.get("first_seen_period"),
                "last_seen_period": item.get("last_seen_period"),
                "immediate_previous_period": item.get("immediate_previous_period"),
                "balances": balances_map.get(code, []),
                "devises": sample["devises"],
                "comptes": sample["comptes"],
                "line_count": sample["line_count"],
                "catalog_mappings": static_catalog_hits(code),
                "latest_orientation": latest,
                "orientations": oris,
                "proposed_cell_ref": None if latest is None else latest.get("cell_ref"),
                "proposed_operation": None if latest is None else latest.get("operation"),
                "proposed_status": None if latest is None else latest.get("status"),
                "needs_decision": latest is None
                or latest.get("status") in {STATUS_DRAFT, STATUS_PENDING},
                "decision_deferred": bool(
                    latest
                    and latest.get("status") == STATUS_DRAFT
                    and not latest.get("cell_ref")
                    and not latest.get("operation")
                ),
            }
        )

    board_rows.sort(
        key=lambda r: (
            0 if r["ncg"] == "847000" else 1,
            0 if r["structure_status"] == STATUS_NOUVEAU else 1,
            r["ncg"],
        )
    )

    return {
        "campaign_id": str(campaign.id),
        "period_year": campaign.period_year,
        "period_month": campaign.period_month,
        "has_validated_det": bool(structure.get("has_validated_det")),
        "import_id": None if import_uuid is None else str(import_uuid),
        "structure_counts": structure.get("counts") or {},
        "orientation_counts": status_counts,
        "ncg_a_reviser": board_rows,
        "orientations": ori_out,
        "target_cells": catalog_target_cells(),
        "operations": list(NCG_ORIENTATION_OPERATIONS),
        "currency_scopes": list(NCG_ORIENTATION_CURRENCIES),
        "residence_scopes": list(NCG_ORIENTATION_RESIDENCES),
        "sheets": list(NCG_ORIENTATION_SHEETS),
        "statuses": list(NCG_ORIENTATION_STATUSES),
        "orientation_auto": False,
        "note": (
            "Revue Comptabilité : aucune activation automatique. "
            "Un NCG peut rester sans orientation tant que la destination métier n'est pas connue. "
            "Validation explicite (mapping.validate) et séparation des rôles requises."
        ),
    }