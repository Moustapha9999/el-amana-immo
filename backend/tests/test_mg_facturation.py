"""Règles métier gestion des factures : références, montants, paiements, échéances, alertes, import."""

import io
from datetime import date
from decimal import Decimal

import pytest
from openpyxl import Workbook

from app.core.exceptions import AppError
from app.services.mg_facturation_analytics import detecter_hausse, mois_attendus, periode_couverte
from app.services.mg_facturation_import import (
    analyser_classeur,
    deduire_type,
    nom_point,
    ressemble_reference,
    suggerer_agence,
)
from app.services.mg_facturation_service import (
    TRANSITIONS,
    actions_possibles,
    calculer_ttc,
    champs_manquants,
    contient_numero_carte,
    controles_facture,
    detail_paiement,
    ecart_tva,
    masquer_carte,
    total_a_payer_auto,
    decouper_reference,
    etat_echeance,
    mois_suivant,
    normaliser_reference,
    periode_facture,
    statut_paiement,
    tranche_echeance,
    variation_pct,
)


def test_reference_espacee_normalisee():
    assert normaliser_reference("36 32 15 238 221") == "363215238221"
    assert normaliser_reference(351471001228) == "351471001228"
    assert normaliser_reference(351471001228.0) == "351471001228"


def test_reference_avec_compteur():
    affichee, digits, compteur = decouper_reference("41MT417(414141799184)")
    assert (affichee, digits, compteur) == ("414141799184", "414141799184", "41MT417")


def test_ttc_calcule_depuis_ht():
    assert calculer_ttc(Decimal("1000"), Decimal("160"), Decimal("20"), Decimal("50"), None) == Decimal("1130.00")


def test_ttc_saisi_sans_ht_conserve():
    assert calculer_ttc(None, None, None, None, Decimal("4520.5")) == Decimal("4520.50")


def test_montant_absent_jamais_invente():
    assert calculer_ttc(None, None, None, None, None) == Decimal("0")


def test_ttc_negatif_refuse():
    with pytest.raises(AppError):
        calculer_ttc(Decimal("100"), None, None, Decimal("200"), None)


@pytest.mark.parametrize(
    ("statut", "du", "paye", "attendu"),
    [
        ("VALIDEE", Decimal("1000"), Decimal("0"), "A_PAYER"),
        ("VALIDEE", Decimal("1000"), Decimal("400"), "PARTIELLEMENT_PAYEE"),
        ("VALIDEE", Decimal("1000"), Decimal("1000"), "PAYEE"),
        ("ARCHIVEE", Decimal("1000"), Decimal("1000"), "PAYEE"),
        ("RECUE", Decimal("1000"), Decimal("0"), None),
        ("ANNULEE", Decimal("1000"), Decimal("0"), None),
    ],
)
def test_statut_paiement(statut, du, paye, attendu):
    assert statut_paiement(statut, du, paye) == attendu


def test_etat_echeance():
    today = date(2026, 10, 5)
    assert etat_echeance(date(2026, 10, 1), "VALIDEE", "A_PAYER", today, 7) == ("EN_RETARD", -4)
    assert etat_echeance(date(2026, 10, 9), "VALIDEE", "A_PAYER", today, 7) == ("PROCHE", 4)
    assert etat_echeance(date(2026, 11, 30), "RECUE", None, today, 7) == ("A_VENIR", 56)
    assert etat_echeance(date(2026, 10, 1), "VALIDEE", "PAYEE", today, 7) == ("SOLDEE", None)
    assert etat_echeance(date(2026, 10, 1), "ANNULEE", None, today, 7) == (None, None)


def test_tranches_echeance():
    assert [tranche_echeance(j) for j in (-1, 0, 7, 8, 30, 31)] == ["retard", "j7", "j7", "j30", "j30", "plus30"]


def test_periode_facture():
    assert periode_facture(None, date(2026, 9, 12), None, None) == (2026, 9)
    assert periode_facture(date(2026, 8, 1), date(2026, 9, 12), None, None) == (2026, 8)
    assert periode_facture(None, date(2026, 9, 12), 7, 2026) == (2026, 7)


