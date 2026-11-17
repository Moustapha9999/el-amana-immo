# -*- coding: utf-8 -*-
"""Générateur documentaire — matrice / dossier / questionnaire SM BCM.
Strictement hors moteur : lecture des sources, écriture de 3 livrables."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.formatting.rule import FormulaRule

DL = Path(r"C:\Users\sallm\Downloads")
REPO = Path(r"C:\Users\sallm\bea-digital")
OUT = REPO / "docs" / "comptabilite" / "reporting-bcm-sm"
JSONL = OUT / "T3_2_MAPPING_SEED_CANDIDATES.jsonl"
CANVAS = DL / "BEA-SM-10-2026.xlsx"
CORR = DL / "Correspondance_BAL_SM_BEA_10-2026_1==SCD.xlsx"
OFFICIAL_SHA = "54e3b687434f4901889c1164b8d6d7fbc3bd225a117b1b36016c84e8fc852658"

SHEETS = (
    "informations à fournir",
    "ETAT A",
    "ETAT B",
    "ETAT C",
    "CALCUL FPN",
    "RATIO COUVERTURE DE RISQUE",
    "RATIO DE LIQUIDITE",
    "RATIO FP ET AI",
)
AXIS_A = {
    "C": "Provisions et amortissements",
    "D": "Ouguiyas / Résidents",
    "E": "Ouguiyas / Non-résidents",
    "F": "Devises / Résidents",
    "G": "Devises / Non-résidents",
    "H": "Total (SUM D:G sur détail)",
}
AXIS_B = {
    "C": "Résidents — EPA",
    "D": "Résidents — EPC",
    "E": "Résidents — privé",
    "F": "Résidents — particuliers",
    "G": "Résidents — divers",
    "H": "Non-résidents",
    "I": "Total (SUM C:H)",
    "L": "Contrôle vs ETAT A (IF)",
}
AXIS_C = {
    "C": "Maturité < 3 mois",
    "D": "Maturité 3 mois – 2 ans",
    "E": "Maturité > 2 ans",
    "F": "Total",
    "I": "Contrôle vs ETAT A (IF)",
}
OCTOBER_CONSTANTS = {
    "ETAT A!D9": "102",
    "ETAT A!D21": "114",
    "ETAT A!D38": "131",
    "ETAT A!D75": "234",
    "ETAT A!D76": "235",
    "ETAT A!D106": "322",
    "ETAT A!D112": "328",
    "ETAT A!D123": "403",
    "ETAT A!D167": "516",
}
D09_PCT = {"ETAT B!E46", "ETAT B!E48", "ETAT B!E49"}
D09_REM = {"ETAT B!D46", "ETAT B!D48", "ETAT B!D49"}
PARAMS = [
    ("caisse_devises", "Caisse devises", "ETAT A F9 (et soustraction dans D9)", "Proposition DET NCG 101* EUR — D04 ouvert", "20 254,50"),
    ("publics_mru", "Publics MRU", "ETAT A D106 (et retranchement D107)", "Liste comptes publics — D05 ouvert", "306 615 460,65"),
    ("publics_dev", "Publics devises", "ETAT A F106 (et retranchement D107)", "Liste comptes publics devises — D05", "24 408 887"),
    ("prives_dev", "Privés devises", "ETAT A F107 (et retranchement D107)", "Dépôts privés en devises", "819 359 898"),
    ("projets", "Projets", "Retranchement D107 + ajout D123", "Liste comptes projets — D05", "296 461 984"),
    ("dat_public", "DAT public", "ETAT A D111 (et retranchement D112)", "Détail DAT — valeur juin reconduite en oct. (D04)", "70 000 000"),
    ("amort_frais_immo", "Amortissement frais immobiliers", "ETAT A C75/D75/C76/D76", "Tableau amortissements — valeur juin reconduite", "3 910 448,68"),
    ("cautions_dev", "Cautions devises", "ETAT A G167 (retranchement D167)", "Hors-bilan devises", "135 030"),
]
UNMAPPED_67: dict[str, list[int]] = {}  # chargé depuis Analyse_metier_SM_matrice.docx table 4
CELL_RE = re.compile(r"(?:'([^']+)'!)?(\$?[A-Z]{1,3}\$?\d{1,4})")
NUM_RE = re.compile(r"(?<![A-Z])(\d{4,})")

FILL_H = PatternFill("solid", fgColor="1A5278")
FILL_H2 = PatternFill("solid", fgColor="2874A6")
FILL_OK = PatternFill("solid", fgColor="DCFCE7")
FILL_DED = PatternFill("solid", fgColor="FEF9C3")
FILL_PROP = PatternFill("solid", fgColor="FFEDD5")
FILL_VAL = PatternFill("solid", fgColor="FEE2E2")
FILL_ALT = PatternFill("solid", fgColor="F8FAFC")
FONT_H = Font(bold=True, color="FFFFFF", name="Calibri", size=10)
FONT_N = Font(name="Calibri", size=10)
FONT_B = Font(name="Calibri", size=10, bold=True)
THIN = Border(
    left=Side(style="thin", color="CBD5E1"),
    right=Side(style="thin", color="CBD5E1"),
    top=Side(style="thin", color="CBD5E1"),
    bottom=Side(style="thin", color="CBD5E1"),
)
WRAP = Alignment(wrap_text=True, vertical="top")


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def colrow(addr: str) -> tuple[str, int]:
    m = re.match(r"^([A-Z]+)(\d+)$", addr)
    return m.group(1), int(m.group(2))


def as_code(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, str) and v.strip().isdigit():
        return f"{int(v.strip()):03d}"
    if isinstance(v, (int, float)) and float(v).is_integer() and 1 <= int(v) <= 999:
        return f"{int(v):03d}"
    return None


def formula_of(cell) -> str | None:
    val = cell.value
    if val is None:
        return None
    if cell.data_type == "f" or (isinstance(val, str) and str(val).startswith("=")):
        return str(val)
    return None


def interpret_formula(formula: str | None, sheet: str, addr: str) -> tuple[str, str, str]:
    """Retourne (nature, opération, interprétation)."""
    if not formula:
        return ("saisie_ou_vide", "", "Pas de formule dans le canevas. La valeur d'octobre n'est pas une règle permanente.")
    f = formula.replace("$", "")
    key = f"{sheet}!{addr}"
    refs = CELL_RE.findall(f)
    ref_txt = ", ".join((f"'{s}'!{a}" if s else a) for s, a in refs)
    if key in OCTOBER_CONSTANTS:
        return (
            "constante_historique",
            f"Formule contenant un montant d'octobre — BCM {OCTOBER_CONSTANTS[key]}",
            "NE PAS réutiliser comme règle. Les littéraux (ex. 2873218, 588160767) sont le mois d'octobre, pas le moteur.",
        )
    if key in D09_PCT:
        return (
            "formule_provisoire_D09",
            "30 % d'un montant ETAT A",
            "Clé de répartition forfaitaire crédits (D09). Conservée dans le canevas, non validée métier.",
        )
    if key in D09_REM:
        return (
            "formule_provisoire_D09",
            "Complément 70 % = total ETAT A − 30 %",
            "Dépend de la cellule 30 %. Même porte D09.",
        )
    if "30%" in f.replace(" ", ""):
        return ("formule_provisoire_D09", "Pourcentage 30 %", "Répartition forfaitaire — D09.")
    if f.upper().startswith("=IF(") or f.upper().startswith("=+IF("):
        return (
            "controle",
            f"Test d'égalité / plafond. Références : {ref_txt}",
            "TRUE Excel avec cellules vides n'est PAS une validation. Résultat trompeur si les entrées sont vides.",
        )
    if re.search(r"/", f) and "SUM" not in f.upper():
        return ("ratio", f"Division. Références : {ref_txt}", "Numérateur et dénominateur doivent être renseignés. 0 au dénominateur = indéterminé, pas 0 métier.")
    if "*10" in f.replace(" ", "") or "* 10" in f:
        return ("echelle_canevas", f"Multiplication ×10. Références : {ref_txt}", "Mise à l'échelle d'affichage du canevas (ex. H31), pas une règle BCM.")
    if "SUM(" in f.upper():
        col, _ = colrow(addr)
        if col == "H" and sheet == "ETAT A" and re.search(r"SUM\(D\d+:G\d+\)", f.upper().replace(" ", "")):
            return ("agregat", "Total horizontal = D+E+F+G de la même ligne", "Formule structurelle. Calculable seulement si les axes D–G sont renseignés (porte D16/D17).")
        return ("agregat", f"Somme Excel. Plage : {ref_txt}", "Formule structurelle du canevas. Ne pas réécrire par le moteur.")
    if sheet != "ETAT A" and "ETAT A" in f:
        return ("copie_etat_a", f"Copie / lien depuis ETAT A. {ref_txt}", "La feuille aval ne se calcule qu'après remplissage d'ETAT A. Ce n'est pas une ventilation métier (sauf 30 % D09).")
    if any(x in f for x in ("ETAT B", "ETAT C", "CALCUL FPN", "informations")):
        return ("copie_inter_feuille", f"Lien inter-feuilles. {ref_txt}", "Dépendance aval. Incomplet tant que la source est vide.")
    if f.count("+") >= 1 and "SUM" not in f.upper() and "IF" not in f.upper():
        return ("agregat", f"Somme de cellules enfants. {ref_txt}", "Agrégat vertical (rubrique = sous-rubriques). Le moteur ne doit pas l'écrire.")
    lits = NUM_RE.findall(f)
    if any(int(x) >= 1000 for x in lits):
        return (
            "constante_historique",
            f"Littéraux numériques {', '.join(lits)}. Réfs {ref_txt}",
            "Montant incrusté d'octobre — à valider / remplacer par une règle.",
        )
    return ("formule", f"Opération Excel. Références : {ref_txt}", "Formule du canevas officiel. Interprétation métier à confirmer si non structurelle.")


def axes_from_colonne_sm(txt: str | None) -> set[str]:
    t = (txt or "").strip()
    if t == "UM Rés.":
        return {"D"}
    if t == "Dev. Non Rés.":
        return {"G"}
    if t == "Provisions":
        return {"C"}
    if t == "Selon auxiliaire":
        return {"D", "E", "F", "G"}
    return set()  # « — » ou vide : axe non établi


def nature_affichage(excel_nature: str, has_formula: bool, has_value, is_sep: bool) -> str:
    if is_sep:
        return "separateur"
    if excel_nature:
        return excel_nature
    if has_formula:
        return "formule"
    if has_value == 0:
        return "zero_octobre"
    if has_value not in (None, ""):
        return "valeur_octobre"
    return "vide"


def certitude(kind: str) -> str:
    if kind in (
        "agregat",
        "controle",
        "copie_etat_a",
        "copie_inter_feuille",
        "header",
        "separateur",
        "echelle_canevas",
        "libelle_officiel",
        "code_bcm_officiel",
        "structure",
    ):
        return "CONFIRMÉ FICHIER"
    if kind in ("constante_historique", "formule_provisoire_D09", "zero_octobre", "valeur_octobre", "formule_lien_suspect"):
        return "DÉDUIT"
    if kind in ("mapping_scd", "parametre"):
        return "À VALIDER COMPTABILITÉ"
    return "À VALIDER COMPTABILITÉ"


def missing_if_empty(kind: str) -> str:
    if kind in ("agregat", "copie_etat_a", "copie_inter_feuille", "controle", "ratio", "echelle_canevas"):
        return "La formule s'évalue. Si une entrée est vide : résultat partiel / trompeur — jamais 0 métier automatique."
    if kind in ("separateur", "header"):
        return "Aucune donnée attendue."
    return "Absence ≠ zéro. Laisser vide / NON_RENSEIGNÉ jusqu'à saisie, mapping validé ou décision."


# ---------------------------------------------------------------------------
# Chargement sources
# ---------------------------------------------------------------------------

def load_jsonl() -> list[dict]:
    rows = []
    if JSONL.exists():
        for line in JSONL.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def load_correspondance() -> list[dict]:
    wb = load_workbook(CORR, data_only=False)
    ws = wb["Correspondance"]
    out = []
    for i, row in enumerate(ws.iter_rows(min_row=5, values_only=True), start=5):
        compte = row[1]
        if compte is None or str(compte).strip() in ("", "None"):
            continue
        out.append(
            {
                "excel_row": i,
                "classe": row[0],
                "compte": str(compte).strip(),
                "base": row[5],
                "sens": row[6],
                "code_bcm": str(row[8]).strip() if row[8] is not None else "",
                "rubrique": row[9],
                "colonne_sm": row[10],
                "cle_controle": row[11],
                "remarque": row[12],
            }
        )
    wb.close()
    return out


def load_analyse_doc():
    """Tables 4 (67 codes) et 20 (règles cellule) de l'analyse T1."""
    p = DL / "Analyse_metier_SM_matrice.docx"
    empty = {}, []
    if not p.exists():
        return empty
    from docx import Document as D

    doc = D(str(p))
    unmapped: dict[str, list[int]] = {}
    if len(doc.tables) > 4:
        for row in doc.tables[4].rows[1:]:
            bloc = row.cells[0].text.strip().lower()
            codes = [int(x) for x in re.findall(r"\d{3}", row.cells[2].text)]
            if "actif" in bloc:
                unmapped["actif"] = codes
            elif "passif" in bloc:
                unmapped["passif"] = codes
            elif "hors" in bloc:
                unmapped["hors_bilan"] = codes
    rows = []
    if len(doc.tables) > 20:
        for row in doc.tables[20].rows:
            rows.append([c.text.replace("\n", " ").strip() for c in row.cells])
    return unmapped, rows


