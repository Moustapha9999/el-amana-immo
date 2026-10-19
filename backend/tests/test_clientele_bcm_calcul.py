"""Calcul BCM (tableaux 1 et 4) : règles appliquées sur des lignes client, sans base de données."""

from __future__ import annotations

from datetime import date

import pytest

from app.data.clientele_bcm_regles import PAR_CODE, REGLES, valider_valeur
from app.services.clientele.bcm_calcul import (
    ClientBcm,
    DatesBcm,
    agreger,
    debut_fenetre_maj,
    exception,
    forme_client,
    risque_bcm,
    selection,
    statut_actif,
)

DATES = DatesBcm(debut=date(2026, 8, 1), fin=date(2026, 8, 31), fin_mois_precedent=date(2026, 7, 31),
                 fenetre_maj_debut=date(2021, 1, 1))
COUVERT = {"historique_classif_min": date(2020, 1, 1), "maj_min": date(2020, 1, 1)}
PP, PM = "PERSONNE PHYSIQUE", "SOCIETE COMMERCIALE"


def _regles(**surcharges) -> dict:
    out = {r["code"]: r["valeur"] for r in REGLES}
    out.update({k.replace("__", "."): v for k, v in surcharges.items()})
    return out


def _statuts(tout_confirme: bool = False) -> dict:
    return {r["code"]: "CONFIRMEE" if tout_confirme else r["statut"] for r in REGLES}


def _c(racine: str, entree: date | None, *, ouvert: bool = True, cat: str | None = PP, gel: str | None = "Actif",
       m1: str | None = "FAIBLE", fin: str | None = "FAIBLE", maj: date | None = None, profil: str | None = None):
    return ClientBcm(racine=racine, d_entree=entree, a_ouvert=ouvert, categorie=cat, profil=profil, gel=gel,
                     risque_m1=m1, risque_fin=fin, d_maj=maj)


def _agg(clients, regles=None, couverture=None, statuts=None):
    return agreger(clients, regles or _regles(), statuts or _statuts(), DATES, couverture or COUVERT)


def test_fenetre_cinq_ans_calendaire_et_glissante():
    assert debut_fenetre_maj(date(2026, 8, 31), {"type": "CALENDAIRE", "annees": 5}) == date(2021, 1, 1)
    assert debut_fenetre_maj(date(2026, 8, 31), {"type": "GLISSANTE", "annees": 5}) == date(2021, 9, 1)
    assert debut_fenetre_maj(date(2026, 1, 31), {"type": "CALENDAIRE", "annees": 3}) == date(2023, 1, 1)


def test_stock_eer_et_identite_t4():
    clients = [
        _c("000001", date(2010, 1, 5)),
        _c("000002", date(2026, 7, 31), cat=PM),
        _c("000003", date(2026, 8, 1)),
        _c("000004", date(2026, 8, 31), cat=PM),
        _c("000005", date(2026, 9, 1)),
        _c("000006", date(2015, 3, 1), ouvert=False, gel="Cloturé"),
    ]
    agg = _agg(clients)
    assert agg["t1a"]["stock_m1"]["total"]["valeur"] == 3
    assert agg["t1a"]["stock_m1"]["pp"]["valeur"] == 2 and agg["t1a"]["stock_m1"]["pm"]["valeur"] == 1
    assert agg["t1a"]["maj_mois"]["total"]["valeur"] == 2
    assert agg["t4"]["total"]["valeur"]["valeur"] == 5
    assert agg["t4"]["total"]["valeur"]["valeur"] == (agg["t1a"]["stock_m1"]["total"]["valeur"]
                                                     + agg["t1a"]["maj_mois"]["total"]["valeur"])
    assert agg["t1a"]["cible"]["total"]["valeur"] == 4


def test_compte_et_gel_restent_distincts():
    r = _regles()
    assert statut_actif(_c("1", date(2020, 1, 1), ouvert=True, gel="Actif"), r) == "ACTIF"
    assert statut_actif(_c("1", date(2020, 1, 1), ouvert=True, gel="Inactif"), r) == "INACTIF"
    assert statut_actif(_c("1", date(2020, 1, 1), ouvert=False, gel="Actif"), r) == "INACTIF"
    assert statut_actif(_c("1", date(2020, 1, 1), ouvert=True, gel=None), r) == "INDETERMINE"
    assert statut_actif(_c("1", date(2020, 1, 1), ouvert=True, gel="Cloturé"), r) == "INACTIF"


