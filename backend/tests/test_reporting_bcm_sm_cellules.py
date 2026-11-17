"""Catalogue Cellules SM + BAL DET octobre 2026 — sans DB."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.services.reporting_bcm_sm.engine.det_basis import (
    DetLine,
    aggregate,
    is_fx,
    lines_from_rows,
)
from app.services.reporting_bcm_sm.engine.evaluate import classes_1_8_gap, evaluate_sm
from app.services.reporting_bcm_sm.engine.rules_catalog import (
    AUTO_KEYS,
    MANUAL_KEYS,
    catalog_stats,
)

DET_CANDIDATES = (
    Path(r"C:\Users\sallm\bea-digital\BAL DET 31-10-2026.xlsx"),
    Path("/workspace/BAL DET 31-10-2026.xlsx"),
)


def _det_path() -> Path:
    for p in DET_CANDIDATES:
        if p.is_file():
            return p
    pytest.skip("BAL DET 31-10-2026.xlsx introuvable")


def _oct_lines() -> list[DetLine]:
    from app.services.reporting_bcm_sm.import_service import analyze_bal_det

    parsed = analyze_bal_det(_det_path().read_bytes())
    assert parsed["header_ok"]
    return lines_from_rows(parsed["rows"])


def test_d15_legend_fx_and_bases():
    lines = [
        DetLine("100000", "01101900026", "Caisse Chami", "EUR", Decimal("20254.50"), Decimal("0")),
        DetLine("100000", "1", "Caisse MRU", "MRU", Decimal("100"), Decimal("10")),
        DetLine("100000", "2", "Caisse MRO", "MRO", Decimal("5"), Decimal("0")),
    ]
    assert is_fx("EUR") and not is_fx("MRU") and not is_fx("MRO")
    net, n = aggregate(lines, ncgs=("100000",), basis="NET")
    assert net == Decimal("20349.50")
    assert n == 3
    fx_d, nfx = aggregate(lines, ncgs=("100000",), basis="DEBIT", currency="FX")
    assert fx_d == Decimal("20254.50")
    assert nfx == 1
    cred, _ = aggregate(lines, ncgs=("100000",), basis="CREDIT")
    assert cred == Decimal("10.00")


def test_catalog_counts():
    stats = catalog_stats()
    assert stats["auto"] >= 40
    assert "A:102:D" in AUTO_KEYS
    assert "A:322:D" in MANUAL_KEYS
    assert "A:114:D" in MANUAL_KEYS
    assert "A:327:D" in MANUAL_KEYS
    assert "A:234:C" in MANUAL_KEYS


def test_empty_match_is_zero_for_mapped_auto():
    values = evaluate_sm([])
    assert values["A:105:D"].calculated == Decimal("0.00")
    assert values["A:114:D"].calculated is None
    assert values["A:114:D"].status == "NON_RENSEIGNE"


def test_manual_param_and_decision_preserved():
    values = evaluate_sm(
        [],
        params={"amort_frais_immo": Decimal("3910448.68"), "dat_public": Decimal("70000000")},
        decisions={"A:322:D": Decimal("1.00")},
    )
    assert values["A:234:C"].retained == Decimal("3910448.68")
    assert values["A:234:C"].status == "SAISIE_MANUELLE"
    assert values["A:327:D"].retained == Decimal("70000000.00")
    assert values["A:322:D"].retained == Decimal("1.00")
    assert values["A:322:D"].status == "CORRECTION_MANUELLE"
    assert values["A:322:D"].calculated is None


def test_october_det_spotcheck():
    lines = _oct_lines()
    values = evaluate_sm(lines)
    # Recalculs Comptabilité (colonne « Recalculé depuis la balance »)
    expected = {
        "A:102:F": Decimal("20254.50"),
        "A:102:D": Decimal("588140512.53"),
        "A:105:D": Decimal("258052445.05"),
        "A:131:C": Decimal("1445481198.00"),
        "A:128:D": Decimal("592958186.58"),
        "A:332:D": Decimal("148811205.00"),
        "A:325:D": Decimal("24541098.00"),
        "A:516:G": Decimal("135030.00"),
    }
    for key, want in expected.items():
        got = values[key].calculated
        assert got == want, f"{key}: {got} != {want}"

    gap = classes_1_8_gap(lines)
    assert gap == Decimal("2873238.05")

    # D38 = DET − C38, sans les constantes manuelles 2 873 218 et 5
    d38 = values["A:131:D"].calculated
    assert d38 is not None
    assert d38 > Decimal("2523670062")
    assert values["A:131:D"].status == "A_AJUSTER"
    assert values["A:322:D"].status == "NON_RENSEIGNE"
    assert values["A:327:D"].calculated is None

    # 30 % ETAT B
    assert values["B:210:E"].calculated == quantize(values["A:134:D"].calculated, Decimal("0.30"))
    assert values["B:209:D"].calculated == values["A:133:D"].calculated - values["B:209:E"].calculated


def quantize(value: Decimal | None, pct: Decimal) -> Decimal:
    assert value is not None
    return (value * pct).quantize(Decimal("0.01"))


def test_projets_param_adjusts_d107():
    lines = _oct_lines()
    base = evaluate_sm(lines)
    with_p = evaluate_sm(lines, params={"projets": Decimal("296461984")})
    assert base["A:323:D"].calculated is not None
    assert with_p["A:323:D"].calculated == base["A:323:D"].calculated - Decimal("296461984")
    assert with_p["A:403:D"].calculated == base["A:403:D"].calculated + Decimal("296461984")
