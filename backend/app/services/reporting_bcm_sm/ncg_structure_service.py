"""Comparaison de structure NCG entre BAL DET validées — hors orientation mapping.

Rapport descriptif uniquement. Ne modifie ni le catalogue, ni les BAL, ni les cellules.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.reporting_bcm_sm import RbcmBalanceNcg, RbcmCampaign, RbcmImport
from app.services.reporting_bcm_sm.engine.det_basis import canonical_ncg
from app.services.reporting_bcm_sm.engine.rules_catalog import ALL_RULES

STATUS_NOUVEAU = "nouveau"
STATUS_CONNU_NON_ORIENTE = "connu_non_oriente"
STATUS_DEJA_MAPPE = "deja_mappe"
STATUS_ABSENT_MAPPE = "absent_mappe"
STATUS_ABSENT_HISTORIQUE = "absent_historique"

ZERO = Decimal("0.00")


@dataclass(frozen=True)
class PeriodNcgRow:
    ncg: str
    libelle: str | None
    tot_debit: Decimal
    tot_credit: Decimal


@dataclass(frozen=True)
class PeriodSnapshot:
    period_year: int
    period_month: int
    campaign_id: UUID
    import_id: UUID
    rows: dict[str, PeriodNcgRow]

    @property
    def period_key(self) -> int:
        return self.period_year * 12 + self.period_month

    @property
    def ncg_set(self) -> frozenset[str]:
        return frozenset(self.rows)


def catalog_exact_ncg_index() -> dict[str, list[dict[str, Any]]]:
    """NCG exacts du catalogue central → cellules (basis, sign). Pas les ncg_class."""
    index: dict[str, list[dict[str, Any]]] = {}
    for rule in ALL_RULES:
        for term in rule.terms:
            for raw in term.ncgs:
                code = canonical_ncg(raw)
                if not code:
                    continue
                entry = {
                    "cell_ref": rule.key,
                    "basis": term.basis,
                    "sign": term.sign,
                }
                bucket = index.setdefault(code, [])
                if entry not in bucket:
                    bucket.append(entry)
    return index


def catalog_class_prefixes() -> frozenset[str]:
    return frozenset(
        term.ncg_class
        for rule in ALL_RULES
        for term in rule.terms
        if term.ncg_class
    )


def _period_label(year: int, month: int) -> str:
    return f"{month:02d}/{year}"


def _primary_status(*, in_history: bool, mapped: bool) -> str:
    if mapped:
        return STATUS_DEJA_MAPPE
    if in_history:
        return STATUS_CONNU_NON_ORIENTE
    return STATUS_NOUVEAU


def build_structure_report(
    *,
    current: PeriodSnapshot | None,
    history: list[PeriodSnapshot],
    mapped_index: dict[str, list[dict[str, Any]]] | None = None,
    class_prefixes: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Construit le rapport de structure pour une période courante.

    ``history`` = snapshots de périodes strictement antérieures, tous VALIDATED.
    """
    mapped_index = mapped_index if mapped_index is not None else catalog_exact_ncg_index()
    class_prefixes = class_prefixes if class_prefixes is not None else catalog_class_prefixes()
    mapped_set = frozenset(mapped_index)

    history_sorted = sorted(history, key=lambda s: s.period_key)
    hist_union: set[str] = set()
    first_seen: dict[str, tuple[int, int]] = {}
    last_seen: dict[str, tuple[int, int]] = {}
    for snap in history_sorted:
        for ncg in snap.ncg_set:
            hist_union.add(ncg)
            if ncg not in first_seen:
                first_seen[ncg] = (snap.period_year, snap.period_month)
            last_seen[ncg] = (snap.period_year, snap.period_month)

    available_periods = [
        {"period_year": s.period_year, "period_month": s.period_month, "label": _period_label(s.period_year, s.period_month)}
        for s in history_sorted
    ]
    if current is not None:
        available_periods.append(
            {
                "period_year": current.period_year,
                "period_month": current.period_month,
                "label": _period_label(current.period_year, current.period_month),
            }
        )

    if current is None:
        return {
            "has_validated_det": False,
            "period_year": None,
            "period_month": None,
            "campaign_id": None,
            "import_id": None,
            "ncg_count": 0,
            "history_period_count": len(history_sorted),
            "available_periods": available_periods,
            "counts": {
                "nouveau": 0,
                "connu_non_oriente": 0,
                "deja_mappe": 0,
                "present_zero": 0,
                "reapparu": 0,
                "absent_mappe": 0,
                "absent_historique": 0,
            },
            "items": [],
            "absents": [],
            "orientation_auto": False,
            "note": (
                "Aucune BAL DET validée pour cette campagne. "
                "Le rapport de structure NCG n'est pas disponible."
            ),
        }

    immediate_prev = history_sorted[-1] if history_sorted else None
    prev_set = immediate_prev.ncg_set if immediate_prev else frozenset()

    items: list[dict[str, Any]] = []
    counts = {
        "nouveau": 0,
        "connu_non_oriente": 0,
        "deja_mappe": 0,
        "present_zero": 0,
        "reapparu": 0,
        "absent_mappe": 0,
        "absent_historique": 0,
    }

    for ncg in sorted(current.ncg_set):
        row = current.rows[ncg]
        mapped = ncg in mapped_set
        in_history = ncg in hist_union
        status = _primary_status(in_history=in_history, mapped=mapped)
        present_zero = row.tot_debit == ZERO and row.tot_credit == ZERO
        # Réapparu : déjà vu plus tôt, absent de la période immédiatement précédente disponible.
        reapparu = bool(in_history and immediate_prev is not None and ncg not in prev_set)
        covered_by_class = (not mapped) and bool(ncg) and ncg[0] in class_prefixes
        cells = mapped_index.get(ncg, [])
        first = first_seen.get(ncg)
        last = last_seen.get(ncg)
        item = {
            "ncg": ncg,
            "libelle": row.libelle,
            "tot_debit": str(row.tot_debit),
            "tot_credit": str(row.tot_credit),
            "status": status,
            "present_zero": present_zero,
            "reapparu": reapparu,
            "covered_by_class": covered_by_class,
            "cells": cells,
            "first_seen_period": None if first is None else _period_label(*first),
            "last_seen_period": None if last is None else _period_label(*last),
            "immediate_previous_period": (
                None
                if immediate_prev is None
                else _period_label(immediate_prev.period_year, immediate_prev.period_month)
            ),
        }
        items.append(item)
        counts[status] += 1
        if present_zero:
            counts["present_zero"] += 1
        if reapparu:
            counts["reapparu"] += 1

    absents: list[dict[str, Any]] = []
    current_set = current.ncg_set
    for ncg in sorted(mapped_set | hist_union):
        if ncg in current_set:
            continue
        mapped = ncg in mapped_set
        status = STATUS_ABSENT_MAPPE if mapped else STATUS_ABSENT_HISTORIQUE
        first = first_seen.get(ncg)
        last = last_seen.get(ncg)
        absents.append(
            {
                "ncg": ncg,
                "status": status,
                "cells": mapped_index.get(ncg, []),
                "covered_by_class": (not mapped) and bool(ncg) and ncg[0] in class_prefixes,
                "first_seen_period": None if first is None else _period_label(*first),
                "last_seen_period": None if last is None else _period_label(*last),
            }
        )
        counts[status] += 1

    return {
        "has_validated_det": True,
        "period_year": current.period_year,
        "period_month": current.period_month,
        "campaign_id": str(current.campaign_id),
        "import_id": str(current.import_id),
        "ncg_count": len(current.ncg_set),
        "history_period_count": len(history_sorted),
        "available_periods": available_periods,
        "counts": counts,
        "items": items,
        "absents": absents,
        "orientation_auto": False,
        "note": (
            "Rapport descriptif. Aucune orientation automatique vers une cellule SM. "
            "L'écart de bilan reste un contrôle, hors cellules métier."
        ),
    }