def scan_canvas() -> tuple[list[dict], dict]:
    wb = load_workbook(CANVAS, data_only=False)
    meta = {"sheets": list(wb.sheetnames), "formulas": 0, "sha": sha256(CANVAS)}
    cells = []
    for sheet in SHEETS:
        ws = wb[sheet]
        max_r = min(ws.max_row or 1, 200)
        max_c = min(ws.max_column or 1, 20)
        # RCR utile ~ l.33 ; LIQ ~49
        if sheet == "RATIO COUVERTURE DE RISQUE":
            max_r = 35
        if sheet == "RATIO DE LIQUIDITE":
            max_r = 50
        if sheet == "ETAT A":
            max_r, max_c = 181, 11
        if sheet == "ETAT B":
            max_r, max_c = 55, 12
        if sheet == "ETAT C":
            max_r, max_c = 53, 12
        if sheet == "CALCUL FPN":
            max_r, max_c = 49, 9
        if sheet == "informations à fournir":
            max_r, max_c = 20, 6
        if sheet == "RATIO FP ET AI":
            max_r, max_c = 18, 9

        for r in range(1, max_r + 1):
            bcm = as_code(ws.cell(r, 2).value) if sheet in ("ETAT A", "ETAT B", "ETAT C") else None
            lib = ws.cell(r, 1).value
            lib_s = str(lib).strip() if lib not in (None, "") else ""
            is_sep = "……" in lib_s or lib_s in ("……", "...")
            interesting_cols = list(range(1, max_c + 1))
            for c in interesting_cols:
                cell = ws.cell(r, c)
                addr = cell.coordinate
                col, _ = colrow(addr)
                f = formula_of(cell)
                val = cell.value if not f else None
                if f:
                    meta["formulas"] += 1
                # Skip pure empty decorative cells (no bcm, no formula, no value, not header)
                empty = f is None and (val is None or val == "")
                header = addr in ("A1", "A2", "B2", "A3", "B3", "D1", "E1", "D2", "E2")
                data_axis = False
                if sheet == "ETAT A" and col in "CDEFGH" and bcm:
                    data_axis = True
                if sheet == "ETAT B" and col in "CDEFGHIL" and bcm:
                    data_axis = True
                if sheet == "ETAT C" and col in "CDEFI" and bcm:
                    data_axis = True
                if sheet == "informations à fournir" and col == "C" and r >= 6:
                    data_axis = True
                if empty and not data_axis and not header and not (col == "A" and lib_s):
                    continue
                if empty and not data_axis and not header and col not in "AB" and not f:
                    continue
                kind, op, interp = interpret_formula(f, sheet, addr)
                if header:
                    kind = "header"
                    interp = "En-tête réglementaire. B2 = date d'arrêté de la SM ; B3 = banque."
                if col == "A" and lib_s and not f and sheet in ("ETAT A", "ETAT B", "ETAT C", "CALCUL FPN", "informations à fournir", "RATIO COUVERTURE DE RISQUE", "RATIO DE LIQUIDITE", "RATIO FP ET AI"):
                    kind = "libelle_officiel"
                    interp = "Libellé officiel du canevas BCM. Ce n'est pas une donnée à calculer."
                if col == "B" and sheet in ("ETAT A", "ETAT B", "ETAT C") and (bcm or (val not in (None, "") and not f)):
                    kind = "code_bcm_officiel"
                    interp = "Code BCM imprimé dans le canevas. Identifiant de rubrique, pas un montant."
                if is_sep and col in "CDEFGHI":
                    kind = "separateur"
                axis_label = ""
                if sheet == "ETAT A":
                    axis_label = AXIS_A.get(col, "")
                elif sheet == "ETAT B":
                    axis_label = AXIS_B.get(col, "")
                elif sheet == "ETAT C":
                    axis_label = AXIS_C.get(col, "")
                ex = ""
                if not f and isinstance(val, (int, float)):
                    ex = str(val)
                elif f:
                    ex = "Cache octobre non retenu comme règle (formules non évaluées ici)."
                cells.append(
                    {
                        "feuille": sheet,
                        "adresse": addr,
                        "ligne": r,
                        "colonne": col,
                        "bcm": bcm or "",
                        "libelle": lib_s,
                        "axe": axis_label,
                        "formule": f or "",
                        "kind": kind,
                        "operation": op,
                        "interpretation": interp,
                        "exemple_octobre": ex,
                        "valeur_fichier": val if not f else None,
                        "separateur": is_sep,
                    }
                )
    wb.close()
    return cells, meta


def style_header(ws, ncols):
    for col in range(1, ncols + 1):
        c = ws.cell(1, col)
        c.fill = FILL_H
        c.font = FONT_H
        c.alignment = Alignment(wrap_text=True, vertical="center")
        c.border = THIN
    ws.auto_filter.ref = ws.dimensions
    ws.freeze_panes = "A2"
    ws.row_dimensions[1].height = 32
    ws.sheet_properties.pageSetUpPr.fitToPage = True


def write_row(ws, r, values, fill=None):
    for i, v in enumerate(values, 1):
        cell = ws.cell(r, i, v)
        cell.font = FONT_N
        cell.alignment = WRAP
        cell.border = THIN
        if fill:
            cell.fill = fill
        elif r % 2 == 0:
            cell.fill = FILL_ALT


def autosize(ws, widths):
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def fill_for_cert(s: str):
    if s == "CONFIRMÉ FICHIER":
        return FILL_OK
    if s == "DÉDUIT":
        return FILL_DED
    if s == "PROPOSITION":
        return FILL_PROP
    return FILL_VAL


