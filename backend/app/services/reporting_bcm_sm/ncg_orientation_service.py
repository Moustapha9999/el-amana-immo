"""Orientations NCG → cellules SM — cycle de validation, fusion catalogue unique.

Les orientations VALIDE_ACTIF sont fusionnées dans le catalogue central au calcul.
Aucun second moteur. Aucune activation automatique. Aucune règle mensuelle.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import User
from app.models.reporting_bcm_sm import RbcmBalanceNcg, RbcmCampaign, RbcmImport, RbcmNcgOrientation
from app.services.reporting_bcm_sm.constants import (
    NCG_ORIENTATION_CURRENCIES,
    NCG_ORIENTATION_OPERATIONS,
    NCG_ORIENTATION_RESIDENCES,
    NCG_ORIENTATION_SHEETS,
    NCG_ORIENTATION_STATUSES,
)
from app.services.reporting_bcm_sm.engine.det_basis import (
    BASIS_CREDIT,
    BASIS_DEBIT,
    canonical_ncg,
)
from app.services.reporting_bcm_sm.engine.rules_catalog import (
    ALL_RULES,
    AUTO_KEYS,
    RULES_BY_KEY,
    CellRule,
    Term,
)
from app.services.reporting_bcm_sm.ncg_structure_service import load_structure_report

STATUS_DRAFT = "A_ORIENTER"
STATUS_PENDING = "EN_ATTENTE_VALIDATION"
STATUS_ACTIVE = "VALIDE_ACTIF"
STATUS_REJECTED = "REJETE"
STATUS_DISABLED = "DESACTIVE"

_OPEN = frozenset({STATUS_DRAFT, STATUS_PENDING, STATUS_ACTIVE})

_OP_TO_TERM = {
    "ADD_DEBIT": (BASIS_DEBIT, 1),
    "ADD_CREDIT": (BASIS_CREDIT, 1),
    "SUB_DEBIT": (BASIS_DEBIT, -1),
    "SUB_CREDIT": (BASIS_CREDIT, -1),
}


def operation_to_term_parts(operation: str) -> tuple[str, int]:
    try:
        return _OP_TO_TERM[operation]
    except KeyError as exc:
        raise AppError(
            f"Opération d'orientation inconnue : {operation}",
            status_code=422,
            code="NCG_ORI_OPERATION",
        ) from exc


def sheet_from_cell_ref(cell_ref: str) -> str:
    if cell_ref.startswith("A:"):
        return "ETAT_A"
    if cell_ref.startswith("B:"):
        return "ETAT_B"
    raise AppError(
        "La cellule doit appartenir à ETAT A ou ETAT B (ex. A:402:D).",
        status_code=422,
        code="NCG_ORI_SHEET",
    )


def residence_from_cell_ref(cell_ref: str) -> str:
    parts = cell_ref.split(":")
    if len(parts) != 3:
        return "ALL"
    col = parts[2]
    # ETAT A : D/E ≈ résidents ouguiyas/autres ; F/G ≈ devises.
    # ETAT B : H = non-résidents (convention moteur).
    if parts[0] == "B" and col == "H":
        return "NON_RESIDENTS"
    if col in {"D", "E", "F", "G", "C"}:
        return "RESIDENTS"
    return "ALL"


def catalog_target_cells() -> list[dict[str, Any]]:
    """Cellules AUTO du catalogue central pouvant recevoir une orientation."""
    out: list[dict[str, Any]] = []
    for key in AUTO_KEYS:
        rule = RULES_BY_KEY[key]
        if not key.startswith(("A:", "B:")):
            continue
        out.append(
            {
                "cell_ref": key,
                "sheet": sheet_from_cell_ref(key),
                "origin": rule.origin,
                "notes": rule.notes or None,
                "existing_ncgs": sorted(
                    {canonical_ncg(n) for t in rule.terms for n in t.ncgs if canonical_ncg(n)}
                ),
            }
        )
    return out


def static_catalog_hits(ncg: str) -> list[dict[str, Any]]:
    code = canonical_ncg(ncg)
    hits: list[dict[str, Any]] = []
    for rule in ALL_RULES:
        for term in rule.terms:
            if code in {canonical_ncg(n) for n in term.ncgs}:
                hits.append(
                    {
                        "cell_ref": rule.key,
                        "basis": term.basis,
                        "sign": term.sign,
                        "currency": term.currency,
                        "source": "rules_catalog",
                    }
                )
    return hits


def merge_active_orientations(
    base_rules: tuple[CellRule, ...] = ALL_RULES,
    orientations: list[RbcmNcgOrientation] | list[dict[str, Any]] | None = None,
) -> tuple[CellRule, ...]:
    """Fusionne les orientations actives dans le catalogue central (même moteur)."""
    if not orientations:
        return base_rules
    by_key: dict[str, CellRule] = {r.key: r for r in base_rules}
    order = [r.key for r in base_rules]
    for raw in orientations:
        if isinstance(raw, dict):
            cell_ref = raw.get("cell_ref")
            ncg = canonical_ncg(raw.get("ncg"))
            operation = raw.get("operation")
            currency = (raw.get("currency_scope") or "ALL").upper()
            status = raw.get("status")
        else:
            cell_ref = raw.cell_ref
            ncg = canonical_ncg(raw.ncg)
            operation = raw.operation
            currency = (raw.currency_scope or "ALL").upper()
            status = raw.status
        if status != STATUS_ACTIVE:
            continue
        if not cell_ref or not ncg or not operation:
            continue
        if cell_ref not in by_key:
            continue
        basis, sign = operation_to_term_parts(operation)
        extra = Term(ncgs=(ncg,), basis=basis, sign=sign, currency=currency)
        rule = by_key[cell_ref]
        # Évite de dupliquer un terme déjà présent (statique ou déjà fusionné).
        duplicate = False
        for term in rule.terms:
            if (
                ncg in {canonical_ncg(n) for n in term.ncgs}
                and term.basis == basis
                and term.sign == sign
                and (term.currency or "ALL").upper() == currency
            ):
                duplicate = True
                break
        if duplicate:
            continue
        by_key[cell_ref] = replace(rule, terms=rule.terms + (extra,))
        note = (rule.notes or "").strip()
        tag = f"ori:{ncg}:{operation}"
        if tag not in note:
            by_key[cell_ref] = replace(
                by_key[cell_ref],
                notes=(f"{note} | {tag}" if note else tag),
            )
    return tuple(by_key[k] for k in order if k in by_key)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require(value: str | None, *, code: str, message: str) -> str:
    if not value:
        raise AppError(message, status_code=422, code=code)
    return value


async def list_orientations(
    db: AsyncSession,
    *,
    ncg: str | None = None,
    status: str | None = None,
    cell_ref: str | None = None,
) -> list[RbcmNcgOrientation]:
    q = select(RbcmNcgOrientation).order_by(RbcmNcgOrientation.created_at.desc())
    if ncg:
        q = q.where(RbcmNcgOrientation.ncg == canonical_ncg(ncg))
    if status:
        q = q.where(RbcmNcgOrientation.status == status)
    if cell_ref:
        q = q.where(RbcmNcgOrientation.cell_ref == cell_ref)
    return list((await db.scalars(q)).all())


async def list_active_orientations(db: AsyncSession) -> list[RbcmNcgOrientation]:
    return list(
        (
            await db.scalars(
                select(RbcmNcgOrientation).where(RbcmNcgOrientation.status == STATUS_ACTIVE)
            )
        ).all()
    )


async def get_orientation(db: AsyncSession, orientation_id: UUID) -> RbcmNcgOrientation:
    row = await db.get(RbcmNcgOrientation, orientation_id)
    if row is None:
        raise AppError("Orientation introuvable", status_code=404, code="NCG_ORI_NOT_FOUND")
    return row


async def _find_open_duplicate(
    db: AsyncSession,
    *,
    ncg: str,
    cell_ref: str,
    operation: str,
    currency_scope: str,
    exclude_id: UUID | None = None,
) -> RbcmNcgOrientation | None:
    q = select(RbcmNcgOrientation).where(
        RbcmNcgOrientation.ncg == ncg,
        RbcmNcgOrientation.cell_ref == cell_ref,
        RbcmNcgOrientation.operation == operation,
        RbcmNcgOrientation.currency_scope == currency_scope,
        RbcmNcgOrientation.status.in_(tuple(_OPEN)),
    )
    if exclude_id is not None:
        q = q.where(RbcmNcgOrientation.id != exclude_id)
    return await db.scalar(q.limit(1))


def _assert_no_static_conflict(ncg: str, cell_ref: str, operation: str, currency_scope: str) -> None:
    basis, sign = operation_to_term_parts(operation)
    rule = RULES_BY_KEY.get(cell_ref)
    if rule is None:
        raise AppError(
            f"Cellule {cell_ref} absente du catalogue central AUTO.",
            status_code=422,
            code="NCG_ORI_CELL_UNKNOWN",
        )
    if cell_ref not in AUTO_KEYS:
        raise AppError(
            f"La cellule {cell_ref} n'est pas une cellule automatique orientable.",
            status_code=422,
            code="NCG_ORI_CELL_NOT_AUTO",
        )
    for term in rule.terms:
        if ncg not in {canonical_ncg(n) for n in term.ncgs}:
            continue
        if (
            term.basis == basis
            and term.sign == sign
            and (term.currency or "ALL").upper() == currency_scope.upper()
        ):
            raise AppError(
                f"Conflit : {ncg} est déjà dans le catalogue pour {cell_ref} "
                f"({operation}, {currency_scope}).",
                status_code=409,
                code="NCG_ORI_CATALOG_CONFLICT",
            )


async def prepare_orientation(
    db: AsyncSession,
    *,
    user: User,
    ncg: str,
    sheet: str,
    cell_ref: str | None = None,
    operation: str | None = None,
    currency_scope: str = "ALL",
    residence_scope: str | None = None,
    ncg_libelle: str | None = None,
    notes: str | None = None,
) -> RbcmNcgOrientation:
    code = canonical_ncg(ncg)
    if not code:
        raise AppError("NCG invalide", status_code=422, code="NCG_ORI_NCG")
    sheet = _require(sheet, code="NCG_ORI_SHEET", message="État requis (ETAT_A ou ETAT_B).")
    if sheet not in NCG_ORIENTATION_SHEETS:
        raise AppError("État invalide", status_code=422, code="NCG_ORI_SHEET")
    if currency_scope not in NCG_ORIENTATION_CURRENCIES:
        raise AppError("Devise invalide", status_code=422, code="NCG_ORI_CURRENCY")
    if operation is not None and operation not in NCG_ORIENTATION_OPERATIONS:
        raise AppError("Opération invalide", status_code=422, code="NCG_ORI_OPERATION")

    resolved_residence = residence_scope
    if cell_ref:
        if sheet_from_cell_ref(cell_ref) != sheet:
            raise AppError(
                "L'état sélectionné ne correspond pas à la cellule.",
                status_code=422,
                code="NCG_ORI_SHEET_MISMATCH",
            )
        resolved_residence = residence_scope or residence_from_cell_ref(cell_ref)
        if operation:
            _assert_no_static_conflict(code, cell_ref, operation, currency_scope)
            dup = await _find_open_duplicate(
                db,
                ncg=code,
                cell_ref=cell_ref,
                operation=operation,
                currency_scope=currency_scope,
            )
            if dup is not None:
                raise AppError(
                    "Orientation déjà ouverte pour ce NCG, cette cellule et cette opération.",
                    status_code=409,
                    code="NCG_ORI_DUPLICATE",
                )
    if resolved_residence is None:
        resolved_residence = "RESIDENTS"
    if resolved_residence not in NCG_ORIENTATION_RESIDENCES:
        raise AppError("Catégorie invalide", status_code=422, code="NCG_ORI_RESIDENCE")

    row = RbcmNcgOrientation(
        ncg=code,
        ncg_libelle=ncg_libelle,
        sheet=sheet,
        cell_ref=cell_ref,
        currency_scope=currency_scope,
        residence_scope=resolved_residence,
        operation=operation,
        status=STATUS_DRAFT,
        notes=notes,
        prepared_by_id=user.id,
        prepared_at=_now(),
    )
    db.add(row)
    await db.flush()
    return row


async def update_orientation(
    db: AsyncSession,
    *,
    orientation: RbcmNcgOrientation,
    user: User,
    cell_ref: str | None = None,
    operation: str | None = None,
    currency_scope: str | None = None,
    residence_scope: str | None = None,
    sheet: str | None = None,
    ncg_libelle: str | None = None,
    notes: str | None = None,
    clear_destination: bool = False,
) -> RbcmNcgOrientation:
    if orientation.status not in {STATUS_DRAFT, STATUS_PENDING}:
        raise AppError(
            "Seule une orientation à orienter ou en attente peut être modifiée.",
            status_code=409,
            code="NCG_ORI_LOCKED",
        )
    prev_cell = orientation.cell_ref
    prev_op = orientation.operation
    prev_status = orientation.status

    if sheet is not None:
        if sheet not in NCG_ORIENTATION_SHEETS:
            raise AppError("État invalide", status_code=422, code="NCG_ORI_SHEET")
        orientation.sheet = sheet
    if clear_destination:
        orientation.cell_ref = None
        orientation.operation = None
    else:
        if cell_ref is not None:
            orientation.cell_ref = cell_ref
            if sheet_from_cell_ref(cell_ref) != orientation.sheet:
                orientation.sheet = sheet_from_cell_ref(cell_ref)
            if residence_scope is None:
                orientation.residence_scope = residence_from_cell_ref(cell_ref)
        if operation is not None:
            if operation not in NCG_ORIENTATION_OPERATIONS:
                raise AppError("Opération invalide", status_code=422, code="NCG_ORI_OPERATION")
            orientation.operation = operation
    if currency_scope is not None:
        if currency_scope not in NCG_ORIENTATION_CURRENCIES:
            raise AppError("Devise invalide", status_code=422, code="NCG_ORI_CURRENCY")
        orientation.currency_scope = currency_scope
    if residence_scope is not None:
        if residence_scope not in NCG_ORIENTATION_RESIDENCES:
            raise AppError("Catégorie invalide", status_code=422, code="NCG_ORI_RESIDENCE")
        orientation.residence_scope = residence_scope
    if ncg_libelle is not None:
        orientation.ncg_libelle = ncg_libelle
    if notes is not None:
        orientation.notes = notes

    if orientation.cell_ref and orientation.operation:
        _assert_no_static_conflict(
            orientation.ncg,
            orientation.cell_ref,
            orientation.operation,
            orientation.currency_scope,
        )
        dup = await _find_open_duplicate(
            db,
            ncg=orientation.ncg,
            cell_ref=orientation.cell_ref,
            operation=orientation.operation,
            currency_scope=orientation.currency_scope,
            exclude_id=orientation.id,
        )
        if dup is not None:
            raise AppError(
                "Orientation déjà ouverte pour ce NCG, cette cellule et cette opération.",
                status_code=409,
                code="NCG_ORI_DUPLICATE",
            )

    # Traçabilité correction : ancienne → nouvelle (notes append-only).
    if (
        prev_cell != orientation.cell_ref
        or prev_op != orientation.operation
        or clear_destination
    ):
        stamp = _now().isoformat()
        delta = (
            f"[correction {stamp} par {user.id}] "
            f"statut {prev_status} → {orientation.status} ; "
            f"cellule {prev_cell or '—'} → {orientation.cell_ref or '—'} ; "
            f"opération {prev_op or '—'} → {orientation.operation or '—'}"
        )
        orientation.notes = f"{orientation.notes}\n{delta}" if orientation.notes else delta
        # Correction d'une proposition en attente → repasse « À orienter » (re-soumission).
        if prev_status == STATUS_PENDING:
            orientation.status = STATUS_DRAFT
            orientation.submitted_by_id = None
            orientation.submitted_at = None

    orientation.prepared_by_id = user.id
    orientation.prepared_at = _now()
    await db.flush()
    return orientation


async def defer_orientation(
    db: AsyncSession,
    *,
    user: User,
    ncg: str,
    ncg_libelle: str | None = None,
    notes: str | None = None,
) -> RbcmNcgOrientation:
    """Marque un NCG « sans orientation » (À orienter, sans cellule) — décision différée."""
    code = canonical_ncg(ncg)
    open_rows = [
        o
        for o in await list_orientations(db, ncg=code)
        if o.status in {STATUS_DRAFT, STATUS_PENDING, STATUS_ACTIVE}
    ]
    for row in open_rows:
        if row.status == STATUS_ACTIVE:
            raise AppError(
                "Une orientation active existe déjà : désactivez-la avant de différer.",
                status_code=409,
                code="NCG_ORI_ACTIVE_EXISTS",
            )
        if row.status == STATUS_PENDING:
            raise AppError(
                "Une proposition est en attente : rejetez-la ou corrigez-la avant de différer.",
                status_code=409,
                code="NCG_ORI_PENDING_EXISTS",
            )
        return await update_orientation(
            db,
            orientation=row,
            user=user,
            clear_destination=True,
            notes=notes
            or "Décision différée — destination métier non connue. Aucune cellule attribuée.",
        )
    return await prepare_orientation(
        db,
        user=user,
        ncg=code,
        sheet="ETAT_A",
        cell_ref=None,
        operation=None,
        currency_scope="ALL",
        residence_scope="RESIDENTS",
        ncg_libelle=ncg_libelle,
        notes=notes
        or "Décision différée — destination métier non connue. Aucune cellule attribuée.",
    )

async def submit_orientation(
    db: AsyncSession,
    *,
    orientation: RbcmNcgOrientation,
    user: User,
    comment: str | None = None,
) -> RbcmNcgOrientation:
    if orientation.status != STATUS_DRAFT:
        raise AppError(
            "Seule une orientation « À orienter » peut être soumise.",
            status_code=409,
            code="NCG_ORI_BAD_STATUS",
        )
    if not orientation.cell_ref or not orientation.operation:
        raise AppError(
            "Cellule et opération requises avant soumission.",
            status_code=422,
            code="NCG_ORI_INCOMPLETE",
        )
    _assert_no_static_conflict(
        orientation.ncg,
        orientation.cell_ref,
        orientation.operation,
        orientation.currency_scope,
    )
    dup = await _find_open_duplicate(
        db,
        ncg=orientation.ncg,
        cell_ref=orientation.cell_ref,
        operation=orientation.operation,
        currency_scope=orientation.currency_scope,
        exclude_id=orientation.id,
    )
    if dup is not None and dup.id != orientation.id:
        raise AppError(
            "Orientation déjà ouverte pour ce NCG, cette cellule et cette opération.",
            status_code=409,
            code="NCG_ORI_DUPLICATE",
        )
    orientation.status = STATUS_PENDING
    orientation.submitted_by_id = user.id
    orientation.submitted_at = _now()
    if comment:
        orientation.decision_comment = comment
    await db.flush()
    return orientation


async def validate_orientation(
    db: AsyncSession,
    *,
    orientation: RbcmNcgOrientation,
    user: User,
    comment: str | None = None,
) -> RbcmNcgOrientation:
    if orientation.status != STATUS_PENDING:
        raise AppError(
            "Seule une orientation en attente peut être validée.",
            status_code=409,
            code="NCG_ORI_BAD_STATUS",
        )
    if orientation.submitted_by_id and orientation.submitted_by_id == user.id:
        raise AppError(
            "Séparation des rôles : le soumissionnaire ne peut pas valider sa propre orientation.",
            status_code=403,
            code="NCG_ORI_SAME_ACTOR",
        )
    if not orientation.cell_ref or not orientation.operation:
        raise AppError("Orientation incomplète", status_code=422, code="NCG_ORI_INCOMPLETE")
    _assert_no_static_conflict(
        orientation.ncg,
        orientation.cell_ref,
        orientation.operation,
        orientation.currency_scope,
    )
    orientation.status = STATUS_ACTIVE
    orientation.validated_by_id = user.id
    orientation.validated_at = _now()
    if comment:
        orientation.decision_comment = comment
    await db.flush()
    return orientation


async def reject_orientation(
    db: AsyncSession,
    *,
    orientation: RbcmNcgOrientation,
    user: User,
    comment: str | None = None,
) -> RbcmNcgOrientation:
    if orientation.status not in {STATUS_DRAFT, STATUS_PENDING}:
        raise AppError(
            "Seule une orientation à orienter ou en attente peut être rejetée.",
            status_code=409,
            code="NCG_ORI_BAD_STATUS",
        )
    motif = (comment or "").strip()
    if not motif:
        raise AppError(
            "Motif de rejet obligatoire.",
            status_code=422,
            code="NCG_ORI_REJECT_REASON",
        )
    orientation.status = STATUS_REJECTED
    orientation.rejected_by_id = user.id
    orientation.rejected_at = _now()
    orientation.decision_comment = motif
    await db.flush()
    return orientation

async def deactivate_orientation(
    db: AsyncSession,
    *,
    orientation: RbcmNcgOrientation,
    user: User,
    comment: str | None = None,
) -> RbcmNcgOrientation:
    if orientation.status != STATUS_ACTIVE:
        raise AppError(
            "Seule une orientation active peut être désactivée.",
            status_code=409,
            code="NCG_ORI_BAD_STATUS",
        )
    orientation.status = STATUS_DISABLED
    orientation.deactivated_by_id = user.id
    orientation.deactivated_at = _now()
    if comment:
        orientation.decision_comment = comment
    await db.flush()
    return orientation


async def ncg_detail_for_campaign(
    db: AsyncSession,
    *,
    campaign: RbcmCampaign,
    ncg: str,
) -> dict[str, Any]:
    """Fiche NCG : structure, soldes historiques, mappings catalogue, orientations."""
    code = canonical_ncg(ncg)
    structure = await load_structure_report(db, campaign=campaign)
    item = next((i for i in structure.get("items") or [] if i.get("ncg") == code), None)
    absent = next((a for a in structure.get("absents") or [] if a.get("ncg") == code), None)

    # Soldes par période (BAL DET validées).
    camps = list((await db.scalars(select(RbcmCampaign))).all())
    balances: list[dict[str, Any]] = []
    for camp in sorted(camps, key=lambda c: (c.period_year, c.period_month)):
        imp = await db.scalar(
            select(RbcmImport).where(
                RbcmImport.campaign_id == camp.id,
                RbcmImport.file_type == "BAL_DET",
                RbcmImport.status == "VALIDATED",
            )
        )
        if imp is None:
            continue
        row = await db.scalar(
            select(RbcmBalanceNcg).where(
                RbcmBalanceNcg.import_id == imp.id,
                RbcmBalanceNcg.source == "BAL_DET",
                RbcmBalanceNcg.ncg == code,
            )
        )
        balances.append(
            {
                "period_year": camp.period_year,
                "period_month": camp.period_month,
                "label": f"{camp.period_month:02d}/{camp.period_year}",
                "present": row is not None,
                "tot_debit": None if row is None else str(row.tot_debit),
                "tot_credit": None if row is None else str(row.tot_credit),
                "libelle": None if row is None else row.libelle,
            }
        )

    oris = await list_orientations(db, ncg=code)
    return {
        "ncg": code,
        "libelle": (item or {}).get("libelle")
        or (balances[-1]["libelle"] if balances and balances[-1]["present"] else None),
        "detection": item or absent,
        "structure_status": (item or {}).get("status") or (absent or {}).get("status"),
        "balances": balances,
        "catalog_mappings": static_catalog_hits(code),
        "orientations": [_ori_dict(o) for o in oris],
        "target_cells": catalog_target_cells(),
        "operations": list(NCG_ORIENTATION_OPERATIONS),
        "currency_scopes": list(NCG_ORIENTATION_CURRENCIES),
        "residence_scopes": list(NCG_ORIENTATION_RESIDENCES),
        "sheets": list(NCG_ORIENTATION_SHEETS),
        "statuses": list(NCG_ORIENTATION_STATUSES),
        "orientation_auto": False,
        "note": (
            "La création d'une orientation ne l'active jamais. "
            "Validation explicite requise (mapping.validate). "
            "Aucune injection d'écart de bilan."
        ),
    }


def _ori_dict(o: RbcmNcgOrientation) -> dict[str, Any]:
    return {
        "id": str(o.id),
        "ncg": o.ncg,
        "ncg_libelle": o.ncg_libelle,
        "sheet": o.sheet,
        "cell_ref": o.cell_ref,
        "currency_scope": o.currency_scope,
        "residence_scope": o.residence_scope,
        "operation": o.operation,
        "status": o.status,
        "notes": o.notes,
        "prepared_by_id": None if o.prepared_by_id is None else str(o.prepared_by_id),
        "prepared_at": None if o.prepared_at is None else o.prepared_at.isoformat(),
        "submitted_by_id": None if o.submitted_by_id is None else str(o.submitted_by_id),
        "submitted_at": None if o.submitted_at is None else o.submitted_at.isoformat(),
        "validated_by_id": None if o.validated_by_id is None else str(o.validated_by_id),
        "validated_at": None if o.validated_at is None else o.validated_at.isoformat(),
        "rejected_by_id": None if o.rejected_by_id is None else str(o.rejected_by_id),
        "rejected_at": None if o.rejected_at is None else o.rejected_at.isoformat(),
        "deactivated_by_id": None if o.deactivated_by_id is None else str(o.deactivated_by_id),
        "deactivated_at": None if o.deactivated_at is None else o.deactivated_at.isoformat(),
        "decision_comment": o.decision_comment,
        "supersedes_id": None if o.supersedes_id is None else str(o.supersedes_id),
        "created_at": o.created_at.isoformat() if o.created_at else None,
        "updated_at": o.updated_at.isoformat() if getattr(o, "updated_at", None) else None,
    }
