"""Moteur de scoring LBC/FT CDC 1.0 : SCORE uniquement, INTERDIT bloquant, pas de FAIBLE par défaut."""
from __future__ import annotations

from datetime import date

from app.data.clientele_classif_matrice import CRITERES_MAITRE, VERSION_REGLES
from app.data.clientele_classif_referentiel import REFERENTIEL
from app.data.clientele_classif_valeurs import synthese_valeurs, valeurs_maitres
from app.services.clientele.scoring import (
    DonneesClient,
    evaluer,
    niveau_depuis_score_cdc,
    niveau_depuis_score_v4,
)


def test_referentiel_extrait_des_excel():
    assert REFERENTIEL["synthese_pays"]["niveaux_matrice"]["INTERDIT"] == 7
    assert len(REFERENTIEL["synthese_pays"]["inacceptable_v4"]) == 4
    assert REFERENTIEL["synthese_secteurs"]["niveaux_matrice"]["INTERDIT"] == 5
    assert "K/L" in REFERENTIEL["liste_v4_avertissement"] or "M/N" in REFERENTIEL["liste_v4_avertissement"]
    assert any(d["statut"] == "INVALIDE_SOURCE" for d in REFERENTIEL["divergences"])
    assert any(c["code"] == "PPE" for c in CRITERES_MAITRE)
    assert VERSION_REGLES.startswith("CLASSIFICATION-")


def test_referentiel_maitre_lot1():
    rows = valeurs_maitres()
    syn = synthese_valeurs()
    assert syn["total"] == len(rows)
    assert syn["par_dimension"]["CLIENT"] > 100
    assert syn["par_dimension"]["GEOGRAPHIE"] >= 247
    assert syn["nb_blocking"] >= 12  # 5 secteurs + 7 pays
    assert all(r["actif"] is False for r in rows)
    pm = next(r for r in rows if r["critere"] == "PROFIL" and "privee" in r["code"].lower())
    assert pm["conflit"] is True and pm["statut"] == "A_ARBITRER" and pm["score_retenu"] is None
    casino = next(r for r in rows if r["critere"] == "SOUS_SECTEUR" and "CASINO" in r["code"])
    assert casino["niveau_v1"] == "INTERDIT" and casino["is_blocking"] is True
    assert casino["statut"] == "SOURCE_V1"
    digital = next(r for r in rows if r["code"] == "DIGITAL" and r["critere"] == "CANAL_OPERATION")
    assert digital["statut"] == "A_CONFIGURER" and digital["score_retenu"] is None


def test_aucun_critere_n_est_pas_faible():
    ev = evaluer(DonneesClient(racine="000001"), au_jour=date(2026, 10, 8))
    assert ev.nb_evalues == 0
    assert ev.niveau_final is None
    assert ev.statut == "NON_CLASSE"
    assert ev.score_total == 0
    assert ev.mode == "SCORE"


def test_ppe_inconnu_n_est_pas_non():
    ev = evaluer(DonneesClient(
        racine="000001", statut_resident="R", nationalite="Mauritanienne",
    ), au_jour=date(2026, 10, 8))
    ppe = next(lg for lg in ev.lignes if lg.critere == "PPE")
    assert ppe.etat == "NON_DISPONIBLE"
    assert ppe.poids is None
    assert ev.niveau_final != "INTERDIT"


def test_exemple_ppe_eleve():
    ev = evaluer(DonneesClient(
        racine="000001",
        statut_resident="R",
        nationalite="Mauritanienne",
        agent_economique="PARTICULIERS",
        type_client="PP",
        ppe=True,
        filtrage_confirme=None,
        categorie_juridique="Salarié",
    ), au_jour=date(2026, 10, 8))
    ppe = next(lg for lg in ev.lignes if lg.critere == "PPE")
    assert ppe.etat == "EVALUE" and ppe.poids == 100_000
    assert ev.score_total >= 100_000
    assert ev.niveau_final == "ELEVE"
    assert ev.mode == "SCORE"
    assert ev.motif_genere
    assert "PPE" in (ev.motif_principal + " ".join(lg.critere for lg in ev.lignes if lg.poids == 100_000))


def test_non_resident_eleve_matrice():
    ev = evaluer(DonneesClient(racine="000001", statut_resident="N"), au_jour=date(2026, 10, 8))
    lig = next(lg for lg in ev.lignes if lg.critere == "RESIDENCE")
    assert lig.etat == "EVALUE" and lig.niveau_matrice == "ELEVE" and lig.poids == 100_000
    assert ev.niveau_final == "ELEVE"