def build_matrix(canvas_cells, corr, jsonl, analyse_rows, sources_note, unmapped_67) -> tuple[Workbook, dict]:
    by_bcm = defaultdict(list)
    for r in corr:
        by_bcm[re.sub(r"\D", "", str(r["code_bcm"]).split("/")[0] or "0")].append(r)
    jsonl_by_bcm = defaultdict(list)
    for r in jsonl:
        code = str(r.get("cell_ref", "")).replace("BCM:", "")
        jsonl_by_bcm[code].append(r)

    rows_by_compte = defaultdict(list)
    for r in corr:
        rows_by_compte[r["compte"]].append(r)
    conflits_d22 = {cpt: rows for cpt, rows in rows_by_compte.items() if len(rows) > 1}

    unmapped_set = {f"{n:03d}" for lst in unmapped_67.values() for n in lst}

    wb = Workbook()
    # ---- LIRE MOI ----
    ws = wb.active
    ws.title = "00_LIRE_MOI"
    intro = [
        ["DOSSIER MÉTIER — Matrice exhaustive des règles de la Situation Mensuelle BCM"],
        ["Destinataire", "Comptabilité — Banque El Amana (Mauritanie)"],
        ["Canevas de référence", "BEA-SM-10-2026.xlsx"],
        ["SHA-256 canevas", sources_note["sha"]],
        ["Date du dossier", date.today().isoformat()],
        ["Statut", "Document de travail pour validation Comptabilité — AUCUNE règle n'est activée dans le moteur"],
        [],
        ["Comment lire cette matrice"],
        ["Chaque ligne = une cellule utile du canevas officiel (donnée, agrégat, contrôle, saisie)."],
        ["CONFIRMÉ FICHIER = lu dans le xlsx / la correspondance SCD, sans hypothèse."],
        ["DÉDUIT = interprétation cohérente des fichiers, pas encore visée Comptabilité."],
        ["PROPOSITION = piste issue de l'analyse T1/audit, à trancher."],
        ["À VALIDER COMPTABILITÉ = le moteur ne doit rien écrire tant que la réponse n'est pas visée."],
        ["Une cellule vide d'octobre n'est PAS un zéro permanent. Un 0 d'octobre n'est PAS une règle."],
        ["Les formules SUM / copies ETAT A sont structurelles : le moteur ne les réécrit pas."],
        ["ETAT A n'alimente B, C, FPN et ratios que via ces formules, une fois les feuilles de base renseignées."],
        [],
        ["Onglets"],
        ["01_MATRICE_CELLULES", "Inventaire cellule par cellule des 8 feuilles (y compris libellés)"],
        ["01b_DONNEES_ET_CALCULS", "Même inventaire filtré : montants, formules, saisies — à utiliser en priorité"],
        ["11_FPN_ET_RATIOS", "Formules FPN / RCR / liquidité / FP-AI expliquées (numérateur, dénominateur)"],
        ["02_CORRESPONDANCE_242", "242 lignes SCD compte → code BCM (A_VALIDER)"],
        ["03_REGLES_ANALYSE_T1", "Règles cellule reconstituées par l'analyse métier (115 / table cellule)"],
        ["04_NON_MAPPEES_D06", "67 lignes de détail sans règle (liste analyse T1)"],
        ["05_CONFLITS_D22", "Comptes pointant vers plusieurs codes BCM"],
        ["06_PARAMETRES", "Huit paramètres hors balance + annexes FPN"],
        ["07_FORMULES_DANGEREUSES", "Constantes octobre, 30/70 %, IF trompeurs, double comptage"],
        ["08_DECISIONS_OUVERTES", "Portes D01–D22 et questions"],
        ["09_SOURCES", "Fichiers utilisés / manquants"],
        ["10_SYNTHESE", "Comptages"],
    ]
    for i, row in enumerate(intro, 1):
        for j, v in enumerate(row, 1):
            cell = ws.cell(i, j, v)
            cell.font = FONT_B if j == 1 and len(row) == 2 else FONT_N
            cell.alignment = WRAP
        if i == 1:
            ws.cell(i, 1).font = Font(name="Calibri", size=16, bold=True, color="1A5278")
    ws.column_dimensions["A"].width = 36
    ws.column_dimensions["B"].width = 110
    ws.row_dimensions[1].height = 24

    # ---- MATRICE ----
    wm = wb.create_sheet("01_MATRICE_CELLULES")
    headers = [
        "ID",
        "Feuille",
        "Adresse",
        "Code BCM",
        "Libellé rubrique",
        "Axe / colonne",
        "Nature",
        "Ce que représente la valeur",
        "Source exacte",
        "Comptes / filtres",
        "Base D/C/SD/SC",
        "Opération mathématique",
        "Conditions",
        "Exclusions / exceptions",
        "Dépendances amont",
        "Cellules dépendantes (aval)",
        "Formule Excel actuelle",
        "Interprétation métier de la formule",
        "Exemple chiffré (oct. 2026, illustration)",
        "Si la donnée manque",
        "Statut de certitude",
        "Question à la Comptabilité",
        "Réponse Comptabilité",
        "Référence justificative",
        "Validateur",
        "Date validation",
        "Porte métier",
    ]
    wm.append(headers)
    style_header(wm, len(headers))

    aval = defaultdict(list)
    for cell in canvas_cells:
        if not cell["formule"]:
            continue
        for sh, a in CELL_RE.findall(cell["formule"].replace("$", "")):
            src_sheet = sh or cell["feuille"]
            aval[f"{src_sheet}!{a.replace('$', '')}"].append(f"{cell['feuille']}!{cell['adresse']}")

    stats = {"cells": 0, "confirme": 0, "deduit": 0, "proposition": 0, "avalider": 0}

    for i, cell in enumerate(canvas_cells, 1):
        bcm = cell["bcm"]
        maps = jsonl_by_bcm.get(bcm.lstrip("0") if bcm else "", []) or jsonl_by_bcm.get(bcm, [])
        corrs = [x for x in corr if bcm and bcm.lstrip("0") in re.findall(r"\d+", str(x["code_bcm"]))]
        axes_scd: set[str] = set()
        for x in corrs:
            axes_scd |= axes_from_colonne_sm(str(x.get("colonne_sm") or ""))
        maps_axe = [m for m in maps]
        corrs_axe = [x for x in corrs if cell["colonne"] in axes_from_colonne_sm(str(x.get("colonne_sm") or "")) or not axes_from_colonne_sm(str(x.get("colonne_sm") or ""))]
        comptes = []
        bases = []
        filtres = []
        for m in maps:
            comptes.append(f"{m.get('match_type')} {m.get('compte_or_prefix')} ×{m.get('sign_multiplier', 1)}")
            bases.append(str(m.get("amount_basis") or ""))
        for x in corrs:
            if x["colonne_sm"]:
                filtres.append(str(x["colonne_sm"]))
        kind = cell["kind"]
        source = "Canevas officiel (formule structurelle)" if cell["formule"] else "Non déterminée — à valider"
        porte = ""
        question = ""
        if kind in ("libelle_officiel", "code_bcm_officiel"):
            source = "Canevas officiel — texte / identifiant, pas un montant"
            question = ""
        elif cell["separateur"]:
            source = "Canevas — ligne de réserve sans montant"
            question = "Confirmer qu'aucune donnée n'est attendue sur cette ligne."
        elif kind == "header":
            source = "En-tête SM (période / banque)"
        elif cell["feuille"] == "RATIO COUVERTURE DE RISQUE" and cell["adresse"] in ("D14", "D15"):
            kind = "formule_lien_suspect"
            source = "Canevas : lien vers informations à fournir!B7/B8 (colonne code), pas C7/C8 (montant)"
            porte = "D21"
            question = "Corriger le lien vers C7/C8 (montants) ou confirmer que B7/B8 est voulu ?"
        elif kind in ("agregat", "copie_etat_a", "copie_inter_feuille", "controle", "ratio", "echelle_canevas"):
            source = "Formule du canevas officiel BEA-SM-10-2026.xlsx"
            question = "Confirmer que cette formule officielle doit être conservée telle quelle."
            if cell["feuille"] == "ETAT C" and cell["adresse"] in ("C50", "D50", "E50"):
                source = "Formule officielle TOTAL ressources — C50 = C40+C39+C38+C35+C36+C31+C28"
                porte = "D10"
                question = "C35 (code 208) = C36 (code 209) : le total recompte 209. Confirmer l'alerte sans modifier le xlsx BCM ?"
        elif kind == "constante_historique":
            source = "Formule d'octobre avec littéraux — PAS une règle permanente"
            porte = "D02" if cell["adresse"] == "D38" else "D04"
            question = "Par quelle règle (comptes, base, paramètre) remplacer cette constante d'octobre ?"
        elif kind == "formule_provisoire_D09":
            source = "Canevas octobre — clé 30/70 % (D09)"
            porte = "D09"
            question = "Conserver 30/70 % ou alimenter depuis un fichier crédits / dépôts ?"
        elif cell["feuille"] == "ETAT A" and bcm and bcm in unmapped_set and not cell["formule"] and cell["colonne"] in "CDEFG":
            source = "Aucune correspondance SCD — D06"
            porte = "D06"
            question = f"Si un compte non mappé apparaît, faut-il l'affecter au code BCM {bcm} ou créer une règle ?"
            kind = "non_mappee_D06"
        elif cell["feuille"] == "ETAT A" and maps and not cell["formule"] and cell["colonne"] in "CDEFG" and (not axes_scd or cell["colonne"] in axes_scd or "Selon auxiliaire" in filtres):
            source = "Correspondance SCD (242 règles A_VALIDER) — non activée"
            porte = "D01 ; D16/D17"
            if cell["colonne"] not in axes_scd and axes_scd:
                source = "Axe hors « Colonne SM » SCD pour ce code — ne pas y coller le mapping par défaut"
                porte = "D16/D17"
                question = f"L'axe {cell['axe'] or cell['colonne']} n'est pas celui de la SCD ({', '.join(sorted(set(filtres)))}). Faut-il quand même une valeur ici ?"
                kind = "axe_non_scd"
            else:
                question = (
                    f"Confirmer les comptes {', '.join(m.get('compte_or_prefix') for m in maps[:8])} "
                    f"et l'axe {cell['axe'] or cell['colonne']} (la DET n'a pas la résidence)."
                )
                kind = "mapping_scd"
        elif cell["feuille"] == "ETAT A" and not cell["formule"] and cell["colonne"] in "CDEFG" and bcm:
            source = "Feuille de saisie / import — source non établie dans SCD pour cet axe"
            porte = "D01 / D06 / D16"
            question = "Cette cellule doit-elle être alimentée ? Par quels comptes, quel fichier, ou rester vide ?"
        elif cell["feuille"] in ("ETAT B", "ETAT C") and not cell["formule"] and cell["colonne"] in "CDEFGHI" and not cell["separateur"]:
            source = "Hors BAL DET — ventilation secteur / maturité (D09) ou copie ETAT A absente"
            porte = "D09"
            question = "Cette cellule B/C doit-elle copier ETAT A, venir d'un fichier crédits/échéances, ou rester vide ?"
            kind = "saisie_etat_bc"
        elif cell["feuille"] == "informations à fournir" and cell["colonne"] == "C" and cell["ligne"] >= 6:
            if cell["formule"]:
                source = "Lien ETAT A (bénéfice)"
                porte = "D03 / D13"
            else:
                source = "Annexe FPN — saisie mensuelle (les 0 d'octobre ne se reconduisent pas)"
                porte = "D21"
                question = "Quelle pièce justifie ce montant chaque mois ? L'absence est-elle un vrai zéro ?"
                kind = "saisie_fpn"

        cert = certitude(kind)
        if kind == "mapping_scd":
            cert = "À VALIDER COMPTABILITÉ"
        if kind == "non_mappee_D06":
            cert = "À VALIDER COMPTABILITÉ"
        if kind == "saisie_fpn":
            cert = "À VALIDER COMPTABILITÉ"
        if kind == "formule_provisoire_D09":
            cert = "DÉDUIT"
        if kind == "axe_non_scd":
            cert = "À VALIDER COMPTABILITÉ"
        if kind == "formule_lien_suspect":
            cert = "DÉDUIT"

        desc = cell["axe"] or cell["libelle"] or ""
        if bcm:
            desc = f"Code BCM {bcm} — {cell['libelle']} — {cell['axe'] or cell['colonne']}"

        key_src = f"{cell['feuille']}!{cell['adresse']}"
        deps_aval = ", ".join(aval.get(key_src, [])[:12])
        deps_amont = ""
        if cell["formule"]:
            deps_amont = ", ".join(
                (f"'{s}'!{a}" if s else f"{cell['feuille']}!{a}").replace("$", "")
                for s, a in CELL_RE.findall(cell["formule"].replace("$", ""))
            )

        stats["cells"] += 1
        if cert == "CONFIRMÉ FICHIER":
            stats["confirme"] += 1
        elif cert == "DÉDUIT":
            stats["deduit"] += 1
        elif cert == "PROPOSITION":
            stats["proposition"] += 1
        else:
            stats["avalider"] += 1

        write_row(
            wm,
            i + 1,
            [
                f"C{i:04d}",
                cell["feuille"],
                cell["adresse"],
                bcm,
                cell["libelle"],
                cell["axe"] or cell["colonne"],
                kind,
                desc,
                source,
                " ; ".join(comptes) if comptes and kind in ("mapping_scd", "axe_non_scd") else (" ; ".join(sorted(set(filtres))) if filtres and kind == "mapping_scd" else (" ; ".join(comptes) if comptes and cell["colonne"] in "CDEFG" and not cell["formule"] else "")),
                " / ".join(sorted({b for b in bases if b})) if bases and kind in ("mapping_scd", "axe_non_scd") else "",
                cell["operation"],
                "Mapping non ACTIVE tant que D01 ouvert" if maps else "",
                "Ne jamais inférer résidence/secteur/maturité depuis un champ DET absent",
                deps_amont,
                deps_aval,
                cell["formule"],
                cell["interpretation"],
                cell["exemple_octobre"],
                missing_if_empty(kind),
                cert,
                question,
                "",
                "",
                "",
                "",
                porte,
            ],
            fill_for_cert(cert),
        )
    autosize(wm, [8, 28, 10, 10, 42, 28, 22, 42, 42, 36, 14, 40, 28, 36, 36, 36, 40, 44, 28, 36, 22, 44, 24, 22, 16, 14, 16])
    wm.auto_filter.ref = wm.dimensions

    wdata = wb.create_sheet("01b_DONNEES_ET_CALCULS")
    wdata.append(headers)
    style_header(wdata, len(headers))
    skip_nat = {"libelle_officiel", "code_bcm_officiel", "header", "separateur", "structure"}
    di = 2
    for r in range(2, wm.max_row + 1):
        nat = wm.cell(r, 7).value
        if nat in skip_nat:
            continue
        for c in range(1, len(headers) + 1):
            wdata.cell(di, c, wm.cell(r, c).value)
            wdata.cell(di, c).font = FONT_N
            wdata.cell(di, c).alignment = WRAP
            wdata.cell(di, c).border = THIN
            wdata.cell(di, c).fill = fill_for_cert(str(wm.cell(r, 21).value or ""))
        di += 1
    autosize(wdata, [8, 28, 10, 10, 42, 28, 22, 42, 42, 36, 14, 40, 28, 36, 36, 36, 40, 44, 28, 36, 22, 44, 24, 22, 16, 14, 16])
    wdata.auto_filter.ref = wdata.dimensions
    stats["cells_donnees"] = di - 2

    # ---- 242 ----
    w2 = wb.create_sheet("02_CORRESPONDANCE_242")
    h2 = [
        "ID source",
        "Compte",
        "Match",
        "Code BCM SCD",
        "Rubrique",
        "Colonne SM (SCD)",
        "Base",
        "Sens",
        "Lifecycle actuel",
        "Remarque SCD",
        "Multi-cellule ?",
        "Certitude",
        "Question Comptabilité",
        "Réponse",
        "Validateur",
        "Date",
        "Statut",
    ]
    w2.append(h2)
    style_header(w2, len(h2))
    for i, r in enumerate(jsonl, 1):
        cpt = str(r.get("compte_or_prefix"))
        multi = "OUI — D22 (plusieurs lignes SCD)" if cpt in conflits_d22 else "NON"
        write_row(
            w2,
            i + 1,
            [
                r.get("source_id"),
                cpt,
                r.get("match_type"),
                str(r.get("cell_ref", "")).replace("BCM:", ""),
                r.get("notes"),
                next((x["colonne_sm"] for x in corr if x["compte"] == cpt and str(x["code_bcm"]).startswith(str(r.get("cell_ref", "")).replace("BCM:", ""))), ""),
                r.get("amount_basis"),
                r.get("sign_multiplier"),
                "A_VALIDER (aucune ACTIVE)",
                "",
                multi,
                "À VALIDER COMPTABILITÉ",
                "Activer cette règle ? Base D/C/SD/SC conforme à la pratique ? Colonne (résidence/devise) confirmée ?",
                "",
                "",
                "",
                "À arbitrer",
            ],
            FILL_VAL,
        )
    autosize(w2, [12, 12, 10, 12, 40, 18, 8, 8, 22, 28, 16, 24, 50, 24, 16, 12, 14])

    # ---- analyse T1 ----
    w3 = wb.create_sheet("03_REGLES_ANALYSE_T1")
    if analyse_rows:
        w3.append(analyse_rows[0] + ["Écart vs SCD 242", "Certitude dossier"])
        style_header(w3, len(analyse_rows[0]) + 2)
        for i, row in enumerate(analyse_rows[1:], 1):
            note = "Règle cellule T1 (souvent préfixe) ≠ 1 ligne SCD EXACT. Divergence 115 vs 242."
            write_row(w3, i + 1, row + [note, "À VALIDER COMPTABILITÉ"], FILL_PROP)
        autosize(w3, [10] * (len(analyse_rows[0]) + 2))
    else:
        w3.append(["Source Analyse_metier_SM_matrice.docx absente ou table 20 illisible"])

    # ---- D06 ----
    w4 = wb.create_sheet("04_NON_MAPPEES_D06")
    w4.append(["Bloc", "Code BCM", "Présent dans SCD 242 ?", "Traitement actuel", "Question Comptabilité", "Réponse", "Validateur", "Date", "Statut"])
    style_header(w4, 9)
    mapped_codes = {str(r.get("cell_ref", "")).replace("BCM:", "").lstrip("0") for r in jsonl}
    ri = 2
    for bloc, codes in unmapped_67.items():
        for n in codes:
            code = f"{n:03d}"
            in_scd = "OUI" if str(n) in mapped_codes else "NON"
            write_row(
                w4,
                ri,
                [
                    bloc,
                    code,
                    in_scd,
                    "Jamais 0 automatique. Ligne nulle en octobre 2026 selon l'analyse T1.",
                    "Si un compte non mappé non nul apparaît, l'affecter à ce code, créer une règle, ou bloquer l'import ?",
                    "",
                    "",
                    "",
                    "À arbitrer",
                ],
                FILL_VAL,
            )
            ri += 1
    autosize(w4, [14, 12, 22, 50, 60, 24, 16, 12, 14])

    # ---- D22 ----
    w5 = wb.create_sheet("05_CONFLITS_D22")
    w5.append(["Compte", "Codes BCM cibles", "Lignes SCD", "Question", "Réponse", "Validateur", "Date", "Statut"])
    style_header(w5, 8)
    ri = 2
    for cpt, lignes in sorted(conflits_d22.items()):
        codes = sorted({str(x["code_bcm"]) for x in lignes})
        write_row(
            w5,
            ri,
            [
                cpt,
                " / ".join(codes),
                " ; ".join(f"BCM {x['code_bcm']} base {x['base']} sens {x['sens']} col {x['colonne_sm']}" for x in lignes),
                "Double affectation légitime (D d'un côté, C de l'autre) ou conflit à trancher (une seule cellule) ?",
                "",
                "",
                "",
                "À arbitrer",
            ],
            FILL_VAL,
        )
        ri += 1
    autosize(w5, [12, 18, 70, 70, 24, 16, 12, 14])

    # ---- PARAM ----
    w6 = wb.create_sheet("06_PARAMETRES")
    w6.append(["Code", "Libellé", "Cellules visées (analyse T1)", "Source à confirmer", "Exemple oct. 2026", "Reconduction", "Question", "Réponse", "Validateur", "Date", "Statut"])
    style_header(w6, 11)
    for i, p in enumerate(PARAMS, 1):
        write_row(
            w6,
            i + 1,
            [
                p[0],
                p[1],
                p[2],
                p[3],
                p[4],
                "INTERDITE — saisie chaque mois. Absence ≠ zéro.",
                "Confirmer la source documentaire du mois et les cellules exactes du canevas.",
                "",
                "",
                "",
                "À compléter",
            ],
            FILL_VAL,
        )
    write_row(
        w6,
        len(PARAMS) + 2,
        [
            "FPN annexes",
            "Informations à fournir C6–C8, C10–C20",
            "Feuille informations à fournir",
            "Pièces FPN (créances radiées, actions propres, etc.)",
            "0 numériques d'octobre — non reconduits",
            "INTERDITE",
            "Pour chaque ligne : vrai zéro justifié ou non applicable ce mois ?",
            "",
            "",
            "",
            "À compléter",
        ],
        FILL_VAL,
    )
    autosize(w6, [18, 36, 42, 50, 22, 36, 56, 24, 16, 12, 14])

    # ---- DANGER ----
    w7 = wb.create_sheet("07_FORMULES_DANGEREUSES")
    w7.append(["Feuille", "Adresse", "Sujet", "Formule / constat", "Risque", "Porte", "Question", "Réponse", "Statut"])
    style_header(w7, 9)
    dangers = [
        ("ETAT A", "D9", "Constante octobre caisse", "=588160767-F9", "Le 588160767 est le total caisse d'octobre, pas une règle.", "D04", "Remplacer par SD 100000+100100 − caisse_devises ?", "À arbitrer"),
        ("ETAT A", "D21", "Constante qui s'annule", "=150000000-150000000", "Toujours 0. Résidu de saisie.", "D21", "Écrire 0 structurel ou alimenter par comptes ?", "À arbitrer"),
        ("ETAT A", "D38", "ECART incrusté", "=3972024483-C38-2873218-5", "2873218 ≈ écart classes 1–8. Compensation automatique interdite sans D02.", "D02", "Règle ECART ACTIVE sur décision, jamais constante ?", "À arbitrer"),
        ("ETAT A", "D75", "Constante immo", "Littéral octobre − C75", "Doit venir du 470000 − amort_frais_immo.", "D04", "Confirmer la formule comptes ?", "À arbitrer"),
        ("ETAT A", "D76", "Constante incorporels", "Littéral octobre − C76", "Idem 475000 / 487000.", "D04", "Confirmer ?", "À arbitrer"),
        ("ETAT A", "D106", "Constante publics", "Littéral − F106", "Doit être le paramètre publics_mru.", "D04/D05", "Liste des comptes publics ?", "À arbitrer"),
        ("ETAT A", "D112", "Constante DAT", "Littéral − D111", "DAT public (70 M reconduits de juin).", "D04", "Source DAT du mois ?", "À arbitrer"),
        ("ETAT A", "D123", "Constante créditeurs", "463722024+296461984-21", "Projets + soldes 218xxx. Le −21 = débit 218200.", "D01/D05", "Confirmer composition ?", "À arbitrer"),
        ("ETAT A", "D167", "Constante cautions", "5874268360-G167", "Hors-bilan 9238xx − cautions_dev.", "D04", "Confirmer ?", "À arbitrer"),
        ("ETAT B", "E46/E48/E49", "30 % forfaitaire", "×30% depuis ETAT A", "Pas un fichier crédits. D09.", "D09", "Fichier crédits/dépôts ou conserver 30/70 ?", "À arbitrer"),
        ("ETAT B", "D46/D48/D49", "70 % complémentaire", "total A − 30 %", "Dépend des 30 %.", "D09", "Idem", "À arbitrer"),
        ("ETAT C", "C50/D50/E50 code 220", "Double comptage 209", "C50=+C40+C39+C38+C35+C36+C31+C28 alors que C35 (208)=C36 (209)", "209 est compté deux fois dans TOTAL 220. Formule officielle : ne pas la réécrire. Alerter.", "D10", "Confirmer l'alerte sans modifier le xlsx BCM ?", "À arbitrer"),
        ("RCR", "D14 / D15", "Lien colonne B au lieu de C", "D14='informations à fournir'!B7 ; D15=!B8", "B7/B8 = codes, C7/C8 = montants. Le ratio lit 0 même si l'annexe est saisie.", "D21", "Corriger vers C7/C8 ?", "À arbitrer"),
        ("ETAT A", "I147", "Contrôle actif/passif", "=+H147-H81", "TRUE/0 trompeur si H vides.", "—", "Conserver comme contrôle d'équilibre après fill ?", "À valider"),
        ("RCR", "H31", "×10 canevas", "C39*10", "Échelle d'affichage.", "—", "Ne pas interpréter comme ratio métier ×10 ?", "À valider"),
        ("Toutes IF B/C", "colonnes L / I", "Concordance IF", "IF(ETAT A = total, TRUE, FALSE)", "TRUE si les deux côtés sont vides/0.", "D09", "Ne jamais prendre TRUE pour validation réglementaire.", "À valider"),
    ]
    for i, d in enumerate(dangers, 1):
        write_row(w7, i + 1, list(d), FILL_DED)
    autosize(w7, [12, 16, 28, 40, 50, 12, 50, 14, 14])

    # ---- decisions ----
    w8 = wb.create_sheet("08_DECISIONS_OUVERTES")
    w8.append(["ID", "Sujet", "Impact moteur", "Priorité pour un moteur juste", "Question précise", "Réponse", "Comptes / rubriques", "Formule retenue", "Exemple chiffré", "Source", "Justification", "Validateur", "Date", "Statut"])
    style_header(w8, 14)
    decisions = [
        ("D01", "Activer le mapping", "Sans ACTIVE, aucune cellule ETAT A n'est alimentée depuis la DET", "P0", "Quelles règles des 242 SCD (et/ou 115 T1) deviennent ACTIVE ? Préfixe 21* / 32* / 913* ?"),
        ("D15", "Nature TOTDEB / TOTCRE", "17 règles en D et 19 en C ; 23 comptes bi-mouvementés", "P0", "TOTDEB/TOTCRE DET = mouvements de la période ou somme des soldes individuels ?"),
        ("D16/D17", "Résidents / non-résidents", "Colonnes D vs E et F vs G d'ETAT A ; la DET n'a que la devise", "P0", "Convention par nature de compte (ex. 210100) ou fichier auxiliaire obligatoire ?"),
        ("D02", "Écart de balance", "D38 octobre absorbe 2 873 218 / 2 873 223", "P0", "Règle ECART formalisée (cellule, signe) ou correction hors SM ? Ne jamais laisser la constante."),
        ("D06", "67 rubriques sans règle", "Interdiction du zéro automatique", "P0", "Liste T1 ci-jointe : confirmer + conduite si compte non mappé non nul."),
        ("D09", "ETAT B et ETAT C", "Hors DET. 30/70 % forfaitaires dans le canevas", "P0", "Fichier crédits/dépôts/échéances ou ventilation forfaitaire visée ?"),
        ("D22", "Multi-cellules", "14 comptes SCD sur 2 lignes (D vs C souvent)", "P1", "Affectations légitimes (D vs C) vs conflits à une seule cellule ?"),
        ("D04/D05", "8 paramètres + listes", "Cellules mixtes caisse, publics, projets, DAT, amort, cautions", "P0", "Source documentaire mensuelle et listes de comptes ?"),
        ("D08", "Provisions 290000 / 356000", "Retranchement COD (C38)", "P1", "Confirmer les comptes de provisions dans D38/C38."),
        ("D10/D20", "Double comptage ETAT C", "Alerte sans modifier le canevas", "P1", "Confirmer l'anomalie de formule du total ressources."),
        ("D03/D13", "Résultat et FPN", "D146 inclut 358000 (position de change) ; C9 FPN", "P1", "Le bénéfice déclaré inclut-il toujours la position de change ? Plafond FPN ?"),
        ("D21", "Saisies FPN / contre-garanties / quotités RCR", "Feuilles INFO, E7:E25 RCR, D12/D17–19/D23 LIQ", "P1", "Quelles lignes sont de vrais zéros vs non applicables ?"),
        ("MATRICE", "Fichier Claude Matrice_SM_cellule_regle_source.xlsx", "115 règles compte×cellule non retrouvées", "P1", "Fournir le classeur ou confirmer que la SCD 242 est la seule matrice."),
        ("115 vs 242", "Divergence de cardinal", "T1=115 cellules ; SCD=242 lignes EXACT / 43 codes", "P0", "Quelle est la matrice officielle à implémenter ?"),
        ("DET vs COND", "Source unique", "T3 : BAL DET uniquement ; analyses T1 souvent sur COND", "P0", "Les règles T1 (TOTDEB COND) s'appliquent-elles telles quelles à la DET (DEB/CRE par ligne) ?"),
    ]
    for i, d in enumerate(decisions, 1):
        write_row(w8, i + 1, list(d) + ["", "", "", "", "", "", "", "À arbitrer"], FILL_VAL)
    autosize(w8, [12, 36, 50, 14, 60, 24, 24, 24, 18, 18, 18, 14, 12, 14])

    # ---- sources ----
    w9 = wb.create_sheet("09_SOURCES")
    w9.append(["Fichier", "Emplacement", "Rôle", "Statut"])
    style_header(w9, 4)
    src_rows = [
        ("BEA-SM-10-2026.xlsx", str(CANVAS), "Canevas officiel 8 feuilles — SHA 54e3b687…", "Présent, hash conforme"),
        ("Correspondance_BAL_SM_BEA_10-2026_1==SCD.xlsx", str(CORR), "242 correspondances compte→BCM", "Présent"),
        ("BAL DET 31-10-2026.xlsx", str(DL / "BAL DET 31-10-2026.xlsx"), "Source unique T3 (NCG, DEB, CRE, DEVISE)", "Présent"),
        ("BAL COND 31-10-2026.xlsx", str(DL / "BAL COND 31-10-2026.xlsx"), "Historique T1 / SCD (TOTDEB/TOTCRE) — plus d'import T3", "Présent (lecture)"),
        ("Copie de Maquette SM-RC-MF.xlsx", str(DL / "Copie de Maquette SM-RC-MF.xlsx"), "Aide mapping, pas le canevas", "Présent"),
        ("Audit_Reporting_BCM_BEA.docx", str(DL / "Audit_Reporting_BCM_BEA.docx"), "Audit 12/11/2026", "Présent"),
        ("Cahier_des_charges_Fonctionnel_Reporting_BCM_SM.docx", str(DL / "Cahier_des_charges_Fonctionnel_Reporting_BCM_SM.docx"), "CdC fonctionnel", "Présent"),
        ("Cahier_des_charges_Technique_Reporting_BCM_SM_Cursor.docx", str(DL / "Cahier_des_charges_Technique_Reporting_BCM_SM_Cursor.docx"), "CdC technique", "Présent"),
        ("Analyse_metier_SM_matrice.docx", str(DL / "Analyse_metier_SM_matrice.docx"), "Analyse T1 16/11/2026 + 67 codes + exemples", "Présent"),
        ("T3_2_MAPPING_SEED_CANDIDATES.jsonl", str(JSONL), "242 règles seed A_VALIDER", "Présent (dépôt)"),
        ("Matrice_SM_cellule_regle_source.xlsx", "Cité par Analyse métier — introuvable", "115 règles compte×cellule", "MANQUANT"),
        ("BAL + SM septembre 2026", "Décision SEPT", "Non-régression", "MANQUANT"),
        ("Fichier crédits / dépôts / échéances", "D09", "ETAT B / ETAT C réels", "MANQUANT"),
        ("Listes comptes publics / projets", "D05", "Paramètres 322/323/403", "MANQUANT"),
        ("Instruction BCM / circulaire SM", "Référentiel réglementaire externe", "Libellés officiels hors canevas", "NON FOURNIE"),
        ("Déclaration mensuelle - BEA - juillet - 2026.xlsx", str(DL / "Déclaration mensuelle - BEA - juillet - 2026.xlsx"), "SM d'un autre mois (contrôle de stabilité des formules)", "Présent (non utilisé comme règle d'octobre)"),
    ]
    for i, r in enumerate(src_rows, 1):
        fl = FILL_VAL if r[3].startswith("MANQUANT") or r[3].startswith("NON") else FILL_OK
        write_row(w9, i + 1, list(r), fl)
    autosize(w9, [56, 70, 50, 28])

    stats["d22"] = len(conflits_d22)
    stats["jsonl"] = len(jsonl)
    stats["corr"] = len(corr)
    stats["unmapped"] = sum(len(v) for v in unmapped_67.values())
    stats["analyse"] = max(0, len(analyse_rows) - 1)

    w10 = wb.create_sheet("10_SYNTHESE")
    w10.append(["Indicateur", "Valeur", "Commentaire"])
    style_header(w10, 3)
    syn = [
        ("Cellules documentées (matrice)", stats["cells"], "8 feuilles, hors plages de mise en forme vides"),
        ("Formules du canevas (scan)", sources_note["formulas"], "Cible officielle 663"),
        ("Règles SCD / seed A_VALIDER", stats["jsonl"], "0 ACTIVE"),
        ("Règles cellule analyse T1 (table)", stats["analyse"], "Divergence 115 vs 242 à trancher"),
        ("Codes BCM SCD distincts (normalisés)", len({re.findall(r"\d+", str(r.get("cell_ref", "")))[0] for r in jsonl if re.findall(r"\d+", str(r.get("cell_ref", "")))}), "43 attendus T3.2"),
        ("Lignes D06 (liste T1)", stats["unmapped"], "30 actif + 25 passif + 12 hors-bilan = 67"),
        ("Comptes multi-cellules D22", stats["d22"], "Arbitrage légitime vs conflit"),
        ("CONFIRMÉ FICHIER", stats["confirme"], "Formules structurelles / en-têtes"),
        ("DÉDUIT", stats["deduit"], "Constantes, 30 %, zéros octobre"),
        ("À VALIDER COMPTABILITÉ", stats["avalider"], "Mapping, D06, paramètres, axes — y compris libellés si non filtrés"),
        ("Cellules de données / calculs (01b)", stats.get("cells_donnees", ""), "Hors libellés A/B, en-têtes et séparateurs"),
        ("SHA canevas", sources_note["sha"], "Doit égaler 54e3b687…"),
    ]

    w11 = wb.create_sheet("11_FPN_ET_RATIOS")
    w11.append(["Feuille", "Adresse", "Formule", "Opération métier", "Numérateur / source", "Dénominateur / source", "Si entrée vide", "Certitude"])
    style_header(w11, 8)
    fpn_rows = [
        ("CALCUL FPN", "C7", "='ETAT A'!H143", "Capital social = total ETAT A code 423", "ETAT A H143", "—", "Résultat 0 trompeur", "CONFIRMÉ FICHIER"),
        ("CALCUL FPN", "C8", "='ETAT A'!H141", "Primes liées au capital", "ETAT A H141", "—", "Résultat 0 trompeur", "CONFIRMÉ FICHIER"),
        ("CALCUL FPN", "C9", "='ETAT A'!H142-'informations à fournir'!C13", "Réserves moins réserve de réévaluation saisie", "H142", "INFO C13", "Si C13 vide, Excel traite 0 : FPN trop élevé", "CONFIRMÉ FICHIER"),
        ("CALCUL FPN", "C10", "=+'ETAT A'!D144+'ETAT A'!D145", "Report à nouveau créditeur", "D144+D145", "—", "Somme partielle", "CONFIRMÉ FICHIER"),
        ("CALCUL FPN", "C11", "='informations à fournir'!C9", "Bénéfice hors dividendes", "INFO C9 = ETAT A D146", "—", "Chaîne A→INFO→FPN", "CONFIRMÉ FICHIER"),
        ("CALCUL FPN", "C13", "=SUM(C7:C12)", "FPB article 6 = somme des lignes 7 à 12", "C7:C12", "—", "Formule structurelle", "CONFIRMÉ FICHIER"),
        ("CALCUL FPN", "C27", "=IF(C33<C35,C35-C33,0)", "Si FPC bruts < déductions FPC, reporter l'excédent sur FPB", "C35-C33", "—", "0 Excel ≠ 0 métier si C33/C35 vides", "CONFIRMÉ FICHIER"),
        ("CALCUL FPN", "C28", "=SUM(C16:C27)", "Total déductions FPB", "C16:C27", "—", "—", "CONFIRMÉ FICHIER"),
        ("CALCUL FPN", "C29", "=+C13+C15-C28", "FPB nets = A + B − C", "C13+C15", "C28", "—", "CONFIRMÉ FICHIER"),
        ("CALCUL FPN", "C36", "=IF(C33>=C35,C33-C35,0)", "FPC nets : E−F si E≥F sinon 0", "C33", "C35", "TRUE/0 trompeur si vides", "CONFIRMÉ FICHIER"),
        ("CALCUL FPN", "C39", "=+C29+C36", "FPN = FPB nets + FPC nets", "C29+C36", "—", "Cible des trois ratios", "CONFIRMÉ FICHIER"),
        ("RCR", "D7:D13, D16:D25", "='ETAT A'!H…", "Montants nets = totaux ETAT A", "Colonne H ETAT A", "—", "Copies", "CONFIRMÉ FICHIER"),
        ("RCR", "E7:E25", "0 saisis octobre", "Contre-garanties — saisie mensuelle, pas un zéro permanent", "Saisie", "—", "Absence ≠ 0", "À VALIDER COMPTABILITÉ"),
        ("RCR", "F*", "=D-E", "Net = brut − contre-garantie", "D", "E", "—", "CONFIRMÉ FICHIER"),
        ("RCR", "G*", "1 / 0,33 / 0,25", "Quotités du canevas (crédits 100 %, acceptations 33 %, autres 25 %)", "Paramètre canevas", "—", "Confirmer si BCM a d'autres taux", "DÉDUIT"),
        ("RCR", "H*", "=G*F", "Pondéré = quotité × net", "G et F", "—", "—", "CONFIRMÉ FICHIER"),
        ("RCR", "H26", "=SUM(H20:H25,H7:H17)", "Total engagements pondérés", "H7:H17 et H20:H25", "—", "—", "CONFIRMÉ FICHIER"),
        ("RCR", "H27", "='CALCUL FPN'!C39", "FPN corrigés = FPN", "FPN C39", "—", "—", "CONFIRMÉ FICHIER"),
        ("RCR", "H28", "=H27/H26", "Ratio couverture = FPN / engagements pondérés", "H27", "H26", "Division par 0 si H26 vide", "CONFIRMÉ FICHIER"),
        ("RCR", "H29", "0,1", "Norme 10 %", "Constante réglementaire dans le canevas", "—", "Ne pas la changer sans instruction BCM", "CONFIRMÉ FICHIER"),
        ("RCR", "H31", "='CALCUL FPN'!C39*10", "Plafond théorique = FPN × 10 (inverse de 10 %)", "FPN", "—", "Échelle canevas, pas une saisie", "CONFIRMÉ FICHIER"),
        ("RCR", "D14", "='informations à fournir'!B7", "Titres participation non bancaire — LIEN SUR LA COLONNE CODE", "B7 (vide) au lieu de C7", "—", "Toujours 0 même si C7 saisi", "DÉDUIT"),
        ("LIQ", "D6", "=SUM(D7:D13)", "Numérateur actifs liquides", "Caisse, BCM, BT, chèques, effets, marge, position prêteuse", "—", "—", "CONFIRMÉ FICHIER"),
        ("LIQ", "D7", "='ETAT A'!H8", "Caisse = total ETAT A code 101", "H8", "—", "—", "CONFIRMÉ FICHIER"),
        ("LIQ", "D14", "=SUM(D15:D24)", "Dénominateur exigibilités CT", "D15:D24", "—", "—", "CONFIRMÉ FICHIER"),
        ("LIQ", "D16", "=+'ETAT A'!H105", "COD clientèle", "H105", "—", "—", "CONFIRMÉ FICHIER"),
        ("LIQ", "D17:D19, D12, D23", "0 octobre", "Terme / bons / obligataire / marges — saisie ou ETAT C col. <3 mois", "D09 / saisie", "—", "Absence ≠ 0", "À VALIDER COMPTABILITÉ"),
        ("LIQ", "D20", "=+'ETAT A'!H116/2", "Livrets à 50 %", "H116", "2", "Règle 50 % dans le canevas", "CONFIRMÉ FICHIER"),
        ("LIQ", "C26", "=D6/D14", "Ratio liquidité = numérateur / dénominateur", "D6", "D14", "Indéterminé si D14 vide", "CONFIRMÉ FICHIER"),
        ("LIQ", "C27", "0,2", "Norme 20 %", "Constante canevas", "—", "—", "CONFIRMÉ FICHIER"),
        ("LIQ", "C48", "=IF(C39-C47>0,C39-C47,0)", "Position prêteuse nette = max(W−X, 0)", "TOTAL W C39", "TOTAL X C47", "—", "CONFIRMÉ FICHIER"),
        ("LIQ", "C49", "=IF(C47-C39>0,C47-C39,0)", "Position emprunteuse nette = max(X−W, 0)", "C47", "C39", "—", "CONFIRMÉ FICHIER"),
        ("FP/AI", "C6", "='CALCUL FPN'!C39", "FPN retenus (A)", "FPN C39", "—", "—", "CONFIRMÉ FICHIER"),
        ("FP/AI", "C8", "='ETAT A'!H59", "Titres de participation (B)", "H59", "—", "—", "CONFIRMÉ FICHIER"),
        ("FP/AI", "C9", "='informations à fournir'!C12", "Titres déduits des FP (C) = actions propres saisies", "INFO C12", "—", "Si C12 vide → 0 Excel", "CONFIRMÉ FICHIER"),
        ("FP/AI", "C10", "=C8-C9", "Titres retenus D = B − C", "C8", "C9", "—", "CONFIRMÉ FICHIER"),
        ("FP/AI", "C11", "='ETAT A'!H65-'ETAT A'!H68", "Immobilisations corporelles hors encours", "H65", "H68", "—", "CONFIRMÉ FICHIER"),
        ("FP/AI", "C15", "=C14+C13+C10", "Valeurs immobilisées nettes I = D+G+H", "C10, C13, C14", "—", "—", "CONFIRMÉ FICHIER"),
        ("FP/AI", "C16", "=(C6/C15)*100", "Ratio J = (FPN / immobilisations) × 100", "C6", "C15", "Indéterminé si C15 vide", "CONFIRMÉ FICHIER"),
    ]
    for i, row in enumerate(fpn_rows, 1):
        write_row(w11, i + 1, list(row), fill_for_cert(row[-1]))
    autosize(w11, [16, 18, 42, 56, 36, 22, 36, 24])
    for i, r in enumerate(syn, 1):
        write_row(w10, i + 1, list(r), FILL_ALT if i % 2 == 0 else None)
    autosize(w10, [42, 22, 56])
    stats["_wb"] = wb
    return wb, stats