def test_mois_suivant():
    assert mois_suivant(2026, 12) == (2027, 1)
    assert mois_suivant(2026, 1, -1) == (2025, 12)
    assert mois_suivant(2026, 11, 3) == (2027, 2)


def test_variation():
    assert variation_pct(130, 100) == 30.0
    assert variation_pct(100, 0) is None


def test_mois_attendus_avec_delai_reception():
    attendus = mois_attendus(date(2026, 7, 1), date(2026, 10, 5), 1, 5)
    assert attendus == [(2026, 7), (2026, 8)]
    assert mois_attendus(date(2026, 7, 1), date(2026, 10, 6), 1, 5) == [(2026, 7), (2026, 8), (2026, 9)]


def test_periode_couverte_bimestrielle():
    factures = {2026 * 12 + 6}
    assert periode_couverte(factures, 2026, 8, 2)
    assert not periode_couverte(factures, 2026, 9, 2)


def test_hausse_detectee():
    assert detecter_hausse(1500, [1000, 1000, 1000], 30) == 50.0
    assert detecter_hausse(1100, [1000, 1000, 1000], 30) is None
    assert detecter_hausse(5000, [1000], 30) is None


def test_ressemble_reference():
    assert ressemble_reference(414844008443)
    assert ressemble_reference("79 12 01 176  127")
    assert ressemble_reference("41MT417(414141799184)")
    assert not ressemble_reference("Agence route de NDB")
    assert not ressemble_reference(2026)


def test_types_et_noms_de_points():
    assert deduire_type("Siege Amanty") == "SIEGE"
    assert deduire_type("Nouveau siege") == "SIEGE"
    assert deduire_type("PVD CARREFOUR 24") == "PDV"
    assert deduire_type("SKY RIM", "PDV AMANTY") == "PDV"
    assert deduire_type("Agence Rosso") == "AGENCE"
    assert deduire_type("Bureau El GHAYRA") == "AGENCE"
    assert deduire_type("Maison Archive Port") == "AUTRE"
    assert nom_point("PVD CARREFOUR 24", "PDV") == "PDV Amanty Carrefour 24"
    assert nom_point("PDV AMANTY SKY RIM", "PDV") == "PDV Amanty Sky Rim"
    assert nom_point("SKY RIM", "PDV") == "PDV Amanty Sky Rim"


def test_suggestion_agence():
    agences = [("1", "Agence Rosso"), ("2", "Agence Tevragh Zeina"), ("3", "Agence Kiffa")]
    assert suggerer_agence("Agence Rosso", agences)[0] == "1"
    assert suggerer_agence("Nouveau siege", agences)[0] is None


def _classeur_somelec() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "REFERENCE"
    ws.append(["Agence /Siège", "Nouveau siege", "Agence Rosso", "Siege Amanty", "Agence chami"])
    ws.append(["Réferance", "41MT417(414141799184)", "79 12 01 176  127", 412703906213, "36 32 15 238 221"])
    ws.append(["Montant à payer", None, None, None, None])
    ref = wb.create_sheet("REF")
    ref.append(["PDV AMANTY SKY RIM", 414844008443])
    ref.append(["PVD CARREFOUR 24", 486901836238])
    ref.append([])
    ref.append(["PDV AMANTY"])
    ref.append(["SKY RIM", 414844008443])
    ref.append(["TIGUINT", 722500527194])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_analyse_classeur_somelec():
    analyse = analyser_classeur(_classeur_somelec())
    par_ref = {l.normalisee: l for l in analyse.lignes if l.statut == "NOUVEAU"}
    assert set(par_ref) == {
        "414141799184", "791201176127", "412703906213", "363215238221", "414844008443", "486901836238", "722500527194",
    }
    assert par_ref["414141799184"].compteur == "41MT417"
    assert par_ref["414141799184"].type_point == "SIEGE"
    assert par_ref["791201176127"].nom == "Agence Rosso"
    assert par_ref["722500527194"].type_point == "PDV"
    assert par_ref["722500527194"].nom == "PDV Amanty Tiguint"
    doublons = [l for l in analyse.lignes if l.statut == "DOUBLON_FICHIER"]
    assert [l.normalisee for l in doublons] == ["414844008443"]
    assert analyse.montants_detectes == 0

