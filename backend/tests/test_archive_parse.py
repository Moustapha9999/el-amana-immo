"""Tests parse archive Excel / PDF (sans impact parc actif)."""

from datetime import date
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

from app.core.exceptions import ValidationError
from app.services.archive_pdf_parse import parse_bank_pdf
from app.services.archive_service import nature_label, validate_nature_code
from app.services.bank_immo_import import parse_bank_workbook


def _build_aai_xlsx() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "aai"
    ws.append(["TABLEAU D'AMORTISSEMENT AAI"])
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
        [
            "06/01/2026",
            1,
            "RGLT FACT ETS KERIM",
            203500.00,
            "10%",
            None,
            9892.36,
            9892.36,
            193607.64,
            "NDB",
        ]
    )
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_excel_archive_fixture():
    rows = parse_bank_workbook(_build_aai_xlsx(), filename="aai.xlsx")
    assert any(r.categorie_code == "TY-142010" for r in rows)
    acq = [r for r in rows if r.date_acquisition == date(2026, 1, 6)]
    assert len(acq) == 1
    assert acq[0].designation.startswith("RGLT")
    assert acq[0].valeur_brute == Decimal("203500.00")
    assert acq[0].is_report is False


def test_validate_nature_code():
    assert validate_nature_code("TY-142010", required=False) == "TY-142010"
    assert validate_nature_code(None, required=False) is None
    try:
        validate_nature_code(None, required=True)
        assert False, "expected ValidationError"
    except ValidationError:
        pass
    assert nature_label("TY-142010") == "AAI"


def _build_table_pdf() -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    data = [
        [
            "Date",
            "Qté",
            "Désignation",
            "Valeur d'Acquisition",
            "Taux",
            "Fin Exr.Précé",
            "Dotation",
            "Fin Exercice",
            "Net Comptable",
            "AGENCE",
        ],
        [
            "15/03/2025",
            "1",
            "PC PORTABLE DELL",
            "45000,00",
            "20%",
            "0",
            "6750,00",
            "6750,00",
            "38250,00",
            "SIEGE",
        ],
    ]
    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
            ]
        )
    )
    doc.build([table])
    return buf.getvalue()


def test_parse_pdf_table_fixture():
    rows = parse_bank_pdf(_build_table_pdf(), nature_code="TY-142041", filename="matinfo.pdf")
    assert len(rows) >= 1
    assert all(r.categorie_code == "TY-142041" for r in rows)
    hit = next(r for r in rows if "DELL" in r.designation.upper())
    assert hit.date_acquisition == date(2025, 3, 15)
    assert hit.valeur_brute == Decimal("45000.00")


def test_parse_pdf_image_only_errors():
    """PDF sans tableau extractible → ValidationError clair."""
    from reportlab.pdfgen import canvas

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.drawString(100, 750, "Scan image only — no table structure")
    c.save()
    try:
        parse_bank_pdf(buf.getvalue(), nature_code="TY-142010")
        assert False, "expected ValidationError"
    except ValidationError as exc:
        assert "PDF image" in exc.message or "tableau" in exc.message.lower()
