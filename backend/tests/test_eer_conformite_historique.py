"""Référence Excel M/N → S/T et taux historique (Python pur, sans base).

[FORMULE EXCEL] S = IF(M="Conforme", IF(N="Conforme",1,0), 0) ; T = IF(M="Non conforme",1,IF(N="Non conforme",1,0)).
Taux = S / (S + T) : les non classés (S = T = 0) sont HORS du dénominateur.
"""

from __future__ import annotations

from decimal import Decimal
from itertools import product

import pytest

from app.services.eer.conformite_historique import (
    LIBELLE_EXCEL_PROFIL,
    Classement,
    axe_depuis_cellule,
    classer_bea,
    classer_excel,
    compter,
    expliquer_ecart,
    profil_technique,
    taux,
)

C, NC, INC = "CONFORME", "NON_CONFORME", "INCOMPLET"


@pytest.mark.parametrize(("physique", "systeme", "classement", "s", "t"), [
    (C, C, Classement.CONFORME, 1, 0),            # test 1
    (NC, C, Classement.NON_CONFORME, 0, 1),       # test 2
    (C, NC, Classement.NON_CONFORME, 0, 1),       # test 3
    (NC, NC, Classement.NON_CONFORME, 0, 1),      # test 4
    (None, None, Classement.NON_EVALUE, 0, 0),    # test 5
    (C, None, Classement.NON_EVALUE, 0, 0),       # test 6
    (None, C, Classement.NON_EVALUE, 0, 0),       # test 7
    # La formule T classe non conforme dès qu'une seule dimension l'est, même si l'autre est vide.
    (NC, None, Classement.NON_CONFORME, 0, 1),
    (None, NC, Classement.NON_CONFORME, 0, 1),
    # INCOMPLET (moteur BEA-DIGITAL) = cellule vide de l'Excel, jamais non conforme.
    (C, INC, Classement.NON_EVALUE, 0, 0),
    (INC, INC, Classement.NON_EVALUE, 0, 0),
])
def test_matrice_excel(physique, systeme, classement, s, t):
    r = classer_excel(physique, systeme)
    assert (r.classement, r.code_conforme, r.code_non_conforme) == (classement, s, t)


def test_s_et_t_jamais_a_un_ensemble_et_derives_des_deux_dimensions():
    for physique, systeme in product((C, NC, INC, None), repeat=2):
        r = classer_excel(physique, systeme)
        assert r.code_conforme + r.code_non_conforme <= 1
        assert (r.code_conforme == 1) == (physique == C and systeme == C)
        assert (r.code_non_conforme == 1) == (NC in (physique, systeme))


def test_cellules_excel_comme_l_operateur_egal():
    assert classer_excel(C, NC).cellule_m == "Conforme" and classer_excel(C, NC).cellule_n == "Non conforme"
    assert classer_excel(INC, None).cellule_m is None
    assert axe_depuis_cellule("Conforme") == C and axe_depuis_cellule("CONFORME") == C
    assert axe_depuis_cellule("non conforme") == NC
    assert axe_depuis_cellule("Conforme ") is None and axe_depuis_cellule(None) is None
    assert axe_depuis_cellule(1) is None


def test_taux_historique_hors_non_evalues():
    # Test 8 : 20 conformes, 30 non conformes, 50 non évalués → 40 %, pas 20 %.
    classements = [Classement.CONFORME] * 20 + [Classement.NON_CONFORME] * 30 + [Classement.NON_EVALUE] * 50
    k = compter(classements)
    assert (k.total, k.conformes, k.non_conformes, k.non_evalues) == (100, 20, 30, 50)
    assert k.taux == Decimal("40.00")
    # Jeu de référence de l'analyse Excel : 9 / (9 + 24) = 27,27 %.
    assert taux(9, 24) == Decimal("27.27")


def test_taux_sans_dossier_classe_non_calculable():
    # Test 9 : aucun dossier classé → None (l'Excel affichait #DIV/0!), jamais 0 %.
    assert taux(0, 0) is None
    assert compter([Classement.NON_EVALUE] * 5).taux is None
    assert compter([]).taux is None
    assert taux(0, 3) == Decimal("0.00")


def test_decision_bea_classee_sans_inventer():
    assert classer_bea(C) == Classement.CONFORME
    assert classer_bea(NC) == Classement.NON_CONFORME
    assert classer_bea(INC) == Classement.NON_EVALUE and classer_bea(None) == Classement.NON_EVALUE


def test_profil_excel_et_profil_technique_pp_pm():
    assert LIBELLE_EXCEL_PROFIL == {"PP": "Personne_Physique", "PM_PRIVEE": "Personne_Morale_Privée",
                                    "PM_PUBLIQUE": "Personne_Morale_Publique",
                                    "ASSOCIATION": "Personne_Morale_Association"}
    assert profil_technique("PP") == "PP"
    assert {profil_technique(c) for c in ("PM_PRIVEE", "PM_PUBLIQUE", "ASSOCIATION")} == {"PM"}
    # Colonne U : jamais dérivée d'autre chose que du profil (erreur historique U7:U39 non reproduite).
    assert profil_technique("Client Dupont") is None and profil_technique(None) is None


def test_explication_ecart_excel_bea():
    assert expliquer_ecart(physique=C, systeme=C, coherence=C, decision_globale=C) == []
    raisons = expliquer_ecart(physique=C, systeme=C, coherence=NC, decision_globale=NC)
    assert "Référence Excel : CONFORME ; décision BEA-DIGITAL : NON_CONFORME" in raisons[0]
    assert any("cohérence non conforme" in r for r in raisons)
    raisons = expliquer_ecart(physique=C, systeme=C, coherence=C, decision_globale=NC,
                              anomalies_bloquantes=["NIF erroné"])
    assert any("NIF erroné" in r for r in raisons)
    raisons = expliquer_ecart(physique=NC, systeme=C, coherence=C, decision_globale=None)
    assert any("complément reçu" in r for r in raisons)