def test_pm_privee_divergence_pas_de_choix_silencieux():
    ev = evaluer(DonneesClient(
        racine="000001",
        type_client="PM_PRIVEE",
        categorie_juridique="SARL",
    ), au_jour=date(2026, 10, 8))
    profil = next(lg for lg in ev.lignes if lg.critere == "PROFIL")
    forme = next(lg for lg in ev.lignes if lg.critere == "FORME_JURIDIQUE")
    assert profil.divergence or forme.divergence or ev.coherence == "CONFLIT_REFERENTIEL"
    assert profil.contribue_au_score is False
    assert ev.statut == "A_ARBITRER"
    assert ev.niveau_final != "INTERDIT"
    assert ev.niveau_final != "MOYEN" or profil.poids is None


def test_association_eleve_aligne():
    ev = evaluer(DonneesClient(
        racine="000001", categorie_juridique="ASSOCIATION",
    ), au_jour=date(2026, 10, 8))
    lig = next(lg for lg in ev.lignes if lg.critere == "ASSOCIATION")
    assert lig.etat == "EVALUE" and lig.poids == 100_000 and lig.niveau_retenu == "ELEVE"
    assert ev.niveau_final == "ELEVE"


def test_secteur_interdit_applique():
    ev = evaluer(DonneesClient(
        racine="000001", secteur_activite="Casino",
    ), au_jour=date(2026, 10, 8))
    lig = next(lg for lg in ev.lignes if lg.critere == "SECTEUR")
    assert lig.blocking_propose is True
    assert lig.contribue_au_score is True
    assert ev.niveau_final == "INTERDIT"
    assert ev.statut == "BLOQUANT"
    assert ev.score_total >= 100_000
    assert "INTERDIT" in ev.motif_genere


def test_pays_interdit_iran():
    ev = evaluer(DonneesClient(
        racine="000001", pays_residence="Iran",
    ), au_jour=date(2026, 10, 8))
    lig = next(lg for lg in ev.lignes if lg.critere == "PAYS_RESIDENCE")
    assert lig.etat == "EVALUE"
    assert lig.niveau_retenu == "INTERDIT"
    assert ev.niveau_final == "INTERDIT"
    assert lig.famille == "GEOGRAPHIE"


def test_nationalite_etrangere_moyen():
    ev = evaluer(DonneesClient(
        racine="000001", nationalite="française",
    ), au_jour=date(2026, 10, 8))
    lig = next(lg for lg in ev.lignes if lg.critere == "NATIONALITE")
    if lig.etat == "EVALUE":
        assert lig.niveau_retenu == "MOYEN"
        assert lig.poids == 10_000


def test_formule_v4_score_10000_incomplet():
    assert niveau_depuis_score_v4(10000) is None
    assert niveau_depuis_score_v4(100) == "FAIBLE"
    assert niveau_depuis_score_v4(10001) == "MOYEN"
    assert niveau_depuis_score_v4(100001) == "ELEVE"


def test_seuils_cdc():
    assert niveau_depuis_score_cdc(0, 0) is None
    assert niveau_depuis_score_cdc(9999, 1) == "FAIBLE"
    assert niveau_depuis_score_cdc(10_000, 1) == "MOYEN"
    assert niveau_depuis_score_cdc(99_999, 1) == "MOYEN"
    assert niveau_depuis_score_cdc(100_000, 1) == "ELEVE"


def test_liste_non_orion_score_100():
    ev = evaluer(DonneesClient(racine="000001", liste_interdiction=""), au_jour=date(2026, 10, 8))
    lig = next(lg for lg in ev.lignes if lg.critere == "LISTE_INTERDICTION")
    assert lig.etat == "EVALUE" and lig.poids == 100
    assert ev.niveau_final == "FAIBLE"
    assert ev.score_total == 100


def test_age_pp_non_additionne():
    ev = evaluer(DonneesClient(
        racine="000001", type_client="PP", date_naissance=date(2015, 1, 1),
    ), au_jour=date(2026, 10, 8))
    lig = next(lg for lg in ev.lignes if lg.critere == "AGE_PP")
    assert lig.statut_regle == "A_CONFIGURER"
    assert lig.contribue_au_score is False
    assert lig.poids is None


def test_iran_matrice_interdit_v4_pas_identique():
    iran = next(p for p in REFERENTIEL["pays"] if p["nom_fr"].strip().upper() == "IRAN")
    assert iran["niveau_matrice"] == "INTERDIT"
    assert "IRAN" in REFERENTIEL["synthese_pays"]["interdit_matrice"]
    assert not any(x.upper() == "IRAN" for x in (
        sl.upper() for sl in REFERENTIEL["synthese_pays"]["inacceptable_v4"]
    ))
