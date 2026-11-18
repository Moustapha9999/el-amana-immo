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
from app.services.reporting_bcm_sm.engine.evaluate import (
    classes_1_8_gap,
    det_signed_gap,
    evaluate_sm,
    mapping_coverage,
)
from app.services.reporting_bcm_sm.engine.rules_catalog import (
    AUTO_KEYS,
    MANUAL_KEYS,
    RULES_BY_KEY,
    catalog_stats,
)
from app.services.reporting_bcm_sm.work_fill import _etat_b_col_h

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


def test_a102f_aggregates_all_fx_accounts_of_100000_and_100100():
    """F9 = solde débiteur en devises de tous les comptes NCG 100000 et 100100.

    Plus de filtre sur le seul compte EUR 01101900026. MRU/MRO exclus (légende D15).
    D9 = solde net 100000+100100 − F9 (pas de double comptage).
    """
    lines = [
        DetLine("100000", "01101900026", "Caisse Chami EUR", "EUR", Decimal("20254.50"), Decimal("0")),
        DetLine("100000", "01101900099", "Caisse USD", "USD", Decimal("100.00"), Decimal("10.00")),
        DetLine("100100", "07000020008", "GAB EUR", "EUR", Decimal("50.00"), Decimal("0")),
        DetLine("100000", "01100000001", "Caisse MRU", "MRU", Decimal("1000.00"), Decimal("20.00")),
        DetLine("100000", "01100600008", "Caisse MRO", "MRO", Decimal("5.00"), Decimal("0")),
        DetLine("100100", "07000030003", "GAB MRU", "MRU", Decimal("200.00"), Decimal("0")),
        DetLine("120000", "01200000001", "Corresp. EUR", "EUR", Decimal("999.00"), Decimal("0")),
    ]
    values = evaluate_sm(lines)
    # DEB FX : 20254.50 + 100.00 + 50.00 ; CRE FX ignoré (solde débiteur, pas net)
    assert values["A:102:F"].calculated == Decimal("20404.50")
    assert values["A:102:F"].status == "AUTOMATIQUE"
    # NET 100000+100100 = (20254.50-0)+(100-10)+(50-0)+(1000-20)+(5-0)+(200-0) = 21579.50
    # D9 = NET − F9 = 21579.50 − 20404.50 = 1175.00
    assert values["A:102:D"].calculated == Decimal("1175.00")
    # Autre rubrique devises (G16) non affectée
    assert values["A:109:G"].calculated == Decimal("999.00")


