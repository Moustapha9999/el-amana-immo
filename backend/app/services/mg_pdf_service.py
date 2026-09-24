"""Exports PDF fiches Moyens Généraux (BC, notes, demandes) — logo BEA."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
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
            fontSize=13,
            leading=15,
            spaceBefore=0,
            spaceAfter=2,
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
        "meta": ParagraphStyle("MgMeta", parent=base["Normal"], fontSize=8, leading=10),
        "label": ParagraphStyle(
            "BcLabel",
            parent=base["Normal"],
            fontSize=7,
            leading=9,
            textColor=colors.HexColor("#475569"),
            fontName="Helvetica-Bold",
        ),
        "value": ParagraphStyle(
            "BcValue",
            parent=base["Normal"],
            fontSize=8,
            leading=10,
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
            fontSize=8,
            leading=10,
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


def _box(label: str, value: str, styles, *, min_h: float = 8 * mm, width: float = 85 * mm) -> Table:
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
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
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
            [Spacer(1, 0.5 * mm)],
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


def _visa_block(label: str, styles, *, zone_h: float = 16 * mm, width: float = 80 * mm) -> Table:
    """Libellé + zone de signature vide en dessous (sans texte « Signature / cachet »)."""
    zone = Table([[""]], colWidths=[width], rowHeights=[zone_h])
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
            [Spacer(1, 1.5 * mm)],
            [zone],
        ],
        colWidths=[width + 2 * mm],
    )
    block.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
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
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=10 * mm,
        bottomMargin=16 * mm,
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
            story.append(Image(str(logo), width=36 * mm, height=12 * mm))
            story.append(Spacer(1, 0.5 * mm))
        except Exception:
            pass

    story.append(Paragraph("BON DE COMMANDE", styles["bc_title"]))

    # Largeur utile A4 (210 − 2×12) = 186 mm — mêmes extrémités gauche/droite partout.
    content_w = 186 * mm
    left_w = 88 * mm
    gutter = 10 * mm
    right_w = 88 * mm  # 88 + 10 + 88 = 186

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
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
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
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
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
    row_h = 9 * mm
    row_h_tall = 12 * mm
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
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
                # Conditions / paiement : texte libre sous facturation (sans cadre).
                ("BOTTOMPADDING", (0, 4), (0, -1), 0.5),
                ("TOPPADDING", (0, 4), (0, -1), 0.5),
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

    # Même largeur totale que le bloc infos (186 mm).
    col_w = [22 * mm, 24 * mm, 62 * mm, 18 * mm, 16 * mm, 22 * mm, 22 * mm]
    table = Table(rows, colWidths=col_w, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BEA_NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
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
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
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
                _visa_block(s1, styles, zone_h=14 * mm, width=78 * mm),
                _visa_block(s2, styles, zone_h=14 * mm, width=78 * mm),
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
            Spacer(1, 2 * mm),
            fields,
            Spacer(1, 2.5 * mm),
            table,
            Spacer(1, 2 * mm),
            total_block,
            Spacer(1, 6 * mm),
            KeepTogether([visas]),
        ]
    )

    doc.build(
        story,
        onFirstPage=lambda c, d: _bc_footer(c, d, exported_label=exported_label),
        onLaterPages=lambda c, d: _bc_footer(c, d, exported_label=exported_label),
    )
    return buf.getvalue()


def pdf_note_frais(
    note,
    *,
    signataire_1: str | None = None,
    signataire_2: str | None = None,
    signataire_1_role: str | None = None,
    signataire_2_role: str | None = None,
) -> bytes:
    """PDF note de frais — fiche officielle BEA (paysage), cases alignées."""
    styles = _styles()
    s1_role = (signataire_1 or signataire_1_role or "").strip() or "Signature Chef Sce Moyens Généraux"
    s2_role = (signataire_2 or signataire_2_role or "").strip() or "Signature Directrice des Ressources"
    s1_name = ""
    s2_name = ""
    if (signataire_1_role or "").strip() and (signataire_1 or "").strip():
        s1_role = signataire_1_role.strip()
        s1_name = signataire_1.strip()
    if (signataire_2_role or "").strip() and (signataire_2 or "").strip():
        s2_role = signataire_2_role.strip()
        s2_name = signataire_2.strip()

    date_dem = note.date_demande.strftime("%d/%m/%Y") if note.date_demande else "—"
    agence = note.agence_libelle_snapshot or "—"
    title = f"NOTE DE FRAIS : {agence}"

    cell = styles["cell"]
    cell_c = styles["cell_center"]
    label = styles["label"]
    value = styles["value"]
    small = ParagraphStyle(
        "NfDept",
        parent=styles["meta"],
        fontSize=8,
        leading=11,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#0F172A"),
    )
    title_style = ParagraphStyle(
        "NfTitle",
        parent=styles["bc_title"],
        fontSize=11,
        alignment=TA_CENTER,
        spaceBefore=0,
        spaceAfter=0,
    )
    ink = colors.HexColor("#0F172A")
    page_w = 273 * mm  # A4 paysage − marges 12 mm
    # Logo compact à gauche | département centré | identité collée à droite
    logo_w, dept_w, id_w = 48 * mm, 105 * mm, 120 * mm
    header_h = 36 * mm

    dept_title = ParagraphStyle(
        "NfDeptTitle",
        parent=small,
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        alignment=TA_CENTER,
    )
    dept_sub = ParagraphStyle(
        "NfDeptSub",
        parent=small,
        fontSize=8.5,
        leading=11,
        alignment=TA_CENTER,
    )

    # --- Logo (contenu sans cadre propre : cadre fourni par la grille en-tête) ---
    logo_bits: list = []
    logo = resolve_bea_logo_path()
    if logo is not None:
        try:
            logo_bits.append(Image(str(logo), width=32 * mm, height=11 * mm))
        except Exception:
            logo_bits.append(Paragraph("<b>BEA</b>", styles["bank"]))
    else:
        logo_bits.append(Paragraph("<b>BEA — Banque El Amana</b>", styles["bank"]))
    logo_bits.append(Paragraph("<b>Banque El Amana</b>", small))
    logo_inner = Table([[b] for b in logo_bits], colWidths=[logo_w - 2 * mm])
    logo_inner.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    dept_inner = Table(
        [
            [
                Paragraph(
                    "Département Ressources Humaines<br/>et Moyens Généraux",
                    dept_title,
                )
            ],
            [Paragraph("Service Moyens Généraux", dept_sub)],
        ],
        colWidths=[dept_w - 2 * mm],
    )
    dept_inner.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (0, 0), 4),
                ("BOTTOMPADDING", (0, 0), (0, 0), 2),
                ("TOPPADDING", (0, 1), (0, 1), 2),
                ("BOTTOMPADDING", (0, 1), (0, 1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    id_label_w = 46 * mm
    id_value_w = id_w  # rempli à 100 % de la case droite (padding 0 sur la cellule)
    id_rows = [
        [
            Paragraph("Identité du demandeur", label),
            Paragraph(f"<b>{note.demandeur_nom or '—'}</b>", value),
        ],
        [
            Paragraph("Département", label),
            Paragraph(f"<b>{note.departement or '—'}</b>", value),
        ],
        [
            Paragraph("Fonction", label),
            Paragraph(f"<b>{note.fonction or '—'}</b>", value),
        ],
        [
            Paragraph("Date de la demande", label),
            Paragraph(f"<b>{date_dem}</b>", value),
        ],
    ]
    id_inner = Table(id_rows, colWidths=[id_label_w, id_value_w - id_label_w])
    id_inner.setStyle(
        TableStyle(
            [
                ("INNERGRID", (0, 0), (-1, -1), 0.55, ink),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
                ("BACKGROUND", (0, 0), (0, -1), BEA_SOFT),
            ]
        )
    )

    # Une seule grille : 3 cases de même hauteur — identité collée à droite
    header = Table(
        [[logo_inner, dept_inner, id_inner]],
        colWidths=[logo_w, dept_w, id_w],
        rowHeights=[header_h],
    )
    header.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 1.15, ink),
                ("INNERGRID", (0, 0), (-1, -1), 1.15, ink),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (0, 0), "CENTER"),
                ("ALIGN", (1, 0), (1, 0), "CENTER"),
                ("ALIGN", (2, 0), (2, 0), "RIGHT"),
                ("LEFTPADDING", (0, 0), (1, 0), 1),
                ("RIGHTPADDING", (0, 0), (1, 0), 1),
                ("LEFTPADDING", (2, 0), (2, 0), 0),
                ("RIGHTPADDING", (2, 0), (2, 0), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    # --- Tableau dépenses : uniquement les lignes saisies ---
    col_w = [36 * mm, 72 * mm, 58 * mm, 40 * mm, 67 * mm]
    title_row = [Paragraph(f"<b>{title}</b>", title_style), "", "", "", ""]
    header_row = [
        Paragraph("<b>Date de la dépense</b>", cell_c),
        Paragraph("<b>Description</b>", cell_c),
        Paragraph("<b>Motif</b>", cell_c),
        Paragraph("<b>Montant En MRU</b>", cell_c),
        Paragraph("<b>Mode de règlement</b>", cell_c),
    ]
    data_rows: list = [title_row, header_row]

    lignes = sorted(note.lignes or [], key=lambda x: x.sort_order)
    if not lignes:
        data_rows.append(
            [
                Paragraph("—", cell_c),
                Paragraph("Aucune ligne", cell),
                Paragraph("", cell),
                Paragraph("—", cell_c),
                Paragraph("", cell_c),
            ]
        )
    else:
        for lig in lignes:
            d = lig.date_depense.strftime("%d/%m/%Y") if lig.date_depense else ""
            data_rows.append(
                [
                    Paragraph(d, cell_c),
                    Paragraph(lig.description or "", cell),
                    Paragraph(lig.motif or "", cell),
                    Paragraph(money(lig.montant), cell_c),
                    Paragraph(lig.mode_reglement or "", cell_c),
                ]
            )

    data_rows.append(
        [
            Paragraph("<b>TOTAL</b>", cell_c),
            "",
            "",
            Paragraph(f"<b>{money(note.total_mru)}</b>", cell_c),
            "",
        ]
    )

    body = Table(data_rows, colWidths=col_w)
    last = len(data_rows) - 1
    body.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 1.15, ink),
                ("LINEBELOW", (0, 0), (-1, 0), 1.15, ink),
                ("INNERGRID", (0, 1), (-1, -1), 0.7, ink),
                ("SPAN", (0, 0), (-1, 0)),
                ("SPAN", (0, last), (2, last)),
                ("BACKGROUND", (0, 0), (-1, 0), colors.white),
                ("BACKGROUND", (0, 1), (-1, 1), BEA_SOFT),
                ("BACKGROUND", (0, last), (-1, last), BEA_FILL),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, 0), 7),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 7),
            ]
        )
    )

    # Signatures : uniquement les libellés / noms (pas de trait ni « Nom du signataire »)
    sig_style = ParagraphStyle(
        "NfSig",
        parent=cell_c,
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        alignment=TA_CENTER,
    )

    def _sig(role: str, name: str) -> Table:
        text = name.strip() if name and name.strip() else role
        t = Table([[Paragraph(f"<b>{text}</b>", sig_style)]], colWidths=[page_w / 2 - 6 * mm])
        t.setStyle(
            TableStyle(
                [
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        return t

    signs = Table(
        [[_sig(s1_role, s1_name), _sig(s2_role, s2_name)]],
        colWidths=[page_w / 2, page_w / 2],
    )
    signs.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    meta = Paragraph(
        f"Réf. {note.reference} &nbsp;·&nbsp; Statut {note.statut} "
        f"&nbsp;·&nbsp; Version {getattr(note, 'pdf_version', 1)}",
        ParagraphStyle("NfMeta", parent=styles["export_meta"], fontSize=7, alignment=TA_CENTER, spaceAfter=0),
    )

    # Cadre unique autour de l'en-tête + tableau (comme la fiche papier)
    fiche = Table(
        [[header], [body]],
        colWidths=[page_w],
    )
    fiche.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 1.35, ink),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 1), (0, 1), 0),
            ]
        )
    )

    story = [fiche, Spacer(1, 10 * mm), signs, Spacer(1, 4 * mm), meta]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        title=f"Note de frais {note.reference}",
    )
    doc.build(story)
    return buf.getvalue()


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