def structure_summary(report: dict[str, Any]) -> dict[str, Any]:
    """Résumé compact pour control_report à la confirmation d'import."""
    return {
        "has_validated_det": report.get("has_validated_det"),
        "period_year": report.get("period_year"),
        "period_month": report.get("period_month"),
        "import_id": report.get("import_id"),
        "ncg_count": report.get("ncg_count"),
        "history_period_count": report.get("history_period_count"),
        "counts": report.get("counts"),
        "nouveaux": [i["ncg"] for i in report.get("items") or [] if i.get("status") == STATUS_NOUVEAU],
        "reapparus": [i["ncg"] for i in report.get("items") or [] if i.get("reapparu")],
        "absents_mappe": [
            a["ncg"] for a in report.get("absents") or [] if a.get("status") == STATUS_ABSENT_MAPPE
        ][:40],
        "orientation_auto": False,
    }


async def _validated_det_import(
    db: AsyncSession, campaign_id: UUID
) -> RbcmImport | None:
    return await db.scalar(
        select(RbcmImport).where(
            RbcmImport.campaign_id == campaign_id,
            RbcmImport.file_type == "BAL_DET",
            RbcmImport.status == "VALIDATED",
        )
    )


async def _load_snapshot(
    db: AsyncSession, campaign: RbcmCampaign, imp: RbcmImport
) -> PeriodSnapshot:
    rows = list(
        (
            await db.scalars(
                select(RbcmBalanceNcg).where(
                    RbcmBalanceNcg.import_id == imp.id,
                    RbcmBalanceNcg.source == "BAL_DET",
                )
            )
        ).all()
    )
    by_ncg: dict[str, PeriodNcgRow] = {}
    for row in rows:
        code = canonical_ncg(row.ncg)
        if not code:
            continue
        prev = by_ncg.get(code)
        if prev is None:
            by_ncg[code] = PeriodNcgRow(
                ncg=code,
                libelle=row.libelle,
                tot_debit=row.tot_debit or ZERO,
                tot_credit=row.tot_credit or ZERO,
            )
        else:
            by_ncg[code] = PeriodNcgRow(
                ncg=code,
                libelle=row.libelle or prev.libelle,
                tot_debit=(prev.tot_debit + (row.tot_debit or ZERO)),
                tot_credit=(prev.tot_credit + (row.tot_credit or ZERO)),
            )
    return PeriodSnapshot(
        period_year=campaign.period_year,
        period_month=campaign.period_month,
        campaign_id=campaign.id,
        import_id=imp.id,
        rows=by_ncg,
    )


