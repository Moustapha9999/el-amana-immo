"""Exports PDF fiches Moyens Généraux (BC, notes, demandes) — logo BEA."""

from __future__ import annotations

from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.services.reporting_export import resolve_bea_logo_path
import io


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "MgTitle",
            parent=base["Heading1"],
            fontSize=14,
            spaceAfter=8,
            textColor=colors.HexColor("#1E3A5F"),
        ),
        "meta": ParagraphStyle("MgMeta", parent=base["Normal"], fontSize=9, leading=12),
        "cell": ParagraphStyle("MgCell", parent=base["Normal"], fontSize=8, leading=10),
    }


def _doc_buffer(build_fn) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )
    styles = _styles()
    story = []
    logo = resolve_bea_logo_path()
    if logo is not None:
        try:
            story.append(Image(str(logo), width=45 * mm, height=15 * mm))
            story.append(Spacer(1, 3 * mm))
        except Exception:
            pass
    story.extend(build_fn(styles))
    doc.build(story)
    return buf.getvalue()


def pdf_bon_commande(bon) -> bytes:
    def body(styles):
        out = [
            Paragraph("BANQUE EL AMANA — BON DE COMMANDE", styles["title"]),
            Paragraph(
                f"<b>Réf.</b> {bon.reference} &nbsp;|&nbsp; <b>Date</b> {bon.date_bc} "
                f"&nbsp;|&nbsp; <b>Statut</b> {bon.statut}",
                styles["meta"],
            ),
            Paragraph(
                f"<b>Fournisseur</b> {bon.fournisseur_raison_sociale or '—'} "
                f"(NIF {bon.fournisseur_nif or '—'})<br/>"
                f"<b>Tél.</b> {bon.fournisseur_telephone or '—'} — {bon.fournisseur_adresse or ''}<br/>"
                f"<b>Département</b> {bon.departement or '—'} — <b>Acheteur</b> {bon.acheteur_nom or '—'}",
                styles["meta"],
            ),
            Spacer(1, 6 * mm),
        ]
        rows = [["Code", "Description", "Qté", "UOM", "PU", "Total"]]
        for ligne in sorted(bon.lignes, key=lambda x: x.sort_order):
            rows.append(
                [
                    ligne.code_produit or "",
                    Paragraph(ligne.description, styles["cell"]),
                    f"{ligne.quantite}",
                    ligne.uom,
                    f"{ligne.prix_unitaire}",
                    f"{ligne.prix_total}",
                ]
            )
        rows.append(["", "", "", "", "Total HT", f"{bon.total_ht}"])
        table = Table(rows, colWidths=[22 * mm, 70 * mm, 18 * mm, 15 * mm, 25 * mm, 25 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A5F")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        out.append(table)
        out.append(Spacer(1, 12 * mm))
        out.append(
            Paragraph(
                "Visa Chef Sce Moyens Généraux _______________ &nbsp;&nbsp;&nbsp; "
                "Visa Directrice des Ressources _______________",
                styles["meta"],
            )
        )
        return out

    return _doc_buffer(body)


def pdf_note_frais(note) -> bytes:
    def body(styles):
        out = [
            Paragraph("BANQUE EL AMANA — NOTE DE FRAIS", styles["title"]),
            Paragraph(
                f"<b>Réf.</b> {note.reference} &nbsp;|&nbsp; <b>Date</b> {note.date_demande} "
                f"&nbsp;|&nbsp; <b>Statut</b> {note.statut}<br/>"
                f"<b>Demandeur</b> {note.demandeur_nom or '—'} — {note.fonction or ''} / {note.departement or ''}<br/>"
                f"<b>Agence</b> {note.agence_libelle_snapshot or '—'}",
                styles["meta"],
            ),
            Spacer(1, 6 * mm),
        ]
        rows = [["Date", "Description", "Motif", "Montant", "Règlement"]]
        for ligne in sorted(note.lignes, key=lambda x: x.sort_order):
            rows.append(
                [
                    str(ligne.date_depense),
                    Paragraph(ligne.description, styles["cell"]),
                    ligne.motif or "",
                    f"{ligne.montant}",
                    ligne.mode_reglement or "",
                ]
            )
        rows.append(["", "TOTAL", "", f"{note.total_mru}", ""])
        table = Table(rows, colWidths=[25 * mm, 55 * mm, 40 * mm, 25 * mm, 30 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A5F")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ]
            )
        )
        out.extend([table, Spacer(1, 12 * mm)])
        out.append(
            Paragraph(
                "Visa Chef Sce MG _______________ &nbsp;&nbsp;&nbsp; "
                "Visa Directrice des Ressources _______________",
                styles["meta"],
            )
        )
        return out

    return _doc_buffer(body)


def pdf_demande_fourniture(demande) -> bytes:
    def body(styles):
        out = [
            Paragraph("BANQUE EL AMANA — EXPRESSION DE BESOIN / BON DE SORTIE", styles["title"]),
            Paragraph(
                f"<b>Réf.</b> {demande.reference} &nbsp;|&nbsp; <b>Date</b> {demande.date_demande} "
                f"&nbsp;|&nbsp; <b>Statut</b> {demande.statut}<br/>"
                f"<b>Agence</b> {demande.agence_libelle_snapshot or '—'} — {demande.agence_adresse_snapshot or ''}<br/>"
                f"<b>Demandeur</b> {demande.demandeur_nom or '—'} ({demande.fonction or '—'})",
                styles["meta"],
            ),
            Spacer(1, 6 * mm),
        ]
        rows = [["Désignation", "Qté demandée", "Qté accordée"]]
        for ligne in sorted(demande.lignes, key=lambda x: x.sort_order):
            rows.append(
                [
                    Paragraph(ligne.designation, styles["cell"]),
                    f"{ligne.quantite_demandee}",
                    f"{ligne.quantite_accordee if ligne.quantite_accordee is not None else ''}",
                ]
            )
        table = Table(rows, colWidths=[110 * mm, 35 * mm, 35 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A5F")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ]
            )
        )
        out.extend([table, Spacer(1, 12 * mm)])
        out.append(
            Paragraph(
                "Visa Agence _______________ &nbsp;&nbsp;&nbsp; Visa Moyens Généraux _______________",
                styles["meta"],
            )
        )
        return out

    return _doc_buffer(body)


def money(value: Decimal | None) -> str:
    if value is None:
        return "0"
    return f"{value:.2f}"