# ——— Profils fournisseurs, contrôles, détail des paiements ———


def _facture(**kw):
    from app.models.mg_achats import MgAchatFacture

    base = dict(
        statut="RECUE", numero_fournisseur=None, reference_fournisseur=None, annee=2026, mois=8,
        periode_debut=None, periode_fin=None, montant_ht=None, montant_tva=None, autres_taxes=Decimal("0"),
        remise=Decimal("0"), montant_ttc=Decimal("0"), arrieres=None, reglage=None, montant_a_payer=None,
        date_echeance=None, statut_paiement=None,
    )
    base.update(kw)
    return MgAchatFacture(**base)


def test_total_a_payer_ajoute_les_arrieres():
    assert total_a_payer_auto(Decimal("1000"), Decimal("250.5")) == Decimal("1250.50")
    assert total_a_payer_auto(Decimal("1000"), None) == Decimal("1000.00")


def test_champs_obligatoires_du_profil():
    champs = {"numero_fournisseur": "obligatoire", "montant_ttc": "obligatoire", "arrieres": "facultatif"}
    assert champs_manquants(_facture(), champs) == ["numero_fournisseur", "montant_ttc"]
    assert champs_manquants(_facture(numero_fournisseur="F1", montant_ttc=Decimal("10")), champs) == []
    # Sans profil : aucun champ n'est imposé (pas de N° obligatoire inventé, ex. RIMATEL).
    assert champs_manquants(_facture(), None) == []


def test_tva_controlee_seulement_si_taux_configure():
    assert ecart_tva(Decimal("1000"), Decimal("180"), Decimal("18")) == Decimal("0.00")
    assert ecart_tva(Decimal("1000"), Decimal("160"), None) is None  # SNDE : taux non supposé
    f = _facture(numero_fournisseur="X", montant_ht=Decimal("1000"), montant_tva=Decimal("100"), montant_ttc=Decimal("1100"))
    codes = {c["code"] for c in controles_facture(f, None, Decimal("18"), 1)}
    assert "tva_incoherente" in codes
    assert "tva_incoherente" not in {c["code"] for c in controles_facture(f, None, None, 1)}


def test_controle_bloquant_si_champs_manquants():
    f = _facture(montant_ttc=Decimal("500"))
    niveaux = {c["code"]: c["niveau"] for c in controles_facture(f, {"numero_fournisseur": "obligatoire"}, None, 0)}
    assert niveaux["champs_obligatoires"] == "bloquant"
    assert niveaux["document_absent"] == "attention"


def test_validation_seulement_apres_controle():
    sources, cible = TRANSITIONS["valider"]
    assert sources == {"CONTROLEE"} and cible == "VALIDEE"
    caps = {"update": True, "validate": True, "delete": True, "archive": True}
    assert "valider" not in actions_possibles(_facture(statut="A_CONTROLER"), caps, 0)
    assert "valider_controle" in actions_possibles(_facture(statut="A_CONTROLER"), caps, 0)
    assert "valider" in actions_possibles(_facture(statut="CONTROLEE"), caps, 0)


def test_carte_jamais_stockee_en_clair():
    assert masquer_carte("1234") == "•••• 1234"
    with pytest.raises(AppError):
        masquer_carte("4111111111111111")
    assert contient_numero_carte("payé avec 4111 1111 1111 1111")
    assert not contient_numero_carte("RIB 00012 00034 5678901234 56")  # non Luhn
    with pytest.raises(AppError):
        detail_paiement("Carte", {"carte_derniers_chiffres": "1234", "reference_paiement": "4111111111111111"})


def test_detail_paiement_par_moyen():
    d = detail_paiement("Virement", {"compte": " MR13 0001 ", "banque": "BEA", "numero_cheque": "99"})
    assert d["compte"] == "MR13 0001" and d["banque"] == "BEA" and d["numero_cheque"] is None
    with pytest.raises(AppError):
        detail_paiement("Chèque", {"banque": "BEA"})
    with pytest.raises(AppError):
        detail_paiement("Bitcoin", {})
    assert detail_paiement("Espèces", {})["carte_masquee"] is None
