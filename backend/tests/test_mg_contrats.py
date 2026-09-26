"""Règles métier contrats : dates, statuts de paiement, niveaux d'alerte."""

from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.services.mg_contrats_service import MgContratsService, niveau_alerte, paiement_statut


def test_date_fin_avant_debut_refusee():
    svc = MgContratsService(db=None)  # type: ignore[arg-type]
    with pytest.raises(HTTPException) as exc:
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
    with pytest.raises(HTTPException):
        svc._montants(Decimal("-1"), Decimal("18"), None)