def test_a402d_ten_ncg_credit_balances_no_double_count():
    """D122 = Σ CRE des 10 NCG. Les débits des mêmes codes restent hors de cette cellule."""
    lines = [
        DetLine("102000", "1", "a", "MRU", Decimal("10"), Decimal("100")),
        DetLine("180000", "2", "b", "MRU", Decimal("20"), Decimal("200")),
        DetLine("300000", "3", "c", "MRU", Decimal("0"), Decimal("300")),
        DetLine("301110", "4", "d", "MRU", Decimal("5"), Decimal("400")),
        DetLine("311115", "4b", "d2", "MRU", Decimal("7"), Decimal("25")),
        DetLine("311150", "5", "e", "MRU", Decimal("0"), Decimal("50")),
        DetLine("315000", "6", "f", "MRU", Decimal("1"), Decimal("60")),
        DetLine("315100", "6b", "f2", "MRU", Decimal("9"), Decimal("30")),
        DetLine("316000", "7", "g", "MRU", Decimal("8"), Decimal("70")),
        DetLine("316000", "8", "g2", "MRU", Decimal("0"), Decimal("5")),
        DetLine("316100", "9", "h", "MRU", Decimal("0"), Decimal("15")),
        DetLine("110010", "11", "cheques", "MRU", Decimal("1000"), Decimal("0")),
    ]
    first = evaluate_sm(lines)
    second = evaluate_sm(lines)
    # 100+200+300+400+25+50+60+30+70+5+15 = 1255. Les débits n'entrent pas.
    assert first["A:402:D"].calculated == Decimal("1255.00")
    assert second["A:402:D"].calculated == first["A:402:D"].calculated
    terms = RULES_BY_KEY["A:402:D"].terms
    ncgs = tuple(n for t in terms for n in t.ncgs)
    assert ncgs == (
        "102000",
        "180000",
        "300000",
        "301110",
        "311115",
        "311150",
        "315000",
        "315100",
        "316000",
        "316100",
    )
    assert len(terms) == 1 and terms[0].basis == "CREDIT"
    assert len(ncgs) == 10 == len(set(ncgs))
    credit_elsewhere = tuple(
        n
        for rule in RULES_BY_KEY.values()
        if rule.key != "A:402:D"
        for term in rule.terms
        if term.basis == "CREDIT"
        for n in term.ncgs
    )
    for ncg in ncgs:
        assert ncg not in credit_elsewhere
    # Le débit 311115 entre dans A:201:D. Le débit 315100 n'y est pas.
    assert first["A:201:D"].calculated == Decimal("1051.00")
    missing = [line for line in lines if line.ncg not in ("311115", "315100")]
    partial = evaluate_sm(missing)
    assert partial["A:402:D"].calculated == Decimal("1200.00")
    absent = {row["ncg"] for row in mapping_coverage(partial)["absent"] if row["cell"] == "A:402:D"}
    assert absent == {"311115", "315100"}
    zero_lines = missing + [DetLine("315100", "z", "zero", "MRU", Decimal("4"), Decimal("0"))]
    zeroed = evaluate_sm(zero_lines)
    assert zeroed["A:402:D"].calculated == Decimal("1200.00")
    present_zero = {
        row["ncg"] for row in mapping_coverage(zeroed)["present_zero"] if row["cell"] == "A:402:D"
    }
    assert "315100" in present_zero
    assert "311115" not in present_zero
    with_manual = evaluate_sm(
        lines,
        params={"amort_frais_immo": Decimal("12.00"), "dat_public": Decimal("30.00")},
    )
    assert with_manual["A:402:D"].calculated == Decimal("1255.00")
    assert with_manual["A:234:C"].retained == Decimal("12.00")
    assert with_manual["A:327:D"].retained == Decimal("30.00")


A206_NCGS = (
    "120030",
    "218000",
    "218100",
    "218200",
    "320000",
    "320001",
    "322000",
    "323000",
    "323005",
    "323010",
    "323020",
    "323030",
    "323050",
    "323090",
    "323100",
    "323110",
    "324000",
    "326001",
    "326010",
    "326015",
    "326030",
    "326080",
    "326110",
    "350000",
    "325000",
    "352000",
    "352001",
    "359000",
)


