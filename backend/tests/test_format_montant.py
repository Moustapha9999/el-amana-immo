"""Règle BEA DIGITAL : montants affichés en fr-FR (espace insécable milliers, virgule décimale)."""

from decimal import Decimal
from io import BytesIO

from openpyxl import load_workbook

from app.services.mg_pdf_service import money
from app.services.reporting_export import build_styled_workbook, format_montant, valeur_csv

NBSP = "\u00a0"


def test_format_montant_fr():
    assert format_montant(1234567.891) == f"1{NBSP}234{NBSP}567,89"
    assert format_montant(Decimal("-12500.5")) == f"-12{NBSP}500,50"
    assert format_montant(Decimal("1000")) == f"1{NBSP}000,00"
    assert format_montant(0.005) == "0,01"
    assert format_montant(-0.001) == "0,00"
    assert format_montant(0) == "0,00"
    assert format_montant(None) == "—"
    assert format_montant("abc") == "abc"
    assert money(None) == "0,00"
    assert money(Decimal("1250")) == f"1{NBSP}250,00"


def test_valeur_csv_reste_numerique():
    assert valeur_csv(1234.5) == "1234,50"
    assert valeur_csv(Decimal("-7")) == "-7,00"
    assert valeur_csv(41.19, decimales=None) == "41,19"
    assert valeur_csv(3) == 3
    assert valeur_csv(None) == ""
    assert valeur_csv("x") == "x"


def test_excel_cellule_numerique_avec_format():
    contenu = build_styled_workbook(
        sheet_title="T", report_title="T", headers=["Libellé", "Montant"], rows=[["A", Decimal("1234567.89")]]
    )
    cellule = load_workbook(BytesIO(contenu)).active["B6"]
    assert cellule.value == 1234567.89
    assert cellule.number_format == "#,##0.00"