def build_questionnaire(stats, corr, jsonl) -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = "00_MODE_EMPLOI"
    lines = [
        ["QUESTIONNAIRE DE VALIDATION — Comptabilité BEA"],
        ["À remplir pour figer les règles du moteur SM (BAL DET → canevas officiel)."],
        ["Une ligne = une décision. Statuts : À compléter / À arbitrer / Validé / Rejeté."],
        ["Ne pas activer de règle dans BEA DIGITAL avant statut Validé."],
        [],
        ["Feuilles", "Contenu"],
        ["01_DECISIONS_PRIORITAIRES", "Portes P0 (D01, D15, D16/D17, D02, D06, D09, D04)"],
        ["02_MAPPING_242", "Oui/Non d'activation par règle SCD"],
        ["03_PARAMETRES_ET_LISTES", "Huit paramètres + listes D05"],
        ["04_ETAT_B_ET_C", "Source B/C et 30/70 %"],
        ["05_AXES_RESIDENCE", "Convention D/E/F/G"],
        ["06_NON_MAPPEES_D06", "67 codes sans règle SCD"],
        ["07_CONFLITS_D22", "14 comptes sur plusieurs lignes SCD"],
        ["08_SYNTHESE_OUVERTES", "Tableau de bord"],
    ]
    for i, row in enumerate(lines, 1):
        for j, v in enumerate(row, 1):
            ws.cell(i, j, v).font = FONT_B if i == 1 else FONT_N
            ws.cell(i, j).alignment = WRAP
    ws.cell(1, 1).font = Font(name="Calibri", size=16, bold=True, color="1A5278")
    ws.column_dimensions["A"].width = 36
    ws.column_dimensions["B"].width = 80

    qh = [
        "ID",
        "Priorité",
        "Feuille canevas",
        "Sujet",
        "Question précise",
        "Éléments déjà établis (prérempli)",
        "Réponse de la Comptabilité",
        "Comptes ou rubriques concernés",
        "Formule ou méthode retenue",
        "Exemple chiffré",
        "Source documentaire",
        "Justification",
        "Nom du validateur",
        "Date de validation",
        "Statut",
    ]

    def qsheet(title, rows):
        w = wb.create_sheet(title)
        w.append(qh)
        style_header(w, len(qh))
        dv = DataValidation(type="list", formula1='"À compléter,À arbitrer,Validé,Rejeté"', allow_blank=True)
        w.add_data_validation(dv)
        dv.add(f"O2:O{max(2, len(rows)+1)}")
        for i, r in enumerate(rows, 1):
            write_row(w, i + 1, r, FILL_VAL)
        autosize(w, [10, 10, 18, 28, 50, 42, 28, 24, 24, 18, 20, 20, 16, 14, 14])
        return w

    qsheet(
        "01_DECISIONS_PRIORITAIRES",
        [
            ["Q-D01", "P0", "ETAT A", "Mapping officiel", "La matrice à implémenter est-elle la SCD 242 EXACT, l'analyse T1 (préfixes, 115 cellules), ou un mix visé ?", "SCD 242 A_VALIDER, 0 ACTIVE, 43 codes ; T1 parle de 115. Fichier Matrice_SM_cellule_regle_source.xlsx MANQUANT.", "", "", "", "", "", "", "", "", "À arbitrer"],
            ["Q-D15", "P0", "ETAT A", "DEB / CRE", "Dans la BAL DET, DEB et CRE sont-ils des mouvements de la période ou des soldes ? Comment calculer SD/SC ?", "SCD : SD=D−C, SC=C−D, D=débit brut, C=crédit brut. 72 SD, 134 SC, 17 D, 19 C.", "", "", "", "", "", "", "", "", "À arbitrer"],
            ["Q-D16", "P0", "ETAT A", "Résidence MRU", "Comment ventiler Ouguiyas résidents (D) vs non-résidents (E) alors que la DET n'a pas la résidence ?", "SCD colonne « UM Rés. » sur 206 lignes — proposition, pas visa. 210100 cité comme non-résident resté en D107 (T1).", "", "", "", "", "", "", "", "", "À arbitrer"],
            ["Q-D17", "P0", "ETAT A", "Résidence devises", "Même question pour F vs G. Les 9 lignes SCD « Dev. Non Rés. » (ex. 109, 110, 512) sont-elles exhaustives ?", "9 lignes SCD Dev. Non Rés. ; 11 « Selon auxiliaire ».", "", "", "", "", "", "", "", "", "À arbitrer"],
            ["Q-D02", "P0", "ETAT A D38", "Écart de balance", "Où imputer ΣDEB−ΣCRE classes 1–8 ? Cellule, signe, activation ?", "Octobre : 2 873 223 (cl. 1–8 T1) vs 2 873 218 dans la formule D38 (toutes classes −5). Compensation actuelle dans COD.", "", "", "", "", "", "", "", "", "À arbitrer"],
            ["Q-D06", "P0", "ETAT A", "67 sans règle", "Confirmer la liste onglet 04 et le traitement d'un compte non mappé non nul.", "Liste T1 30+25+12. Jamais 0 auto.", "", "", "", "", "", "", "", "", "À arbitrer"],
            ["Q-D09", "P0", "ETAT B / C", "Source B et C", "Fichier crédits/dépôts/échéances obligatoire, ou 30/70 % + copies ETAT A visés ?", "E46/E48/E49 = 30 % ; D46/D48/D49 = 70 %. Beaucoup de copies ETAT A.", "", "", "", "", "", "", "", "", "À arbitrer"],
            ["Q-D04", "P0", "ETAT A", "8 paramètres", "Source mensuelle de chaque paramètre ? Interdiction de reconduire juin/N-1 ?", "Voir 03_PARAMETRES_ET_LISTES. DAT 70 M et amort 3 910 448,68 reconduits de juin en octobre (audit).", "", "", "", "", "", "", "", "", "À arbitrer"],
            ["Q-DET", "P0", "Import", "DET vs COND", "Les règles écrites sur TOTDEB/TOTCRE COND s'appliquent-elles à DEB/CRE DET (55 192 lignes, 228 NCG) ?", "T3 : DET source unique. SCD s'appuie sur onglet BAL (grain NCG).", "", "", "", "", "", "", "", "", "À arbitrer"],
        ],
    )

    map_rows = []
    for i, r in enumerate(jsonl, 1):
        map_rows.append(
            [
                r.get("source_id") or f"M{i}",
                "P0",
                "ETAT A",
                f"BCM {str(r.get('cell_ref','')).replace('BCM:','')} / {r.get('compte_or_prefix')}",
                "Activer ? Corriger la base ou le sens ? Colonne résidence/devise ?",
                f"Base {r.get('amount_basis')} sens {r.get('sign_multiplier')} — {r.get('notes')}",
                "",
                r.get("compte_or_prefix"),
                "",
                "",
                "Correspondance SCD",
                "",
                "",
                "",
                "À arbitrer",
            ]
        )
    qsheet("02_MAPPING_242", map_rows)

    qsheet(
        "03_PARAMETRES_ET_LISTES",
        [
            [p[0], "P0", "ETAT A", p[1], f"Source du mois pour {p[1]} ? Cellules {p[2]} ?", f"Octobre (illustration) : {p[4]} — {p[3]}", "", "", "", p[4], "", "", "", "", "À compléter"]
            for p in PARAMS
        ]
        + [
            ["listes_D05", "P0", "ETAT A", "Listes publics / projets", "Fournir la liste RV des comptes publics et la liste projets (Tekavoul, UNHCR…).", "D05 ouvert. Sans liste, 322/323/403 restent manuels.", "", "", "", "", "", "", "", "", "À compléter"],
            ["INFO", "P1", "informations à fournir", "Annexes FPN", "Pour C6–C8 et C10–C20 : vrai zéro, non applicable, ou montant à justificatif ?", "C9 = ETAT A!D146 (formule confirmée fichier).", "", "", "", "", "", "", "", "", "À compléter"],
        ],
    )
    qsheet(
        "04_ETAT_B_ET_C",
        [
            ["B-30", "P0", "ETAT B", "30/70 % COD / immobilisées / douteuses", "Visa forfait 30 % privé (E46/E48/E49) ou ventilation réelle ?", "Formules lues dans le canevas. Badge provisoire D09.", "", "", "", "", "", "", "", "", "À arbitrer"],
            ["B-copies", "P0", "ETAT B", "Copies ETAT A", "Les liens 'ETAT A'!Dx sont-ils la vérité B ou un pis-aller d'octobre ?", "Nombreuses copies CONFIRMÉ FICHIER.", "", "", "", "", "", "", "", "", "À arbitrer"],
            ["C-matu", "P0", "ETAT C", "Maturités", "Quelle source pour <3 mois / 3 mois–2 ans / >2 ans ?", "DET sans échéance. D09.", "", "", "", "", "", "", "", "", "À arbitrer"],
            ["C-209", "P1", "ETAT C", "Double comptage total ressources", "C50 additionne C35 (208) et C36 (209) alors que C35=C36. Confirmer l'alerte sans modifier le xlsx BCM ?", "Formule lue : C50=+C40+C39+C38+C35+C36+C31+C28.", "", "", "", "", "", "", "", "", "À arbitrer"],
        ],
    )
    qsheet(
        "05_AXES_RESIDENCE",
        [
            ["AX-D", "P0", "ETAT A col. D", "UM résidents", "Tout solde MRU sans marqueur non-résident va-t-il en D ?", "SCD : 206 × « UM Rés. ».", "", "", "", "", "", "", "", "", "À arbitrer"],
            ["AX-E", "P0", "ETAT A col. E", "UM non-résidents", "Quels comptes (ex. 210100) ?", "T1 : 210100 resté dans D107 en octobre.", "", "", "", "", "", "", "", "", "À arbitrer"],
            ["AX-F", "P0", "ETAT A col. F", "Devises résidents", "Filtre DEVISE≠MRU et résidence résident ?", "Caisse devises F9 = paramètre (20 254,50).", "", "", "", "", "", "", "", "", "À arbitrer"],
            ["AX-G", "P0", "ETAT A col. G", "Devises non-résidents", "Les 9 lignes SCD suffisent-elles (109, 110, 512…) ?", "SCD « Dev. Non Rés. » = 9.", "", "", "", "", "", "", "", "", "À arbitrer"],
            ["AX-C", "P1", "ETAT A col. C", "Provisions", "Comptes 29x / 35x / 48x vers C uniquement ?", "4 lignes SCD « Provisions ».", "", "", "", "", "", "", "", "", "À arbitrer"],
        ],
    )

    d06_rows = []
    # Les 67 codes sont dans la matrice ; ici on pose une question par bloc.
    d06_rows.append(["D06-ACTIF", "P0", "ETAT A", "30 codes actif sans SCD", "Confirmer la liste 103,106,111,114,115,118,119,121,122,123,130,202,204,205,207,210,212,213,214,220,221,223,226,229,230,231,232,237,238,239. Traitement si solde non mappé ?", "Liste Analyse_metier_SM_matrice.docx table 4. Jamais 0 auto.", "", "", "", "", "", "", "", "", "À arbitrer"])
    d06_rows.append(["D06-PASSIF", "P0", "ETAT A", "25 codes passif sans SCD", "Confirmer 301,305,309,314,316,318,319,324,329,330,336,401,404,407,409,410,411,412,413,415,416,417,419,421,424 ?", "Table 4 analyse T1.", "", "", "", "", "", "", "", "", "À arbitrer"])
    d06_rows.append(["D06-HB", "P0", "ETAT A", "12 codes hors-bilan sans SCD", "Confirmer 502,503,504,505,507,508,510,513,515,517,518,519 ?", "Table 4 analyse T1.", "", "", "", "", "", "", "", "", "À arbitrer"])
    d06_rows.append(["D06-CONDUITE", "P0", "Import DET", "Compte non mappé non nul", "Bloquer l'import, créer une règle, ou affecter à un code existant ?", "Moteur actuel : ne met pas à zéro. Mapping 0 ACTIVE.", "", "", "", "", "", "", "", "", "À arbitrer"])
    qsheet("06_NON_MAPPEES_D06", d06_rows)

    d22_rows = []
    by_cpt = defaultdict(list)
    for x in corr:
        by_cpt[x["compte"]].append(x)
    for i, (cpt, lignes) in enumerate(sorted(by_cpt.items()), 1):
        if len(lignes) < 2:
            continue
        codes = " / ".join(f"{x['code_bcm']} ({x['base']} {x['sens']}, {x['colonne_sm']})" for x in lignes)
        d22_rows.append([f"D22-{cpt}", "P1", "ETAT A", cpt, "Double ligne légitime (débit vs crédit) ou une seule cellule à retenir ?", codes, "", cpt, "", "", "SCD", "", "", "", "À arbitrer"])
    qsheet("07_CONFLITS_D22", d22_rows)

    syn = wb.create_sheet("08_SYNTHESE_OUVERTES")
    syn.append(["Priorité", "Feuille", "Nb questions type", "Bloque le moteur si non visé", "Commentaire"])
    style_header(syn, 5)
    recap = [
        ("P0", "ETAT A", "D01+D15+D16/D17+D02+D06+D04+DET", "OUI", "Sans ces visas, le moteur ne peut pas remplir ETAT A depuis la DET"),
        ("P0", "ETAT B / C", "D09 + 30/70 %", "OUI pour B/C complets", "Copies A→B/C possibles ; ventilation réelle non"),
        ("P1", "FPN / ratios / INFO", "D13 D21 D10", "Partiel", "Formules aval OK si A (et saisies INFO) sont là"),
        ("P1", "Mapping fin", "D22 D08 D03", "Qualité", "Conflits et résultat / change"),
    ]
    for i, r in enumerate(recap, 1):
        write_row(syn, i + 1, list(r), FILL_VAL if r[3].startswith("OUI") else FILL_DED)
    autosize(syn, [10, 16, 40, 28, 56])
    return wb


