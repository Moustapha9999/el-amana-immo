"""Règles métier contrats : dates, statuts de paiement, niveaux d'alerte."""

from datetime import date
from decimal import Decimal

import pytest

from app.core.exceptions import AppError
from app.services.mg_contrats_service import (
    MgContratsService,
    _match_ligne,
    ajouter_mois,
    montant_annualise,
    doit_rappeler,
    echeance_statut,
    niveau_alerte,
    paiement_statut,
    periode_suivante,
    plan_echeancier,
    repartir,
)


def test_date_fin_avant_debut_refusee():
    svc = MgContratsService(db=None)  # type: ignore[arg-type]
    with pytest.raises(AppError) as exc:
        svc._check_dates(date(2026, 9, 30), date(2026, 9, 1))
    assert exc.value.status_code == 400


def test_dates_coherentes_acceptees():
    MgContratsService(db=None)._check_dates(date(2026, 1, 1), date(2026, 12, 31))  # type: ignore[arg-type]


def test_paiement_a_venir_et_retard():
    assert (
        paiement_statut(
            date_prevue=date(2026, 10, 1),
            date_reelle=None,
            montant_prevu=Decimal("100"),
            montant_paye=Decimal("0"),
            today=date(2026, 9, 25),
        )
        == "A_VENIR"
    )
    assert (
        paiement_statut(
            date_prevue=date(2026, 9, 1),
            date_reelle=None,
            montant_prevu=Decimal("100"),
            montant_paye=Decimal("0"),
            today=date(2026, 9, 25),
        )
        == "EN_RETARD"
    )


def test_paiement_partiel_et_paye():
    assert (
        paiement_statut(
            date_prevue=date(2026, 9, 1),
            date_reelle=date(2026, 9, 2),
            montant_prevu=Decimal("100"),
            montant_paye=Decimal("40"),
            today=date(2026, 9, 25),
        )
        == "PARTIELLEMENT_PAYE"
    )
    assert (
        paiement_statut(
            date_prevue=date(2026, 9, 1),
            date_reelle=date(2026, 9, 2),
            montant_prevu=Decimal("100"),
            montant_paye=Decimal("100"),
            today=date(2026, 9, 25),
        )
        == "PAYE"
    )


def test_niveaux_alerte_configurables():
    assert niveau_alerte(-1, 7, 30) == "CRITIQUE"
    assert niveau_alerte(3, 7, 30) == "URGENT"
    assert niveau_alerte(20, 7, 30) == "ATTENTION"
    assert niveau_alerte(60, 7, 30) == "INFO"


def test_montants_ttc_recalcules():
    svc = MgContratsService(db=None)  # type: ignore[arg-type]
    ht, taux, ttc = svc._montants(Decimal("100000"), Decimal("18"), None)
    assert ht == Decimal("100000")
    assert taux == Decimal("18")
    assert ttc == Decimal("118000.00")


def test_montant_negatif_refuse():
    svc = MgContratsService(db=None)  # type: ignore[arg-type]
    with pytest.raises(AppError):
        svc._montants(Decimal("-1"), Decimal("18"), None)


def test_ttc_tva_16():
    _, _, ttc = MgContratsService(db=None)._montants(Decimal("1000"), Decimal("16"), None)  # type: ignore[arg-type]
    assert ttc == Decimal("1160.00")


