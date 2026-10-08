"""Libellés métier des sources de classification LBC/FT.

Les codes internes (MATRICE_V1, SCORING_V4, champs niveau_v4…) restent stables en base ;
seuls les textes affichés utilisent les noms métier.
"""
from __future__ import annotations

import re
from typing import Any

MATRICE = "Matrice des risques LBC/FT BEA"
FICHE = "Fiche de scoring"

SOURCES_LIBELLES: dict[str, str] = {
    "MATRICE_V1": MATRICE,
    "SCORING_V4": FICHE,
    "SCORING_V4_LISTE": f"{FICHE} (listes)",
    "SCORING_V4_PAYS_ENG_FR": f"{FICHE} (pays)",
    "PROPOSITION_BEA_DIGITAL": "Proposition BEA DIGITAL",
    "SOURCE_V1": f"Source : {MATRICE}",
    "SOURCE_V4": f"Source : {FICHE}",
}

_REMPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b[Dd]u V4\b"), f"de la {FICHE}"),
    (re.compile(r"\b[Aa]u V4\b"), f"à la {FICHE}"),
    (re.compile(r"\b[Ll]e V4\b"), f"la {FICHE}"),
    (re.compile(r"\b[Dd]u V1\b"), f"de la {MATRICE}"),
    (re.compile(r"\b[Ll]e V1\b"), f"la {MATRICE}"),
    (re.compile(r"\bV1\s*/\s*V4\b"), f"{MATRICE} / {FICHE}"),
    (re.compile(r"\b[Mm]atrice\s*(?:\(V1\)|V1)?(?![_\w])(?! des risques)"), MATRICE),
    (re.compile(r"(?<![_\w])V1\b"), MATRICE),
    (re.compile(r"(?<![_\w])v4(?==)"), FICHE),
    (re.compile(r"(?<![_\w])V4\b"), FICHE),
)


def libelle_sources(texte: str) -> str:
    for motif, remplacement in _REMPLACEMENTS:
        texte = motif.sub(remplacement, texte)
    return texte


def nommer(obj: Any) -> Any:
    """Applique les libellés métier à toutes les chaînes d'une réponse (clés inchangées)."""
    if isinstance(obj, str):
        return libelle_sources(obj)
    if isinstance(obj, dict):
        return {k: nommer(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [nommer(v) for v in obj]
    return obj
