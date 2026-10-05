"""Non-régression sur « TABLEAU DE SUIVI EER 2026 v2.xlsx » (feuille FLUX).

SOURCE NON DISPONIBLE — À ANALYSER LORSQU'ELLE SERA FOURNIE. Test sauté tant que la variable
``EER_SUIVI_EXCEL`` ne pointe pas vers le fichier. Aucune donnée client n'est versionnée : le
test relit le fichier et compare la règle BEA-DIGITAL aux colonnes S / T calculées par Excel
(valeurs en cache), ligne par ligne puis par agence (B) et par profil (E).
"""

from __future__ import annotations

import os
from collections import Counter
from pathlib import Path

import pytest

from app.services.eer.conformite_historique import axe_depuis_cellule, classer_excel, taux

FICHIER = os.environ.get("EER_SUIVI_EXCEL")

pytestmark = pytest.mark.skipif(not FICHIER or not Path(FICHIER).is_file(),
                                reason="TABLEAU DE SUIVI EER 2026 v2.xlsx : source non disponible")

# Décalages depuis la colonne AGENCE (B) : E profil, M physique, N système, S / T codes Excel.
PROFIL, M, N, S, T = 3, 11, 12, 17, 18


def _lignes():
    openpyxl = pytest.importorskip("openpyxl")
    ws = openpyxl.load_workbook(FICHIER, data_only=True, read_only=True)["FLUX"]
    rangees = list(ws.iter_rows(values_only=True))
    for i, rangee in enumerate(rangees):
        if "AGENCE" in [str(v).strip().upper() if v else "" for v in rangee]:
            col = [str(v).strip().upper() if v else "" for v in rangee].index("AGENCE")
            break
    else:
        pytest.fail("En-tête AGENCE introuvable dans FLUX")
    for rangee in rangees[i + 1:]:
        cellules = list(rangee[col:col + T + 1]) + [None] * (T + 1)
        if any(v not in (None, "") for v in cellules[:N + 3]):
            yield cellules


def test_regle_bea_digital_identique_aux_colonnes_s_t_excel():
    lignes = list(_lignes())
    assert lignes
    par_agence, par_profil = Counter(), Counter()
    total_s = total_t = 0
    for c in lignes:
        r = classer_excel(axe_depuis_cellule(c[M]), axe_depuis_cellule(c[N]))
        if isinstance(c[S], (int, float)) and isinstance(c[T], (int, float)):
            assert (r.code_conforme, r.code_non_conforme) == (int(c[S]), int(c[T])), c[:1]
        total_s, total_t = total_s + r.code_conforme, total_t + r.code_non_conforme
        par_agence[(c[0], "S")] += r.code_conforme
        par_agence[(c[0], "T")] += r.code_non_conforme
        par_profil[(c[PROFIL], "S")] += r.code_conforme
        par_profil[(c[PROFIL], "T")] += r.code_non_conforme
    # Reproduction de SUMIFS(S|T, B=agence) et SUMIFS(S|T, E=profil) à partir des valeurs Excel.
    for cle, n in par_agence.items():
        attendu = sum(int(c[S if cle[1] == "S" else T] or 0) for c in lignes if c[0] == cle[0])
        assert n == attendu, cle
    for cle, n in par_profil.items():
        attendu = sum(int(c[S if cle[1] == "S" else T] or 0) for c in lignes if c[PROFIL] == cle[0])
        assert n == attendu, cle
    # Jeu de référence de l'analyse du fichier (112 lignes) : 9 conformes, 24 non conformes, 27,27 %.
    if len(lignes) == 112:
        assert (total_s, total_t, str(taux(total_s, total_t))) == (9, 24, "27.27")
