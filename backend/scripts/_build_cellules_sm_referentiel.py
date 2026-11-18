"""Phase 1 — régénère Cellules SM.xlsx depuis le moteur actuel. Ne modifie pas le moteur."""
from __future__ import annotations

import shutil
import sys
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.formatting.rule import FormulaRule
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(r"C:\Users\sallm\bea-digital")
sys.path.insert(0, str(ROOT / "backend"))

from app.services.reporting_bcm_sm.engine.amounts import ZERO, quantize_mru  # noqa: E402
from app.services.reporting_bcm_sm.engine.det_basis import (  # noqa: E402
    BASIS_CREDIT,
    BASIS_CREDIT_MINUS_DEBIT,
    BASIS_DEBIT,
    BASIS_NET,
    DetLine,
    account_matches,
    amount_of,
    currency_ok,
    ncg_matches,
)
from app.services.reporting_bcm_sm.engine.evaluate import (  # noqa: E402
    classes_1_8_gap,
    det_signed_gap,
    evaluate_sm,
)
from app.services.reporting_bcm_sm.engine.rules_catalog import (  # noqa: E402
    ADJUST_KEYS,
    ALL_RULES,
    AUTO_KEYS,
    ETAT_A_RULES,
    ETAT_B_RULES,
    ETAT_C_RULES,
    INFO_RULES,
    MANUAL_KEYS,
    ORIGIN_ADJUST,
    ORIGIN_AUTO,
    ORIGIN_COPY,
    ORIGIN_MANUAL,
    ORIGIN_PCT,
    ORIGIN_REMAINDER,
    RULES_BY_KEY,
    catalog_stats,
)

OUT = ROOT / "Cellules SM.xlsx"
OLD = ROOT / "Cellules SM.xlsx"
TPL = ROOT / "BEA-SM-10-2026.xlsx"
SM08 = Path(r"C:\Users\sallm\Downloads\SM-08-2026.xlsx")
BAL = Path(r"C:\Users\sallm\Downloads\BAL AOUT.xlsx")
W13 = ROOT / (
    "storage/uploads/reporting-bcm-sm/"
    "3429322d-a888-4f59-b133-8f870bcf1911/work/"
    "SM-08-2026_w13_d97a4f39a06ff65a.xlsx"
)
ARCHIVE_TMP = ROOT / "backend" / "scripts" / "_archive_cellules_sm_oct2026.xlsx"

TODAY = date(2026, 11, 18)
PARAMS_08 = {"dat_public": Decimal("70000000.00")}

OCTOBER_CONSTANTS = {
    ("ETAT A", "D9"),
    ("ETAT A", "D21"),
    ("ETAT A", "D38"),
    ("ETAT A", "D75"),
    ("ETAT A", "D76"),
    ("ETAT A", "D106"),
    ("ETAT A", "D112"),
    ("ETAT A", "D123"),
    ("ETAT A", "D167"),
}
D09_PCT = {("ETAT B", a) for a in ("E46", "E48", "E49")}
D09_REMAINDER = {("ETAT B", a) for a in ("D46", "D48", "D49")}
CONCORDANCE_B = {("ETAT B", a) for a in (
    "L11", "L20", "L36", "L40", "L44", "L46", "L47", "L48", "L49", "L51", "L52", "L53",
)}
PRESERVE_B_H_FORMULAS = {"H20", "H36", "H40"}
CLEARED_B_H_NUMBERS = {"H12", "H39", "H43", "H46", "H47", "H48", "H49"}
B_H_ZERO_KEEP = {"H27", "H31"}
FORMULAS_B_PRESERVE = {
    "D12", "F31", "E39", "E43", "D46", "E46", "D47", "D48", "E48", "D49", "E49",
}

AXIS_A = {
    "C": "Provisions et amortissements",
    "D": "Ouguiyas / Résidents",
    "E": "Ouguiyas / Non-résidents",
    "F": "Devises / Résidents",
    "G": "Devises / Non-résidents",
    "H": "Total de ligne (SUM D:G)",
}
AXIS_B = {
    "C": "Résidents — Établissements publics administratifs",
    "D": "Résidents — Établissements publics commerciaux",
    "E": "Résidents — Entreprises du secteur privé",
    "F": "Résidents — Particuliers",
    "G": "Résidents — Divers",
    "H": "Non-résidents (pas un total de ligne)",
    "I": "Total de ligne (SUM C:H)",
    "L": "Concordance / contrôle",
}
BASIS_OP = {
    BASIS_DEBIT: "Somme des DEB",
    BASIS_CREDIT: "Somme des CRE",
    BASIS_NET: "Somme des DEB moins somme des CRE",
    BASIS_CREDIT_MINUS_DEBIT: "Somme des CRE moins somme des DEB",
}
BASIS_SHORT = {
    BASIS_DEBIT: "DEB",
    BASIS_CREDIT: "CRE",
    BASIS_NET: "NET (DEB − CRE)",
    BASIS_CREDIT_MINUS_DEBIT: "CRE − DEB",
}
ORIGIN_FR = {
    ORIGIN_AUTO: "Automatique",
    ORIGIN_MANUAL: "Saisie manuelle",
    ORIGIN_ADJUST: "Automatique puis ajustement",
    ORIGIN_COPY: "Copie",
    ORIGIN_PCT: "Pourcentage (30 %)",
    ORIGIN_REMAINDER: "Reliquat",
}

THIN = Border(
    left=Side(style="thin", color="B0B8C1"),
    right=Side(style="thin", color="B0B8C1"),
    top=Side(style="thin", color="B0B8C1"),
    bottom=Side(style="thin", color="B0B8C1"),
)
FILL_HEAD = PatternFill("solid", fgColor="1F4E79")
FONT_HEAD = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
FONT_TITLE = Font(name="Calibri", bold=True, color="1F4E79", size=16)
FONT_SUB = Font(name="Calibri", bold=True, color="1F4E79", size=12)
FONT_BODY = Font(name="Calibri", size=11)
FONT_SMALL = Font(name="Calibri", size=10, italic=True, color="5B6770")
ALIGN_WRAP = Alignment(wrap_text=True, vertical="center")
ALIGN_TOP = Alignment(wrap_text=True, vertical="top")
NATURE_FILL = {
    "Automatique (moteur)": PatternFill("solid", fgColor="C6EFCE"),
    "Automatique puis ajustement": PatternFill("solid", fgColor="FFE699"),
    "Saisie manuelle": PatternFill("solid", fgColor="FCE4D6"),
    "Formule Excel officielle": PatternFill("solid", fgColor="BDD7EE"),
    "Copie moteur (non écrite dans Excel si formule déjà présente)": PatternFill("solid", fgColor="DDEBF7"),
    "Pourcentage 30 % (formule Excel + moteur)": PatternFill("solid", fgColor="E2D5F1"),
    "Reliquat (formule Excel + moteur)": PatternFill("solid", fgColor="E2D5F1"),
    "Zéro du canevas (conservé)": PatternFill("solid", fgColor="D9D9D9"),
    "Zéro du canevas (vidé au WORK si non mappé)": PatternFill("solid", fgColor="F2F2F2"),
    "Vide volontaire": PatternFill("solid", fgColor="F2F2F2"),
    "En-tête / structure": PatternFill("solid", fgColor="D6DCE4"),
    "À CONFIRMER": PatternFill("solid", fgColor="FFC7CE"),
    "Colonne H ETAT B — non-résidents, jamais recopier un total": PatternFill("solid", fgColor="FFF2CC"),
}
STATUS_FILL = {
    "OK": PatternFill("solid", fgColor="C6EFCE"),
    "ÉCART": PatternFill("solid", fgColor="FFC7CE"),
    "INFO": PatternFill("solid", fgColor="DDEBF7"),
    "À CONFIRMER": PatternFill("solid", fgColor="FFE699"),
    "ANOMALIE FICHIER 08": PatternFill("solid", fgColor="F4B183"),
}


def _dec(value) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, str) and value.startswith("="):
        return None
    try:
        if isinstance(value, Decimal):
            return value.quantize(Decimal("0.01"))
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _fmt_dec(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _bcm(raw) -> str | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, str) and raw.strip().isdigit():
        return str(int(raw.strip()))
    if isinstance(raw, (int, float)) and float(raw).is_integer():
        return str(int(raw))
    return str(raw).strip() or None


def _is_formula(value) -> bool:
    return isinstance(value, str) and value.startswith("=")


def _etat_b_col_h(sheet: str, addr: str) -> bool:
    return sheet == "ETAT B" and len(addr) >= 2 and addr[0] == "H" and addr[1:].isdigit()


def load_sheet_map(path: Path, sheet: str) -> dict[str, object]:
    wb = load_workbook(path, data_only=False)
    ws = wb[sheet]
    out = {}
    for row in ws.iter_rows():
        for cell in row:
            if cell.value is not None:
                out[cell.coordinate] = cell.value
    labels = {}
    bcm_by_row = {}
    max_row = ws.max_row or 1
    for r in range(1, max_row + 1):
        labels[r] = ws.cell(r, 1).value
        bcm_by_row[r] = _bcm(ws.cell(r, 2).value)
    wb.close()
    return {"values": out, "labels": labels, "bcm": bcm_by_row, "max_row": max_row}


def load_det(path: Path) -> list[DetLine]:
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    lines: list[DetLine] = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            continue
        cells = list(row)
        if not cells or all(c is None or c == "" for c in cells[:6]):
            continue
        ncg = str(cells[0] or "").strip()
        if not ncg:
            continue
        debit = _dec(cells[4] if len(cells) > 4 else 0) or Decimal("0")
        credit = _dec(cells[5] if len(cells) > 5 else 0) or Decimal("0")
        lines.append(
            DetLine(
                ncg=ncg,
                compte=str(cells[1] or "").strip(),
                libelle=str(cells[2] or "").strip(),
                devise=(str(cells[3]).strip().upper() if cells[3] else None),
                debit=debit,
                credit=credit,
            )
        )
    wb.close()
    return lines


def term_text(term) -> str:
    bits = []
    op = BASIS_OP.get(term.basis, term.basis)
    if term.ncg_class:
        bits.append(f"{op} de tous les NCG de classe {term.ncg_class}")
    elif term.ncgs:
        bits.append(f"{op} des NCG " + ", ".join(term.ncgs))
    else:
        bits.append(op)
    if term.currency == "FX":
        bits.append("uniquement devises (hors MRU/MRO)")
    if term.accounts:
        bits.append("compte(s) " + ", ".join(term.accounts))
    txt = ", ".join(bits)
    if term.sign < 0:
        txt = "moins (" + txt + ")"
    return txt


def rule_ncgs(rule) -> str:
    parts = []
    for t in rule.terms:
        if t.ncg_class:
            parts.append(f"classe {t.ncg_class}")
        parts.extend(t.ncgs)
    return " ; ".join(parts)


