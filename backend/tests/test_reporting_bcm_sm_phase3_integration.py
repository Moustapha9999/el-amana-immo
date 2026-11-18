"""PHASE 3 — Intégration Structure NCG → Orientation → Moteur SM (données isolées).

Aucun mapping métier réel pour 847000. Les orientations de test utilisent des NCG
synthétiques et ne laissent rien actif dans le catalogue statique.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import AppError
from app.services.reporting_bcm_sm.engine.det_basis import DetLine
from app.services.reporting_bcm_sm.engine.evaluate import evaluate_sm
from app.services.reporting_bcm_sm.engine.rules_catalog import (
    ADJUST_KEYS,
    ALL_RULES,
    MANUAL_KEYS,
    RULES_BY_KEY,
    catalog_stats,
)
from app.services.reporting_bcm_sm.ncg_orientation_service import (
    STATUS_ACTIVE,
    STATUS_DISABLED,
    STATUS_DRAFT,
    STATUS_PENDING,
    STATUS_REJECTED,
    _assert_no_static_conflict,
    merge_active_orientations,
    operation_to_term_parts,
    static_catalog_hits,
    validate_orientation,
)
from app.services.reporting_bcm_sm.ncg_structure_service import (
    PeriodNcgRow,
    PeriodSnapshot,
    STATUS_CONNU_NON_ORIENTE,
    STATUS_DEJA_MAPPE,
    STATUS_NOUVEAU,
    build_structure_report,
)


TEST_CELL = "A:408:D"
TEST_NCG = "999847"  # isolé — jamais 847000 avec cellule métier
REAL_NEW_NCG = "847000"


def _ori(**kwargs):
    base = {
        "id": uuid4(),
        "ncg": TEST_NCG,
        "cell_ref": TEST_CELL,
        "operation": "ADD_CREDIT",
        "currency_scope": "ALL",
        "status": STATUS_ACTIVE,
        "submitted_by_id": uuid4(),
        "validated_by_id": None,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def _row(ncg: str, deb: str = "0", cre: str = "0", lib: str | None = None) -> PeriodNcgRow:
    return PeriodNcgRow(
        ncg=ncg,
        libelle=lib or ncg,
        tot_debit=Decimal(deb),
        tot_credit=Decimal(cre),
    )


def _snap(year: int, month: int, rows: dict[str, PeriodNcgRow]) -> PeriodSnapshot:
    return PeriodSnapshot(
        period_year=year,
        period_month=month,
        campaign_id=uuid4(),
        import_id=uuid4(),
        rows=rows,
    )


def test_catalog_non_regression_89_rules():
    stats = catalog_stats()
    assert len(ALL_RULES) == 89
    assert stats["all"] == 89
    assert stats["auto"] == 45
    assert stats["manual"] == 5
    assert stats["adjust"] == 3
    assert len(MANUAL_KEYS) == 5
    assert len(ADJUST_KEYS) == 3


def test_847000_detected_nouveau_october_isolated():
    """Scénario 1 : 847000 nouveau en octobre (jeu isolé sept/oct)."""
    mapped = {
        "210000": [{"cell_ref": "A:131:D", "basis": "DEBIT", "sign": 1}],
        "315100": [{"cell_ref": "A:402:D", "basis": "CREDIT", "sign": 1}],
    }
    sept = _snap(
        2026,
        9,
        {
            "210000": _row("210000", "100"),
            "315100": _row("315100", "0", "50"),
        },
    )
    octo = _snap(
        2026,
        10,
        {
            "210000": _row("210000", "110"),
            "315100": _row("315100", "0", "55"),
            REAL_NEW_NCG: _row(REAL_NEW_NCG, "2785612", "0", "MOINS VALUES  CESSION"),
        },
    )
    report = build_structure_report(
        current=octo,
        history=[sept],
        mapped_index=mapped,
        class_prefixes=frozenset({"6", "7", "8"}),
    )
    by = {i["ncg"]: i for i in report["items"]}
    assert by[REAL_NEW_NCG]["status"] == STATUS_NOUVEAU
    assert by[REAL_NEW_NCG]["covered_by_class"] is True
    assert by["210000"]["status"] == STATUS_DEJA_MAPPE
    assert by["315100"]["status"] == STATUS_DEJA_MAPPE
    assert static_catalog_hits(REAL_NEW_NCG) == []


def test_847000_without_decision_not_in_active_catalog():
    """Scénario 2 : sans décision métier, 847000 n'entre pas dans le catalogue actif."""
    draft = _ori(ncg=REAL_NEW_NCG, cell_ref=None, operation=None, status=STATUS_DRAFT)
    pending_incomplete = _ori(
        ncg=REAL_NEW_NCG, cell_ref=None, operation=None, status=STATUS_PENDING
    )
    merged = merge_active_orientations(orientations=[draft, pending_incomplete])
    rule = next(r for r in merged if r.key == TEST_CELL)
    assert not any(REAL_NEW_NCG in t.ncgs for t in rule.terms)
    assert RULES_BY_KEY[TEST_CELL].terms == next(
        r for r in ALL_RULES if r.key == TEST_CELL
    ).terms


