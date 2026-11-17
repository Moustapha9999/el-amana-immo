# -*- coding: utf-8 -*-
"""Copie du canevas SM : mêmes feuilles / cellules, texte d'explication à la place des montants."""
from __future__ import annotations

import re
import shutil
from collections import defaultdict
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill, PatternFill as PF
from openpyxl.utils import get_column_letter

DL = Path(r"C:\Users\sallm\Downloads")
OUT_DIR = Path(r"C:\Users\sallm\bea-digital\docs\comptabilite\reporting-bcm-sm")
CANVAS = DL / "BEA-SM-10-2026.xlsx"
CORR = DL / "Correspondance_BAL_SM_BEA_10-2026_1==SCD.xlsx"
DEST_NAME = "SM_EXPLICATIONS_POUR_COMPTABILITE.xlsx"

SHEETS = [
    "informations à fournir",
    "ETAT A",
    "ETAT B",
    "ETAT C",
    "CALCUL FPN",
    "RATIO COUVERTURE DE RISQUE",
    "RATIO DE LIQUIDITE",
    "RATIO FP ET AI",
]
AXE_A = {
    "C": "provisions / amortissements",
    "D": "ouguiyas, résidents",
    "E": "ouguiyas, non-résidents",
    "F": "devises, résidents",
    "G": "devises, non-résidents",
    "H": "total de la ligne",
}
AXE_B = {
    "C": "résidents EPA",
    "D": "résidents EPC",
    "E": "résidents privé",
    "F": "résidents particuliers",
    "G": "résidents divers",
    "H": "non-résidents",
    "I": "total",
    "L": "contrôle vs ETAT A",
}
AXE_C = {
    "C": "échéance < 3 mois",
    "D": "échéance 3 mois à 2 ans",
    "E": "échéance > 2 ans",
    "F": "total",
    "I": "contrôle vs ETAT A",
}
DATA_COLS = {
    "informations à fournir": set("C"),
    "ETAT A": set("CDEFGHI"),
    "ETAT B": set("CDEFGHIL"),
    "ETAT C": set("CDEFI"),
    "CALCUL FPN": set("C"),
    "RATIO COUVERTURE DE RISQUE": set("DEFGH"),
    "RATIO DE LIQUIDITE": set("CD"),
    "RATIO FP ET AI": set("C"),
}
MAX_ROW = {
    "informations à fournir": 20,
    "ETAT A": 181,
    "ETAT B": 55,
    "ETAT C": 53,
    "CALCUL FPN": 49,
    "RATIO COUVERTURE DE RISQUE": 35,
    "RATIO DE LIQUIDITE": 50,
    "RATIO FP ET AI": 18,
}

JAUNE = PatternFill("solid", fgColor="FFF3BF")  # à compléter
BLEU = PatternFill("solid", fgColor="D0E8FF")  # formule canevas
ORANGE = PatternFill("solid", fgColor="FFD8A8")  # constante octobre / piège
VERT = PatternFill("solid", fgColor="D3F9D8")  # contrôle
GRIS = PatternFill("solid", fgColor="F1F3F5")
WRAP = Alignment(wrap_text=True, vertical="center")
FONT = Font(name="Calibri", size=8)
CELL_RE = re.compile(r"(?:'([^']+)'!)?(\$?[A-Z]{1,3}\$?\d{1,4}(?::\$?[A-Z]{1,3}\$?\d{1,4})?)")
NUM_RE = re.compile(r"(?<![A-Z])(\d{5,})")


def ref_fr(sheet_hint: str, token: str) -> str:
    token = token.replace("$", "")
    if "!" in token:
        sh, ad = token.split("!", 1)
        sh = sh.strip("'")
        return f"{sh} {ad}"
    if sheet_hint:
        return f"{sheet_hint} {token}"
    return token


def fmt_num(n: int | str) -> str:
    return f"{int(n):,}".replace(",", " ")