def rule_basis(rule) -> str:
    if not rule.terms:
        if rule.origin == ORIGIN_COPY:
            return "Copie de cellule(s)"
        if rule.origin == ORIGIN_PCT:
            return "30 % d'autres cellules"
        if rule.origin == ORIGIN_REMAINDER:
            return "Reliquat d'autres cellules"
        if rule.origin == ORIGIN_MANUAL:
            return "Saisie / paramètre mensuel"
        return ""
    bases = []
    for t in rule.terms:
        label = BASIS_SHORT.get(t.basis, t.basis)
        if t.currency == "FX":
            label += " FX"
        if t.sign < 0:
            label = "− " + label
        if label not in bases:
            bases.append(label)
    return " + ".join(bases)


def rule_operation(rule) -> str:
    if rule.origin == ORIGIN_COPY:
        return "Copie / somme de cellules SM"
    if rule.origin == ORIGIN_PCT:
        return "30 % × somme des cellules sources"
    if rule.origin == ORIGIN_REMAINDER:
        return "Total − cellules retranchées"
    if rule.origin == ORIGIN_MANUAL:
        return "Aucune agrégation BAL — saisie"
    if not rule.terms:
        return "À CONFIRMER"
    if len(rule.terms) == 1 and not rule.minus_cells and not rule.plus_cells and not rule.minus_param and not rule.plus_param:
        return BASIS_OP.get(rule.terms[0].basis, rule.terms[0].basis)
    return "Règle composée (voir formule métier)"


def rule_formule(rule) -> str:
    parts = []
    if rule.origin == ORIGIN_MANUAL:
        src = f"paramètre « {rule.param_code} »" if rule.param_code else "saisie directe hors paramètre nommé"
        return f"Valeur saisie par la Comptabilité ({src}). Non calculée depuis la BAL DET."
    if rule.origin == ORIGIN_COPY:
        return "Copie de " + " + ".join(rule.copy_from)
    if rule.origin == ORIGIN_PCT:
        src = " + ".join(rule.pct_sources)
        return f"30 % × ({src})"
    if rule.origin == ORIGIN_REMAINDER:
        tot = " + ".join(rule.remainder_total)
        minus = " − ".join(rule.minus_cells) if rule.minus_cells else ""
        return f"({tot})" + (f" − {minus}" if minus else "")
    if rule.terms:
        parts.append(" + ".join(term_text(t) for t in rule.terms))
    for k in rule.plus_cells:
        parts.append(f"plus la cellule {k}")
    for k in rule.minus_cells:
        parts.append(f"moins la cellule {k}")
    if rule.plus_param:
        parts.append(f"plus le paramètre « {rule.plus_param} »")
    if rule.minus_param:
        parts.append(f"moins le paramètre « {rule.minus_param} »")
    txt = " ; ".join(parts) if parts else ""
    if rule.notes:
        txt = (txt + " — " if txt else "") + rule.notes
    return txt


def canvas_nature(sheet: str, addr: str, value) -> str:
    key = (sheet, addr)
    if key in OCTOBER_CONSTANTS:
        return "OCTOBER_CONSTANT_FORMULA"
    if key in D09_PCT:
        return "D09_PCT"
    if key in D09_REMAINDER:
        return "D09_REMAINDER"
    if key in CONCORDANCE_B:
        return "CONCORDANCE_IF"
    if _is_formula(value):
        return "STRUCTURAL_FORMULA"
    if value == 0 or value == 0.0 or value == Decimal("0"):
        return "CANVAS_ZERO"
    if value is None:
        return "EMPTY"
    return "LEAF"


def document_key(sheet: str, addr: str, bcm: str | None, col: str) -> str:
    if sheet == "ETAT A" and addr == "I147":
        return "A:CTRL:I147"
    if sheet == "ETAT A" and col in "CDEFGH" and bcm:
        return f"A:{bcm}:{col}"
    if sheet == "ETAT B" and col in "CDEFGHIL" and bcm:
        return f"B:{bcm}:{col}"
    prefix = "A" if sheet == "ETAT A" else "B"
    return f"{prefix}:STRUCT:{addr}"


def classify_cell(sheet: str, addr: str, bcm: str | None, col: str, tpl_val, sm_val) -> dict:
    key = document_key(sheet, addr, bcm, col)
    rule = RULES_BY_KEY.get(key)
    cn = canvas_nature(sheet, addr, tpl_val)
    is_b_h = _etat_b_col_h(sheet, addr)
    excel_formula = tpl_val if _is_formula(tpl_val) else None

    nature = ""
    recalc = ""
    partic = []
    a_confirmer = False

    if is_b_h:
        nature = "Colonne H ETAT B — non-résidents, jamais recopier un total"
        if excel_formula:
            nature = "Formule Excel officielle"
            recalc = "Préservation — le moteur ne vide pas et n'écrit pas la colonne H d'ETAT B"
            partic.append("Formule officielle de sous-total non-résidents (H20, H36, H40). Conservée.")
        elif tpl_val == 0 or tpl_val == 0.0:
            nature = "Zéro du canevas (conservé)"
            recalc = "Préservation du 0 du canevas — ni vidage ni écriture WORK"
            partic.append("H = non-résidents. Un 0 n'est pas équivalent à une cellule vide.")
            if addr == "H31":
                partic.append(
                    "H31 : la copie erronée de F31 (684 734 272,45) a été invalidée. "
                    "Le canevas prévoit 0. Ce 0 intervient dans le total non-résidents."
                )
            if addr in CLEARED_B_H_NUMBERS:
                partic.append(
                    "Ancien bug : le moteur y recopiait un total de ligne (C+D+E+F+G). "
                    "Correction validée : plus aucune copie."
                )
        else:
            nature = "Vide volontaire"
            recalc = "Préservation colonne H ETAT B — ni vidage ni écriture"
            partic.append("Rubrique sans montant ni 0 dans le canevas (ligne parfois vide).")
    elif excel_formula:
        nature = "Formule Excel officielle"
        recalc = "Préservation — le moteur n'écrase pas les formules structurelles"
        if cn == "OCTOBER_CONSTANT_FORMULA" and rule:
            nature = ORIGIN_FR.get(rule.origin, "Automatique (moteur)")
            if rule.origin == ORIGIN_AUTO:
                nature = "Automatique (moteur)"
            elif rule.origin == ORIGIN_ADJUST:
                nature = "Automatique puis ajustement"
            elif rule.origin == ORIGIN_MANUAL:
                nature = "Saisie manuelle"
            elif rule.origin == ORIGIN_COPY:
                nature = "Automatique (moteur)"
            recalc = (
                "Écrasement WORK : le canevas octobre contenait une formule figée "
                "(OCTOBER_CONSTANT_FORMULA), remplacée par le montant moteur"
            )
            partic.append("Formule d'origine du canevas octobre : " + excel_formula)
            excel_formula = excel_formula  # keep for FORMULES inventory of original
        elif cn == "D09_PCT":
            nature = "Pourcentage 30 % (formule Excel + moteur)"
            recalc = "Préservation de la formule Excel. Le moteur calcule la même chose pour le graphe, sans l'écrire."
        elif cn == "D09_REMAINDER":
            nature = "Reliquat (formule Excel + moteur)"
            recalc = "Préservation de la formule Excel. Le moteur calcule la même chose pour le graphe, sans l'écrire."
        elif cn == "CONCORDANCE_IF":
            nature = "Formule Excel officielle"
            partic.append("Formule de concordance / contrôle du canevas. Non alimentée par la BAL DET.")
        if rule and cn == "STRUCTURAL_FORMULA":
            partic.append(
                f"Le moteur possède aussi une règle {rule.origin} ({key}) pour le graphe interne. "
                "Excel conserve la formule officielle."
            )
    elif rule:
        if rule.origin == ORIGIN_AUTO:
            nature = "Automatique (moteur)"
            recalc = "Écrasement à chaque génération WORK (OCTOBER_LEAF)"
        elif rule.origin == ORIGIN_ADJUST:
            nature = "Automatique puis ajustement"
            recalc = (
                "Écrasement du calcul automatique à chaque WORK ; statut A_AJUSTER. "
                "Une décision documentaire, si elle existe, est conservée (aucune en 08/2026)."
            )
        elif rule.origin == ORIGIN_MANUAL:
            nature = "Saisie manuelle"
            recalc = (
                "Préservation de la saisie / du paramètre mensuel. "
                "Si le paramètre n'est pas renseigné : cellule NON_RENSEIGNE (vidée si OCTOBER_LEAF)."
            )
        elif rule.origin == ORIGIN_COPY:
            nature = "Automatique (moteur)"
            recalc = "Écrasement WORK si la cellule est une feuille (OCTOBER_LEAF) ; sinon formule Excel conservée"
        elif rule.origin == ORIGIN_PCT:
            nature = "Pourcentage 30 % (formule Excel + moteur)"
            recalc = "Si feuille : écrite par le moteur ; si formule : préservée"
        elif rule.origin == ORIGIN_REMAINDER:
            nature = "Reliquat (formule Excel + moteur)"
            recalc = "Si feuille : écrite par le moteur ; si formule : préservée"
        else:
            nature = "À CONFIRMER"
            a_confirmer = True
    else:
        if tpl_val == 0 or tpl_val == 0.0:
            nature = "Zéro du canevas (vidé au WORK si non mappé)"
            recalc = (
                "Pas de règle moteur. À la génération WORK, les OCTOBER_LEAF non mappées "
                "sont vidées (y compris un 0). Vide ≠ 0. Le moteur ne force pas 0."
            )
            partic.append("Néant métier : pas d'agrégation BAL DET identifiée pour cette cellule.")
        elif tpl_val is None:
            nature = "Vide volontaire"
            recalc = "Non alimentée. Conservée vide."
        elif isinstance(tpl_val, str) and not _is_formula(tpl_val):
            nature = "En-tête / structure"
            recalc = "Libellé du canevas. Non alimenté par le moteur."
            partic.append("Texte de présentation (ex. « POUR CONTRÔLE »), pas un montant.")
        else:
            nature = "À CONFIRMER"
            a_confirmer = True
            recalc = "Valeur présente dans le canevas sans règle moteur identifiée"
            partic.append("Ne pas inventer de mapping NCG.")

    if sheet == "ETAT A" and col == "H" and excel_formula:
        partic.append("Sur ETAT A, H est le total de ligne Excel SUM(D:G). Le moteur calcule aussi H en interne pour les copies, mais n'écrit pas la formule.")
    if sheet == "ETAT A" and key == "A:131:D":
        partic.append("C38 (A:131:C) reste visible. D38 = formule métier − C38. Aucune compensation de l'écart BAL.")
    if sheet == "ETAT A" and key == "A:131:C":
        partic.append("Provisions 290000 + 356000, solde créditeur. Mapping conservé.")
    if sheet == "ETAT A" and key == "A:206:D":
        partic.append(
            "28 NCG, soldes débiteurs seulement. 218000 une seule fois. "
            "320000, 320001, 322000, 323000, 323005, 323010 inclus. "
            "350000 ici (pas sur D52). 352000 et 352001 inclus."
        )
    if sheet == "ETAT A" and key == "A:211:D":
        partic.append("17 NCG. Sans 350000 ni 351014. Avec 351062. 350000 reste sur D47.")
    if sheet == "ETAT A" and key == "A:102:F":
        partic.append("Plus de filtre sur le seul compte 01101900026. Tous les comptes FX des NCG 100000 et 100100.")
    if sheet == "ETAT A" and key == "A:114:D":
        partic.append("Hors balance (150 M − 150 M). Pas de NCG. À saisir si un montant existe.")
        a_confirmer = False
    if rule and rule.notes and rule.notes not in " ".join(partic):
        partic.append(rule.notes)

    if is_b_h and addr == "H31" and _dec(sm_val) not in (None, Decimal("0.00")):
        a_confirmer = False
        partic.append(
            "Contrôle SM 08 : le fichier utilisateur contient encore 684 734 272,45. "
            "Règle validée = 0 du canevas. Écart de fichier, pas une règle à conserver."
        )

    return {
        "key": key,
        "rule": rule,
        "canvas_nature": cn,
        "nature": "À CONFIRMER" if a_confirmer else nature,
        "recalc": recalc,
        "partic": " ".join(partic).strip(),
        "excel_formula": tpl_val if _is_formula(tpl_val) else None,
        "a_confirmer": a_confirmer,
    }