def test_a206d_twenty_eight_ncg_debit_balances():
    """D47 = Σ DEB des 28 NCG. Aucune soustraction de crédits."""
    terms = RULES_BY_KEY["A:206:D"].terms
    ncgs = tuple(n for t in terms for n in t.ncgs)
    assert ncgs == A206_NCGS
    assert len(ncgs) == 28 == len(set(ncgs))
    assert terms[0].basis == "DEBIT"
    assert len(terms) == 1
    assert ncgs.count("218000") == 1
    assert "352000" in ncgs and "352001" in ncgs
    for kept in ("320000", "320001", "322000", "323000", "323005", "323010"):
        assert kept in ncgs
    assert "350000" not in tuple(n for t in RULES_BY_KEY["A:211:D"].terms for n in t.ncgs)
    debit_elsewhere = tuple(
        n
        for rule in RULES_BY_KEY.values()
        if rule.key != "A:206:D"
        for term in rule.terms
        if term.basis == "DEBIT"
        for n in term.ncgs
    )
    for ncg in ("320000", "320001", "322000", "323000", "323005", "323010"):
        assert ncg not in debit_elsewhere
    credit_403 = tuple(
        n
        for term in RULES_BY_KEY["A:403:D"].terms
        if term.basis == "CREDIT"
        for n in term.ncgs
    )
    assert "322000" in credit_403

    lines = [
        DetLine("120030", "1", "a", "MRU", Decimal("10"), Decimal("1")),
        DetLine("218000", "2", "b", "MRU", Decimal("20"), Decimal("100")),
        DetLine("218100", "3", "c", "MRU", Decimal("3"), Decimal("0")),
        DetLine("218200", "4", "d", "MRU", Decimal("4"), Decimal("0")),
        DetLine("320000", "5", "e", "MRU", Decimal("30"), Decimal("7")),
        DetLine("320001", "6", "f", "MRU", Decimal("31"), Decimal("0")),
        DetLine("322000", "6b", "f2", "MRU", Decimal("40"), Decimal("11")),
        DetLine("323000", "7", "g", "MRU", Decimal("32"), Decimal("0")),
        DetLine("323005", "8", "h", "MRU", Decimal("33"), Decimal("0")),
        DetLine("323010", "9", "i", "MRU", Decimal("34"), Decimal("0")),
        DetLine("323020", "10", "j", "MRU", Decimal("5"), Decimal("0")),
        DetLine("323030", "11", "k", "MRU", Decimal("6"), Decimal("0")),
        DetLine("323050", "12", "l", "MRU", Decimal("7"), Decimal("0")),
        DetLine("323090", "13", "m", "MRU", Decimal("8"), Decimal("0")),
        DetLine("323100", "14", "n", "MRU", Decimal("9"), Decimal("0")),
        DetLine("323110", "15", "o", "MRU", Decimal("10"), Decimal("0")),
        DetLine("324000", "16", "p", "MRU", Decimal("11"), Decimal("0")),
        DetLine("326001", "17", "q", "MRU", Decimal("12"), Decimal("0")),
        DetLine("326010", "18", "r", "MRU", Decimal("13"), Decimal("0")),
        DetLine("326015", "19", "s", "MRU", Decimal("14"), Decimal("0")),
        DetLine("326030", "20", "t", "MRU", Decimal("15"), Decimal("0")),
        DetLine("326080", "21", "u", "MRU", Decimal("16"), Decimal("0")),
        DetLine("326110", "22", "v", "MRU", Decimal("17"), Decimal("0")),
        DetLine("350000", "23", "w", "MRU", Decimal("18"), Decimal("0")),
        DetLine("325000", "24", "x", "MRU", Decimal("19"), Decimal("0")),
        DetLine("352000", "25", "y", "MRU", Decimal("23"), Decimal("0")),
        DetLine("352001", "26", "z", "MRU", Decimal("21"), Decimal("0")),
        DetLine("359000", "27", "aa", "MRU", Decimal("22"), Decimal("0")),
    ]
    # Σ DEB des 28 = 483. Le crédit de 322000 (11), de 320000 (7) et de 218000 (100) n'entre pas.
    first = evaluate_sm(lines)
    second = evaluate_sm(lines)
    assert first["A:206:D"].calculated == Decimal("483.00")
    assert second["A:206:D"].calculated == first["A:206:D"].calculated
    assert first["A:211:D"].calculated == Decimal("0.00")
    with_manual = evaluate_sm(
        lines,
        params={"amort_frais_immo": Decimal("12.00"), "dat_public": Decimal("30.00")},
    )
    assert with_manual["A:206:D"].calculated == Decimal("483.00")
    assert with_manual["A:234:C"].retained == Decimal("12.00")
    assert with_manual["A:327:D"].retained == Decimal("30.00")
    assert first["A:335:D"].calculated == Decimal("100.00")
    # Crédit 120030 (1) + crédit 320000 (7) + crédit 322000 (11). Le débit 40 reste sur D47.
    assert first["A:403:D"].calculated == Decimal("19.00")


A211_NCGS = (
    "351017",
    "351025",
    "351027",
    "351029",
    "351030",
    "351032",
    "351033",
    "351038",
    "351043",
    "351047",
    "351048",
    "351049",
    "351053",
    "351062",
    "351072",
    "351073",
    "351074",
)