def explain_formula(formula: str, sheet: str, addr: str) -> tuple[str, str]:
    """Texte court + couleur (bleu/orange/vert)."""
    raw = str(formula).strip()
    f = raw[1:] if raw.startswith("=") else raw
    f = f.replace("$", "")
    if f.startswith("+"):
        f = f[1:]
    fu = re.sub(r"\s+", "", f)

    if addr in ("C50", "D50", "E50") and sheet == "ETAT C":
        return (
            "TOTAL ressources = C40 + C39 + C38 + C35 + C36 + C31 + C28. "
            "ATTENTION : C35 (code 208) recopie déjà C36 (code 209), donc 209 est additionné deux fois. "
            "Ne pas changer le canevas BCM ; le noter comme alerte.",
            "orange",
        )
    if sheet == "RATIO COUVERTURE DE RISQUE" and addr in ("D14", "D15"):
        cible = "C7" if addr == "D14" else "C8"
        actuel = "B7" if addr == "D14" else "B8"
        return (
            f"Le canevas lit « informations à fournir » {actuel} (colonne du code, vide). "
            f"Le montant à prendre est {cible}. À corriger ou confirmer.",
            "orange",
        )

    lits = [int(x) for x in NUM_RE.findall(fu) if int(x) >= 1000]
    if lits and not fu.upper().startswith("SUM"):
        ops = explain_plain(f, sheet)
        return (
            "NOMBRE FIGÉ D'OCTOBRE — ce n'est pas la règle du moteur. "
            f"Aujourd'hui le canevas fait : {ops} "
            "Écrire ici les vrais comptes à additionner / retrancher.",
            "orange",
        )

    if fu.upper().startswith("IF("):
        kind = "vert"
        txt = explain_if(f, sheet)
        if "sinon 0" in txt.lower() or "alors" in txt.lower():
            kind = "bleu"
        return (txt, kind)

    return (explain_plain(f, sheet), "bleu")


def explain_if(f: str, sheet: str) -> str:
    inner = f.strip()
    if inner.upper().startswith("IF"):
        inner = inner[2:].lstrip()
    if inner.startswith("(") and inner.endswith(")"):
        inner = inner[1:-1]
    parts = split_args(inner)
    if len(parts) >= 3:
        cond, a, b = parts[0].strip(), parts[1].strip(), parts[2].strip()
        a_u, b_u = a.upper().replace(" ", ""), b.upper().replace(" ", "")
        if a_u in ("TRUE", "VRAI") and b_u in ("FALSE", "FAUX"):
            return (
                f"Contrôle : {explain_plain(cond, sheet).rstrip('.')} → VRAI, sinon FAUX. "
                "(Un VRAI avec des cases vides ne valide rien.)"
            )
        return (
            f"Si {clean_phrase(explain_plain(cond, sheet))} alors {clean_phrase(explain_plain(a, sheet))} "
            f"sinon {clean_phrase(explain_plain(b, sheet))}."
        )
    return f"Contrôle : {f}"


def split_args(s: str) -> list[str]:
    args, buf, depth = [], [], 0
    for ch in s:
        if ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            args.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if buf:
        args.append("".join(buf).strip())
    return args


def expand_sum_range(a: str, b: str) -> str:
    ma = re.match(r"([A-Z]+)(\d+)", a)
    mb = re.match(r"([A-Z]+)(\d+)", b)
    if not ma or not mb:
        return f"{a} à {b}"
    c1, r1 = ma.group(1), int(ma.group(2))
    c2, r2 = mb.group(1), int(mb.group(2))
    if c1 == c2 and r2 != r1:
        return " + ".join(f"{c1}{r}" for r in range(r1, r2 + 1)) if (r2 - r1) <= 8 else f"{c1}{r1} jusqu'à {c1}{r2}"
    if r1 == r2 and c1 != c2:
        cols = []
        for i in range(ord(c1), ord(c2) + 1):
            cols.append(f"{chr(i)}{r1}")
        return " + ".join(cols)
    return f"{a} jusqu'à {b}"