HEADERS = [
    "État",
    "Feuille",
    "Adresse Excel",
    "Code BCM",
    "Libellé officiel",
    "Colonne / axe",
    "Clé documentaire",
    "Nature de la cellule",
    "Origine moteur",
    "Rubriques NCG BAL DET",
    "Type de solde",
    "Opération",
    "Formule métier",
    "Formule Excel officielle",
    "Particularités / exclusions",
    "Comportement au recalcul",
    "Valeur canevas officiel",
    "Valeur SM 08/2026",
    "Valeur moteur (BAL AOUT)",
    "Écart SM 08 − moteur",
    "Contrôle SM 08",
]


def style_header(ws, ncols: int) -> None:
    ws.auto_filter.ref = f"A1:{get_column_letter(ncols)}1"
    ws.freeze_panes = "A2"
    ws.row_dimensions[1].height = 32
    for col in range(1, ncols + 1):
        cell = ws.cell(1, col)
        cell.fill = FILL_HEAD
        cell.font = FONT_HEAD
        cell.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        cell.border = THIN


def autosize(ws, widths: dict[int, int]) -> None:
    for col, w in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = w


def write_rows(ws, rows: list[list], nature_col: int = 8, status_col: int | None = 21) -> None:
    money_cols = {17, 18, 19, 20}
    for r_i, row in enumerate(rows, start=2):
        ws.row_dimensions[r_i].height = 36
        for c_i, val in enumerate(row, start=1):
            cell = ws.cell(r_i, c_i, val)
            cell.font = FONT_BODY
            cell.alignment = ALIGN_TOP
            cell.border = THIN
            if c_i in money_cols and isinstance(val, (int, float)):
                cell.number_format = "#,##0.00"
            nature = row[nature_col - 1] if len(row) >= nature_col else None
            if c_i == nature_col and nature in NATURE_FILL:
                cell.fill = NATURE_FILL[nature]
            if status_col and c_i == status_col:
                st = row[status_col - 1]
                if st in STATUS_FILL:
                    cell.fill = STATUS_FILL[st]


def canvas_display(val) -> str | float | None:
    if val is None:
        return "(vide)"
    if _is_formula(val):
        return val
    d = _dec(val)
    if d is not None:
        return float(d)
    return str(val)


def sm_display(val) -> str | float | None:
    if val is None:
        return "(vide)"
    if _is_formula(val):
        return val
    d = _dec(val)
    if d is not None:
        return float(d)
    return str(val)


def compare_status(sheet, addr, info, sm_val, engine_val, tpl_val) -> tuple[str, Decimal | None]:
    sm_n = _dec(sm_val) if not _is_formula(sm_val) else None
    eng = engine_val
    gap = None
    if info["excel_formula"] and _is_formula(sm_val):
        if str(sm_val).replace(" ", "") == str(tpl_val).replace(" ", ""):
            return "OK", None
        return "ÉCART", None
    if _etat_b_col_h(sheet, addr):
        if addr == "H31":
            if sm_n == Decimal("684734272.45"):
                return "ANOMALIE FICHIER 08", sm_n
            if sm_n in (Decimal("0.00"), None) and (tpl_val == 0 or tpl_val == 0.0):
                return "OK", None
        if addr in PRESERVE_B_H_FORMULAS:
            if _is_formula(sm_val):
                return "OK", None
            return "ANOMALIE FICHIER 08", None
        if addr in CLEARED_B_H_NUMBERS:
            # utilisateur a vidé ; canevas 0 ; moteur conserve 0
            if sm_n is None:
                return "INFO", None
            if sm_n == Decimal("0.00"):
                return "OK", None
            return "ÉCART", sm_n
        if addr == "H27":
            if sm_n in (Decimal("0.00"),) or sm_val == 0:
                return "OK", None
            return "ÉCART", sm_n
        if sm_n is None and (tpl_val == 0 or tpl_val == 0.0):
            return "INFO", None
        return "OK", None
    if info["nature"] == "Formule Excel officielle" or (
        info["nature"] in (
            "Pourcentage 30 % (formule Excel + moteur)",
            "Reliquat (formule Excel + moteur)",
        )
        and info["excel_formula"]
    ):
        if _is_formula(sm_val):
            return "OK", None
        if sm_val is None and info["excel_formula"]:
            return "ÉCART", None
        return "OK", None
    if info["nature"] in (
        "Zéro du canevas (vidé au WORK si non mappé)",
        "Vide volontaire",
        "Zéro du canevas (conservé)",
    ):
        if sm_n not in (None, Decimal("0.00")) and eng is None:
            return "À CONFIRMER", sm_n
        return "OK", None
    if eng is not None and sm_n is not None:
        gap = (sm_n - eng).quantize(Decimal("0.01"))
        if abs(gap) <= Decimal("0.01"):
            return "OK", Decimal("0.00")
        return "ÉCART", gap
    if eng is not None and sm_n is None:
        if info["rule"] and info["rule"].origin == ORIGIN_MANUAL:
            return "INFO", None
        return "ÉCART", eng
    if eng is None and sm_n is not None:
        if info["rule"] and info["rule"].origin == ORIGIN_MANUAL:
            return "INFO", sm_n
        return "À CONFIRMER", sm_n
    return "OK", None


def build_etat_rows(sheet: str, tpl, sm, engine: dict, cols: str) -> list[list]:
    axis = AXIS_A if sheet == "ETAT A" else AXIS_B
    etat = "ETAT A" if sheet == "ETAT A" else "ETAT B"
    rows = []
    max_row = tpl["max_row"]
    for r in range(8, max_row + 1):
        bcm = tpl["bcm"].get(r)
        if not bcm:
            continue
        lib = str(tpl["labels"].get(r) or "").strip()
        for col in cols:
            addr = f"{col}{r}"
            tpl_val = tpl["values"].get(addr)
            sm_val = sm["values"].get(addr)
            # skip completely empty structural gaps without bcm already handled
            if tpl_val is None and sm_val is None and col not in "CDEFGHI":
                continue
            info = classify_cell(sheet, addr, bcm, col, tpl_val, sm_val)
            rule = info["rule"]
            eng = None
            if info["key"] in engine and engine[info["key"]].retained is not None:
                eng = engine[info["key"]].retained
            elif info["key"] in engine and engine[info["key"]].calculated is not None:
                eng = engine[info["key"]].calculated
            status, gap = compare_status(sheet, addr, info, sm_val, eng, tpl_val)
            origin = ORIGIN_FR.get(rule.origin, "") if rule else "Aucune règle moteur"
            rows.append([
                etat,
                sheet,
                addr,
                bcm,
                lib,
                axis.get(col, col),
                info["key"],
                info["nature"],
                origin,
                rule_ncgs(rule) if rule else "",
                rule_basis(rule) if rule else "",
                rule_operation(rule) if rule else ("Formule Excel" if info["excel_formula"] else "Néant / pas d'agrégation"),
                rule_formule(rule) if rule else (
                    info["excel_formula"]
                    or (
                        "Aucun NCG — 0 du canevas conservé (non-résidents)"
                        if info["nature"] == "Zéro du canevas (conservé)"
                        else "Pas de mapping NCG identifié — néant métier"
                    )
                ),
                info["excel_formula"] or "",
                info["partic"],
                info["recalc"],
                canvas_display(tpl_val),
                sm_display(sm_val),
                _fmt_dec(eng),
                _fmt_dec(gap) if gap is not None else ("" if status != "ÉCART" else None),
                status if not info["a_confirmer"] else ("À CONFIRMER" if status == "OK" else status),
            ])
            if info["a_confirmer"]:
                rows[-1][7] = "À CONFIRMER"
                if rows[-1][20] == "OK":
                    rows[-1][20] = "À CONFIRMER"
    return rows


