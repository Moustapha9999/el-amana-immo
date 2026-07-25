"""Tests unitaires légers pour la structure comptes par nature."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.services.comptes_par_nature import CompteNatureLigne, _totaux_ligne


def test_totaux_ligne_somme_montants():
    lignes = [
        CompteNatureLigne(
            immobilisation_id=str(uuid4()),
            code_inventaire="IMMO-1",
            date_acquisition=date(2026, 1, 15),
            quantite=1,
            designation="A",
            valeur_acquisition=Decimal("1000.00"),
            taux=Decimal("10"),
            amorts_cumules_n1=Decimal("100.00"),
            dotations_annee=Decimal("50.00"),
            amorts_cumules_n=Decimal("150.00"),
            vnc=Decimal("850.00"),
            agence_code="AG1",
            agence_libelle="Agence 1",
        ),
        CompteNatureLigne(
            immobilisation_id=str(uuid4()),
            code_inventaire="IMMO-2",
            date_acquisition=date(2026, 3, 1),
            quantite=2,
            designation="B",
            valeur_acquisition=Decimal("500.50"),
            taux=None,
            amorts_cumules_n1=Decimal("0.00"),
            dotations_annee=Decimal("25.25"),
            amorts_cumules_n=Decimal("25.25"),
            vnc=Decimal("475.25"),
            agence_code=None,
            agence_libelle=None,
        ),
    ]
    tot = _totaux_ligne(lignes)
    assert tot.quantite == 3
    assert tot.valeur_acquisition == Decimal("1500.50")
    assert tot.dotations_annee == Decimal("75.25")
    assert tot.vnc == Decimal("1325.25")
    assert tot.taux is None
