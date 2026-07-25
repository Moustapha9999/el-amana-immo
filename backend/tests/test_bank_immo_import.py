"""Tests du parser / helpers d'import tableau banque."""

from datetime import date
from decimal import Decimal
from io import BytesIO

import xlrd
from openpyxl import Workbook

from app.services.bank_immo_import import (
    parse_amount,
    parse_bank_workbook,
    parse_date,
    parse_taux,
    resolve_categorie_code,
)
from app.services.recap_amortissement import _is_import_banque, _mouvements_immo
from app.models.immobilisation import Immobilisation
from app.models.enums import StatutImmobilisation


def test_resolve_categorie_code():
    assert resolve_categorie_code("aai") == "TY-142010"
    assert resolve_categorie_code("matinfo ") == "TY-142041"
    assert resolve_categorie_code("constructé") == "TY-142020"
    assert resolve_categorie_code("FRIAS emmission EMPRT") == "TY-147030"
    assert resolve_categorie_code("recapAmort2022") is None


def test_parse_amount_and_taux():
    assert parse_amount("5 606 827,70") == Decimal("5606827.70")
    assert parse_amount(-168400) == Decimal("-168400.00")
    assert parse_amount("-") is None
    assert parse_taux("10%") == Decimal("10.00")
    assert parse_taux(0.1) == Decimal("10.00")
    assert parse_taux(10) == Decimal("10.00")


def test_parse_date_typo_and_serial():
    assert parse_date("01/01/20120") == date(2020, 1, 1)
    assert parse_date("06/01/2026") == date(2026, 1, 6)
    serial = xlrd.xldate.xldate_from_date_tuple((2007, 1, 2), 0)
    assert parse_date(serial, datemode=0) == date(2007, 1, 2)


def _build_aai_fixture_xlsx() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "aai"
    ws.append(["BEA"])
    ws.append(["TABLEAU D'AMORTISSEMENT AAI"])
    ws.append(["COMPTE N°: 142010"])
    ws.append(
        [
            "Date",
            "Qté",
            "Désignation",
            "d'Acquisition MRU",
            "Taux",
            "Fin Exr.Précé",
            "Exer. En. C",
            "Fin Exercice",
            "Comptable",
            "AGENCE",
        ]
    )
    ws.append(["01/01/03", None, "REPORT 2003", 5606827.70, "10%", 5606827.70, None, 5606827.70, 0, None])
    ws.append(
        ["02/01/07", 1, "Construction chambre forte NDB", 106000.00, 0.1, 106000.00, None, 106000.00, 0, None]
    )
    ws.append(
        [
            "06/01/2026",
            None,
            "RGLT FACT ETS KERIM",
            203500.00,
            "10%",
            None,
            9892.36,
            9892.36,
            193607.64,
            "SIEGE CENTRAL",
        ]
    )
    # Reports de solde annuels — doivent être ignorés
    ws.append(
        ["01/01/10", None, "Report 01/01/2010", 7200000.00, "10%", 7200000.00, None, 7200000.00, 0, None]
    )
    ws.append(
        ["01/01/22", None, "Report de solde 31/12/2021", 9000000.00, None, 9000000.00, None, 9000000.00, 0, None]
    )
    ws.append(
        ["30/06/26", None, "Solde au 30/06/2026", 5916327.70, None, 5712827.70, 9892.36, 5722720.06, 193607.64, None]
    )
    other = wb.create_sheet("recapAmort2022")
    other.append(["RECAP"])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_bank_workbook_aai_fixture():
    content = _build_aai_fixture_xlsx()
    rows = parse_bank_workbook(content, "fixture.xlsx")
    assert len(rows) == 3
    assert rows[0].is_report is True
    assert rows[0].valeur_brute == Decimal("5606827.70")
    assert rows[0].categorie_code == "TY-142010"

    assert rows[1].designation.startswith("Construction")
    assert rows[1].taux == Decimal("10.00")
    assert rows[1].amt_n1 == Decimal("106000.00")
    assert rows[1].dotation == Decimal("0.00")

    assert rows[2].date_acquisition == date(2026, 1, 6)
    assert rows[2].dotation == Decimal("9892.36")
    assert rows[2].vnc == Decimal("193607.64")
    assert rows[2].agence_label == "SIEGE CENTRAL"

    vb = sum((r.valeur_brute for r in rows), Decimal("0"))
    assert vb == Decimal("5916327.70")


def test_mouvements_prefer_bank_seed():
    immo = Immobilisation(
        code_inventaire="142010-TEST",
        designation="Test banque",
        quantite=1,
        date_acquisition=date(2020, 1, 1),
        valeur_brute=Decimal("100000.00"),
        taux=Decimal("10"),
        statut=StatutImmobilisation.EN_SERVICE,
        compte_immobilisation="142010",
        metadata_json={"source": "import_banque"},
    )
    assert _is_import_banque(immo) is True
    mvts = _mouvements_immo(
        immo,
        2026,
        montants_dotation_db=[Decimal("5000.00")],
        cumul_n1_db=Decimal("40000.00"),
        cumul_fin_n_db=Decimal("45000.00"),
        vnc_fin_n_db=Decimal("55000.00"),
    )
    assert mvts is not None
    assert mvts["amorts_cumules_n1"] == Decimal("40000.00")
    assert mvts["dotations_annee"] == Decimal("5000.00")
    assert mvts["amorts_cumules_n"] == Decimal("45000.00")
    assert mvts["vnc"] == Decimal("55000.00")