def add_lire(wb: Workbook, stats: dict) -> None:
    if wb.sheetnames == ["Sheet"]:
        ws = wb.active
        ws.title = "LIRE"
    elif "LIRE" in wb.sheetnames:
        ws = wb["LIRE"]
        if ws.max_row:
            ws.delete_rows(1, ws.max_row)
        wb.move_sheet(ws, offset=-wb.sheetnames.index("LIRE"))
    else:
        ws = wb.create_sheet("LIRE", 0)
    ws.sheet_properties.tabColor = "1F4E79"
    ws["A1"] = "Référentiel Cellules SM — Reporting BCM Situation Mensuelle"
    ws["A1"].font = FONT_TITLE
    ws.merge_cells("A1:F1")
    ws["A2"] = (
        f"Document métier et technique — mis à jour le {TODAY.isoformat()} — "
        "source de vérité = moteur actuel + canevas officiel + SM 08/2026."
    )
    ws["A2"].font = FONT_SMALL
    ws.merge_cells("A2:F2")

    blocks = [
        ("Périmètre", [
            "Plateforme BEA DIGITAL, module Reporting BCM – Situation Mensuelle.",
            "Ce classeur documente comment chaque cellule d'ETAT A et d'ETAT B est obtenue.",
            "Il ne calcule pas la SM. Il ne remplace pas le canevas officiel BCM.",
            "Phase 1 uniquement : pas de menu Paramètres dynamique, pas de nouvelle règle moteur.",
        ]),
        ("Sources examinées", [
            "Moteur : backend/app/services/reporting_bcm_sm/engine/rules_catalog.py (catalogue).",
            "Évaluation : evaluate.py (agrégats, copies, 30 %, reliquats, totaux H d'ETAT A seulement).",
            "Écriture WORK : work_fill.py (OCTOBER_LEAF / OCTOBER_CONSTANT_FORMULA ; colonne H d'ETAT B ignorée).",
            "Canevas officiel : BEA-SM-10-2026.xlsx (8 feuilles, 663 formules).",
            "Les feuilles ETAT A / ETAT B de ce fichier sont celles de la SM 08/2026 validée (mêmes montants, même I147).",
            "SM 08/2026 utilisateur : Downloads/SM-08-2026.xlsx (ETAT A validé ; ETAT B H corrigé : 0 et formules du canevas).",
            "Dernier WORK généré avant correction H : SM-08-2026_w13 (conservé, non modifié).",
            "BAL DET août : Downloads/BAL AOUT.xlsx, campagne 08/2026 CALCULEE.",
            "Paramètre mensuel 08/2026 en base : dat_public = 70 000 000,00. Autres paramètres non saisis.",
        ]),
        ("Légende D15 — soldes BAL DET", [
            "DEB = somme des colonnes DEB des comptes retenus (pas un solde « naturel » max(net, 0)).",
            "CRE = somme des colonnes CRE.",
            "NET = DEB − CRE.",
            "CRE − DEB = somme des CRE moins somme des DEB.",
            "FX = devise hors {MRU, MRO}. MRO est traité comme monnaie locale.",
            "NCG : égalité exacte de code. Un NCG 315000 ne prend pas 315100.",
            "Le moteur n'invente jamais 0 pour une inconnue. Une cellule non mappée n'est pas forcée à 0.",
        ]),
        ("Colonnes ETAT A", [
            "C = Provisions et amortissements ; D = Ouguiyas résidents ; E = Ouguiyas non-résidents ;",
            "F = Devises résidents ; G = Devises non-résidents ; H = Total Excel SUM(D:G).",
            "H d'ETAT A est une formule officielle. Le moteur s'en sert en interne pour quelques copies, sans l'écraser.",
        ]),
        ("Colonnes ETAT B — point validé", [
            "C à G = ventilation résidents (EPA, EPC, privé, particuliers, divers).",
            "H = NON-RÉSIDENTS. Ce n'est PAS un total de ligne. Interdiction de recopier C+D+E+F+G dans H.",
            "I = Total Excel SUM(C:H).",
            "Cellules H dont les copies ont été invalidées : H12, H39, H43, H46, H47, H48, H49.",
            "H31 : rétablir et conserver 0 (canevas). La valeur 684 734 272,45 était une copie de F31.",
            "H27 : 0 du canevas, à conserver.",
            "Formules H20, H36, H40 : conserver.",
            "Formules D12, F31, E39, E43, D46, E46, D47, D48, E48, D49, E49 : conserver.",
            "Vide ≠ 0. Le moteur ne vide plus et n'écrit plus la colonne H d'ETAT B.",
        ]),
        ("Comportement au recalcul WORK", [
            "Écrasées : cellules OCTOBER_LEAF ou OCTOBER_CONSTANT_FORMULA pour lesquelles le moteur a une valeur.",
            "Préservées : formules structurelles, formules 30 % / reliquat D09, concordances, en-têtes.",
            "Colonne H ETAT B : ni vidée ni écrite (0 et formules du canevas restent).",
            "Autres OCTOBER_LEAF non mappées (ETAT A et B hors H) : vidées, y compris un 0 de canevas. Documenté, non modifié dans cette phase.",
            "Saisies manuelles : issues des paramètres mensuels ou d'une décision ; absentes si non renseignées.",
            "Aucune décision documentaire sur la campagne 08/2026.",
        ]),
        ("Ce que ce fichier ne fait pas", [
            "Il ne modifie pas le moteur, les campagnes, le canevas officiel, ni les données.",
            "Il n'invente pas de mapping. Toute cellule sans règle identifiée est marquée « À CONFIRMER ».",
            "D01 / D02 et l'écart BAL restent ouverts : ils ne sont forcés dans aucune cellule.",
            "La Phase 2 (paramétrage dynamique des affectations) n'est pas commencée.",
        ]),
        ("Organisation du classeur", [
            "ETAT A / ETAT B (feuilles officielles) : vrai canevas SM 08, montants moteur, commentaires Excel sur chaque cellule.",
            "Règles ETAT A / B : une ligne par cellule (NCG, solde, opération, SM 08 vs moteur).",
            "Détail NCG / Détail comptes : chaque rubrique et chaque compte DET retenu en août 2026.",
            "FORMULES : inventaire des formules officielles du canevas pour A et B.",
            "MANUELLES : cellules à saisir ou à ajuster.",
            "CONTROLES : rapprochement SM 08/2026, H d'ETAT B, écart BAL.",
            "CATALOGUE : dump des règles moteur (A, B, C, INFO) telles qu'exécutées.",
            "AUTRES FEUILLES : INFO, ETAT C, FPN, ratios — inventaire sans mapping NCG inventé.",
            "ARCHIVE_OCT2026 : ancien onglet Contrôle balance (référentiel octobre, conservé).",
        ]),
    ]
    r = 4
    for title, lines in blocks:
        ws.cell(r, 1, title).font = FONT_SUB
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=6)
        r += 1
        for line in lines:
            ws.cell(r, 1, "• " + line).font = FONT_BODY
            ws.cell(r, 1).alignment = ALIGN_WRAP
            ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=6)
            ws.row_dimensions[r].height = 18
            r += 1
        r += 1
    ws.cell(r, 1, "Chiffres de cette mise à jour").font = FONT_SUB
    r += 1
    for k, v in stats.items():
        ws.cell(r, 1, k).font = FONT_BODY
        ws.cell(r, 2, v).font = FONT_BODY
        r += 1
    ws.column_dimensions["A"].width = 120
    ws.column_dimensions["B"].width = 28
    ws.page_setup.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.orientation = "landscape"
    ws.sheet_view.showGridLines = False
    ws.oddHeader.center.text = "Cellules SM — référentiel BEA DIGITAL"
    ws.print_title_rows = "1:2"


def add_table_sheet(wb, name, color, rows, extra_note: str | None = None) -> None:
    ws = wb.create_sheet(name)
    ws.sheet_properties.tabColor = color
    for c, h in enumerate(HEADERS, start=1):
        ws.cell(1, c, h)
    style_header(ws, len(HEADERS))
    write_rows(ws, rows)
    autosize(ws, {
        1: 10, 2: 12, 3: 12, 4: 12, 5: 42, 6: 38, 7: 16, 8: 42,
        9: 22, 10: 40, 11: 22, 12: 32, 13: 55, 14: 36, 15: 45,
        16: 40, 17: 22, 18: 22, 19: 22, 20: 16, 21: 20,
    })
    ws.auto_filter.ref = f"A1:U{max(1, len(rows)+1)}"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.paperSize = ws.PAPERSIZE_A3
    ws.print_title_rows = "1:1"
    ws.oddHeader.center.text = f"Cellules SM — {name}"
    if extra_note:
        ws.cell(len(rows) + 3, 1, extra_note).font = FONT_SMALL
        ws.merge_cells(start_row=len(rows) + 3, start_column=1, end_row=len(rows) + 3, end_column=8)


def add_formules(wb, tpl_a, tpl_b) -> int:
    ws = wb.create_sheet("FORMULES")
    ws.sheet_properties.tabColor = "5B9BD5"
    heads = [
        "État", "Feuille", "Adresse", "Code BCM", "Libellé", "Axe",
        "Nature canevas", "Formule officielle", "Préservée au WORK ?",
        "Règle moteur associée", "Commentaire",
    ]
    for c, h in enumerate(heads, start=1):
        ws.cell(1, c, h)
    style_header(ws, len(heads))
    n = 0
    r = 2
    for sheet, tpl, axis, etat in (
        ("ETAT A", tpl_a, AXIS_A, "ETAT A"),
        ("ETAT B", tpl_b, AXIS_B, "ETAT B"),
    ):
        cols = "CDEFGH" if sheet == "ETAT A" else "CDEFGHIL"
        for row in range(8, tpl["max_row"] + 1):
            bcm = tpl["bcm"].get(row)
            lib = str(tpl["labels"].get(row) or "").strip()
            for col in cols:
                addr = f"{col}{row}"
                val = tpl["values"].get(addr)
                if not _is_formula(val):
                    continue
                key = document_key(sheet, addr, bcm, col)
                rule = RULES_BY_KEY.get(key)
                cn = canvas_nature(sheet, addr, val)
                preserve = "Oui"
                comment = "Formule du canevas officiel."
                if (sheet, addr) in OCTOBER_CONSTANTS:
                    preserve = "Non — remplacée par le montant moteur (formule figée d'octobre)"
                    comment = "OCTOBER_CONSTANT_FORMULA : le WORK écrit le résultat du catalogue."
                if _etat_b_col_h(sheet, addr):
                    preserve = "Oui — colonne H ETAT B jamais écrasée"
                    comment = "Sous-total non-résidents. Ne pas remplacer par un total de ligne."
                if (sheet, addr) in D09_PCT:
                    comment = "30 % officiel D09. Identique au moteur B:207/209/210 E."
                if (sheet, addr) in D09_REMAINDER:
                    comment = "Reliquat officiel D09. Identique au moteur B:207/209/210 D."
                ws.cell(r, 1, etat)
                ws.cell(r, 2, sheet)
                ws.cell(r, 3, addr)
                ws.cell(r, 4, bcm or "")
                ws.cell(r, 5, lib)
                ws.cell(r, 6, axis.get(col, col))
                ws.cell(r, 7, cn)
                ws.cell(r, 8, val)
                ws.cell(r, 9, preserve)
                ws.cell(r, 10, key if rule else "")
                ws.cell(r, 11, comment)
                for c in range(1, 12):
                    ws.cell(r, c).font = FONT_BODY
                    ws.cell(r, c).alignment = ALIGN_TOP
                    ws.cell(r, c).border = THIN
                    ws.cell(r, c).fill = NATURE_FILL["Formule Excel officielle"]
                n += 1
                r += 1
    # I147
    val = tpl_a["values"].get("I147")
    if _is_formula(val):
        ws.cell(r, 1, "ETAT A")
        ws.cell(r, 2, "ETAT A")
        ws.cell(r, 3, "I147")
        ws.cell(r, 4, "")
        ws.cell(r, 5, "Contrôle actif − passif")
        ws.cell(r, 6, "Contrôle")
        ws.cell(r, 7, "STRUCTURAL_FORMULA")
        ws.cell(r, 8, val)
        ws.cell(r, 9, "Oui")
        ws.cell(r, 10, "A:CTRL:I147")
        ws.cell(r, 11, "H147 − H81. Porte D02 non forcée ici.")
        for c in range(1, 12):
            ws.cell(r, c).font = FONT_BODY
            ws.cell(r, c).border = THIN
        n += 1
    ws.auto_filter.ref = f"A1:K{max(1, n+1)}"
    ws.freeze_panes = "A2"
    autosize(ws, {1: 10, 2: 12, 3: 12, 4: 12, 5: 42, 6: 28, 7: 26, 8: 50, 9: 45, 10: 18, 11: 55})
    return n


