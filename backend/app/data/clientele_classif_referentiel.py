"""Référentiels extraits des Excel LBC/FT BEA — proposition, pas validation.

Sources :
- Matrice des risques LBC FT BEA V1-7-5-25.xlsx (validée Abass N'gam, MAJ 2024-12-27)
- Risque LBC FT Client V4-2026.xlsx (fiche Scoring + Liste masquée + Pays Eng-FR)

Aucune valeur n'est une règle métier validée pour BEA DIGITAL.
Les divergences sont A_ARBITRER. Ne pas charger Liste!Pays / Liste!Nationalité.
Fichier généré par backend/scripts/extract_classif_lbc.py — ne pas éditer à la main.
"""
from __future__ import annotations

import json
from pathlib import Path

REFERENTIEL = json.loads(
    (Path(__file__).with_suffix(".json")).read_text(encoding="utf-8"))
