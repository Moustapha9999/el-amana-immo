"""Échéances EER (fonctions pures) : délai paramétré, expiration proche, cloisonnement GED."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

from app.services.eer_controles_auto import A_VERIFIER, NON_CONFORME, OK, _expiration, jours_parametre
from app.services.eer_export import Section, sections_excel, sections_pdf
from app.services.ged_service import est_cloisonne

AUJOURD_HUI = date(2026, 10, 5)


def _partie(expiration: date | None):
    piece = SimpleNamespace(date_expiration=expiration, date_delivrance=None)
    return SimpleNamespace(partie=SimpleNamespace(pieces=[piece], physique=None))


def test_jours_parametre_n_invente_aucune_valeur():
    assert jours_parametre(None) is None
    assert jours_parametre(True) is None
    assert jours_parametre("abc") is None
    assert jours_parametre(-3) is None
    assert jours_parametre("30") == 30
    assert jours_parametre(0) == 0


def test_expiration_proche_seulement_si_parametre():
    dans_10 = _partie(AUJOURD_HUI + timedelta(days=10))
    assert _expiration("PIECE_VALIDITE", None, dans_10, AUJOURD_HUI).resultat == OK
    assert _expiration("PIECE_VALIDITE", None, dans_10, AUJOURD_HUI, 5).resultat == OK
    proche = _expiration("PIECE_VALIDITE", None, dans_10, AUJOURD_HUI, 30)
    assert proche.resultat == A_VERIFIER and proche.detail["jours_restants"] == 10
    expiree = _expiration("PIECE_VALIDITE", None, _partie(AUJOURD_HUI - timedelta(days=1)), AUJOURD_HUI, 30)
    assert expiree.resultat == NON_CONFORME


def test_modules_cloisonnes_hors_ged_generique():
    assert est_cloisonne("eer") and est_cloisonne("EER ")
    assert est_cloisonne(None, "eer_dossier")
    assert not est_cloisonne("contrats-echeances", "contrat")


def test_rendu_multi_sections_pdf_excel():
    sections = [Section("Par agence", ["Agence", "Conformes"], [["A01 — Siège", 3]], ["left", "right"],
                        ["Total", 3]), Section("Vide", ["Colonne"], [])]
    assert sections_pdf("Synthèse", "Test", sections).startswith(b"%PDF")
    assert sections_excel("Synthèse", "Test", sections, "Synthèse").startswith(b"PK")
