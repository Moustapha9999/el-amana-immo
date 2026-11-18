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


def test_a402d_eight_ncg_credit_balances_no_double_count():
    """D122 = Σ CRE des 8 NCG (102000, 180000, 300000, 301110, 311150, 315000, 316000, 316100).

    315100 n'est plus dans le périmètre. Les DEB des mêmes NCG restent sur A:201:D.
    """
    lines = [
        DetLine("102000", "1", "a", "MRU", Decimal("10"), Decimal("100")),
        DetLine("180000", "2", "b", "MRU", Decimal("20"), Decimal("200")),
        DetLine("300000", "3", "c", "MRU", Decimal("0"), Decimal("300")),
        DetLine("301110", "4", "d", "MRU", Decimal("5"), Decimal("400")),
        DetLine("311150", "5", "e", "MRU", Decimal("0"), Decimal("50")),
        DetLine("315000", "6", "f", "MRU", Decimal("1"), Decimal("60")),
        DetLine("316000", "7", "g", "MRU", Decimal("8"), Decimal("70")),
        DetLine("316000", "8", "g2", "MRU", Decimal("0"), Decimal("5")),
        DetLine("316100", "9", "h", "MRU", Decimal("0"), Decimal("15")),
        DetLine("315100", "10", "hors perimetre", "MRU", Decimal("0"), Decimal("99999")),
        DetLine("110010", "11", "cheques", "MRU", Decimal("1000"), Decimal("0")),
    ]
    first = evaluate_sm(lines)
    second = evaluate_sm(lines)
    assert first["A:402:D"].calculated == Decimal("1200.00")
    assert second["A:402:D"].calculated == first["A:402:D"].calculated
    # 315100 exclu ; pas de préfixe 315000 → 315100
    assert first["A:402:D"].calculated != Decimal("101199.00")
    terms = RULES_BY_KEY["A:402:D"].terms
    ncgs = tuple(n for t in terms for n in t.ncgs)
    assert ncgs == (
        "102000",
        "180000",
        "300000",
        "301110",
        "311150",
        "315000",
        "316000",
        "316100",
    )
    assert len(ncgs) == len(set(ncgs))
    assert "315100" not in ncgs
    # A:201:D (chèques, soldes débiteurs) non régressé
    assert first["A:201:D"].calculated == Decimal("1044.00")
    # Saisies manuelles conservées
    with_manual = evaluate_sm(
        lines,
        params={"amort_frais_immo": Decimal("12.00"), "dat_public": Decimal("30.00")},
    )
    assert with_manual["A:402:D"].calculated == Decimal("1200.00")
    assert with_manual["A:234:C"].retained == Decimal("12.00")
    assert with_manual["A:327:D"].retained == Decimal("30.00")


A206_NCGS = (
    "120030",
    "218000",
    "218100",
    "218200",
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


def test_a206d_twenty_two_ncg_debit_balances():
    """D47 = Σ DEB des 22 NCG. 218000 une seule fois. 352000 et 352001 tous les deux."""
    terms = RULES_BY_KEY["A:206:D"].terms
    ncgs = tuple(n for t in terms for n in t.ncgs)
    assert ncgs == A206_NCGS
    assert len(ncgs) == 22 == len(set(ncgs))
    assert ncgs.count("218000") == 1
    assert "350000" in ncgs
    assert "352000" in ncgs
    assert "352001" in ncgs
    assert "350000" not in tuple(n for t in RULES_BY_KEY["A:211:D"].terms for n in t.ncgs)
    assert "351014" not in tuple(n for t in RULES_BY_KEY["A:211:D"].terms for n in t.ncgs)
    for retired in ("320000", "320001", "322000", "323000", "323005", "323010"):
        assert retired not in ncgs

    lines = [
        DetLine("120030", "1", "a", "MRU", Decimal("10"), Decimal("1")),
        DetLine("218000", "2", "b", "MRU", Decimal("20"), Decimal("100")),
        DetLine("218100", "3", "c", "MRU", Decimal("3"), Decimal("0")),
        DetLine("218200", "4", "d", "MRU", Decimal("4"), Decimal("0")),
        DetLine("323020", "5", "e", "MRU", Decimal("5"), Decimal("0")),
        DetLine("323030", "6", "f", "MRU", Decimal("6"), Decimal("0")),
        DetLine("323050", "7", "g", "MRU", Decimal("7"), Decimal("0")),
        DetLine("323090", "8", "h", "MRU", Decimal("8"), Decimal("0")),
        DetLine("323100", "9", "i", "MRU", Decimal("9"), Decimal("0")),
        DetLine("323110", "10", "j", "MRU", Decimal("10"), Decimal("0")),
        DetLine("324000", "11", "k", "MRU", Decimal("11"), Decimal("0")),
        DetLine("326001", "12", "l", "MRU", Decimal("12"), Decimal("0")),
        DetLine("326010", "13", "m", "MRU", Decimal("13"), Decimal("0")),
        DetLine("326015", "14", "n", "MRU", Decimal("14"), Decimal("0")),
        DetLine("326030", "15", "o", "MRU", Decimal("15"), Decimal("0")),
        DetLine("326080", "16", "p", "MRU", Decimal("16"), Decimal("0")),
        DetLine("326110", "17", "q", "MRU", Decimal("17"), Decimal("0")),
        DetLine("350000", "18", "r", "MRU", Decimal("18"), Decimal("0")),
        DetLine("325000", "19", "s", "MRU", Decimal("19"), Decimal("0")),
        DetLine("352000", "20", "t0", "MRU", Decimal("23"), Decimal("0")),
        DetLine("352001", "21", "t", "MRU", Decimal("21"), Decimal("0")),
        DetLine("359000", "22", "u", "MRU", Decimal("22"), Decimal("0")),
        DetLine("320000", "23", "retire", "MRU", Decimal("888"), Decimal("0")),
    ]
    # Σ DEB 10+20+3+…+19+23+21+22 = 283 ; 352000 et 352001 distincts (égalité exacte)
    first = evaluate_sm(lines)
    second = evaluate_sm(lines)
    assert first["A:206:D"].calculated == Decimal("283.00")
    assert second["A:206:D"].calculated == first["A:206:D"].calculated
    assert first["A:211:D"].calculated == Decimal("0.00")
    with_manual = evaluate_sm(
        lines,
        params={"amort_frais_immo": Decimal("12.00"), "dat_public": Decimal("30.00")},
    )
    assert with_manual["A:206:D"].calculated == Decimal("283.00")
    assert with_manual["A:234:C"].retained == Decimal("12.00")
    assert with_manual["A:327:D"].retained == Decimal("30.00")
    # 218000 CREDIT reste sur A:335:D (autre cellule, autre base)
    assert first["A:335:D"].calculated == Decimal("100.00")


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
        "A:402:D": Decimal("7722754.00"),
        "A:201:D": Decimal("171527928.11"),
        "A:206:D": Decimal("108118467.43"),
        "A:211:D": Decimal("93003518.63"),
        "A:131:D": Decimal("2526543286.06"),
    }
    for key, want in expected.items():
        got = values[key].calculated
        assert got == want, f"{key}: {got} != {want}"

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


def test_projets_param_adjusts_d107():
    lines = _oct_lines()
    base = evaluate_sm(lines)
    with_p = evaluate_sm(lines, params={"projets": Decimal("296461984")})
    assert base["A:323:D"].calculated is not None
    assert with_p["A:323:D"].calculated == base["A:323:D"].calculated - Decimal("296461984")
    assert with_p["A:403:D"].calculated == base["A:403:D"].calculated + Decimal("296461984")