def explain_plain(f: str, sheet: str) -> str:
    s = f.strip()
    if s.startswith("+"):
        s = s[1:]
    su = re.sub(r"\s+", "", s).upper()

    mm = re.fullmatch(r"SUM\((.+)\)", su, re.I)
    if mm:
        inside = mm.group(1)
        bits = []
        for part in inside.split(","):
            part = part.strip()
            if ":" in part:
                a, b = part.split(":", 1)
                a = a.split("!")[-1]
                b = b.split("!")[-1]
                bits.append(expand_sum_range(a, b))
            else:
                bits.append(pretty_ref(part, sheet))
        return "Additionner " + " et ".join(bits) + "."

    if re.search(r"[A-Z]{1,3}\d+", s, re.I) or "!" in s or NUM_RE.search(s):
        return explain_arith(s, sheet)

    return f"Formule du canevas : {f}"


def pretty_ref(token: str, sheet: str) -> str:
    token = token.replace("$", "").strip().strip("()")
    if not token:
        return token
    if token.replace(" ", "").replace(".", "").isdigit() or re.fullmatch(r"\d+", token):
        return fmt_num(token)
    m = re.match(r"(?:'([^']+)'|([^'!]+))!([A-Z]+\d+(?::[A-Z]+\d+)?)$", token, re.I)
    if m:
        sh = (m.group(1) or m.group(2) or "").strip()
        return f"{sh} {m.group(3)}"
    if "!" in token:
        sh, ad = token.split("!", 1)
        return f"{sh.strip().strip(chr(39))} {ad}"
    return token


def clean_phrase(t: str) -> str:
    t = t.rstrip(".")
    for p in ("Reprendre ", "Prendre ", "Formule du canevas : "):
        if t.startswith(p):
            t = t[len(p) :]
    return t


def explain_arith(s: str, sheet: str) -> str:
    """Traduit + - * / en français, en gardant les cellules et les noms de feuilles."""
    s2 = s.strip()
    s_cmp = re.sub(r"\s+", "", s2)
    if "30%" in s_cmp:
        base = re.sub(r"\*?\s*30\s*%\s*$", "", s2, flags=re.I).strip()
        if base.startswith("(") and base.endswith(")"):
            base = base[1:-1]
        return f"30 % de ({clean_phrase(explain_arith(base, sheet))})."
    if s_cmp.endswith("/2"):
        left = s2[: s2.upper().rfind("/2")]
        return f"La moitié de {pretty_ref(left.replace(' ', ''), sheet) if '!' not in left else pretty_ref(left, sheet)} (50 %)."
    if s_cmp.endswith("*10"):
        left = s2[: s2.upper().rfind("*10")]
        return f"{pretty_ref(left, sheet)} × 10."
    if "*10/100" in s_cmp:
        left = s2.split("*")[0]
        return f"10 % de {pretty_ref(left, sheet)}."

    # comparaisons IF
    for op, mot in ((">=", "≥"), ("<=", "≤"), ("<>", "≠"), (">", ">"), ("<", "<"), ("=", "=")):
        if op in s2:
            left, right = s2.split(op, 1)
            return f"{clean_phrase(explain_arith(left, sheet))} {mot} {clean_phrase(explain_arith(right, sheet))}"

    pattern = re.compile(
        r"'[^']+'![A-Z]+\d+(?::[A-Z]+\d+)?"
        r"|[A-Za-zÀ-ÿ0-9 ]+![A-Z]+\d+(?::[A-Z]+\d+)?"
        r"|[A-Z]{1,3}\d+(?::[A-Z]{1,3}\d+)?"
        r"|\d+(?:\.\d+)?",
        re.I,
    )
    out = []
    last = 0
    for m in pattern.finditer(s2):
        gap = s2[last:m.start()]
        if gap.strip():
            out.append(("op", gap.replace(" ", "")))
        tok = m.group(0)
        if tok.replace(".", "").isdigit():
            out.append(("ref", fmt_num(int(float(tok))) if "." not in tok else tok))
        else:
            out.append(("ref", pretty_ref(tok, sheet)))
        last = m.end()
    tail = s2[last:]
    if tail.strip():
        out.append(("op", tail.replace(" ", "")))
    if not out:
        return s

    pieces = []
    pending_op = None
    for kind, val in out:
        if kind == "ref":
            if pending_op is None:
                pieces.append(val)
            elif pending_op == "+":
                pieces.append(f"plus {val}")
            elif pending_op == "-":
                pieces.append(f"moins {val}")
            elif pending_op == "*":
                pieces.append(f"× {val}")
            elif pending_op == "/":
                pieces.append(f"divisé par {val}")
            else:
                pieces.append(val)
            pending_op = None
        else:
            op = val.replace("(", "").replace(")", "")
            if op[:1] in "+-*/" and (len(op) == 1 or op.endswith("(")):
                pending_op = op[:1]
            elif op in "+-*/":
                pending_op = op
    if not pieces:
        return f"Calcul : {s}"
    if len(pieces) == 1:
        return f"Reprendre {pieces[0]}."
    return "Prendre " + pieces[0] + " " + " ".join(pieces[1:]) + "."