def set_run_font(run, size=11, bold=False, color=None):
    run.font.name = "Calibri"
    run.font.size = Pt(size)
    run.bold = bold
    if color:
        run.font.color.rgb = RGBColor(*color)


def add_h(doc, text, level=1):
    p = doc.add_heading(text, level=level)
    return p


def add_p(doc, text):
    p = doc.add_paragraph(text)
    p.paragraph_format.space_after = Pt(8)
    for r in p.runs:
        r.font.name = "Calibri"
        r.font.size = Pt(11)
    return p


def add_tbl(doc, rows):
    t = doc.add_table(rows=len(rows), cols=len(rows[0]))
    t.style = "Table Grid"
    for i, row in enumerate(rows):
        for j, v in enumerate(row):
            cell = t.rows[i].cells[j]
            cell.text = str(v)
            for p in cell.paragraphs:
                for r in p.runs:
                    r.font.size = Pt(9)
                    r.font.name = "Calibri"
                    r.bold = i == 0
    doc.add_paragraph("")
    return t


def build_docx(stats, sources_note) -> Document:
    doc = Document()
    sec = doc.sections[0]
    sec.top_margin = Cm(1.8)
    sec.bottom_margin = Cm(1.8)
    sec.left_margin = Cm(2)
    sec.right_margin = Cm(2)

    t = doc.add_paragraph()
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = t.add_run("BANQUE EL AMANA — BEA DIGITAL")
    set_run_font(r, 12, True, (26, 82, 120))
    t2 = doc.add_paragraph()
    t2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = t2.add_run("Dossier des règles métier\nSituation Mensuelle BCM")
    set_run_font(r, 18, True, (26, 82, 120))
    add_p(doc, f"Version de travail du {date.today().isoformat()} — à viser par la Comptabilité. Aucune règle n'est activée dans le système tant qu'elle n'est pas validée ici.")
    add_p(doc, "Public : comptables. Ce document n'explique pas le code informatique. Il explique d'où doit venir chaque montant du canevas officiel BEA-SM-10-2026.xlsx.")

    add_h(doc, "1. Ce que l'on cherche à produire chaque mois", 1)
    add_p(doc, "La Situation Mensuelle (SM) est le classeur réglementaire à déclarer à la Banque Centrale de Mauritanie. Il a huit feuilles. L'objectif opérationnel est : créer la SM du mois, importer la BAL DET de ce mois, contrôler, puis remplir ce classeur — pas un export technique interne.")
    add_p(doc, "La BAL DET (NCG, compte, libellé, devise, débit, crédit) est la source comptable unique retenue dans BEA DIGITAL. Elle ne contient pas la résidence, ni le secteur (EPA/EPC/privé), ni l'échéance. Donc elle ne peut pas, à elle seule, remplir tout le classeur.")

    add_h(doc, "2. Rôle de chaque feuille", 1)
    add_tbl(
        doc,
        [
            ["Feuille", "Rôle", "D'où ça vient"],
            ["informations à fournir", "Annexes fonds propres (créances radiées, bénéfice hors dividendes, actions propres…)", "Saisie mensuelle, sauf C9 = bénéfice ETAT A"],
            ["ETAT A", "Cœur : 157 codes BCM, 5 axes (provisions, MRU rés./non-rés., devises rés./non-rés.) + total", "DET + mapping + paramètres + décisions résidence"],
            ["ETAT B", "Concours à l'économie par contrepartie (EPA, EPC, privé, particuliers, non-résidents)", "Surtout copies ETAT A + 30/70 % (D09) ou fichier crédits"],
            ["ETAT C", "Emplois / ressources / engagements par maturité", "Copies A/B + ventilation échéance (D09)"],
            ["CALCUL FPN", "Fonds propres nets", "Liens ETAT A + annexes « informations à fournir »"],
            ["RATIO COUVERTURE DE RISQUE", "Pondérations crédits / FP", "Liens ETAT A + saisies contre-garanties / quotités"],
            ["RATIO DE LIQUIDITE", "Actifs liquides / exigibilités", "Liens ETAT A + quelques saisies (marge BCM, etc.)"],
            ["RATIO FP ET AI", "Fonds propres / immobilisations", "Liens FPN et ETAT A"],
        ],
    )
    add_p(doc, "Point essentiel : ETAT A n'écrit pas B, C, FPN et les ratios. Le canevas contient déjà les formules de lien (SUM, copies 'ETAT A'!…). Ces formules ne donnent un bon résultat que si les cellules de base d'ETAT A (et les saisies) sont justes. Une formule IF qui affiche VRAI alors que tout est vide n'est pas une validation.")

    add_h(doc, "3. Parcours métier cible", 1)
    add_p(doc, "1) Créer la SM (mois, banque, libellé). 2) Importer et confirmer la BAL DET. 3) Contrôles A (fichier) — caisse devises à confirmer. 4) Saisir les 8 paramètres du mois (jamais recopier N-1). 5) Disposer d'un mapping visé (D01) et d'une convention résidence (D16/D17). 6) Générer le canevas : le moteur écrit les feuilles de détail d'ETAT A ; Excel calcule les totaux et les feuilles aval. 7) B et C complets seulement si la source D09 est tranchée. 8) Saisir les annexes FPN encore vides. 9) Contrôler I147 (passif − actif) et les IF de concordance.")

    add_h(doc, "4. Comment lire un montant — bases D, C, SD, SC", 1)
    add_p(doc, "La feuille Correspondance définit, et c'est confirmé fichier :")
    add_tbl(
        doc,
        [
            ["Base", "Définition dans la SCD", "À confirmer (D15)"],
            ["D", "Mouvement débit brut", "Mouvement de période ou somme de soldes débiteurs ?"],
            ["C", "Mouvement crédit brut", "Idem côté crédit"],
            ["SD", "Solde débiteur (D − C)", "Si D < C, SD est-il 0 ou négatif ?"],
            ["SC", "Solde créditeur (C − D)", "Symétrique"],
        ],
    )
    add_p(doc, "Dans la SCD actuelle : 72 règles SD, 134 SC, 17 D, 19 C. Tant que D15 n'est pas visé, ces bases restent des propositions. Sur la DET (55 192 lignes, 228 NCG), il faut aussi confirmer que l'on agrège au NCG (comme l'onglet BAL de la SCD) et non à chaque compte détaillé.")

    add_h(doc, "5. ETAT A — grandes rubriques", 1)
    add_p(doc, "157 codes BCM : 111 lignes de détail, 34 agrégats, 12 séparateurs « …… » (audit / analyse T1, recoupé canevas). Colonnes C à G = 5 axes ; H = SUM(D:G) sur le détail. I147 = H147 − H81 (contrôle équilibre).")
    add_p(doc, "Les agrégats (Caisse 101 = 102+103, Crédits clientèle 125 = 126 à 130, etc.) sont des formules Excel. Le moteur ne doit pas les écrire.")
    add_p(doc, "Aujourd'hui 242 lignes SCD, toutes « à valider », aucune active, 43 codes BCM seulement. Donc la majorité des lignes de détail n'ont pas de règle machine. L'analyse T1 liste 67 codes sans règle (onglet 04 de la matrice) : elles étaient nulles en octobre ; cela n'autorise pas à les mettre à zéro les mois suivants.")

    add_h(doc, "5.1 Exemples chiffrés d'octobre (illustration, pas règle permanente)", 2)
    add_p(doc, "Ces égalités reproduisent octobre 2026 selon l'analyse métier T1, principalement sur BAL COND. À retraduire sur DET après visa D15.")
    add_tbl(
        doc,
        [
            ["Cellule", "Idée de calcul (T1)", "Montant oct. 2026"],
            ["D9 (102)", "SD 100000 + SD 100100 − caisse_devises", "588 140 512,50"],
            ["F9 (102)", "Paramètre caisse_devises", "20 254,50"],
            ["D38 (131)", "D 21* − D 218* − C 211* − C 290000 − C 356000 − écart cl. 1-8", "2 523 670 062"],
            ["D106 (322)", "Paramètre publics_mru", "306 615 460,65"],
            ["D107 (323)", "C 210* − projets − publics − privés devises − personnel", "3 554 203 861,35"],
            ["D123 (403)", "C 32* / 120030 / 352* / SC 218xxx + projets", "760 183 987"],
            ["D146 (426)", "SC classes 6+7+8 + SC 358000 (position de change)", "213 337 465"],
        ],
    )
    add_p(doc, "D38 dans le canevas n'est pas cette règle : c'est une formule avec 2 873 218 tapé en dur. C'est précisément ce qu'il ne faut plus faire. L'écart de balance doit devenir une règle ECART visée (D02) ou une correction hors SM.")

    add_h(doc, "6. Ce qui ne peut pas venir de la BAL DET", 1)
    add_tbl(
        doc,
        [
            ["Information", "Pourquoi", "Conséquence"],
            ["Résidents / non-résidents", "Pas de champ résidence dans la DET", "Colonnes D/E et F/G : convention D16/D17 ou fichier auxiliaire"],
            ["EPA / EPC / privé / particuliers", "Pas de secteur", "ETAT B : D09"],
            ["Échéances <3 mois / 3 mois–2 ans / >2 ans", "Pas de maturité", "ETAT C : D09"],
            ["Liste publics / projets", "Choix extra-comptable", "Paramètres + D05"],
            ["DAT public, amortissement frais, cautions devises, caisse devises", "Détail ou tableau hors balance condensée", "8 paramètres mensuels"],
            ["Annexes FPN", "Hors balance", "Feuille informations à fournir"],
            ["Contre-garanties / quotités de pondération", "Hors balance", "Saisies RATIO COUVERTURE"],
        ],
    )

    add_h(doc, "7. ETAT B et ETAT C", 1)
    add_p(doc, "Beaucoup de cellules B et C d'octobre sont des copies d'ETAT A, plus trois formules 30 % (privé sur COD, immobilisées, douteuses) et leur complément 70 %. Ce n'est pas un fichier crédits. Tant que D09 n'est pas tranché, B et C restent provisoires même si A est parfait.")
    add_tbl(
        doc,
        [
            ["Cellule", "Formule lue dans le canevas", "Ce que ça fait"],
            ["ETAT B E46", "=+('ETAT A'!C38+'ETAT A'!D38)*30%", "30 % des COD (provisions C38 + UM résidents D38) vers le privé"],
            ["ETAT B D46", "=+('ETAT A'!C38+'ETAT A'!D38)-E46", "Le reste 70 %"],
            ["ETAT B E48 / E49", "D40*30 % et D41*30 %", "Même clé sur créances immobilisées et douteuses"],
            ["ETAT C E36", "=+'ETAT A'!H110", "Comptes à terme (209) : tout le total A est mis en maturité > 2 ans"],
            ["ETAT C C35", "=+C36", "Code 208 = copie de 209"],
            ["ETAT C C50 (220)", "=+C40+C39+C38+C35+C36+C31+C28", "TOTAL ressources : 208 et 209 sont tous les deux additionnés"],
        ],
    )
    add_p(doc, "Double comptage confirmé dans le fichier : la ligne 35 (code 208) copie la ligne 36 (code 209), et le TOTAL ligne 50 les additionne toutes les deux. Consigne : ne pas modifier le canevas BCM ; alerter dans le dossier de contrôle (porte D10).")

    add_h(doc, "8. FPN et ratios", 1)
    add_p(doc, "CALCUL FPN : FPB (A) = capital H143 + primes H141 + (réserves H142 − réserve de réévaluation saisie C13) + RAN D144+D145 + bénéfice INFO C9 + instruments C14. Déductions (C) = capital non libéré, RAN débiteur, pertes, provisions BCM, actions propres, incorporels, participations, apparentés, etc. FPB nets D = A+B−C. FPC nets G = max(E−F, 0). FPN H = D+G (cellule C39), utilisée par les trois ratios.")
    add_p(doc, "RATIO COUVERTURE : D = copie ETAT A (totaux H) ; E = contre-garanties (saisie, 0 d'octobre non reconduit) ; F = D−E ; G = quotité (1 sur crédits, 0,33 acceptations / crédits documentaires, 0,25 autres engagements) ; H = G×F. Total pondéré H26. Ratio H28 = FPN / H26. Norme 10 % (H29). Plafond H31 = FPN×10.")
    add_p(doc, "Anomalie du canevas : RCR D14 et D15 pointent vers informations à fournir!B7 et B8 (colonne des codes, vide) au lieu de C7 et C8 (montants). Même si la Comptabilité saisit les annexes, le ratio lit 0. À viser : corriger le lien ou confirmer B7/B8.")
    add_p(doc, "RATIO LIQUIDITÉ : numérateur D6 = caisse H8 + institut H11 + BT H57 + chèques H42 + effets H44 + marge saisie + position prêteuse C48. Dénominateur D14 = exigibilités CT (dont COD H105, livrets H116/2, etc.). Ratio C26 = D6/D14. Norme 20 %. La position interbancaire nette (annexe W−X) alimente le numérateur si prêteuse, le dénominateur si emprunteuse.")
    add_p(doc, "RATIO FP/AI : J = FPN / (titres retenus + immo corporelles + encours + créances douteuses nettes) × 100. Norme ≥ 100. Titres déduits = actions propres INFO C12.")

    add_h(doc, "9. 242 correspondances, 115 règles, 67 vides — ne pas les confondre", 1)
    add_p(doc, "La feuille Correspondance SCD contient 242 lignes compte exact → code BCM (43 codes). C'est ce qui est chargé dans BEA DIGITAL en « à valider ».")
    add_p(doc, "L'analyse métier T1 parle de 115 règles (souvent des préfixes 21*, 32*…) et d'un classeur compagnon Matrice_SM_cellule_regle_source.xlsx, qui n'a été trouvé ni dans le dépôt ni dans Téléchargements. 115 n'est pas 242. La Comptabilité doit dire quelle matrice est officielle.")
    add_p(doc, "Les 67 codes sans règle (liste dans la matrice Excel, onglet 04) restent dans le canevas. Traitement : jamais zéro automatique. Si un compte non mappé a un solde, bloquer et faire choisir la rubrique.")

    add_h(doc, "10. Conflits de comptes (D22)", 1)
    add_p(doc, "Plusieurs comptes SCD alimentent deux codes BCM (ex. 120000 → 109 et 304 ; 218000 → 206 et 335). Ce n'est pas toujours une erreur : souvent débit d'un côté, crédit de l'autre. Un contrôle naïf « un compte = une cellule » casserait octobre. Il faut viser chaque cas.")

    add_h(doc, "11. Décisions que la Comptabilité doit prendre", 1)
    add_p(doc, "Sans ces visas, le système peut contrôler la DET mais ne doit pas remplir la SM officielle.")
    add_tbl(
        doc,
        [
            ["N°", "Décision", "Pourquoi c'est bloquant"],
            ["D01", "Mapping officiel (242 et/ou 115) à activer", "Sinon 0 cellule auto depuis la DET"],
            ["D15", "Sens de DEB/CRE / TOTDEB/TOTCRE", "Sinon les bases D/C/SD/SC sont ambiguës"],
            ["D16/D17", "Résidence", "Sinon colonnes D–G d'ETAT A fausses, donc H et tous les ratios"],
            ["D02", "Écart de balance", "Sinon D38 reste une constante d'octobre"],
            ["D06", "67 codes + comptes non mappés", "Sinon zéros silencieux ou trous"],
            ["D09", "Source B et C", "Sinon B/C forfaitaires ou vides"],
            ["D04/D05", "8 paramètres et listes", "Sinon caisse devises, publics, projets, DAT…"],
            ["D22", "Multi-cellules", "Sinon double comptage ou oubli"],
        ],
    )

    add_h(doc, "12. Comment vérifier un mois", 1)
    add_p(doc, "Après visa des règles : (a) totaux DET classes 1–8 vs contrôle A ; (b) pour 5 à 10 codes BCM, recalcul manuel NCG × base ; (c) H = D+E+F+G ; (d) I147 proche de 0 ; (e) copies B/C = cellules A visées ; (f) FPN C11 = bénéfice D146 ; (g) aucun 0 là où la source est manquante — la cellule doit rester « à renseigner ».")
    add_p(doc, "Les montants d'octobre cités dans ce dossier servent d'exemple de reproduction historique, pas de cible permanente.")

    add_h(doc, "13. Sources utilisées et manquantes", 1)
    add_p(doc, f"Canevas officiel SHA-256 {sources_note['sha']} (conforme à la copie de référence). Correspondance SCD, BAL DET et COND 31/10/2026, maquette RC, audit du 12/11/2026, cahiers des charges, analyse métier du 16/11/2026, documentation T2/T3 du dépôt.")
    add_p(doc, "Manquants : Matrice_SM_cellule_regle_source.xlsx ; BAL et SM de septembre ; fichier crédits/dépôts/échéances ; listes publics/projets ; circulaire BCM hors canevas.")

    add_h(doc, "14. Documents compagnons", 1)
    add_p(doc, "MATRICE_REGLES_METIER_SM.xlsx — onglet 01 toutes les cellules ; onglet 01b seulement données et calculs ; 02 les 242 règles ; 04 les 67 codes ; 05 les 14 conflits ; 11 les formules FPN et ratios.")
    add_p(doc, "QUESTIONNAIRE_VALIDATION_COMPTABILITE.xlsx — à remplir (réponse, comptes, formule, exemple, source, validateur, date, statut). Commencer par 01_DECISIONS_PRIORITAIRES.")

    add_p(doc, "Fin du dossier. Toute activation dans BEA DIGITAL suppose un statut « Validé » sur les questions P0 du questionnaire.")
    return doc


