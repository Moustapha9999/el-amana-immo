"""Exports PDF fiches Moyens Généraux (BC, notes, demandes) — logo BEA."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.data.el_amana_referentiel import BANQUE_EL_AMANA
from app.services.reporting_export import (
    format_export_datetime,
    resolve_bea_logo_path,
)
import io

BEA_NAVY = colors.HexColor("#1E3A5F")
BEA_LINE = colors.HexColor("#94A3B8")
BEA_FILL = colors.HexColor("#F1F5F9")
BEA_SOFT = colors.HexColor("#E8EEF5")
BEA_META = colors.HexColor("#64748B")
_TZ = ZoneInfo("Africa/Nouakchott")


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "MgTitle",
            parent=base["Heading1"],
            fontSize=14,
            spaceAfter=8,
            textColor=BEA_NAVY,
        ),
        "bank": ParagraphStyle(
            "BcBank",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            textColor=BEA_NAVY,
            spaceAfter=2,
        ),
        "bc_title": ParagraphStyle(
            "BcTitle",
            parent=base["Normal"],
            fontSize=15,
            leading=18,
            spaceBefore=0,
            spaceAfter=4,
            textColor=colors.HexColor("#0F172A"),
            fontName="Helvetica-Bold",
        ),
        "export_meta": ParagraphStyle(
            "BcExportMeta",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=9,
            textColor=BEA_META,
            spaceAfter=8,
        ),
        "meta": ParagraphStyle("MgMeta", parent=base["Normal"], fontSize=9, leading=12),
        "label": ParagraphStyle(
            "BcLabel",
            parent=base["Normal"],
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#475569"),
            fontName="Helvetica-Bold",
        ),
        "value": ParagraphStyle(
            "BcValue",
            parent=base["Normal"],
            fontSize=9,
            leading=11,
            textColor=colors.HexColor("#0F172A"),
        ),
        "cell": ParagraphStyle("MgCell", parent=base["Normal"], fontSize=8, leading=10),
        "cell_center": ParagraphStyle(
            "MgCellCenter", parent=base["Normal"], fontSize=8, leading=10, alignment=TA_CENTER
        ),
        "cell_right": ParagraphStyle(
            "MgCellRight", parent=base["Normal"], fontSize=8, leading=10, alignment=TA_RIGHT
        ),
        "header_cell": ParagraphStyle(
            "BcHeaderCell",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=colors.whitesmoke,
            alignment=TA_CENTER,
        ),
        "small": ParagraphStyle(
            "BcSmall",
            parent=base["Normal"],
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#334155"),
            alignment=TA_CENTER,
        ),
        "visa": ParagraphStyle(
            "BcVisa",
            parent=base["Normal"],
            fontSize=9,
            leading=12,
            alignment=TA_CENTER,
            fontName="Helvetica-Bold",
            textColor=BEA_NAVY,
        ),
    }


def _doc_buffer(build_fn, *, with_logo: bool = True) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=14 * mm,
    )
    styles = _styles()
    story = []
    if with_logo:
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


def money(value: Decimal | None) -> str:
    if value is None:
        return "0,00"
    return f"{value:,.2f}".replace(",", " ").replace(".", ",")


def _box(label: str, value: str, styles, *, min_h: float = 10 * mm, width: float = 85 * mm) -> Table:
    """Libellé au-dessus (hors case) + valeur en gras dans le cadre."""
    inner_w = max(width - 2 * mm, 20 * mm)
    raw = (value or "—").strip() or "—"
    value_cell = Table(
        [[Paragraph(f"<b>{raw}</b>", styles["value"])]],
        colWidths=[inner_w],
    )
    value_cell.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ]
        )
    )
    framed = Table([[value_cell]], colWidths=[width], rowHeights=[min_h])
    framed.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.7, BEA_NAVY),
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    block = Table(
        [
            [Paragraph(label, styles["label"])],
            [Spacer(1, 1 * mm)],
            [framed],
        ],
        colWidths=[width],
    )
    block.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return block


def _qty_int(value) -> str:
    """Quantité affichée en entier (pas comme les prix décimaux)."""
    if value is None:
        return "—"
    try:
        return str(int(value))
    except (TypeError, ValueError):
        try:
            return str(int(float(value)))
        except (TypeError, ValueError):
            return "—"


def _plain_line(label: str, value: str, styles) -> Paragraph:
    return Paragraph(
        f"<b>{label}</b> {value or '—'}",
        styles["meta"],
    )


def _visa_block(label: str, styles) -> Table:
    """Libellé + zone de signature vide en dessous (sans texte « Signature / cachet »)."""
    zone = Table([[""]], colWidths=[80 * mm], rowHeights=[22 * mm])
    zone.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.7, BEA_NAVY),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    block = Table(
        [
            [Paragraph(label, styles["visa"])],
            [Spacer(1, 3 * mm)],
            [zone],
        ],
        colWidths=[82 * mm],
    )
    block.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ]
        )
    )
    return block


def _bc_footer(canvas, doc, *, exported_label: str) -> None:
    """Pied de page style Immo — sans bandeau bleu du haut."""
    canvas.saveState()
    page_w, _ = canvas._pagesize
    canvas.setStrokeColor(colors.HexColor("#1A5278"))
    canvas.setLineWidth(1.2)
    canvas.line(12 * mm, 12 * mm, page_w - 12 * mm, 12 * mm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(BEA_META)
    canvas.drawString(12 * mm, 7 * mm, BANQUE_EL_AMANA["raison_sociale"])
    canvas.drawCentredString(page_w / 2, 7 * mm, exported_label)
    canvas.drawRightString(page_w - 12 * mm, 7 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _bc_pdf_filename(reference: str) -> str:
    """Nom de fichier : Bon-Commande-00XXXX.pdf (chiffres de la référence, pad ≥ 6)."""
    digits = "".join(ch for ch in (reference or "") if ch.isdigit()) or "0"
    return f"Bon-Commande-{digits.zfill(6)}.pdf"


def pdf_bon_commande(
    bon,
    *,
    signataire_1: str | None = None,
    signataire_2: str | None = None,
) -> bytes:
    """PDF BC : en-tête Immo (logo + banque) + fiche métier + tableau stylé."""
    when = datetime.now(_TZ)
    exported_label = f"Exporté le {format_export_datetime(when)}"
    styles = _styles()
    s1 = (signataire_1 or "").strip() or "Signature Chef Sce Moyens Généraux"
    s2 = (signataire_2 or "").strip() or "Signature Directrice des Ressources"
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=18 * mm,
        title=f"Bon de commande {bon.reference}",
    )

    date_bc = bon.date_bc.strftime("%d/%m/%Y") if bon.date_bc else "—"
    dem_date = (
        bon.demandeur_date.strftime("%d/%m/%Y") if getattr(bon, "demandeur_date", None) else ""
    )

    story: list = []
    logo = resolve_bea_logo_path()
    if logo is not None:
        try:
            story.append(Image(str(logo), width=42 * mm, height=14 * mm))
            story.append(Spacer(1, 1 * mm))
        except Exception:
            pass

    story.append(Paragraph("BON DE COMMANDE", styles["bc_title"]))

    # Largeur utile A4 (210 − 2×14) = 182 mm — mêmes extrémités gauche/droite partout.
    content_w = 182 * mm
    left_w = 85 * mm
    gutter = 12 * mm
    right_w = 85 * mm  # 85 + 12 + 85 = 182

    # Ligne d’identité : numéro/date et fournisseur alignés (même hauteur / extrémités).
    numero_cell = Table(
        [
            [
                Paragraph(
                    f"<b>Numéro</b> {bon.reference}<br/><b>Date</b> {date_bc}",
                    styles["meta"],
                )
            ]
        ],
        colWidths=[left_w],
    )
    numero_cell.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, BEA_LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    adresse_fourn = (bon.fournisseur_adresse or "").strip() or "—"
    fournisseur_cell = Table(
        [
            [
                Paragraph(
                    f"<b>{bon.fournisseur_raison_sociale or '—'}</b><br/>"
                    f"NIF {bon.fournisseur_nif or '—'}<br/>"
                    f"{bon.fournisseur_telephone or '—'}<br/>"
                    f"{adresse_fourn}",
                    styles["meta"],
                )
            ]
        ],
        colWidths=[right_w],
    )
    fournisseur_cell.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), BEA_SOFT),
                ("BOX", (0, 0), (-1, -1), 0.5, BEA_LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    header = Table(
        [[numero_cell, "", fournisseur_cell]],
        colWidths=[left_w, gutter, right_w],
    )
    header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    # Lignes appariées : mêmes hauteurs / extrémités gauche-droite.
    # Conditions… collées sous facturation, même largeur / bord gauche.
    row_h = 12 * mm
    row_h_tall = 16 * mm
    fields = Table(
        [
            [
                _box("Département", bon.departement or "", styles, min_h=row_h, width=left_w),
                "",
                _box(
                    "Adresse de livraison",
                    bon.adresse_livraison
                    or getattr(bon, "agence_livraison_snapshot", None)
                    or "",
                    styles,
                    min_h=row_h,
                    width=right_w,
                ),
            ],
            [
                _box("Projet", bon.projet or "", styles, min_h=row_h_tall, width=left_w),
                "",
                _box(
                    "Demandeur",
                    f"Nom : {bon.demandeur_nom or '—'}<br/>"
                    f"Date : {dem_date or '—'}",
                    styles,
                    min_h=row_h_tall,
                    width=right_w,
                ),
            ],
            [
                _box(
                    "Acheteur (interne BEA)",
                    f"Nom : {bon.acheteur_nom or '—'}<br/>Tél. : {bon.acheteur_tel or '—'}",
                    styles,
                    min_h=row_h_tall,
                    width=left_w,
                ),
                "",
                "",
            ],
            [
                _box(
                    "Adresse de facturation",
                    bon.adresse_facturation
                    or getattr(bon, "agence_facturation_snapshot", None)
                    or "",
                    styles,
                    min_h=row_h,
                    width=left_w,
                ),
                "",
                "",
            ],
            [
                _plain_line("Conditions :", bon.conditions or "Voir pièce jointe", styles),
                "",
                "",
            ],
            [
                _plain_line("Incoterm :", bon.incoterm or "N/A", styles),
                "",
                "",
            ],
            [
                _plain_line(
                    "Conditions de paiement :",
                    bon.conditions_paiement or "—",
                    styles,
                ),
                "",
                "",
            ],
            [
                _plain_line("Moyen de paiement :", bon.moyen_paiement or "—", styles),
                "",
                "",
            ],
        ],
        colWidths=[left_w, gutter, right_w],
        spaceBefore=0,
        spaceAfter=0,
    )
    fields.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                # Conditions / paiement : texte libre sous facturation (sans cadre).
                ("BOTTOMPADDING", (0, 4), (0, -1), 1),
                ("TOPPADDING", (0, 4), (0, -1), 1),
            ]
        )
    )

    head = [
        Paragraph("Code produit", styles["header_cell"]),
        Paragraph("Département", styles["header_cell"]),
        Paragraph("Description &amp; Commentaires", styles["header_cell"]),
        Paragraph("Quantité", styles["header_cell"]),
        Paragraph("U.O.M", styles["header_cell"]),
        Paragraph("Prix unitaire (MRU)", styles["header_cell"]),
        Paragraph("Prix total (MRU)", styles["header_cell"]),
    ]
    rows: list = [head]
    lignes = sorted(bon.lignes or [], key=lambda x: x.sort_order)
    for ligne in lignes:
        rows.append(
            [
                Paragraph(ligne.code_produit or "—", styles["cell_center"]),
                Paragraph(ligne.departement or bon.departement or "—", styles["cell_center"]),
                Paragraph(ligne.description or "", styles["cell"]),
                Paragraph(_qty_int(ligne.quantite), styles["cell_center"]),
                Paragraph(ligne.uom or "U", styles["cell_center"]),
                Paragraph(money(ligne.prix_unitaire), styles["cell_right"]),
                Paragraph(money(ligne.prix_total), styles["cell_right"]),
            ]
        )
    if not lignes:
        rows.append(["", "", Paragraph("Aucune ligne", styles["cell"]), "", "", "", ""])

    # Même largeur totale que le bloc infos (182 mm).
    col_w = [22 * mm, 24 * mm, 58 * mm, 18 * mm, 16 * mm, 22 * mm, 22 * mm]
    table = Table(rows, colWidths=col_w, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BEA_NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BEA_FILL]),
            ]
        )
    )

    # Totaux alignés : libellés à gauche, montants à droite, même cadre.
    totals_inner = Table(
        [
            [
                Paragraph("<b>Prix total (MRU) HT</b>", styles["meta"]),
                Paragraph(f"<b>{money(bon.total_ht)}</b>", styles["cell_right"]),
            ],
            [
                Paragraph("<b>Prix total (MRU) TVA</b>", styles["meta"]),
                Paragraph(
                    f"<b>{money(getattr(bon, 'total_tva', None))}</b>",
                    styles["cell_right"],
                ),
            ],
            [
                Paragraph("<b>Prix total (MRU) TTC</b>", styles["meta"]),
                Paragraph(
                    f"<b>{money(getattr(bon, 'total_ttc', None) or bon.total_ht)}</b>",
                    styles["cell_right"],
                ),
            ],
        ],
        colWidths=[52 * mm, 28 * mm],
    )
    totals_inner.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), BEA_SOFT),
                ("BOX", (0, 0), (-1, -1), 0.6, BEA_NAVY),
                ("LINEBELOW", (0, 0), (-1, -2), 0.4, BEA_LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    total_block = Table(
        [["", totals_inner]],
        colWidths=[content_w - 80 * mm, 80 * mm],
    )
    total_block.setStyle(
        TableStyle(
            [
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    visas = Table(
        [
            [
                _visa_block(s1, styles),
                _visa_block(s2, styles),
            ]
        ],
        colWidths=[left_w + gutter / 2, right_w + gutter / 2],
    )
    visas.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    story.extend(
        [
            header,
            Spacer(1, 3 * mm),
            fields,
            Spacer(1, 4 * mm),
            table,
            Spacer(1, 3 * mm),
            total_block,
            Spacer(1, 22 * mm),
            KeepTogether([visas]),
        ]
    )

    doc.build(
        story,
        onFirstPage=lambda c, d: _bc_footer(c, d, exported_label=exported_label),
        onLaterPages=lambda c, d: _bc_footer(c, d, exported_label=exported_label),
    )
    return buf.getvalue()


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
                    money(ligne.montant),
                    ligne.mode_reglement or "",
                ]
            )
        rows.append(["", "TOTAL", "", money(note.total_mru), ""])
        table = Table(rows, colWidths=[25 * mm, 55 * mm, 40 * mm, 25 * mm, 30 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), BEA_NAVY),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ]
            )
        )
        out.extend([table, Spacer(1, 12 * mm)])
        visas = Table(
            [
                [
                    _visa_block("Visa Chef Sce Moyens Généraux", styles),
                    _visa_block("Visa Directrice des Ressources", styles),
                ]
            ],
            colWidths=[95 * mm, 95 * mm],
        )
        out.append(visas)
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
                    ("BACKGROUND", (0, 0), (-1, 0), BEA_NAVY),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ]
            )
        )
        out.extend([table, Spacer(1, 12 * mm)])
        visas = Table(
            [
                [
                    _visa_block("Visa Agence", styles),
                    _visa_block("Visa Moyens Généraux", styles),
                ]
            ],
            colWidths=[95 * mm, 95 * mm],
        )
        out.append(visas)
        return out

    return _doc_buffer(body)
