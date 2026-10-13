"""Critère « Entreprise à ouverture récente » (décision 10/10/2026) et lecture des colonnes de lot."""
from __future__ import annotations

from datetime import date, datetime

from app.services.clientele.lots import lire_date, lire_ligne, resoudre_mapping
from app.services.clientele.scoring import INVALIDE, DonneesClient, evaluer, lire_oui_non

REF = date(2026, 10, 7)
PM = {"agent_economique": "AUTRES SOCIETES", "statut_resident": "R", "nationalite": "MAURITANIE"}


def _ligne(ev, code="ENTREPRISE_RECENTE"):
    return next(lg for lg in ev.lignes if lg.critere == code)


def _ev(**kw):
    return evaluer(DonneesClient(racine="000001", date_reference=REF, source_date_reference="TEST",
                                 **{**PM, **kw}))


def test_366_jours_recente_10000():
    ouverture = date(2025, 10, 6)
    assert (REF - ouverture).days == 366
    lg = _ligne(_ev(date_creation_pm=ouverture, source_date_creation="FICHIER"))
    assert lg.etat == "EVALUE" and lg.poids == 10_000 and lg.niveau_retenu == "MOYEN"
    assert lg.contribue_au_score and lg.statut_regle == "VALIDEE_METIER"


def test_367_jours_ancienne_100():
    ouverture = date(2025, 10, 5)
    assert (REF - ouverture).days == 367
    lg = _ligne(_ev(date_creation_pm=ouverture, source_date_creation="FICHIER"))
    assert lg.poids == 100 and lg.niveau_retenu == "FAIBLE" and lg.contribue_au_score


def test_date_de_reference_et_non_date_du_jour():
    ev = _ev(date_creation_pm=date(2025, 10, 6), source_date_creation="FICHIER")
    assert ev.date_reference == REF.isoformat() and ev.source_date_reference == "TEST"
    tard = evaluer(DonneesClient(racine="000001", date_reference=date(2026, 10, 8), **PM,
                                 date_creation_pm=date(2025, 10, 6)))
    assert _ligne(tard).poids == 100


def test_interaction_score_cumulatif():
    """Résident (100) + mauritanienne (100) + entreprise récente (10 000) = 10 200 → MOYEN."""
    ev = _ev(date_creation_pm=date(2026, 1, 1))
    assert ev.score_total == 10_200 and ev.niveau_final == "MOYEN" and ev.statut == "EVALUE"
    ancienne = _ev(date_creation_pm=date(2020, 1, 1))
    assert ancienne.score_total == 300 and ancienne.niveau_final == "FAIBLE"


def test_declaratif_sans_date():
    lg = _ligne(_ev(entreprise_recente_declaree="Oui", source_entreprise_recente="DECLARATIF_KYC"))
    assert lg.etat == "EVALUE" and lg.poids == 10_000 and lg.source_donnee == "DECLARATIF_KYC"
    assert "Aucune date n'est inventée" in lg.motif
    assert _ligne(_ev(entreprise_recente_declaree="non")).poids == 100


def test_contradiction_declaratif_date_exclue():
    ev = _ev(date_creation_pm=date(2020, 1, 1), entreprise_recente_declaree="Oui")
    lg = _ligne(ev)
    assert lg.etat == "A_VERIFIER" and lg.divergence and not lg.contribue_au_score
    assert "Contradiction" in lg.motif
    assert ev.score_total == 200


def test_concordance_declaratif_date():
    lg = _ligne(_ev(date_creation_pm=date(2020, 1, 1), entreprise_recente_declaree="Non"))
    assert lg.etat == "EVALUE" and lg.poids == 100 and "Concorde" in lg.motif


def test_valeur_illisible_jamais_devinee():
    lg = _ligne(_ev(entreprise_recente_declaree="peut-être", date_creation_pm=date(2020, 1, 1)))
    assert lg.etat == "A_VERIFIER" and not lg.contribue_au_score


def test_date_future_a_verifier():
    lg = _ligne(_ev(date_creation_pm=date(2026, 12, 1)))
    assert lg.etat == "A_VERIFIER" and not lg.contribue_au_score