def main() -> int:
    if not CANVAS.exists() or not CORR.exists():
        print("BLOQUÉ : canevas ou correspondance introuvable dans Downloads", file=sys.stderr)
        return 2
    sha = sha256(CANVAS)
    if sha != OFFICIAL_SHA:
        print("AVERTISSEMENT SHA canevas", sha, "≠", OFFICIAL_SHA)

    print("Scan canevas…")
    cells, meta = scan_canvas()
    meta["sha"] = sha
    print("  cellules", len(cells), "formules", meta["formulas"])
    print("Correspondance + jsonl…")
    corr = load_correspondance()
    jsonl = load_jsonl()
    unmapped_67, analyse = load_analyse_doc()
    print("  SCD", len(corr), "jsonl", len(jsonl), "analyse rows", len(analyse), "d06", sum(len(v) for v in unmapped_67.values()))

    print("Matrice Excel…")
    wb, stats = build_matrix(cells, corr, jsonl, analyse, meta, unmapped_67)
    p_mat = OUT / "MATRICE_REGLES_METIER_SM.xlsx"
    wb.save(p_mat)
    print("  ", p_mat, "cells", stats["cells"])

    print("Questionnaire…")
    wq = build_questionnaire(stats, corr, jsonl)
    p_q = OUT / "QUESTIONNAIRE_VALIDATION_COMPTABILITE.xlsx"
    wq.save(p_q)
    print("  ", p_q)

    print("Dossier Word…")
    doc = build_docx(stats, meta)
    p_d = OUT / "DOSSIER_REGLES_METIER_SM.docx"
    doc.save(p_d)
    print("  ", p_d)

    print("\n=== STATS ===")
    print("cells", stats["cells"])
    print("confirme", stats["confirme"])
    print("deduit", stats["deduit"])
    print("avalider", stats["avalider"])
    print("jsonl", stats["jsonl"], "unmapped", stats["unmapped"], "d22", stats["d22"])
    print("formulas_scan", meta["formulas"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