def test_full_cycle_isolated_ncg_prepare_to_deactivate():
    """Scénarios 3–8 : cycle complet sur NCG de test isolé (jamais 847000 métier)."""
    lines = [
        DetLine(TEST_NCG, "1", "test", "MRU", Decimal("0"), Decimal("250")),
        DetLine("351047", "2", "base", "MRU", Decimal("0"), Decimal("5")),
    ]
    base = evaluate_sm(lines)
    assert base[TEST_CELL].calculated == Decimal("5.00")

    # 3–4 : préparation / attente → non intégrée
    for status in (STATUS_DRAFT, STATUS_PENDING, STATUS_REJECTED):
        merged = merge_active_orientations(
            orientations=[_ori(status=status, operation="ADD_CREDIT")]
        )
        with_pending = evaluate_sm(lines, rules=merged)
        assert with_pending[TEST_CELL].calculated == Decimal("5.00")

    # 5–7 : validation → intégration catalogue + montant
    active = _ori(status=STATUS_ACTIVE, operation="ADD_CREDIT")
    merged_active = merge_active_orientations(orientations=[active])
    rule = next(r for r in merged_active if r.key == TEST_CELL)
    assert any(TEST_NCG in t.ncgs for t in rule.terms)
    # ALL_RULES objet inchangé
    assert not any(TEST_NCG in t.ncgs for t in RULES_BY_KEY[TEST_CELL].terms)
    with_active = evaluate_sm(lines, rules=merged_active)
    assert with_active[TEST_CELL].calculated == Decimal("255.00")  # 5 + 250 CRE

    # 8 : désactivation → plus appliquée, historique représenté par l'objet DESACTIVE
    disabled = _ori(
        id=active.id,
        status=STATUS_DISABLED,
        operation="ADD_CREDIT",
        deactivated_by_id=uuid4(),
    )
    merged_off = merge_active_orientations(orientations=[disabled, active])
    # Si on passe seulement disabled (cas réel après update statut) :
    merged_off = merge_active_orientations(orientations=[disabled])
    with_off = evaluate_sm(lines, rules=merged_off)
    assert with_off[TEST_CELL].calculated == Decimal("5.00")
    assert disabled.status == STATUS_DISABLED
    assert disabled.id == active.id


@pytest.mark.parametrize(
    "operation,debit,credit,expected_delta",
    [
        ("ADD_DEBIT", "40", "0", Decimal("40")),
        ("ADD_CREDIT", "0", "40", Decimal("40")),
        ("SUB_DEBIT", "40", "0", Decimal("-40")),
        ("SUB_CREDIT", "0", "40", Decimal("-40")),
    ],
)
def test_four_operations_deb_cre(operation, debit, credit, expected_delta):
    lines = [
        DetLine(TEST_NCG, "1", "x", "MRU", Decimal(debit), Decimal(credit)),
        DetLine("351047", "2", "base", "MRU", Decimal("0"), Decimal("10")),
    ]
    base = evaluate_sm(lines)[TEST_CELL].calculated
    merged = merge_active_orientations(
        orientations=[_ori(operation=operation, status=STATUS_ACTIVE)]
    )
    got = evaluate_sm(lines, rules=merged)[TEST_CELL].calculated
    assert got == base + expected_delta
    basis, sign = operation_to_term_parts(operation)
    assert basis in {"DEBIT", "CREDIT"}
    assert sign in {-1, 1}


def test_mixed_ops_same_cell_isolated():
    merged = merge_active_orientations(
        orientations=[
            _ori(ncg="999801", cell_ref=TEST_CELL, operation="ADD_DEBIT"),
            _ori(ncg="999802", cell_ref=TEST_CELL, operation="ADD_DEBIT"),
            _ori(ncg="999803", cell_ref=TEST_CELL, operation="SUB_CREDIT"),
        ]
    )
    lines = [
        DetLine("999801", "1", "a", "MRU", Decimal("100"), Decimal("0")),
        DetLine("999802", "2", "b", "MRU", Decimal("20"), Decimal("0")),
        DetLine("999803", "3", "c", "MRU", Decimal("0"), Decimal("15")),
        DetLine("351047", "4", "base", "MRU", Decimal("0"), Decimal("5")),
    ]
    # base 5 + 100 + 20 − 15 = 110
    assert evaluate_sm(lines, rules=merged)[TEST_CELL].calculated == Decimal("110.00")