def add_manuelles(wb, rows_a, rows_b) -> int:
    ws = wb.create_sheet("MANUELLES")
    ws.sheet_properties.tabColor = "ED7D31"
    heads = [
        "État", "Adresse", "Clé", "Code BCM", "Libellé", "Nature",
        "Paramètre mensuel", "Formule métier", "Comportement au recalcul",
        "Valeur SM 08/2026", "Statut 08/2026",
    ]
    for c, h in enumerate(heads, start=1):
        ws.cell(1, c, h)
    style_header(ws, len(heads))
    keep_natures = {
        "Saisie manuelle",
        "Automatique puis ajustement",
    }
    r = 2
    n = 0
    for row in rows_a + rows_b:
        if row[8] not in ("Saisie manuelle", "Automatique puis ajustement") and row[7] not in keep_natures:
            continue
        rule = RULES_BY_KEY.get(row[6])
        param = rule.param_code if rule and rule.param_code else (rule.minus_param or rule.plus_param or "")
        if rule and rule.origin == ORIGIN_ADJUST:
            param = " ; ".join(x for x in (rule.minus_param, rule.plus_param) if x)
        statut = "Non saisi en 08/2026" if row[17] in ("(vide)", None, "") else "Présent dans la SM 08"
        if row[6] == "A:327:D":
            statut = "Saisi (dat_public = 70 000 000,00)"
        if row[6] == "A:114:D":
            statut = "Non saisi — hors BAL DET"
        vals = [
            row[0], row[2], row[6], row[3], row[4], row[7],
            param or "", row[12], row[15], row[17], statut,
        ]
        for c, v in enumerate(vals, start=1):
            cell = ws.cell(r, c, v)
            cell.font = FONT_BODY
            cell.alignment = ALIGN_TOP
            cell.border = THIN
            if row[7] in NATURE_FILL:
                if c == 6:
                    cell.fill = NATURE_FILL[row[7]]
        r += 1
        n += 1
    # paramètres existants non encore liés à une cellule
    extra = [
        ("caisse_devises", "Ancien paramètre — F9 est désormais automatique (NCG 100000+100100 FX). Ne plus saisir pour F9."),
        ("publics_mru", "A:322:D — non saisi en 08/2026."),
        ("publics_dev", "A:322:F — non saisi en 08/2026."),
        ("prives_dev", "Paramètre existant, aucune cellule catalogue ne l'utilise aujourd'hui."),
        ("projets", "Retranché de A:323:D et ajouté à A:403:D — non saisi en 08/2026."),
        ("cautions_dev", "Paramètre existant, aucune cellule catalogue ne l'utilise aujourd'hui (A:516:G est automatique)."),
        ("amort_frais_immo", "A:234:C — non saisi en 08/2026 ; C76 n'est donc pas diminué de C75."),
    ]
    ws.cell(r + 1, 1, "Paramètres mensuels du module (non reconduits d'un mois sur l'autre)").font = FONT_SUB
    rr = r + 2
    ws.cell(rr, 1, "Code")
    ws.cell(rr, 2, "Usage actuel")
    for c in range(1, 3):
        ws.cell(rr, c).fill = FILL_HEAD
        ws.cell(rr, c).font = FONT_HEAD
    rr += 1
    for code, note in extra:
        ws.cell(rr, 1, code)
        ws.cell(rr, 2, note)
        rr += 1
    autosize(ws, {1: 12, 2: 12, 3: 14, 4: 12, 5: 42, 6: 32, 7: 22, 8: 55, 9: 45, 10: 22, 11: 36})
    ws.auto_filter.ref = f"A1:K{max(1, n+1)}"
    return n


def add_controles(wb, rows_a, rows_b, engine, lines, tpl_b, sm_b) -> dict:
    ws = wb.create_sheet("CONTROLES")
    ws.sheet_properties.tabColor = "C00000"
    ws["A1"] = "Contrôles de cohérence — SM 08/2026 × moteur × canevas"
    ws["A1"].font = FONT_TITLE
    ws.merge_cells("A1:G1")

    signed = det_signed_gap(lines)
    c18 = classes_1_8_gap(lines)
    r = 3
    ws.cell(r, 1, "1. Synthèse").font = FONT_SUB
    r += 1
    summary = [
        ("Campagne", "BEA 08/2026 v1 — CALCULEE — id 3429322d-a888-4f59-b133-8f870bcf1911"),
        ("BAL DET", str(BAL)),
        ("Lignes DET", len(lines)),
        ("Σ DEB − Σ CRE (toutes classes)", float(signed)),
        ("Σ DEB − Σ CRE classes 1–8", float(c18)),
        ("Écart forcé dans une cellule SM ?", "Non — D02 ouvert, snapshot inactif, D38 non compensé"),
        ("Paramètre dat_public", "70 000 000,00 (A:327:D)"),
        ("Autres paramètres", "Non saisis (publics, projets, amort_frais_immo, …)"),
        ("Décisions documentaires", "Aucune"),
        ("Moteur / campagnes / canevas", "Non modifiés par cette Phase 1"),
    ]
    for k, v in summary:
        ws.cell(r, 1, k).font = Font(name="Calibri", bold=True, size=11)
        ws.cell(r, 2, v).font = FONT_BODY
        if isinstance(v, float):
            ws.cell(r, 2).number_format = "#,##0.00"
        r += 1

    r += 1
    ws.cell(r, 1, "2. Colonne H ETAT B (correction validée)").font = FONT_SUB
    r += 1
    h_heads = ["Adresse", "Canevas", "SM 08 utilisateur", "WORK w13 (avant correction)", "Règle validée", "Contrôle"]
    for c, h in enumerate(h_heads, start=1):
        cell = ws.cell(r, c, h)
        cell.fill = FILL_HEAD
        cell.font = FONT_HEAD
        cell.border = THIN
    r += 1
    w13_map = load_sheet_map(W13, "ETAT B") if W13.is_file() else {"values": {}}
    h_addrs = ["H12", "H20", "H27", "H31", "H36", "H39", "H40", "H43", "H46", "H47", "H48", "H49"]
    h_ok = 0
    h_anom = 0
    for addr in h_addrs:
        tpl_v = tpl_b["values"].get(addr)
        sm_v = sm_b["values"].get(addr)
        w13_v = w13_map["values"].get(addr)
        if addr in PRESERVE_B_H_FORMULAS:
            rule = "Conserver la formule officielle"
            ctrl = "OK" if _is_formula(sm_v) else "ANOMALIE FICHIER 08 — formule absente du fichier 08 ; le prochain WORK la rétablit depuis le canevas"
        elif addr == "H31":
            rule = "0 du canevas (pas la copie de F31)"
            ctrl = "ANOMALIE FICHIER 08 — 684 734 272,45 encore présent ; règle validée = 0" if _dec(sm_v) == Decimal("684734272.45") else "OK"
        elif addr == "H27":
            rule = "0 du canevas"
            ctrl = "OK" if _dec(sm_v) in (Decimal("0.00"),) or sm_v == 0 else "ÉCART"
        else:
            rule = "0 du canevas, jamais un total de ligne"
            if sm_v is None:
                ctrl = "INFO — utilisateur a vidé ; prochain WORK écrira/laissera 0 du canevas (skip H)"
            elif _dec(sm_v) == Decimal("0.00"):
                ctrl = "OK"
            else:
                ctrl = "ÉCART"
        if ctrl.startswith("OK"):
            h_ok += 1
        if ctrl.startswith("ANOMALIE"):
            h_anom += 1
        vals = [addr, canvas_display(tpl_v), sm_display(sm_v), sm_display(w13_v), rule, ctrl]
        for c, v in enumerate(vals, start=1):
            cell = ws.cell(r, c, v)
            cell.border = THIN
            cell.alignment = ALIGN_WRAP
            if c == 6:
                if ctrl.startswith("OK"):
                    cell.fill = STATUS_FILL["OK"]
                elif ctrl.startswith("ANOMALIE"):
                    cell.fill = STATUS_FILL["ANOMALIE FICHIER 08"]
                else:
                    cell.fill = STATUS_FILL["INFO"]
        r += 1

    r += 1
    ws.cell(r, 1, "3. Formules officielles ETAT B à préserver").font = FONT_SUB
    r += 1
    f_ok = 0
    for addr in sorted(FORMULAS_B_PRESERVE | PRESERVE_B_H_FORMULAS):
        tpl_v = tpl_b["values"].get(addr)
        sm_v = sm_b["values"].get(addr)
        ok = _is_formula(sm_v) and _is_formula(tpl_v) and str(sm_v).replace(" ", "") == str(tpl_v).replace(" ", "")
        # H20/36/40 may be missing in user file
        status = "OK" if ok else ("ANOMALIE FICHIER 08" if addr in PRESERVE_B_H_FORMULAS else "ÉCART")
        if ok:
            f_ok += 1
        ws.cell(r, 1, addr)
        ws.cell(r, 2, tpl_v)
        ws.cell(r, 3, sm_v if sm_v is not None else "(vide)")
        ws.cell(r, 4, status)
        for c in range(1, 5):
            ws.cell(r, c).border = THIN
        if status == "OK":
            ws.cell(r, 4).fill = STATUS_FILL["OK"]
        else:
            ws.cell(r, 4).fill = STATUS_FILL.get(status, STATUS_FILL["ÉCART"])
        r += 1

    r += 1
    ws.cell(r, 1, "4. Cellules automatiques ETAT A — SM 08 vs moteur (BAL AOUT + dat_public)").font = FONT_SUB
    r += 2
    for c, h in enumerate(["Clé", "Adresse", "SM 08", "Moteur", "Écart", "Contrôle"], start=1):
        cell = ws.cell(r, c, h)
        cell.fill = FILL_HEAD
        cell.font = FONT_HEAD
        cell.border = THIN
    r += 1
    a_ok = a_ecart = 0
    for row in rows_a:
        if row[7] not in ("Automatique (moteur)", "Automatique puis ajustement"):
            continue
        if isinstance(row[17], str) and str(row[17]).startswith("="):
            continue
        if row[18] is None and row[17] in ("(vide)", None, ""):
            continue
        sm_v = row[17]
        eng = row[18]
        gap = row[19]
        st = row[20]
        if st == "OK":
            a_ok += 1
        elif st == "ÉCART":
            a_ecart += 1
        ws.cell(r, 1, row[6])
        ws.cell(r, 2, row[2])
        ws.cell(r, 3, sm_v if not isinstance(sm_v, str) else sm_v)
        ws.cell(r, 4, eng)
        ws.cell(r, 5, gap)
        ws.cell(r, 6, st)
        for c in range(1, 7):
            ws.cell(r, c).border = THIN
            if c in (3, 4, 5) and isinstance(ws.cell(r, c).value, (int, float)):
                ws.cell(r, c).number_format = "#,##0.00"
        if st in STATUS_FILL:
            ws.cell(r, 6).fill = STATUS_FILL[st]
        r += 1

    r += 1
    ws.cell(r, 1, "5. Points ouverts (non masqués)").font = FONT_SUB
    r += 1
    opens = [
        "D01 / D02 : écart BAL (classes 1–8 et toutes classes) constaté, non affecté à une cellule SM.",
        "A:114:D (D21) : saisie hors balance, non renseignée en 08/2026.",
        "A:234:C, A:322:D, A:322:F, projets : paramètres non saisis en 08/2026 ; les cellules liées sont calculées sans ces retranchements.",
        "H31 du fichier SM 08 utilisateur : copie F31 encore présente. Règle validée = 0. Le prochain WORK (depuis le canevas) rétablit 0.",
        "H20 / H36 / H40 du fichier SM 08 utilisateur : formules absentes (vidées par erreur). Le prochain WORK les rétablit.",
        "OCTOBER_LEAF non mappées hors colonne H ETAT B : le WORK actuel les vide (0 de canevas → vide). Documenté, non modifié.",
        "ETAT C ligne 208 recopie 209 et le TOTAL 220 additionne les deux (double comptage du canevas officiel, conservé).",
        "Paramètres prives_dev et cautions_dev : définis dans le module, sans cellule catalogue aujourd'hui.",
    ]
    for line in opens:
        ws.cell(r, 1, "• " + line).alignment = ALIGN_WRAP
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=7)
        ws.row_dimensions[r].height = 28
        r += 1

    autosize(ws, {1: 42, 2: 55, 3: 28, 4: 28, 5: 55, 6: 70})
    counts = defaultdict(int)
    for row in rows_a + rows_b:
        counts[row[20]] += 1
    return {
        "h_ok": h_ok,
        "h_anom": h_anom,
        "formules_b_ok": f_ok,
        "etat_a_auto_ok": a_ok,
        "etat_a_auto_ecart": a_ecart,
        "signed_gap": str(signed),
        "classes_1_8_gap": str(c18),
        "controle_counts": dict(counts),
    }


