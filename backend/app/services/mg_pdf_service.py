"""Exports PDF fiches Moyens Généraux (BC, notes, demandes) — logo BEA."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    KeepTogether,
    PageTemplate,
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


def resolve_note_frais_logo_path() -> Path | None:
    """Logo empilé (cercle BEA, arabe, Banque El Amana) pour la fiche note de frais."""
    path = Path(__file__).resolve().parents[1] / "assets" / "brand" / "logo-bea-empile.png"
    return path if path.is_file() else None


def _esc(value: object | None, *, empty: str = "") -> str:
    text = "" if value is None else str(value).strip()
    return escape(text) if text else empty


def pdf_note_frais(
    note,
    *,
    signataire_1: str | None = None,
    signataire_2: str | None = None,
    signataire_1_role: str | None = None,
    signataire_2_role: str | None = None,
    orientation: str | None = None,
) -> bytes:
    """PDF note de frais — fiche papier BEA, A4 portrait ou paysage."""
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

    date_dem = note.date_demande.strftime("%d/%m/%Y") if note.date_demande else ""
    agence = (note.agence_libelle_snapshot or "").strip()
    title = f"NOTE DE FRAIS : {agence.upper()}" if agence else "NOTE DE FRAIS"

    ink = colors.black
    orient = (orientation or "paysage").strip().lower()
    portrait = orient in {"portrait", "p", "a4-portrait"}
    page_size = A4 if portrait else landscape(A4)
    margin_x = 11 * mm
    margin_top = 11 * mm
    margin_bottom = 14 * mm
    page_w = page_size[0] - 2 * margin_x
    frame_h = page_size[1] - margin_top - margin_bottom

    inset = 3.5 * mm
    content_w = page_w - 2 * inset
    expense_w = content_w
    ratios = (0.16, 0.20, 0.22, 0.18, 0.24) if portrait else (0.16, 0.22, 0.26, 0.15, 0.21)
    col_w = [expense_w * part for part in ratios]
    col_w[-1] = expense_w - sum(col_w[:-1])
    # Libellés du demandeur = colonne Montant, valeurs = colonne Mode de règlement.
    split = 6 * mm
    id_label_w = col_w[3]
    id_value_w = col_w[4]
    right_w = id_label_w + id_value_w
    left_w = col_w[0] + col_w[1] + col_w[2] - split
    logo_w = 36 * mm if portrait else 42 * mm
    dept_w = left_w - logo_w
    header_h = 40 * mm if portrait else 36 * mm
    row_h = header_h / 4

    dept_style = ParagraphStyle(
        "NfDept",
        fontName="Helvetica",
        fontSize=10,
        leading=13,
        alignment=TA_CENTER,
        textColor=ink,
        spaceBefore=0,
        spaceAfter=0,
    )
    id_label_style = ParagraphStyle(
        "NfIdLabel",
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        alignment=TA_LEFT,
        textColor=ink,
    )
    id_value_style = ParagraphStyle(
        "NfIdValue",
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        alignment=TA_LEFT,
        textColor=ink,
    )
    title_style = ParagraphStyle(
        "NfTitle",
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        alignment=TA_CENTER,
        textColor=ink,
        spaceBefore=0,
        spaceAfter=0,
    )
    head_style = ParagraphStyle(
        "NfHead",
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        alignment=TA_CENTER,
        textColor=ink,
    )
    cell = ParagraphStyle(
        "NfCell",
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=ink,
    )
    cell_c = ParagraphStyle("NfCellC", parent=cell, alignment=TA_CENTER)
    total_style = ParagraphStyle(
        "NfTotal",
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        alignment=TA_CENTER,
        textColor=ink,
    )
    sig_style = ParagraphStyle(
        "NfSig",
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        alignment=TA_CENTER,
        textColor=ink,
    )
    sig_name_style = ParagraphStyle(
        "NfSigName",
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        alignment=TA_CENTER,
        textColor=ink,
    )

    logo_flow = Paragraph("<b>BEA</b>", dept_style)
    logo_path = resolve_note_frais_logo_path()
    if logo_path is not None:
        try:
            iw, ih = ImageReader(str(logo_path)).getSize()
            max_h = header_h - 7 * mm
            max_w = logo_w - 6 * mm
            draw_h = max_h
            draw_w = draw_h * (iw / float(ih))
            if draw_w > max_w:
                draw_w = max_w
                draw_h = draw_w * (ih / float(iw))
            logo_flow = Image(str(logo_path), width=draw_w, height=draw_h, mask="auto")
        except Exception:
            logo_flow = Paragraph("<b>BEA</b>", dept_style)

    dept_flow = Paragraph(
        "<b>Département Ressources Humaines et Moyens Généraux</b>"
        "<br/><br/>Service Moyens Généraux",
        dept_style,
    )

    def _id(label: str, raw: object | None) -> list:
        return [
            Paragraph(label, id_label_style),
            Paragraph(_esc(raw, empty="—"), id_value_style),
        ]

    # Deux cadres distincts, comme la fiche papier : logo+département | identité.
    left_box = Table(
        [[logo_flow, dept_flow]],
        colWidths=[logo_w, dept_w],
        rowHeights=[header_h],
    )
    left_box.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 1.05, ink),
                ("LINEAFTER", (0, 0), (0, 0), 0.8, ink),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    right_box = Table(
        [
            _id("Identité du demandeur", note.demandeur_nom),
            _id("Département", note.departement),
            _id("Fonction", note.fonction),
            _id("date de la demande", date_dem),
        ],
        colWidths=[id_label_w, id_value_w],
        rowHeights=[row_h, row_h, row_h, row_h],
    )
    right_box.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 1.05, ink),
                ("INNERGRID", (0, 0), (-1, -1), 0.7, ink),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ]
        )
    )
    header = Table(
        [[left_box, "", right_box]],
        colWidths=[left_w, split, right_w],
        rowHeights=[header_h],
    )
    header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    header.hAlign = "CENTER"

    title_box = Table(
        [[Paragraph(_esc(title), title_style)]],
        colWidths=[expense_w],
    )
    title_box.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 1.05, ink),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    title_box.hAlign = "CENTER"

    header_row = [
        Paragraph("Date de la dépense", head_style),
        Paragraph("Description", head_style),
        Paragraph("Motif", head_style),
        Paragraph("Montant En MRU", head_style),
        Paragraph("Mode de règlement", head_style),
    ]
    data_rows: list = [header_row]
    lignes = sorted(note.lignes or [], key=lambda x: x.sort_order)
    if not lignes:
        data_rows.append([Paragraph("", cell_c)] * 5)
    else:
        for lig in lignes:
            d = lig.date_depense.strftime("%d/%m/%Y") if lig.date_depense else ""
            data_rows.append(
                [
                    Paragraph(_esc(d), cell_c),
                    Paragraph(_esc(lig.description), cell_c),
                    Paragraph(_esc(lig.motif), cell_c),
                    Paragraph(money(lig.montant), cell_c),
                    Paragraph(_esc(lig.mode_reglement), cell_c),
                ]
            )
    data_rows.append(
        [
            Paragraph("total", total_style),
            "",
            "",
            Paragraph(money(note.total_mru), total_style),
            "",
        ]
    )

    body = Table(data_rows, colWidths=col_w)
    last = len(data_rows) - 1
    body_style = [
        ("BOX", (0, 0), (-1, -1), 1.05, ink),
        ("INNERGRID", (0, 0), (-1, -1), 0.6, ink),
        ("SPAN", (0, last), (2, last)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, 0), 5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("TOPPADDING", (0, 1), (-1, last), 6),
        ("BOTTOMPADDING", (0, 1), (-1, last), 6),
    ]
    if not lignes:
        body_style.extend(
            [
                ("TOPPADDING", (0, 1), (-1, 1), 12),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 12),
            ]
        )
    body.setStyle(TableStyle(body_style))
    body.hAlign = "CENTER"

    def _sig(role: str, name: str, width: float) -> Table:
        bits = []
        if name and name.strip():
            bits.append(Paragraph(_esc(name), sig_name_style))
        bits.append(Paragraph(_esc(role), sig_style))
        block = Table([[bit] for bit in bits], colWidths=[width])
        block.setStyle(
            TableStyle(
                [
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        return block

    # Écart avec le cadre extérieur : les cases ne touchent ni les côtés ni le bas.
    side_inset = 8 * mm
    gutter = 10 * mm
    sig_w = (page_w - 2 * side_inset - gutter) / 2
    top_gap = 4 * mm
    gap = 5 * mm
    title_gap = 4 * mm
    _, header_real = header.wrap(page_w, frame_h)
    _, title_real = title_box.wrap(expense_w, frame_h)
    _, body_real = body.wrap(expense_w, frame_h)
    room = frame_h - top_gap - header_real - gap - title_real - title_gap - body_real
    min_lift = 8 * mm
    min_after = 6 * mm
    sig_h = 30 * mm if portrait else 24 * mm
    lift = 14 * mm if portrait else 10 * mm
    if room >= min_after + sig_h + lift:
        after = room - sig_h - lift
    else:
        lift = min(min_lift, max(4 * mm, room * 0.2))
        after = min(min_after, max(3 * mm, room * 0.15))
        sig_h = max(18 * mm, room - lift - after)

    signs = Table(
        [[_sig(s1_role, s1_name, sig_w - 4 * mm), "", _sig(s2_role, s2_name, sig_w - 4 * mm)]],
        colWidths=[sig_w, gutter, sig_w],
        rowHeights=[sig_h],
    )
    signs.hAlign = "CENTER"
    signs.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (0, 0), 1.05, ink),
                ("BOX", (2, 0), (2, 0), 1.05, ink),
                ("VALIGN", (0, 0), (0, 0), "BOTTOM"),
                ("VALIGN", (2, 0), (2, 0), "BOTTOM"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (0, 0), 4),
                ("RIGHTPADDING", (0, 0), (0, 0), 4),
                ("LEFTPADDING", (2, 0), (2, 0), 4),
                ("RIGHTPADDING", (2, 0), (2, 0), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (0, 0), 5 * mm),
                ("BOTTOMPADDING", (2, 0), (2, 0), 5 * mm),
                ("LEFTPADDING", (1, 0), (1, 0), 0),
                ("RIGHTPADDING", (1, 0), (1, 0), 0),
            ]
        )
    )

    story = [
        Spacer(1, top_gap),
        header,
        Spacer(1, gap),
        title_box,
        Spacer(1, title_gap),
        body,
        Spacer(1, after),
        signs,
        Spacer(1, lift),
    ]

    def _paint(canvas, _doc):
        canvas.saveState()
        canvas.setStrokeColor(ink)
        canvas.setLineWidth(1.5)
        canvas.rect(_doc.leftMargin, _doc.bottomMargin, _doc.width, _doc.height, stroke=1, fill=0)
        canvas.setFillColor(colors.HexColor("#4B5563"))
        canvas.setFont("Helvetica", 7)
        ref = str(getattr(note, "reference", "") or "").strip()
        canvas.drawCentredString(page_size[0] / 2.0, 5.2 * mm, f"Réf. {ref}")
        canvas.restoreState()

    buf = io.BytesIO()
    doc = BaseDocTemplate(
        buf,
        pagesize=page_size,
        leftMargin=margin_x,
        rightMargin=margin_x,
        topMargin=margin_top,
        bottomMargin=margin_bottom,
        title=f"Note de frais {getattr(note, 'reference', '')}",
    )
    frame = Frame(
        doc.leftMargin,
        doc.bottomMargin,
        doc.width,
        doc.height,
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
        id="fiche",
    )
    doc.addPageTemplates([PageTemplate(id="fiche", frames=[frame], onPage=_paint, pagesize=page_size)])
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