def as_code(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, str) and v.strip().isdigit():
        return f"{int(v.strip()):03d}"
    if isinstance(v, (int, float)) and float(v).is_integer() and 1 <= int(v) <= 999:
        return f"{int(v):03d}"
    return None


def load_scd() -> dict[str, list[str]]:
    """code BCM normalisé -> courtes lignes compte/base/colonne."""
    if not CORR.exists():
        return {}
    wb = load_workbook(CORR, data_only=True)
    ws = wb["Correspondance"]
    by: dict[str, list[str]] = defaultdict(list)
    for row in ws.iter_rows(min_row=5, values_only=True):
        if not row[1]:
            continue
        compte = str(row[1]).strip()
        base = row[5]
        col = row[10]
        bcm_raw = str(row[8]).strip() if row[8] is not None else ""
        codes = re.findall(r"\d{3}", bcm_raw)
        hint = f"{compte} ({base}"
        if col and str(col) not in ("None", "—"):
            hint += f", {col}"
        hint += ")"
        if not codes:
            continue
        for c in codes:
            if hint not in by[c]:
                by[c].append(hint)
    wb.close()
    return by


def axe_txt(sheet: str, col: str) -> str:
    if sheet == "ETAT A":
        return AXE_A.get(col, col)
    if sheet == "ETAT B":
        return AXE_B.get(col, col)
    if sheet == "ETAT C":
        return AXE_C.get(col, col)
    return col


def scd_hint(code: str, col: str, by_bcm: dict) -> str:
    items = by_bcm.get(str(int(code)) if code and code.isdigit() else "", []) or by_bcm.get(code, [])
    if not items:
        return ""
    col_map = {"C": "Provisions", "D": "UM Rés.", "G": "Dev. Non Rés."}
    want = col_map.get(col)
    if col in ("E", "F"):
        return ""
    if not want:
        return ""
    filtered = [x for x in items if want in x]
    if not filtered:
        return ""
    show = filtered[:6]
    more = f" … +{len(filtered) - 6} comptes" if len(filtered) > 6 else ""
    return "Piste (non validée) : " + ", ".join(show) + more + " — corriger si faux."


def apply_style(cell, kind: str):
    cell.font = FONT
    cell.alignment = WRAP
    if kind == "bleu":
        cell.fill = BLEU
    elif kind == "jaune":
        cell.fill = JAUNE
    elif kind == "orange":
        cell.fill = ORANGE
    elif kind == "vert":
        cell.fill = VERT
    else:
        cell.fill = GRIS