def add_catalogue(wb) -> None:
    ws = wb.create_sheet("CATALOGUE")
    ws.sheet_properties.tabColor = "548235"
    heads = [
        "Clé", "État", "Origine", "NCG / classe / comptes", "Solde", "Opération",
        "Cellules +", "Cellules −", "Copies / sources", "Paramètre +", "Paramètre −",
        "Paramètre saisie", "%", "Notes",
    ]
    for c, h in enumerate(heads, start=1):
        ws.cell(1, c, h)
    style_header(ws, len(heads))
    r = 2
    for rule in ALL_RULES:
        etat = {"A": "ETAT A", "B": "ETAT B", "C": "ETAT C", "I": "INFO"}.get(rule.key[0], rule.key[0])
        ncg_bits = []
        for t in rule.terms:
            ncg_bits.append(term_text(t))
        row = [
            rule.key,
            etat,
            ORIGIN_FR.get(rule.origin, rule.origin),
            " | ".join(ncg_bits),
            rule_basis(rule),
            rule_operation(rule),
            " ; ".join(rule.plus_cells),
            " ; ".join(rule.minus_cells),
            " ; ".join(rule.copy_from or rule.pct_sources or rule.remainder_total),
            rule.plus_param or "",
            rule.minus_param or "",
            rule.param_code or "",
            str(rule.pct) if rule.pct is not None else "",
            rule.notes,
        ]
        for c, v in enumerate(row, start=1):
            cell = ws.cell(r, c, v)
            cell.font = FONT_BODY
            cell.alignment = ALIGN_TOP
            cell.border = THIN
        r += 1
    ws.auto_filter.ref = f"A1:N{r-1}"
    autosize(ws, {1: 14, 2: 12, 3: 26, 4: 70, 5: 22, 6: 32, 7: 16, 8: 18, 9: 28, 10: 14, 11: 14, 12: 16, 13: 8, 14: 50})
    ws.cell(r + 1, 1, "Les totaux structurels (Somme codes, D+E+F+G, I d'ETAT B) restent des formules Excel, hors catalogue.").font = FONT_SMALL


def add_autres(wb) -> int:
    ws = wb.create_sheet("AUTRES FEUILLES")
    ws.sheet_properties.tabColor = "7F7F7F"
    ws["A1"] = "Feuilles du canevas hors détail NCG d'ETAT A / B"
    ws["A1"].font = FONT_TITLE
    ws.merge_cells("A1:F1")
    ws["A2"] = (
        "Aucun mapping NCG n'est inventé ici. Les cellules sont qualifiées d'après le canevas "
        "et les quelques règles moteur COPY (ETAT C, INFO:C9)."
    )
    ws["A2"].font = FONT_SMALL
    heads = ["Feuille", "Adresse", "Clé moteur si connue", "Nature", "Formule / valeur canevas", "Commentaire"]
    r = 4
    for c, h in enumerate(heads, start=1):
        cell = ws.cell(r, c, h)
        cell.fill = FILL_HEAD
        cell.font = FONT_HEAD
        cell.border = THIN
    r = 5
    n = 0
    wb_tpl = load_workbook(TPL, data_only=False)
    comments = {
        "INFO:C9": "Copie moteur de A:426:D (bénéfice).",
        "C:110:D": "Copie B:105:D",
        "C:112:D": "Copie B:124:F",
        "C:114:D": "Copie B:132:E",
        "C:115:E": "Copie B:204:E",
        "C:203:E": "Copie A:313:D + A:313:G",
        "C:209:E": "Copie A:326:H",
        "C:208:C": "Copie C:209:C — alerte double comptage avec le TOTAL 220",
        "C:208:D": "Copie C:209:D — alerte double comptage",
        "C:208:E": "Copie C:209:E — alerte double comptage",
    }
    info_keep = {f"C{n}" for n in list(range(6, 21))}
    liq_keep = {"D12", "D17", "D18", "D19", "D23", "C26", "C27", "C48", "C49"}
    for sheet in (
        "informations à fournir",
        "ETAT C",
        "CALCUL FPN",
        "RATIO COUVERTURE DE RISQUE",
        "RATIO DE LIQUIDITE",
        "RATIO FP ET AI",
    ):
        wss = wb_tpl[sheet]
        for row in wss.iter_rows():
            for cell in row:
                val = cell.value
                addr = cell.coordinate
                if val is None or addr in {"A1", "A2", "A3", "B2", "B3"}:
                    continue
                mapped = ""
                nature = "Formule Excel officielle" if _is_formula(val) else "Valeur / saisie du canevas"
                comment = ""
                keep = _is_formula(val)
                if sheet == "informations à fournir":
                    keep = addr in info_keep or _is_formula(val)
                    if addr == "C9":
                        mapped = "INFO:C9"
                        comment = comments["INFO:C9"]
                elif sheet == "ETAT C":
                    bcm = _bcm(wss.cell(cell.row, 2).value)
                    col = "".join(ch for ch in addr if ch.isalpha())
                    if bcm and col in "CDEFI":
                        keep = True
                        mapped = f"C:{bcm}:{col}"
                        comment = comments.get(mapped, "")
                        if not comment and mapped in RULES_BY_KEY:
                            comment = f"Règle moteur {RULES_BY_KEY[mapped].origin}"
                    elif not _is_formula(val):
                        keep = False
                elif sheet == "RATIO DE LIQUIDITE":
                    keep = addr in liq_keep or _is_formula(val)
                    if keep and not _is_formula(val):
                        nature = "À CONFIRMER"
                        comment = "Feuille du canevas sans mapping NCG dans le catalogue actuel."
                else:
                    if not _is_formula(val) and not isinstance(val, (int, float, Decimal)):
                        keep = False
                    elif not _is_formula(val):
                        nature = "À CONFIRMER"
                        comment = "Valeur du canevas sans mapping NCG dans le catalogue actuel."
                if not keep:
                    continue
                if mapped in comments:
                    comment = comments[mapped]
                    if nature == "À CONFIRMER":
                        nature = "Automatique (moteur)"
                ws.cell(r, 1, sheet)
                ws.cell(r, 2, addr)
                ws.cell(r, 3, mapped)
                ws.cell(r, 4, nature)
                ws.cell(r, 5, val if not isinstance(val, Decimal) else float(val))
                ws.cell(r, 6, comment)
                for c in range(1, 7):
                    ws.cell(r, c).border = THIN
                    ws.cell(r, c).alignment = ALIGN_TOP
                    ws.cell(r, c).font = FONT_BODY
                if nature in NATURE_FILL:
                    ws.cell(r, 4).fill = NATURE_FILL[nature]
                r += 1
                n += 1
    wb_tpl.close()
    ws.auto_filter.ref = f"A4:F{max(4, r-1)}"
    ws.freeze_panes = "A5"
    autosize(ws, {1: 32, 2: 12, 3: 16, 4: 36, 5: 50, 6: 70})
    return n


def add_archive(wb) -> None:
    ws = wb.create_sheet("ARCHIVE_OCT2026")
    ws.sheet_properties.tabColor = "833C0C"
    src_path = ARCHIVE_TMP if ARCHIVE_TMP.is_file() else (OUT if OUT.is_file() else None)
    if src_path is None:
        ws["A1"] = "Archive octobre 2026 indisponible"
        return
    src = load_workbook(src_path, data_only=False)
    if "Contrôle balance" in src.sheetnames:
        ws["A1"] = "Archive — ancien référentiel octobre 2026 (ne plus utiliser pour le calcul)"
        ws["A1"].font = FONT_TITLE
        ws.merge_cells("A1:I1")
        ws["A2"] = (
            "Conservation historique demandée. Plusieurs règles de cet onglet sont obsolètes "
            "(ex. F9 limité au compte 01101900026, D47/D52, D38). La vérité actuelle est dans ETAT A / ETAT B."
        )
        ws["A2"].font = FONT_SMALL
        old = src["Contrôle balance"]
        offset = 3
    elif "ARCHIVE_OCT2026" in src.sheetnames:
        old = src["ARCHIVE_OCT2026"]
        offset = 0
    else:
        src.close()
        ws["A1"] = "Archive octobre 2026 indisponible"
        return
    for r in old.iter_rows():
        for cell in r:
            dest = ws.cell(cell.row + offset, cell.column, cell.value)
            dest.font = FONT_BODY
            dest.border = THIN
            dest.alignment = ALIGN_WRAP
            if offset and cell.row == 1:
                dest.fill = FILL_HEAD
                dest.font = FONT_HEAD
            elif not offset and cell.row == 1:
                dest.font = FONT_TITLE
    src.close()
    ws.freeze_panes = "A5"
    autosize(ws, {1: 12, 2: 12, 3: 36, 4: 14, 5: 70, 6: 18, 7: 22, 8: 14, 9: 16})