def test_gel_inconnu_rend_la_cible_non_calculable():
    agg = _agg([_c("000001", date(2020, 1, 1)), _c("000002", date(2020, 1, 1), gel=None)])
    cible = agg["t1a"]["cible"]["total"]
    assert cible["valeur"] is None and cible["calculable"] is False
    assert "gel" in cible["raison"]
    assert agg["exceptions"]["gel_indetermine"] == 1
    assert agg["t1a"]["stock_m1"]["total"]["valeur"] == 2


def test_changement_de_risque_selon_la_date():
    agg = _agg([_c("000001", date(2020, 1, 1), m1="FAIBLE", fin="ELEVE")])
    assert agg["t1b"]["stock_m1"]["faible"]["valeur"] == 1
    assert agg["t1b"]["stock_m1"]["eleve"]["valeur"] == 0
    assert agg["t4"]["eleve"]["valeur"]["valeur"] == 1
    assert agg["t4"]["faible"]["valeur"]["valeur"] == 0


def test_interdit_non_classe_invalide_hors_colonnes():
    clients = [
        _c("000001", date(2020, 1, 1), fin="INTERDIT"),
        _c("000002", date(2020, 1, 1), fin=None),
        _c("000003", date(2020, 1, 1), fin="BIZARRE"),
        _c("000004", date(2020, 1, 1), fin="MOYEN"),
    ]
    agg = _agg(clients)
    assert agg["t4"]["total"]["valeur"]["valeur"] == 4
    assert sum(agg["t4"][n]["valeur"]["valeur"] for n in ("eleve", "moyen", "faible")) == 1
    assert agg["exceptions"]["risque_fin"] == {"INTERDIT": 1, "NON_CLASSE": 1, "INVALIDE": 1}
    assert agg["t4"]["moyen"]["ratio"]["valeur"] == 25.0


def test_interdit_rattache_a_eleve_seulement_par_regle():
    r = _regles(interdit__rattachement="ELEVE")
    assert risque_bcm("INTERDIT", r) == "eleve"
    assert risque_bcm("INTERDIT", _regles()) == "INTERDIT"
    c = _c("000001", date(2020, 1, 1), fin="INTERDIT")
    agg = _agg([c], regles=r)
    assert agg["t4"]["eleve"]["valeur"]["valeur"] == 1
    assert c.risque_fin == "INTERDIT"
    assert "interdit.rattachement" in agg["t4"]["eleve"]["valeur"]["regles_a_valider"]


def test_historique_absent_rend_le_risque_non_calculable():
    cov = {"historique_classif_min": date(2026, 10, 10), "maj_min": None}
    agg = _agg([_c("000001", date(2020, 1, 1))], couverture=cov)
    assert agg["t1b"]["stock_m1"]["eleve"]["valeur"] is None
    assert agg["t1b"]["stock_m1"]["eleve"]["fiabilite"] == "HISTORIQUE_INDISPONIBLE"
    assert agg["t4"]["faible"]["valeur"]["valeur"] is None
    assert agg["t4"]["faible"]["ratio"]["valeur"] is None
    assert agg["t1b"]["stock_m1"]["total"]["valeur"] == 1
    assert agg["t4"]["total"]["valeur"]["valeur"] == 1
    assert agg["t1a"]["maj_5ans"]["total"]["valeur"] is None
    assert agg["couverture"]["classif_m1"] is False and agg["couverture"]["maj"] is False


def test_historique_couvrant_juillet_mais_pas_juin():
    cov = {"historique_classif_min": date(2026, 8, 15), "maj_min": date(2020, 1, 1)}
    agg = _agg([_c("000001", date(2020, 1, 1))], couverture=cov)
    assert agg["t1b"]["stock_m1"]["faible"]["valeur"] is None
    assert agg["t4"]["faible"]["valeur"]["valeur"] == 1