def main() -> None:
    dest = OUT_DIR / DEST_NAME
    shutil.copy2(CANVAS, dest)
    by_bcm = load_scd()
    wb = load_workbook(dest)

    for sheet in SHEETS:
        ws = wb[sheet]
        max_r = MAX_ROW[sheet]
        data_cols = DATA_COLS[sheet]
        # widen data columns
        for col in data_cols:
            letter = col
            ws.column_dimensions[letter].width = max(ws.column_dimensions[letter].width or 12, 36)
        ws.column_dimensions["A"].width = max(ws.column_dimensions["A"].width or 20, 42)

        for r in range(1, max_r + 1):
            lib = ws.cell(r, 1).value
            lib_s = str(lib).strip() if lib not in (None, "") else ""
            bcm = as_code(ws.cell(r, 2).value) if sheet in ("ETAT A", "ETAT B", "ETAT C") else None
            is_sep = "…" in lib_s
            filled = False
            for c in range(1, 13):
                col = get_column_letter(c)
                if col not in data_cols:
                    continue
                cell = ws.cell(r, c)
                val = cell.value
                is_f = isinstance(val, str) and val.startswith("=")
                empty = val in (None, "")
                # skip title rows 1-5 mostly if no formula and no bcm
                if r <= 5 and not is_f and empty:
                    continue
                if r <= 4 and not is_f:
                    continue

                if is_f:
                    txt, kind = explain_formula(val, sheet, cell.coordinate)
                    cell.value = txt
                    apply_style(cell, kind)
                    filled = True
                    continue

                if is_sep and col in "CDEFGHI":
                    cell.value = "Ligne de réserve du canevas — pas de montant."
                    apply_style(cell, "gris")
                    filled = True
                    continue

                if empty and not bcm and sheet not in ("informations à fournir", "CALCUL FPN", "RATIO COUVERTURE DE RISQUE", "RATIO DE LIQUIDITE", "RATIO FP ET AI"):
                    continue

                # valeurs numériques d'octobre ou vides à expliquer
                if col not in data_cols:
                    continue

                axe = axe_txt(sheet, col)
                if sheet == "ETAT A" and bcm and col in "CDEFG":
                    hint = scd_hint(bcm, col, by_bcm)
                    if hint:
                        cell.value = (
                            f"À COMPLÉTER. Rubrique {bcm} — {axe}. "
                            f"Le moteur met ici le montant issu de la BAL DET. {hint} "
                            f"Écrire : comptes à additionner / retrancher, et si on prend le débit, le crédit ou le solde."
                        )
                    else:
                        cell.value = (
                            f"À COMPLÉTER. Rubrique {bcm} ({lib_s}) — {axe}. "
                            f"Quels comptes BAL DET ? Additionner / retrancher ? Débit, crédit ou solde ? "
                            f"Si rien ne va ici, écrire « jamais de montant »."
                        )
                    apply_style(cell, "jaune")
                    filled = True
                elif sheet == "ETAT A" and col == "H":
                    cell.value = "Total = D + E + F + G de cette ligne (formule du canevas)."
                    apply_style(cell, "bleu")
                    filled = True
                elif sheet == "ETAT A" and col == "I":
                    if empty:
                        continue
                    cell.value = "Contrôle (voir formule d'origine si besoin)."
                    apply_style(cell, "vert")
                    filled = True
                elif sheet == "ETAT B" and bcm and col in "CDEFGH":
                    cell.value = (
                        f"À COMPLÉTER. ETAT B rubrique {bcm} — {axe}. "
                        f"Soit reprise d'une cellule ETAT A, soit ventilation crédits (EPA/EPC/privé…). "
                        f"Écrire : quelle cellule A, ou quels comptes, et l'opération."
                    )
                    apply_style(cell, "jaune")
                    filled = True
                elif sheet == "ETAT C" and bcm and col in "CDE":
                    cell.value = (
                        f"À COMPLÉTER. ETAT C rubrique {bcm} — {axe}. "
                        f"Soit copie ETAT A / ETAT B, soit ventilation par échéance. "
                        f"Écrire la cellule source et l'opération."
                    )
                    apply_style(cell, "jaune")
                    filled = True
                elif sheet == "informations à fournir" and col == "C" and r >= 6:
                    if r == 9:
                        continue  # formula already handled
                    cell.value = (
                        f"À COMPLÉTER. Annexe FPN : {lib_s}. "
                        f"Saisie mensuelle (pas la BAL DET). Si le montant est vraiment 0, l'écrire et justifier. Sinon laisser vide n'est pas un zéro."
                    )
                    apply_style(cell, "jaune")
                    filled = True
                elif sheet in ("RATIO COUVERTURE DE RISQUE", "RATIO DE LIQUIDITE", "RATIO FP ET AI", "CALCUL FPN"):
                    if empty:
                        continue
                    if isinstance(val, (int, float)) and val == 0:
                        cell.value = (
                            "0 dans le canevas d'octobre — pas une règle. "
                            "Saisie du mois (contre-garantie, marge, annexe…) ou vrai zéro à confirmer."
                        )
                        apply_style(cell, "jaune")
                        filled = True
                    elif isinstance(val, (int, float)):
                        cell.value = (
                            f"Valeur figée dans le canevas ({val}). "
                            f"Si c'est une norme (10 %, 20 %, quotité), confirmer. Sinon remplacer par la règle."
                        )
                        apply_style(cell, "orange")
                        filled = True

            if filled:
                ws.row_dimensions[r].height = max(ws.row_dimensions[r].height or 15, 48)

        ws.freeze_panes = "C6" if sheet in ("ETAT A", "ETAT B", "ETAT C") else "A5"
        ws.sheet_view.showGridLines = True

    # Feuille mode d'emploi en premier
    if "LIRE" in wb.sheetnames:
        del wb["LIRE"]
    ws0 = wb.create_sheet("LIRE", 0)
    ws0.sheet_view.showGridLines = False
    ws0.column_dimensions["A"].width = 110
    lines = [
        ("COMMENT REMPLIR CE CLASSEUR", True),
        ("C'est le canevas officiel SM (mêmes feuilles, mêmes cases). Les montants ont été remplacés par une explication.", False),
        ("Vous corrigez le texte DANS la cellule. Une phrase suffit.", False),
        ("", False),
        ("Couleurs", True),
        ("Bleu = formule déjà dans le canevas BCM (somme, copie d'une autre feuille, division). Le moteur ne réécrit pas ces cases : Excel les calcule.", False),
        ("Jaune = à vous de dire d'où vient le montant (comptes BAL DET, saisie, autre cellule).", False),
        ("Orange = piège : nombre d'octobre tapé en dur, ou formule trompeuse. Il faut la vraie règle, pas le chiffre d'octobre.", False),
        ("Vert = contrôle (VRAI / FAUX). Un VRAI avec des cases vides ne veut rien dire.", False),
        ("", False),
        ("Comment écrire une règle", True),
        ("Exemples utiles :", False),
        ("• Additionner les soldes débiteurs des comptes 100000 et 100100, puis retrancher la caisse devises (F9).", False),
        ("• Reprendre ETAT A H38.", False),
        ("• Additionner ETAT A C38 et ETAT A D38, puis prendre 30 %.", False),
        ("• Diviser CALCUL FPN C39 par RCR H26.", False),
        ("• Saisie du mois (pas la BAL). Si 0, écrire « vrai zéro ».", False),
        ("• Jamais de montant sur cette case.", False),
        ("", False),
        ("Ce que le moteur ne peut pas inventer tout seul", True),
        ("La BAL DET n'a pas la résidence, ni le secteur (EPA/privé), ni l'échéance. Les colonnes jaunes d'ETAT A (E, F, G), tout ETAT B et ETAT C jaunes, et les annexes FPN, c'est vous.", False),
        ("Ne recopiez pas les chiffres d'octobre. Dites les comptes et l'opération.", False),
        ("", False),
        ("Fichier source : BEA-SM-10-2026.xlsx (inchangé). Ce classeur est une copie de travail.", False),
    ]
    for i, (txt, bold) in enumerate(lines, 1):
        cell = ws0.cell(i, 1, txt)
        cell.font = Font(name="Calibri", size=14 if bold else 11, bold=bold, color="1A5278" if bold else "212529")
        cell.alignment = Alignment(wrap_text=True)
        ws0.row_dimensions[i].height = 22 if not bold else 26
    ws0.row_dimensions[2].height = 36
    ws0.row_dimensions[21].height = 48

    wb.save(dest)
    shutil.copy2(dest, DL / DEST_NAME)
    print("OK", dest)
    print("copie", DL / DEST_NAME)


if __name__ == "__main__":
    main()