def _comment_text(info: dict, rule, sm_val, eng) -> str:
    lines = [
        info["key"],
        info["nature"],
    ]
    if rule:
        lines.append(ORIGIN_FR.get(rule.origin, rule.origin))
        frm = rule_formule(rule)
        if frm:
            lines.append(frm)
        ncg = rule_ncgs(rule)
        if ncg:
            lines.append("NCG : " + ncg)
        lines.append("Solde : " + rule_basis(rule))
    elif info["excel_formula"]:
        lines.append("Formule canevas : " + str(info["excel_formula"]))
    if info["partic"]:
        lines.append(info["partic"])
    if info["recalc"]:
        lines.append(info["recalc"])
    if eng is not None:
        lines.append(f"Moteur 08/2026 : {eng:,.2f}".replace(",", " "))
    elif sm_val is not None and not _is_formula(sm_val):
        d = _dec(sm_val)
        if d is not None:
            lines.append(f"SM 08 : {d:,.2f}".replace(",", " "))
    return "\n".join(lines)[:2000]


def fix_etat_b_h(wb, tpl_b) -> None:
    """H ETAT B = canevas officiel (0 / formules), jamais les totaux de ligne."""
    ws = wb["ETAT B"]
    src = load_workbook(TPL, data_only=False)["ETAT B"]
    max_row = tpl_b["max_row"]
    for r in range(8, max_row + 1):
        addr = f"H{r}"
        ws[addr].value = src[addr].value
    src.parent.close()


def comment_canvas(wb, engine, tpl_a, tpl_b, sm_a, sm_b) -> int:
    """Commente ETAT A/B sans modifier les montants de la SM 08."""
    commented = 0
    for sheet, cols, tpl, sm in (
        ("ETAT A", "CDEFGH", tpl_a, sm_a),
        ("ETAT B", "CDEFGHI", tpl_b, sm_b),
    ):
        ws = wb[sheet]
        for r in range(8, tpl["max_row"] + 1):
            bcm = tpl["bcm"].get(r)
            if not bcm:
                continue
            for col in cols:
                addr = f"{col}{r}"
                cell = ws[addr]
                key = document_key(sheet, addr, bcm, col)
                tpl_val = tpl["values"].get(addr)
                sm_val = sm["values"].get(addr)
                info = classify_cell(sheet, addr, bcm, col, tpl_val, sm_val)
                rule = info["rule"]
                eng = None
                if key in engine:
                    cellv = engine[key]
                    eng = cellv.retained if cellv.retained is not None else cellv.calculated
                cell.comment = Comment(_comment_text(info, rule, sm_val, eng), "BEA DIGITAL")
                cell.comment.width = 320
                cell.comment.height = 160
                commented += 1
        if sheet == "ETAT A":
            ws["I147"].comment = Comment(
                "A:CTRL:I147 = H147 − H81 (total passif − total actif, colonnes D:G). "
                "Même formule et mêmes feuilles que la SM 08/2026. "
                "L'écart BAL (D02) n'est pas forcé ici.",
                "BEA DIGITAL",
            )
            commented += 1
    return commented


def add_legende(wb: Workbook) -> None:
    ws = wb.create_sheet("Légende", 1)
    ws.sheet_properties.tabColor = "833C0C"
    ws["A1"] = "LÉGENDE — Cellules SM (moteur réel, SM 08/2026, canevas officiel)"
    ws["A1"].font = FONT_TITLE
    ws.merge_cells("A1:C1")
    rows = [
        ("Soldes BAL DET (légende D15)", ""),
        ("DEB", "Somme des colonnes DEB des comptes retenus. Pas un solde « naturel » max(net, 0)."),
        ("CRE", "Somme des colonnes CRE."),
        ("NET", "DEB − CRE."),
        ("CRE − DEB", "Somme des CRE moins somme des DEB."),
        ("FX", "Devise hors {MRU, MRO}. MRO = monnaie locale."),
        ("NCG", "Égalité exacte du code. 315000 ne prend pas 315100."),
        ("", ""),
        ("Couleurs sur ETAT A / ETAT B", ""),
        ("Vert clair", "Cellule automatique alimentée par le moteur (BAL DET)."),
        ("Orange clair", "Saisie manuelle / paramètre mensuel."),
        ("Jaune", "Colonne H d'ETAT B = non-résidents : 0 ou formule du canevas, jamais un total de ligne."),
        ("Commentaire Excel", "Clic droit / afficher les commentaires : règle, NCG, recalcul, montant moteur."),
        ("", ""),
        ("Colonnes ETAT A", "C provisions ; D ouguiyas résidents ; E ouguiyas non-résidents ; F devises résidents ; G devises non-résidents ; H total SUM(D:G)."),
        ("Colonnes ETAT B", "C–G résidents (EPA, EPC, privé, particuliers, divers) ; H NON-RÉSIDENTS ; I total SUM(C:H)."),
        ("Vide ≠ 0", "Une cellule vide n'est pas un zéro métier. H d'ETAT B conserve les 0 du canevas."),
        ("H31", "0 du canevas. Ne pas y recopier F31 (684 734 272,45)."),
        ("D38 / C38", "D38 = Σ DEB 14 NCG − Σ CRE 211100/110/130 − C38. C38 visible. Pas de compensation d'écart BAL."),
        ("", ""),
        ("Onglets de détail", ""),
        ("Règles ETAT A / B", "Une ligne par cellule : NCG, solde, opération, formule, valeur SM 08, valeur moteur."),
        ("Détail NCG", "Chaque rubrique NCG retenue pour une cellule, avec Σ DEB, Σ CRE et montant retenu (août 2026)."),
        ("Détail comptes", "Chaque compte DET des NCG listés (hors agrégats de classe 6/7/8)."),
    ]
    r = 3
    for a, b in rows:
        ws.cell(r, 1, a).font = Font(name="Calibri", bold=bool(b == "" and a), size=12, color="1F4E79") if b == "" else FONT_BODY
        if b == "" and a:
            ws.cell(r, 1).font = FONT_SUB
        ws.cell(r, 2, b).font = FONT_BODY
        ws.cell(r, 2).alignment = ALIGN_WRAP
        r += 1
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 110
    ws.column_dimensions["C"].width = 20
    ws.sheet_view.showGridLines = False


def _term_groups(term, lines: list[DetLine]) -> dict[str, dict]:
    groups: dict[str, dict] = {}
    for line in lines:
        if not ncg_matches(line.ncg, ncgs=term.ncgs, ncg_class=term.ncg_class):
            continue
        if not currency_ok(line, term.currency):
            continue
        if not account_matches(line, term.accounts):
            continue
        g = groups.setdefault(
            line.ncg,
            {"deb": ZERO, "cre": ZERO, "n": 0, "lib": "", "accounts": []},
        )
        g["deb"] += line.debit or ZERO
        g["cre"] += line.credit or ZERO
        g["n"] += 1
        if not g["lib"]:
            g["lib"] = line.libelle
        g["accounts"].append(line)
    return groups


def add_detail_ncg(wb, lines: list[DetLine], engine, tpl_a, tpl_b) -> int:
    ws = wb.create_sheet("Détail NCG")
    ws.sheet_properties.tabColor = "7030A0"
    heads = [
        "État", "Adresse", "Clé", "Code BCM", "Libellé rubrique",
        "NCG", "Libellé NCG", "Filtre devise", "Filtre compte",
        "Type de solde", "Signe", "Σ DEB", "Σ CRE", "Montant retenu",
        "Nb lignes DET", "Présent dans la BAL 08 ?", "Notes de la règle",
    ]
    for c, h in enumerate(heads, start=1):
        ws.cell(1, c, h)
    style_header(ws, len(heads))
    bcm_lib = {}
    for sheet, tpl in (("ETAT A", tpl_a), ("ETAT B", tpl_b)):
        for r, bcm in tpl["bcm"].items():
            if bcm:
                bcm_lib[(sheet, bcm)] = str(tpl["labels"].get(r) or "").strip()
    r = 2
    n = 0
    for rule in ALL_RULES:
        if not rule.terms:
            continue
        etat = {"A": "ETAT A", "B": "ETAT B", "C": "ETAT C"}.get(rule.key[0], "")
        parts = rule.key.split(":")
        addr = ""
        bcm = parts[1] if len(parts) >= 3 else ""
        col = parts[2] if len(parts) >= 3 else ""
        if etat in ("ETAT A", "ETAT B") and bcm.isdigit() and col:
            # find row
            tpl = tpl_a if etat == "ETAT A" else tpl_b
            for row, b in tpl["bcm"].items():
                if b == bcm:
                    addr = f"{col}{row}"
                    break
        lib = bcm_lib.get((etat, bcm), "")
        for term in rule.terms:
            groups = _term_groups(term, lines)
            listed = list(term.ncgs) if term.ncgs else sorted(groups)
            if term.ncg_class:
                listed = sorted(groups)
            seen = set()
            for ncg in listed:
                seen.add(ncg)
                g = groups.get(ncg, {"deb": ZERO, "cre": ZERO, "n": 0, "lib": "", "accounts": []})
                amt = quantize_mru(amount_of(
                    DetLine(ncg, "", "", None, g["deb"], g["cre"]),
                    term.basis,
                ) * Decimal(term.sign))
                present = "Oui" if ncg in groups else "Non — NCG prévu, absent de la BAL 08"
                row = [
                    etat,
                    addr or rule.key,
                    rule.key,
                    bcm,
                    lib,
                    ncg if not term.ncg_class else ncg,
                    g["lib"],
                    "FX (hors MRU/MRO)" if term.currency == "FX" else "Toutes",
                    " ; ".join(term.accounts) if term.accounts else "",
                    BASIS_SHORT.get(term.basis, term.basis),
                    term.sign,
                    float(quantize_mru(g["deb"])),
                    float(quantize_mru(g["cre"])),
                    float(amt),
                    g["n"],
                    present,
                    rule.notes,
                ]
                for c, v in enumerate(row, start=1):
                    cell = ws.cell(r, c, v)
                    cell.font = FONT_BODY
                    cell.alignment = ALIGN_TOP
                    cell.border = THIN
                    if c in (12, 13, 14) and isinstance(v, float):
                        cell.number_format = "#,##0.00"
                    if present.startswith("Non"):
                        cell.fill = PatternFill("solid", fgColor="F2F2F2")
                r += 1
                n += 1
            if term.ncg_class:
                continue
    ws.auto_filter.ref = f"A1:Q{max(1, r-1)}"
    ws.freeze_panes = "A2"
    autosize(ws, {
        1: 10, 2: 12, 3: 14, 4: 12, 5: 36, 6: 12, 7: 36, 8: 18, 9: 22,
        10: 16, 11: 8, 12: 16, 13: 16, 14: 16, 15: 14, 16: 28, 17: 40,
    })
    return n