def test_absente_non_disponible_jamais_faible():
    lg = _ligne(_ev())
    assert lg.etat == "NON_DISPONIBLE" and lg.poids is None and not lg.contribue_au_score


def test_personne_physique_non_applicable():
    lg = _ligne(evaluer(DonneesClient(racine="000001", type_client="PP", date_reference=REF)))
    assert lg.etat == "NON_APPLICABLE"
    pp_oui = _ligne(evaluer(DonneesClient(racine="000001", type_client="PP", date_reference=REF,
                                          entreprise_recente_declaree="Oui")))
    assert pp_oui.etat == "A_VERIFIER"


def test_pm_publique_regle_366_jours():
    lg = _ligne(evaluer(DonneesClient(racine="000001", type_client="PM_PUBLIQUE", date_reference=REF,
                                      date_creation_pm=date(2026, 6, 1))))
    assert lg.poids == 10_000


def test_admissibilite():
    assert _ev(date_creation_pm=date(2026, 1, 1)).admissible
    assert not evaluer(DonneesClient(racine="000001")).admissible


def test_lire_oui_non():
    assert lire_oui_non("OUI") is True and lire_oui_non("Non") is False
    assert lire_oui_non("") is None and lire_oui_non(None) is None
    assert lire_oui_non("bof") == INVALIDE


def test_lire_date():
    assert lire_date("06/10/2025") == date(2025, 10, 6)
    assert lire_date("2025-10-06") == date(2025, 10, 6)
    assert lire_date(datetime(2025, 10, 6, 0, 0)) == date(2025, 10, 6)
    assert lire_date(45936) == date(2025, 10, 6)
    assert lire_date("") is None
    assert lire_date("31/02/2025") == INVALIDE


ENTETES = ["CLIENT", "RAISON SOCIALE", "AGENCE", "NCG", "DEVISE", "ETAT", "SOLDE",
           "Motif de risque", "Classe risque LBC/FT", "Entreprise ouverture récente ", "Date ouverture ",
           "Date de mise à jour", "Analyste KYC", "Colonne 14 libre"]


def test_mapping_reconnait_les_six_colonnes():
    m = resoudre_mapping(ENTETES, None)
    assert m["racine"] == "CLIENT"
    assert m["motif"] == "Motif de risque"
    assert m["niveau"] == "Classe risque LBC/FT"
    assert m["entreprise_recente"] == "Entreprise ouverture récente "
    assert m["date_ouverture"] == "Date ouverture "
    assert m["date_maj"] == "Date de mise à jour"
    assert m["analyste"] == "Analyste KYC"


def test_mapping_explicite_vide():
    m = resoudre_mapping(ENTETES, {"niveau": ""})
    assert m["niveau"] is None and m["racine"] == "CLIENT"


def test_ligne_conserve_toutes_les_colonnes():
    row = (1234, "ALPHA SARL", "00001", "210000", "MRU", "Ouvert", 10,
           "Activité récente", "Moyen", "Oui", datetime(2025, 10, 6), "08/10/2026", "A. SALL", "valeur 14")
    x = lire_ligne(5, row, ENTETES, resoudre_mapping(ENTETES, None))
    assert x["racine_client"] == "001234"
    assert x["classe_source"] == "MOYEN" and x["motif_source"] == "Activité récente"
    assert x["entreprise_recente_brut"] == "Oui"
    assert x["date_ouverture_entreprise"] == date(2025, 10, 6) and x["source_date_ouverture"] == "FICHIER"
    assert x["date_maj_metier"] == date(2026, 10, 8) and x["analyste_kyc"] == "A. SALL"
    assert x["donnees"]["Colonne 14 libre"] == "valeur 14"
    assert len(x["donnees"]) == len(ENTETES)
    assert x["anomalies"] == []


def test_ligne_anomalies_sans_invention():
    row = (1234, "ALPHA", None, None, None, None, None, None, "???", "peut-être", "xx/yy", "demain", None, None)
    x = lire_ligne(6, row, ENTETES, resoudre_mapping(ENTETES, None))
    assert x["classe_source"] is None and x["date_ouverture_entreprise"] is None and x["date_maj_metier"] is None
    assert len(x["anomalies"]) == 4
