"""Scénarios de la simulation de classement (recalcul sur les lignes du moteur, sans base)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.clientele.scoring import POIDS_ECHELLE, niveau_depuis_score_cdc

_CHEMIN = Path(__file__).resolve().parents[1] / "scripts" / "simulation_classification.py"
_spec = importlib.util.spec_from_file_location("simulation_classification", _CHEMIN)
sim = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sim)

F, M, E = POIDS_ECHELLE["FAIBLE"], POIDS_ECHELLE["MOYEN"], POIDS_ECHELLE["ELEVE"]


def lg(critere, poids, *, contribue=True, divergence=False, niveau_v4=None, bloquant=False,
       statut="APPLICABLE", etat="EVALUE"):
    return SimpleNamespace(critere=critere, poids=poids, contribue_au_score=contribue, divergence=divergence,
                           niveau_v4=niveau_v4, blocking_propose=bloquant, statut_regle=statut, etat=etat)


BASE = [lg("RESIDENCE", F), lg("NATIONALITE", F), lg("LISTE_INTERDICTION", 0, contribue=False)]


def test_s0_ignore_la_liste_orion():
    niv, statut, score = sim._recalcul(BASE, "S0", ["OI"], ["OI"])
    assert (score, statut) == (2 * F, "EVALUE") and niv == niveau_depuis_score_cdc(2 * F, 2)


def test_s1_compte_la_liste_tous_comptes_et_s2_comptes_ouverts_seulement():
    assert sim._recalcul(BASE, "S1", ["OI"], [])[2] == 2 * F + E
    assert sim._recalcul(BASE, "S1", [], [])[2] == 2 * F
    assert sim._recalcul(BASE, "S2", ["OI"], [])[2] == 2 * F
    assert sim._recalcul(BASE, "S2", ["OI"], ["OI"])[2] == 2 * F + E


def test_s3_supprime_le_double_comptage_association_profil():
    lignes = [*BASE, lg("ASSOCIATION", E), lg("PROFIL", E)]
    assert sim._recalcul(lignes, "S0", [], [])[2] == 2 * F + 2 * E
    assert sim._recalcul(lignes, "S3", [], [])[2] == 2 * F + E
    seul = [*BASE, lg("ASSOCIATION", E), lg("PROFIL", M)]
    assert sim._recalcul(seul, "S3", [], [])[2] == 2 * F + E + M


def test_s4_secteur_en_conflit_au_niveau_de_la_fiche():
    lignes = [*BASE, lg("SECTEUR", E, divergence=True, niveau_v4="FAIBLE")]
    assert sim._recalcul(lignes, "S0", [], [])[2] == 3 * F + E - F
    assert sim._recalcul(lignes, "S4", [], [])[2] == 3 * F
    sans_conflit = [*BASE, lg("SECTEUR", E, divergence=False, niveau_v4="FAIBLE")]
    assert sim._recalcul(sans_conflit, "S4", [], [])[2] == 2 * F + E


def test_bloquant_conflit_et_non_classe():
    assert sim._recalcul([*BASE, lg("SECTEUR", E, bloquant=True)], "S0", [], [])[:2] == ("INTERDIT", "BLOQUANT")
    assert sim._recalcul([*BASE, lg("PAYS", 0, contribue=False, statut="A_ARBITRER")], "S0", [], [])[1] == "A_ARBITRER"
    assert sim._recalcul([lg("PPE", 0, contribue=False)], "S0", [], [])[:2] == (None, "NON_CLASSE")


@pytest.mark.parametrize("actuelle, niveau, statut, attendu", [
    (None, "MOYEN", "EVALUE", ("MOYEN", "ECRIT")),
    (("FAIBLE", "MOTEUR"), "MOYEN", "EVALUE", ("MOYEN", "ECRIT")),
    (("MOYEN", "MOTEUR"), "MOYEN", "EVALUE", ("MOYEN", "INCHANGE")),
    (("FAIBLE", "MANUEL"), "ELEVE", "EVALUE", ("FAIBLE", "MANUEL_PRESERVE")),
    (("FAIBLE", "MANUEL_SURCHARGE"), "INTERDIT", "BLOQUANT", ("FAIBLE", "MANUEL_PRESERVE")),
    (("ELEVE", "EXCEL"), "FAIBLE", "EVALUE", ("ELEVE", "FICHIER_PRESERVE")),
    (("ELEVE", "EXCEL_CONFORMITE"), "FAIBLE", "EVALUE", ("ELEVE", "FICHIER_PRESERVE")),
    (("ELEVE", "MOTEUR"), "FAIBLE", "A_ARBITRER", ("ELEVE", "NON_ADMISSIBLE")),
    (None, None, "NON_CLASSE", (None, "NON_ADMISSIBLE")),
])
def test_retenu_suit_ecrire_resultat_moteur(actuelle, niveau, statut, attendu):
    assert sim._retenu(actuelle, niveau, statut) == attendu