def test_a211d_seventeen_ncg_debit_balances():
    """D52 = Σ DEB des 17 NCG listés. 350000 et 351014 exclus ; 351062 inclus."""
    terms = RULES_BY_KEY["A:211:D"].terms
    ncgs = tuple(n for t in terms for n in t.ncgs)
    assert ncgs == A211_NCGS
    assert len(ncgs) == 17 == len(set(ncgs))
    assert "351062" in ncgs
    assert "350000" not in ncgs
    assert "351014" not in ncgs
    assert "350000" in tuple(n for t in RULES_BY_KEY["A:206:D"].terms for n in t.ncgs)

    lines = [
        DetLine(n, str(i), n, "MRU", Decimal("2"), Decimal("0"))
        for i, n in enumerate(A211_NCGS, start=1)
    ] + [
        DetLine("350000", "90", "hors D52", "MRU", Decimal("999"), Decimal("0")),
        DetLine("351014", "91", "hors D52", "MRU", Decimal("888"), Decimal("50")),
        DetLine("351047", "92", "cre 408", "MRU", Decimal("0"), Decimal("40")),
    ]
    first = evaluate_sm(lines)
    second = evaluate_sm(lines)
    assert first["A:211:D"].calculated == Decimal("34.00")
    assert second["A:211:D"].calculated == first["A:211:D"].calculated
    with_manual = evaluate_sm(
        lines,
        params={"amort_frais_immo": Decimal("12.00"), "dat_public": Decimal("30.00")},
    )
    assert with_manual["A:211:D"].calculated == Decimal("34.00")
    assert with_manual["A:234:C"].retained == Decimal("12.00")
    assert with_manual["A:327:D"].retained == Decimal("30.00")
    # 350000 DEB reste sur D47 ; 351014 CREDIT reste sur A:408:D
    assert first["A:206:D"].calculated == Decimal("999.00")
    assert first["A:408:D"].calculated == Decimal("90.00")


def test_catalog_counts():
    stats = catalog_stats()
    assert stats["auto"] >= 40
    assert "A:102:D" in AUTO_KEYS
    assert "A:227:D" in AUTO_KEYS
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
        "A:402:D": Decimal("26259079.00"),
        "A:201:D": Decimal("171527928.11"),
        "A:206:D": Decimal("108297671.53"),
        "A:211:D": Decimal("93003518.63"),
        "A:131:D": Decimal("2526543286.06"),
    }
    for key, want in expected.items():
        got = values[key].calculated
        assert got == want, f"{key}: {got} != {want}"
    part_322, count_322 = aggregate(lines, ncgs=("322000",), basis="DEBIT")
    assert count_322 == 1 and part_322 == Decimal("585.00")

    gap = classes_1_8_gap(lines)
    assert gap == Decimal("2873238.05")

    # Déséquilibre BAL non retranché de D38 (pas de compensation artificielle)
    signed = det_signed_gap(lines)
    assert signed == Decimal("2873233.84")
    assert values["A:131:D"].status == "AUTOMATIQUE"
    assert values["A:131:C"].calculated == Decimal("1445481198.00")
    assert values["A:322:D"].status == "NON_RENSEIGNE"
    assert values["A:327:D"].calculated is None

    # 30 % ETAT B (formules Excel) ; H n'est pas un total de ligne
    assert values["B:210:E"].calculated == quantize(values["A:134:D"].calculated, Decimal("0.30"))
    assert values["B:209:D"].calculated == values["A:133:D"].calculated - values["B:209:E"].calculated
    assert "B:210:H" not in values
    assert "B:105:H" not in values
    assert "B:207:H" not in values
    assert _etat_b_col_h("ETAT B", "H12")
    assert _etat_b_col_h("ETAT B", "H46")
    assert not _etat_b_col_h("ETAT A", "H38")
    assert not _etat_b_col_h("ETAT B", "D46")

    # NCG 453000 (IMMO.EN COURS) absent de la BAL DET 31-10-2026 : solde débiteur = 0
    assert values["A:227:D"].calculated == Decimal("0.00")
    assert values["A:225:D"].calculated == Decimal("747655449.09")


def quantize(value: Decimal | None, pct: Decimal) -> Decimal:
    assert value is not None
    return (value * pct).quantize(Decimal("0.01"))


A131_DEB_NCGS = (
    "210000",
    "210005",
    "210010",
    "210020",
    "210021",
    "210022",
    "210030",
    "210100",
    "210400",
    "211100",
    "211110",
    "211130",
    "216000",
    "216100",
)
A131_CRE_NCGS = ("211100", "211110", "211130")