@pytest.mark.asyncio
async def test_permissions_same_actor_cannot_validate():
    proposer = uuid4()
    orientation = SimpleNamespace(
        status=STATUS_PENDING,
        submitted_by_id=proposer,
        cell_ref=TEST_CELL,
        operation="ADD_CREDIT",
        ncg=TEST_NCG,
        currency_scope="ALL",
        validated_by_id=None,
        validated_at=None,
        decision_comment=None,
    )
    same = SimpleNamespace(id=proposer)
    with pytest.raises(AppError) as exc:
        await validate_orientation(SimpleNamespace(), orientation=orientation, user=same)  # type: ignore[arg-type]
    assert exc.value.code == "NCG_ORI_SAME_ACTOR"
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_permissions_other_actor_can_validate():
    proposer = uuid4()
    validator = uuid4()
    orientation = SimpleNamespace(
        status=STATUS_PENDING,
        submitted_by_id=proposer,
        cell_ref=TEST_CELL,
        operation="ADD_CREDIT",
        ncg=TEST_NCG,
        currency_scope="ALL",
        validated_by_id=None,
        validated_at=None,
        decision_comment=None,
    )
    db = SimpleNamespace(flush=lambda: _async_noop())

    async def _async_noop():
        return None

    db.flush = _async_noop
    other = SimpleNamespace(id=validator)
    row = await validate_orientation(db, orientation=orientation, user=other)  # type: ignore[arg-type]
    assert row.status == STATUS_ACTIVE
    assert row.validated_by_id == validator


def test_duplicate_and_catalog_conflict_blocked():
    with pytest.raises(AppError) as exc:
        _assert_no_static_conflict("315100", "A:402:D", "ADD_CREDIT", "ALL")
    assert exc.value.code == "NCG_ORI_CATALOG_CONFLICT"

    # Doublon de fusion idempotent
    ori = _ori()
    once = merge_active_orientations(orientations=[ori])
    twice = merge_active_orientations(orientations=[ori, ori])
    c1 = sum(1 for t in next(r for r in once if r.key == TEST_CELL).terms for n in t.ncgs if n == TEST_NCG)
    c2 = sum(1 for t in next(r for r in twice if r.key == TEST_CELL).terms for n in t.ncgs if n == TEST_NCG)
    assert c1 == c2 == 1


def test_absent_zero_reappeared_and_late_import():
    mapped = {"210000": [{"cell_ref": "A:131:D", "basis": "DEBIT", "sign": 1}]}
    aout = _snap(2026, 8, {"210000": _row("210000", "1"), "500010": _row("500010", "2")})
    sept = _snap(2026, 9, {"210000": _row("210000", "3"), "500011": _row("500011", "0", "0")})
    octo = _snap(
        2026,
        10,
        {
            "210000": _row("210000", "4"),
            "500010": _row("500010", "5"),  # réapparu
            "500011": _row("500011", "0", "0"),  # présent zéro
            "500012": _row("500012", "9"),  # nouveau
        },
    )
    report = build_structure_report(
        current=octo,
        history=[sept, aout],  # ordre d'import inversé
        mapped_index=mapped,
        class_prefixes=frozenset(),
    )
    by = {i["ncg"]: i for i in report["items"]}
    assert by["210000"]["status"] == STATUS_DEJA_MAPPE
    assert by["500010"]["status"] == STATUS_CONNU_NON_ORIENTE
    assert by["500010"]["reapparu"] is True
    assert by["500011"]["present_zero"] is True
    assert by["500012"]["status"] == STATUS_NOUVEAU
    # 500010 vu en août : pas nouveau malgré import tardif d'août
    assert by["500010"]["status"] != STATUS_NOUVEAU


def test_merge_preserves_manual_and_adjust_origins():
    before_manual = {k: RULES_BY_KEY[k].origin for k in MANUAL_KEYS}
    before_adjust = {k: RULES_BY_KEY[k].origin for k in ADJUST_KEYS}
    merged = merge_active_orientations(
        orientations=[_ori(status=STATUS_ACTIVE, operation="ADD_CREDIT")]
    )
    for k, origin in before_manual.items():
        assert next(r for r in merged if r.key == k).origin == origin
    for k, origin in before_adjust.items():
        assert next(r for r in merged if r.key == k).origin == origin
    # Objet catalogue central intact
    assert RULES_BY_KEY[TEST_CELL].terms == next(r for r in ALL_RULES if r.key == TEST_CELL).terms