def test_ajouter_mois_fin_de_mois():
    assert ajouter_mois(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert ajouter_mois(date(2026, 11, 15), 3) == date(2027, 2, 15)


def test_repartition_centimes_sur_derniere():
    parts = repartir(Decimal("100.00"), 3)
    assert parts == [Decimal("33.33"), Decimal("33.33"), Decimal("33.34")]
    assert sum(parts) == Decimal("100.00")


def test_echeancier_mensuel_un_an():
    plan = plan_echeancier(date(2026, 1, 1), date(2026, 12, 31), "MENSUEL", Decimal("116000"))
    assert len(plan) == 12
    assert plan[0] == (date(2026, 1, 1), Decimal("9666.66"))
    assert plan[-1][0] == date(2026, 12, 1)
    assert sum(m for _, m in plan) == Decimal("116000")


def test_echeancier_trimestriel_et_unique():
    assert [d for d, _ in plan_echeancier(date(2026, 1, 1), date(2026, 12, 31), "TRIMESTRIEL", Decimal("400"))] == [
        date(2026, 1, 1),
        date(2026, 4, 1),
        date(2026, 7, 1),
        date(2026, 10, 1),
    ]
    assert plan_echeancier(date(2026, 3, 5), None, "UNIQUE", Decimal("50")) == [(date(2026, 3, 5), Decimal("50"))]


def test_echeancier_periodique_sans_fin_refuse():
    with pytest.raises(AppError) as exc:
        plan_echeancier(date(2026, 1, 1), None, "MENSUEL", Decimal("100"))
    assert exc.value.code == "ECHEANCIER_IMPOSSIBLE"


def test_statuts_echeance():
    today = date(2026, 10, 1)
    base = dict(montant=Decimal("100"), statut_actuel="A_VENIR", fenetre_due=7, today=today)
    assert echeance_statut(date_prevue=date(2026, 11, 1), montant_paye=Decimal("0"), **base) == "A_VENIR"
    assert echeance_statut(date_prevue=date(2026, 10, 5), montant_paye=Decimal("0"), **base) == "DUE"
    assert echeance_statut(date_prevue=date(2026, 9, 20), montant_paye=Decimal("40"), **base) == "EN_RETARD"
    assert echeance_statut(date_prevue=date(2026, 9, 20), montant_paye=Decimal("100"), **base) == "PAYEE"


def test_echeance_payee_ne_tient_qu_aux_paiements():
    today = date(2026, 10, 1)
    assert (
        echeance_statut(
            date_prevue=date(2026, 9, 1), montant=Decimal("100"), montant_paye=Decimal("0"),
            statut_actuel="PAYEE", fenetre_due=7, today=today,
        )
        == "EN_RETARD"
    )
    assert (
        echeance_statut(
            date_prevue=date(2026, 9, 1), montant=None, montant_paye=Decimal("0"),
            statut_actuel="FAITE", fenetre_due=7, today=today,
        )
        == "FAITE"
    )


def test_periode_suivante_mois_entiers_et_jours():
    assert periode_suivante(date(2026, 1, 1), date(2026, 12, 31)) == (date(2027, 1, 1), date(2027, 12, 31))
    assert periode_suivante(date(2026, 1, 10), date(2026, 1, 19)) == (date(2026, 1, 20), date(2026, 1, 29))


def test_debut_periode_suit_la_derniere_reconduction():
    from types import SimpleNamespace

    contrat = SimpleNamespace(
        date_debut=date(2026, 1, 1),
        avenants=[
            SimpleNamespace(type_avenant="MONTANT", date_effet=date(2026, 6, 1)),
            SimpleNamespace(type_avenant="RECONDUCTION", date_effet=date(2027, 1, 1)),
            SimpleNamespace(type_avenant="RECONDUCTION", date_effet=date(2028, 1, 1)),
        ],
    )
    assert MgContratsService._debut_periode(contrat) == date(2028, 1, 1)
    assert periode_suivante(MgContratsService._debut_periode(contrat), date(2028, 12, 31)) == (date(2029, 1, 1), date(2029, 12, 31))
    contrat.avenants = []
    assert MgContratsService._debut_periode(contrat) == date(2026, 1, 1)


def test_jalons_de_rappel():
    assert doit_rappeler(60, 60)
    assert doit_rappeler(7, 90)
    assert not doit_rappeler(8, 90)
    assert doit_rappeler(-1, 30) and doit_rappeler(-8, 30)
    assert not doit_rappeler(-2, 30)


def test_montant_annualise_ramene_a_douze_mois():
    assert montant_annualise(Decimal("1200"), date(2026, 1, 1), date(2026, 12, 31)) == Decimal("1200.00")
    assert montant_annualise(Decimal("2400"), date(2026, 1, 1), date(2027, 12, 31)) == Decimal("1200.00")
    assert montant_annualise(Decimal("600"), date(2026, 1, 1), date(2026, 6, 30)) == Decimal("1209.94")
    assert montant_annualise(Decimal("500"), date(2026, 1, 1), None) == Decimal("500")


def test_filtres_lignes_echeances_paiements():
    r = {"reference": "CT-2026-0001", "titre": "Gardiennage", "fournisseur": "SECURIS", "agence": "Tevragh Zeina"}
    base = dict(q=None, fournisseur=None, agence=None, jour=date(2026, 5, 10), date_du=None, date_au=None)
    assert _match_ligne(r, **base)
    assert _match_ligne(r, **{**base, "q": "garDi"})
    assert not _match_ligne(r, **{**base, "q": "nettoyage"})
    assert not _match_ligne(r, **{**base, "fournisseur": "AUTRE"})
    assert _match_ligne(r, **{**base, "agence": "Tevragh Zeina"})
    assert not _match_ligne(r, **{**base, "date_du": date(2026, 6, 1)})
    assert not _match_ligne(r, **{**base, "date_au": date(2026, 5, 1)})
    assert _match_ligne(r, **{**base, "date_du": date(2026, 5, 1), "date_au": date(2026, 5, 31)})