def test_same_rules_when_one_ncg_is_absent_and_when_code_formatting_differs():
    """Une rubrique absente vaut 0. Elle n'efface pas les autres termes DEB ou CRE.

    Un code écrit ``211 100`` ou ``211100.0`` reste la rubrique 211100.
    Un solde présent à zéro n'est pas une absence.
    """
    lines = [
        DetLine("210000", "1", "a", "MRU", Decimal("100"), Decimal("1")),
        DetLine("211 100", "2", "b", "MRU", Decimal("15"), Decimal("4")),
        DetLine("211110.0", "3", "c", "MRU", Decimal("6"), Decimal("3")),
        DetLine("216000", "4", "d", "MRU", Decimal("0"), Decimal("0")),
        DetLine("290000", "5", "prov", "MRU", Decimal("0"), Decimal("10")),
    ]
    values = evaluate_sm(lines)
    # Σ DEB 100+15+6+0 − Σ CRE 4+3 − C38 10 = 104
    # 210400, 211130 et les autres codes listés sont absents : contribution 0
    assert values["A:131:D"].calculated == Decimal("104.00")
    assert values["A:131:C"].calculated == Decimal("10.00")
    coverage = mapping_coverage(values)
    absent = {(row["cell"], row["ncg"]) for row in coverage["absent"]}
    assert ("A:131:D", "210400") in absent
    assert ("A:131:D", "211130") in absent
    assert ("A:131:D", "211100") not in absent
    assert ("A:131:D", "210000") not in absent
    zero = {(row["cell"], row["ncg"]) for row in coverage["present_zero"]}
    assert ("A:131:D", "216000") in zero
    deb = next(step for step in values["A:131:D"].traces if step.get("basis") == "DEBIT")
    cre = next(step for step in values["A:131:D"].traces if step.get("sign") == -1)
    assert deb["ncg_present"] == 4
    assert deb["ncg_absent"] == 10
    assert cre["ncg_present"] == 2
    assert cre["ncg_absent"] == 1
    again = evaluate_sm(lines)
    assert again["A:131:D"].calculated == values["A:131:D"].calculated


def test_october_uses_mapped_ncg_absent_from_august():
    """311115 est dans la règle A:201:D. Absent en août, présent en octobre : il compte."""
    from app.services.reporting_bcm_sm.import_service import analyze_bal_det

    aout = Path(r"C:\Users\sallm\Downloads\BAL AOUT.xlsx")
    octo = Path(r"C:\Users\sallm\Downloads\BAL DET 31-10-2026.xlsx")
    if not aout.is_file() or not octo.is_file():
        pytest.skip("BAL août ou octobre introuvable")
    aout_lines = lines_from_rows(analyze_bal_det(aout.read_bytes())["rows"])
    oct_lines = lines_from_rows(analyze_bal_det(octo.read_bytes())["rows"])
    aout_values = evaluate_sm(aout_lines, params={"dat_public": Decimal("70000000")})
    oct_values = evaluate_sm(oct_lines)
    assert aout_values["A:131:D"].calculated == Decimal("2447928406.68")
    assert aout_values["A:131:C"].calculated == Decimal("1353359552.22")
    assert aout_values["A:206:D"].calculated == Decimal("55119199.63")
    aout_zero = {
        row["ncg"]
        for row in mapping_coverage(aout_values)["present_zero"]
        if row["cell"] == "A:206:D"
    }
    for ncg in ("320000", "320001", "323000", "323005", "323010"):
        assert ncg in aout_zero
    assert ("A:206:D", "322000") in {
        (row["cell"], row["ncg"]) for row in mapping_coverage(aout_values)["absent"]
    }
    assert aout_values["A:227:D"].calculated == Decimal("47800322.64")
    assert ("A:201:D", "311115") in {
        (row["cell"], row["ncg"]) for row in mapping_coverage(aout_values)["absent"]
    }
    part, n = aggregate(oct_lines, ncgs=("311115",), basis="DEBIT")
    assert n == 1 and part == Decimal("18536325.00")
    assert oct_values["A:201:D"].calculated == Decimal("171527928.11")
    assert ("A:201:D", "311115") not in {
        (row["cell"], row["ncg"]) for row in mapping_coverage(oct_values)["absent"]
    }
    assert aout_values["A:402:D"].calculated == Decimal("65311502.86")
    aout_absent_402 = {
        row["ncg"] for row in mapping_coverage(aout_values)["absent"] if row["cell"] == "A:402:D"
    }
    assert aout_absent_402 == {"311115", "315100"}
    cre_115, n_cre = aggregate(oct_lines, ncgs=("311115",), basis="CREDIT")
    cre_100, n_100 = aggregate(oct_lines, ncgs=("315100",), basis="CREDIT")
    assert n_cre == 1 and cre_115 == Decimal("0.00")
    assert n_100 == 1 and cre_100 == Decimal("18536325.00")
    assert oct_values["A:402:D"].calculated == Decimal("26259079.00")
    assert ("A:402:D", "311115") not in {
        (row["cell"], row["ncg"]) for row in mapping_coverage(oct_values)["absent"]
    }


