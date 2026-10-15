"""Cohérence des compléments provisoires de l'organigramme (ajouts suggérés 🟡)."""

import re
import unicodedata

from app.data.organigramme_bea_2024 import aplatir
from app.data.organigramme_bea_suggestions import SOURCE, aplatir_suggestions
from app.models.organisation import TYPES_ENTITE


def _cle(texte: str) -> str:
    sans_accents = unicodedata.normalize("NFD", texte).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", sans_accents.lower()).strip()


def test_suggestions_rattachees_a_l_officiel_sans_doublon():
    officiel = list(aplatir())
    suggestions = list(aplatir_suggestions())
    codes_officiels = {n["code"] for n in officiel}
    codes = [n["code"] for n in suggestions]

    assert SOURCE == "SUGGESTION_2026_10"
    assert len(codes) == len(set(codes))
    assert not set(codes) & codes_officiels
    assert all(len(c) <= 20 for c in codes)

    libelles_par_parent = {(n["parent_code"], _cle(n["libelle"])) for n in officiel}
    for n in suggestions:
        assert n["type_entite"] in TYPES_ENTITE
        assert n["parent_code"] in codes_officiels | set(codes)
        assert (n["parent_code"], _cle(n["libelle"])) not in libelles_par_parent
        libelles_par_parent.add((n["parent_code"], _cle(n["libelle"])))
        assert n["a_confirmer"] and n["note"]
        assert all(p["a_confirmer"] and p["note"] for p in n["postes"])
