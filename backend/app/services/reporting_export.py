from datetime import date
from io import BytesIO

from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models import EcritureComptable, Immobilisation


def ecritures_to_excel(rows: list[EcritureComptable]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Ecritures"
    headers = [
        "Date",
        "Journal",
        "Libellé",
        "Débit",
        "Crédit",
        "Montant",
        "Référence",
        "Auto",
        "Validée",
    ]
    ws.append(headers)
    for row in rows:
        ws.append(
            [
                row.date_ecriture.isoformat(),
                row.journal_code,
                row.libelle,
                row.compte_debit,
                row.compte_credit,
                float(row.montant),
                row.reference or "",
                "Oui" if row.generee_auto else "Non",
                "Oui" if row.validee else "Non",
            ]
        )
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def ecritures_to_pdf(rows: list[EcritureComptable], *, titre: str = "Journal des écritures comptables") -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), title=titre)
    styles = getSampleStyleSheet()
    story = [Paragraph(titre, styles["Title"]), Spacer(1, 12)]
    data = [["Date", "Jnl", "Libellé", "Débit", "Crédit", "Montant", "Réf."]]
    for row in rows:
        data.append(
            [
                row.date_ecriture.strftime("%d/%m/%Y"),
                row.journal_code,
                row.libelle[:40],
                row.compte_debit,
                row.compte_credit,
                f"{row.montant:,.2f}",
                (row.reference or "")[:20],
            ]
        )
    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    return buf.getvalue()


def audit_logs_to_excel(rows: list) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Audit"
    ws.append(["Date", "Utilisateur", "Action", "Entité", "ID entité", "IP"])
    for row in rows:
        email = row.user.email if getattr(row, "user", None) else ""
        ws.append(
            [
                row.created_at.isoformat() if row.created_at else "",
                email,
                row.action,
                row.entity,
                row.entity_id or "",
                row.ip_address or "",
            ]
        )
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def immobilisations_to_excel(rows: list[Immobilisation]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Immobilisations"
    ws.append(
        [
            "Code inventaire",
            "Désignation",
            "Statut",
            "Valeur brute",
            "Compte immo",
            "Date acquisition",
        ]
    )
    for row in rows:
        ws.append(
            [
                row.code_inventaire,
                row.designation,
                row.statut.value if hasattr(row.statut, "value") else str(row.statut),
                float(row.valeur_brute),
                row.compte_immobilisation or "",
                row.date_acquisition.isoformat(),
            ]
        )
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