async def load_structure_report(
    db: AsyncSession,
    *,
    campaign: RbcmCampaign,
) -> dict[str, Any]:
    """Charge les BAL DET validées et produit le rapport pour la campagne."""
    current_imp = await _validated_det_import(db, campaign.id)
    current: PeriodSnapshot | None = None
    if current_imp is not None:
        current = await _load_snapshot(db, campaign, current_imp)

    # Toutes les campagnes avec BAL DET validée, période strictement antérieure.
    # Timeline = période métier, jamais created_at.
    prior_campaigns = list(
        (
            await db.scalars(
                select(RbcmCampaign).where(
                    (RbcmCampaign.period_year < campaign.period_year)
                    | (
                        (RbcmCampaign.period_year == campaign.period_year)
                        & (RbcmCampaign.period_month < campaign.period_month)
                    )
                )
            )
        ).all()
    )
    history: list[PeriodSnapshot] = []
    # Une seule BAL DET VALIDATED par campagne / période.
    seen_periods: set[int] = set()
    for prior in sorted(
        prior_campaigns,
        key=lambda c: (c.period_year, c.period_month, c.campaign_version),
    ):
        key = prior.period_year * 12 + prior.period_month
        if key in seen_periods:
            # Plusieurs versions de campagne : garder la dernière version traitée
            # (tri croissant → la plus récente version écrase).
            history = [h for h in history if h.period_key != key]
        imp = await _validated_det_import(db, prior.id)
        if imp is None:
            continue
        history.append(await _load_snapshot(db, prior, imp))
        seen_periods.add(key)

    return build_structure_report(current=current, history=history)


async def attach_structure_summary_to_import(
    db: AsyncSession,
    *,
    campaign: RbcmCampaign,
    imp: RbcmImport,
) -> dict[str, Any]:
    """Attache un résumé ncg_structure au control_report (append-only, hors BAL)."""
    report = await load_structure_report(db, campaign=campaign)
    summary = structure_summary(report)
    payload = dict(imp.control_report or {})
    payload["ncg_structure"] = summary
    imp.control_report = payload
    await db.flush()
    return summary