def test_a131d_does_not_absorb_balance_sheet_gap():
    """Un déséquilibre hors mapping ne modifie pas D38. Il reste visible au contrôle."""
    lines = [
        DetLine("210000", "1", "cod", "MRU", Decimal("100"), Decimal("0")),
        DetLine("211100", "2", "cre", "MRU", Decimal("0"), Decimal("4")),
        DetLine("290000", "3", "prov", "MRU", Decimal("0"), Decimal("40")),
    ]
    base = evaluate_sm(lines)
    # 199000 n'est pas dans le mapping 131. Son débit crée un écart de bilan.
    dirty = lines + [DetLine("199000", "9", "ecart", "MRU", Decimal("500000"), Decimal("0"))]
    shifted = evaluate_sm(dirty)
    assert base["A:131:D"].calculated == Decimal("56.00")
    assert shifted["A:131:D"].calculated == base["A:131:D"].calculated
    assert shifted["A:131:C"].calculated == base["A:131:C"].calculated
    gap_base = classes_1_8_gap(lines)
    gap_dirty = classes_1_8_gap(dirty)
    assert gap_dirty - gap_base == Decimal("500000.00")
    assert gap_dirty != shifted["A:131:D"].calculated
    assert "Aucun déséquilibre" in (RULES_BY_KEY["A:131:D"].notes or "")
    runner = Path(__file__).resolve().parents[1] / "app/services/reporting_bcm_sm/engine/runner.py"
    source = runner.read_text(encoding="utf-8")
    assert "is_active_in_run=False" in source
    assert '"ecart_active": False' in source
    assert "non forcé dans ETAT A" in source
    assert "A:131:D" not in source


def test_a131d_fourteen_debit_minus_three_credit():
    """BCM 131 D38 = Σ DEB 14 NCG − Σ CRE 211100/110/130 − C38. C38 visible."""
    terms = RULES_BY_KEY["A:131:D"].terms
    assert tuple(terms[0].ncgs) == A131_DEB_NCGS
    assert len(A131_DEB_NCGS) == 14 == len(set(A131_DEB_NCGS))
    assert tuple(terms[1].ncgs) == A131_CRE_NCGS
    assert RULES_BY_KEY["A:131:D"].minus_cells == ("A:131:C",)
    assert "210400" in A131_DEB_NCGS
    assert "211100" in A131_DEB_NCGS
    assert "211100" in A131_CRE_NCGS

    lines = [
        DetLine("210000", "1", "a", "MRU", Decimal("100"), Decimal("9")),
        DetLine("210400", "2", "b", "MRU", Decimal("20"), Decimal("8")),
        DetLine("211100", "3", "c", "MRU", Decimal("15"), Decimal("4")),
        DetLine("211110", "4", "d", "MRU", Decimal("6"), Decimal("3")),
        DetLine("211130", "5", "e", "MRU", Decimal("7"), Decimal("2")),
        DetLine("216000", "6", "f", "MRU", Decimal("8"), Decimal("1")),
        DetLine("290000", "7", "prov", "MRU", Decimal("0"), Decimal("999")),
        DetLine("100000", "8", "hors", "MRU", Decimal("50"), Decimal("0")),
    ]
    # Σ DEB 156 − Σ CRE 9 − C38 999 = −852 ; C38 reste 999
    first = evaluate_sm(lines)
    second = evaluate_sm(lines)
    assert first["A:131:C"].calculated == Decimal("999.00")
    assert first["A:131:D"].calculated == Decimal("-852.00")
    assert second["A:131:D"].calculated == first["A:131:D"].calculated
    assert first["B:207:E"].calculated == Decimal("44.10")
    with_manual = evaluate_sm(
        lines,
        params={"amort_frais_immo": Decimal("12.00"), "dat_public": Decimal("30.00")},
    )
    assert with_manual["A:131:D"].calculated == Decimal("-852.00")
    assert with_manual["A:131:C"].calculated == Decimal("999.00")
    assert with_manual["A:234:C"].retained == Decimal("12.00")
    assert with_manual["A:327:D"].retained == Decimal("30.00")
    # 210400 CREDIT (et 210000 CREDIT) restent sur A:323:D — autre cellule, autre base
    assert first["A:323:D"].calculated == Decimal("17.00")