def add_detail_comptes(wb, lines: list[DetLine], tpl_a, tpl_b) -> int:
    ws = wb.create_sheet("Détail comptes")
    ws.sheet_properties.tabColor = "5B9BD5"
    heads = [
        "Clé cellule", "Adresse", "NCG", "Compte", "Libellé compte", "Devise",
        "DEB", "CRE", "Montant selon la base", "Base", "Signe",
    ]
    for c, h in enumerate(heads, start=1):
        ws.cell(1, c, h)
    style_header(ws, len(heads))
    r = 2
    n = 0
    by_ncg: dict[str, list[DetLine]] = defaultdict(list)
    for line in lines:
        by_ncg[line.ncg].append(line)
    for rule in ALL_RULES:
        if not rule.terms:
            continue
        parts = rule.key.split(":")
        etat = {"A": "ETAT A", "B": "ETAT B"}.get(rule.key[0])
        if etat is None:
            continue
        bcm = parts[1] if len(parts) >= 3 else ""
        col = parts[2] if len(parts) >= 3 else ""
        tpl = tpl_a if etat == "ETAT A" else tpl_b
        addr = rule.key
        for row, b in tpl["bcm"].items():
            if b == bcm:
                addr = f"{col}{row}"
                break
        for term in rule.terms:
            if term.ncg_class:
                continue
            if not term.ncgs:
                continue
            candidates: list[DetLine] = []
            for ncg in term.ncgs:
                candidates.extend(by_ncg.get(ncg, []))
            for line in candidates:
                if not currency_ok(line, term.currency):
                    continue
                if not account_matches(line, term.accounts):
                    continue
                amt = quantize_mru(amount_of(line, term.basis) * Decimal(term.sign))
                if amt == ZERO and (line.debit or ZERO) == ZERO and (line.credit or ZERO) == ZERO:
                    continue
                rowv = [
                    rule.key,
                    addr,
                    line.ncg,
                    line.compte,
                    line.libelle,
                    line.devise or "",
                    float(quantize_mru(line.debit or ZERO)),
                    float(quantize_mru(line.credit or ZERO)),
                    float(amt),
                    BASIS_SHORT.get(term.basis, term.basis),
                    term.sign,
                ]
                for c, v in enumerate(rowv, start=1):
                    cell = ws.cell(r, c, v)
                    cell.font = FONT_BODY
                    cell.border = THIN
                    cell.alignment = ALIGN_TOP
                    if c in (7, 8, 9) and isinstance(v, float):
                        cell.number_format = "#,##0.00"
                r += 1
                n += 1
    ws.auto_filter.ref = f"A1:K{max(1, r-1)}"
    ws.freeze_panes = "A2"
    autosize(ws, {1: 14, 2: 12, 3: 12, 4: 16, 5: 42, 6: 10, 7: 16, 8: 16, 9: 18, 10: 16, 11: 8})
    return n


def nature_counts(rows: list[list]) -> dict[str, int]:
    d = defaultdict(int)
    for row in rows:
        d[row[7]] += 1
    return dict(d)


def main() -> None:
    if not TPL.is_file():
        raise SystemExit(f"canevas introuvable: {TPL}")
    if not SM08.is_file():
        raise SystemExit(f"SM 08 introuvable: {SM08}")
    if not BAL.is_file():
        raise SystemExit(f"BAL AOUT introuvable: {BAL}")
    def _has_sheet(path: Path, name: str) -> bool:
        if not path.is_file():
            return False
        wb_chk = load_workbook(path, read_only=True)
        ok = name in wb_chk.sheetnames
        wb_chk.close()
        return ok

    if not _has_sheet(ARCHIVE_TMP, "Contrôle balance") and _has_sheet(OLD, "Contrôle balance"):
        shutil.copy2(OLD, ARCHIVE_TMP)

    print("BAL DET…")
    lines = load_det(BAL)
    print(f"  {len(lines)} lignes")
    engine = evaluate_sm(lines, params=PARAMS_08)
    print(f"  {len(engine)} cellules moteur")

    print("Canevas + SM 08…")
    tpl_a = load_sheet_map(TPL, "ETAT A")
    tpl_b = load_sheet_map(TPL, "ETAT B")
    sm_a = load_sheet_map(SM08, "ETAT A")
    sm_b = load_sheet_map(SM08, "ETAT B")

    rows_a = build_etat_rows("ETAT A", tpl_a, sm_a, engine, "CDEFGH")
    i147_tpl = tpl_a["values"].get("I147")
    i147_sm = sm_a["values"].get("I147")
    rows_a.append([
        "ETAT A",
        "ETAT A",
        "I147",
        "",
        "Contrôle total actif − total passif",
        "Contrôle",
        "A:CTRL:I147",
        "Formule Excel officielle",
        "Aucune règle moteur",
        "",
        "",
        "Formule Excel",
        i147_tpl or "",
        i147_tpl or "",
        "H147 − H81. L'écart BAL (D02) n'est pas forcé dans cette cellule.",
        "Préservation — le moteur n'écrase pas les formules structurelles",
        canvas_display(i147_tpl),
        sm_display(i147_sm),
        None,
        None,
        "OK" if _is_formula(i147_sm) else "ÉCART",
    ])
    rows_b = build_etat_rows("ETAT B", tpl_b, sm_b, engine, "CDEFGHI")
    rows_b += build_etat_rows("ETAT B", tpl_b, sm_b, engine, "L")
    # dédoublonner L already only L in third call - wait third call with L only is cleaner:
    # I concatenated I then L via two calls would duplicate C-I if I'm not careful.
    # Above: first CDEFGHI then += L only. Good.

    cat = catalog_stats()
    n_auto = sum(1 for x in rows_a + rows_b if x[7] == "Automatique (moteur)")
    n_form = sum(1 for x in rows_a + rows_b if "Formule Excel" in x[7] or "Pourcentage" in x[7] or "Reliquat" in x[7])
    n_man = sum(1 for x in rows_a + rows_b if x[7] == "Saisie manuelle")
    n_conf = sum(1 for x in rows_a + rows_b if x[7] == "À CONFIRMER")
    n_zero = sum(1 for x in rows_a + rows_b if "Zéro" in x[7] or x[7] == "Vide volontaire")

    print("Écriture classeur (SM 08 + règles, sans montants d'octobre)…")
    wb = load_workbook(SM08)
    for extra in ("AVERTISSEMENT", "À LIRE"):
        if extra in wb.sheetnames:
            del wb[extra]
    fix_etat_b_h(wb, tpl_b)
    n_comments = comment_canvas(wb, engine, tpl_a, tpl_b, sm_a, sm_b)
    print(f"  commentaires canevas : {n_comments}")
    add_lire(wb, {
        "Cellules ETAT A documentées": len(rows_a),
        "Cellules ETAT B documentées": len(rows_b),
        "Commentaires sur le canevas": n_comments,
        "Règles moteur catalogue (A+B+C+INFO)": cat["all"],
        "dont AUTO / manuelles / ajustements": f"{cat['auto']} / {cat['manual']} / {cat['adjust']}",
        "Règles ETAT A / ETAT B": f"{cat['etat_a']} / {cat['etat_b']}",
        "Lignes BAL AOUT": len(lines),
        "Paramètre 08/2026": "dat_public = 70 000 000,00",
        "Fichier généré": str(OUT),
    })
    add_legende(wb)
    add_table_sheet(wb, "Règles ETAT A", "2E7D32", rows_a)
    add_table_sheet(
        wb, "Règles ETAT B", "C65911", rows_b,
        extra_note="H = non-résidents. Ne jamais y recopier un total de résidents. H31 = 0 du canevas.",
    )
    n_ncg = add_detail_ncg(wb, lines, engine, tpl_a, tpl_b)
    print(f"  lignes détail NCG : {n_ncg}")
    n_cpt = add_detail_comptes(wb, lines, tpl_a, tpl_b)
    print(f"  lignes détail comptes : {n_cpt}")
    n_formules = add_formules(wb, tpl_a, tpl_b)
    n_manuelles_sheet = add_manuelles(wb, rows_a, rows_b)
    ctrl = add_controles(wb, rows_a, rows_b, engine, lines, tpl_b, sm_b)
    add_catalogue(wb)
    n_autres = add_autres(wb)
    add_archive(wb)

    # I147 on ETAT A extra if missing
    tmp = ROOT / "backend" / "scripts" / "_cellules_sm_out.xlsx"
    if tmp.exists():
        tmp.unlink()
    wb.save(tmp)
    wb.close()
    shutil.copy2(tmp, OUT)
    tmp.unlink(missing_ok=True)

    report = {
        "out": str(OUT),
        "etat_a": len(rows_a),
        "etat_b": len(rows_b),
        "total_ab": len(rows_a) + len(rows_b),
        "natures_a": nature_counts(rows_a),
        "natures_b": nature_counts(rows_b),
        "auto": n_auto,
        "formules_ab": n_form,
        "manuelles_ab": n_man,
        "a_confirmer": n_conf,
        "neant": n_zero,
        "commentaires": n_comments,
        "detail_ncg": n_ncg,
        "detail_comptes": n_cpt,
        "formules_sheet": n_formules,
        "manuelles_sheet": n_manuelles_sheet,
        "autres": n_autres,
        "catalogue": cat,
        "controles": ctrl,
        "engine_cells": len(engine),
        "a131c": str(engine.get("A:131:C").retained if "A:131:C" in engine else None),
        "a131d": str(engine.get("A:131:D").retained if "A:131:D" in engine else None),
        "h31_sm08": sm_b["values"].get("H31"),
        "h31_tpl": tpl_b["values"].get("H31"),
    }
    report_path = ROOT / "backend" / "scripts" / "_cellules_sm_report.txt"
    report_path.write_text(repr(report), encoding="utf-8")
    print("OK", OUT, "cells", report["total_ab"], "confirm", n_conf)
    print("report", report_path)


if __name__ == "__main__":
    main()