def test_forme_juridique_exceptions_jamais_affectees():
    r = _regles()
    assert forme_client(_c("1", None, cat=" personne  physique "), r) == "PP"
    assert forme_client(_c("1", None, cat=None), r) == "EXC_FORME_VIDE"
    assert forme_client(_c("1", None, cat="GROUPEMENT DE DROIT PRIVE"), r) == "EXC_FORME_NON_RATTACHEE"
    assert forme_client(_c("1", None, cat=None, profil="PM"), r) == "EXC_FORME_VIDE"
    assert forme_client(_c("1", None, cat=None, profil="PM"), _regles(forme__repli_profil=True)) == "PM"
    agg = _agg([_c("000001", date(2020, 1, 1), cat=None), _c("000002", date(2020, 1, 1),
                                                              cat="GROUPEMENT DE DROIT PRIVE")])
    a = agg["t1a"]["stock_m1"]
    assert (a["pp"]["valeur"], a["pm"]["valeur"], a["cj"]["valeur"], a["total"]["valeur"]) == (0, 0, 0, 2)
    assert agg["exceptions"]["forme"] == {"EXC_FORME_VIDE": 1, "EXC_FORME_NON_RATTACHEE": 1}


def test_maj_cinq_ans_compte_les_clients_avec_evenement():
    clients = [_c("000001", date(2010, 1, 1), maj=date(2023, 5, 2)), _c("000002", date(2010, 1, 1))]
    agg = _agg(clients)
    assert agg["t1a"]["maj_5ans"]["total"]["valeur"] == 1
    assert selection(clients, _regles(), DATES, "maj_5ans") == ["000001"]


def test_mois_sans_activite_zeros_justifies():
    agg = _agg([_c("000001", date(2010, 1, 1))])
    assert agg["t1a"]["maj_mois"]["total"]["valeur"] == 0
    assert agg["t1a"]["maj_mois"]["total"]["calculable"] is True
    vide = _agg([])
    assert vide["t4"]["total"]["valeur"]["valeur"] == 0
    assert vide["t4"]["eleve"]["ratio"]["valeur"] is None
    assert vide["t4"]["total"]["ratio"]["valeur"] is None


def test_doublons_et_selection_reproductible():
    clients = [_c("000002", date(2020, 1, 1), cat=PM), _c("000001", date(2020, 1, 1)),
               _c("000001", date(2020, 1, 1))]
    agg = _agg(clients)
    assert agg["exceptions"]["doublons"] == 1
    assert selection(clients, _regles(), DATES, "stock_m1", "pm") == ["000002"]
    assert exception(clients, _regles(), DATES, "t4_NON_CLASSE") == []


def test_statut_regles_a_valider_et_confirmees():
    clients = [_c("000001", date(2020, 1, 1))]
    agg = _agg(clients)
    assert agg["t1a"]["stock_m1"]["total"]["fiabilite"] == "CALCULE"
    assert agg["t1a"]["stock_m1"]["pp"]["fiabilite"] == "AVEC_RESERVE"
    assert "forme.correspondance" in agg["t1a"]["stock_m1"]["pp"]["regles_a_valider"]
    confirme = _agg(clients, statuts=_statuts(True))
    assert confirme["t1a"]["stock_m1"]["pp"]["fiabilite"] == "CALCULE"


def test_eer_module_controle_croise():
    clients = [_c("000001", date(2026, 8, 3)), _c("000002", date(2026, 8, 4))]
    cov = {**COUVERT, "eer_module_racines": ["000001", "000099"]}
    e = _agg(clients, couverture=cov)["exceptions"]["eer_module"]
    assert e == {"realises": 2, "hors_premier_compte": 1, "premier_compte_sans_dossier": 1}


def test_valider_valeur_des_regles():
    assert valider_valeur("interdit.rattachement", "ELEVE") == "ELEVE"
    with pytest.raises(ValueError):
        valider_valeur("interdit.rattachement", "FAIBLE")
    assert valider_valeur("maj.fenetre", {"type": "GLISSANTE", "annees": 5}) == {"type": "GLISSANTE", "annees": 5}
    with pytest.raises(ValueError):
        valider_valeur("maj.fenetre", {"type": "CALENDAIRE", "annees": 0})
    assert valider_valeur("actif.valeurs_gel", [" actif ", "Actif"]) == ["ACTIF"]
    corr = {"PP": ["Personne physique"], "PM": [], "CJ": ["GROUPEMENT DE DROIT PRIVE"]}
    assert valider_valeur("forme.correspondance", corr)["CJ"] == ["GROUPEMENT DE DROIT PRIVE"]
    with pytest.raises(ValueError):
        valider_valeur("forme.correspondance", {"PP": ["X"], "PM": ["X"], "CJ": []})
    with pytest.raises(ValueError):
        valider_valeur("stock.date_entree", "PREMIERE_EXTRACTION")
    assert set(PAR_CODE) == {r["code"] for r in REGLES}