def test_a227d_immo_en_cours_debit_not_in_225():
    """BCM 227 D = NCG 453000 solde débiteur, hors 420000 (pas de double comptage)."""
    lines = [
        DetLine("453000", "01453000048", "IMMO.EN COURS", "MRU", Decimal("300000"), Decimal("0")),
        DetLine("453000", "01453000051", "IMMO.EN COURS", "MRU", Decimal("153000"), Decimal("0")),
        DetLine("420000", "01420000002", "TERRAINS IMMO EXPL", "MRU", Decimal("1000000"), Decimal("0")),
        DetLine("482000", "01482110008", "AMOR CONSTRUCTION", "MRU", Decimal("0"), Decimal("100000")),
    ]
    values = evaluate_sm(lines)
    assert values["A:227:D"].calculated == Decimal("453000.00")
    assert values["A:227:D"].retained == Decimal("453000.00")
    assert values["A:227:D"].status == "AUTOMATIQUE"
    assert values["A:227:H"].calculated == Decimal("453000.00")
    assert values["A:225:D"].calculated == Decimal("900000.00")
    assert values["A:225:C"].calculated == Decimal("100000.00")

    with_decision = evaluate_sm(lines, decisions={"A:227:D": Decimal("1")})
    assert with_decision["A:227:D"].calculated == Decimal("453000.00")
    assert with_decision["A:227:D"].retained == Decimal("1.00")
    assert with_decision["A:227:D"].status == "CORRECTION_MANUELLE"
    assert with_decision["A:225:D"].calculated == Decimal("900000.00")


def test_september_debits_divers_and_comptes_ordinaires():
    """SM 09/2026 : D47 = Σ DEB des 28 NCG. 322000 absent. D38 reste le mapping."""
    from app.services.reporting_bcm_sm.import_service import analyze_bal_det

    sept = Path(r"C:\Users\sallm\Downloads\BAL DET SEPT.xlsx")
    if not sept.is_file():
        pytest.skip("BAL DET SEPT.xlsx introuvable")
    lines = lines_from_rows(analyze_bal_det(sept.read_bytes())["rows"])
    values = evaluate_sm(lines)
    assert values["A:206:D"].calculated == Decimal("161023022.01")
    coverage = mapping_coverage(values)
    absent = {row["ncg"] for row in coverage["absent"] if row["cell"] == "A:206:D"}
    zero = {row["ncg"] for row in coverage["present_zero"] if row["cell"] == "A:206:D"}
    assert absent == {"322000", "325000"}
    for ncg in ("320000", "320001", "323005", "323010"):
        assert ncg in zero
    part, count = aggregate(lines, ncgs=("323000",), basis="DEBIT")
    assert count == 3 and part == Decimal("17955840.80")
    assert values["A:131:D"].calculated == Decimal("2660345694.61")
    assert values["A:131:C"].calculated == Decimal("1352232883.07")
    gap = classes_1_8_gap(lines)
    assert gap == Decimal("621486.46")
    assert values["A:131:D"].calculated != gap
    dirty = lines + [DetLine("199000", "gap", "ecart", "MRU", Decimal("500000"), Decimal("0"))]
    shifted = evaluate_sm(dirty)
    assert shifted["A:131:D"].calculated == values["A:131:D"].calculated
    assert shifted["A:206:D"].calculated == values["A:206:D"].calculated
    assert classes_1_8_gap(dirty) - gap == Decimal("500000.00")


def test_projets_param_adjusts_d107():
    lines = _oct_lines()
    base = evaluate_sm(lines)
    with_p = evaluate_sm(lines, params={"projets": Decimal("296461984")})
    assert base["A:323:D"].calculated is not None
    assert with_p["A:323:D"].calculated == base["A:323:D"].calculated - Decimal("296461984")
    assert with_p["A:403:D"].calculated == base["A:403:D"].calculated + Decimal("296461984")
