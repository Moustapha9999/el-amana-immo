"""Règles saisie acquisition — note Banque El Amana."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import ValidationError
from app.schemas.immobilisation import ImmobilisationCreate
from app.services.immobilisation_defaults import (
    apply_categorie_defaults,
    prepare_create,
    validate_immobilisation,
)


def _categorie(**kwargs):
    defaults = dict(
        id=uuid4(),
        code="TY-142041",
        amortissable=True,
        compte_immobilisation="142041",
        compte_amortissement="148041",
        compte_dotation="681041",
        duree_annees_defaut=5,
        taux_lineaire_defaut=Decimal("20"),
        mode_amortissement_defaut="lineaire",
        deleted_at=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_prepare_create_uses_categorie_taux_by_default():
    cat = _categorie()
    payload = ImmobilisationCreate(
        code_inventaire="IMMO-T1",
        designation="Serveur",
        categorie_id=cat.id,
        date_acquisition=date(2026, 1, 15),
        date_comptabilisation=date(2026, 1, 20),
        valeur_brute=Decimal("100000"),
    )
    data = prepare_create(payload, cat)
    assert data["taux"] == Decimal("20")
    assert data["date_comptabilisation"] == date(2026, 1, 20)
    assert data["compte_immobilisation"] == "142041"


def test_prepare_create_allows_taux_override():
    cat = _categorie()
    payload = ImmobilisationCreate(
        code_inventaire="IMMO-T2",
        designation="Serveur",
        categorie_id=cat.id,
        date_acquisition=date(2026, 1, 15),
        date_comptabilisation=date(2026, 1, 15),
        valeur_brute=Decimal("100000"),
        taux=Decimal("15"),
    )
    data = prepare_create(payload, cat)
    assert data["taux"] == Decimal("15")


def test_validate_requires_compte_immobilisation():
    cat = _categorie()
    immo = SimpleNamespace(
        designation="PC",
        date_acquisition=date(2026, 3, 1),
        date_comptabilisation=date(2026, 3, 1),
        date_mise_en_service=None,
        quantite=1,
        compte_immobilisation=None,
        duree_annees=5,
        taux=Decimal("20"),
        periodicite="annuel",
    )
    with pytest.raises(ValidationError, match="compte comptable"):
        validate_immobilisation(immo, cat)


def test_validate_backfills_date_comptabilisation_from_acquisition():
    cat = _categorie()
    immo = SimpleNamespace(
        designation="PC",
        date_acquisition=date(2026, 3, 1),
        date_comptabilisation=None,
        date_mise_en_service=None,
        quantite=1,
        compte_immobilisation="142041",
        duree_annees=5,
        taux=Decimal("20"),
        periodicite="annuel",
    )
    validate_immobilisation(immo, cat)
    assert immo.date_comptabilisation == date(2026, 3, 1)
    assert immo.periodicite == "trimestriel"


def test_validate_rejects_comptabilisation_before_acquisition():
    cat = _categorie()
    immo = SimpleNamespace(
        designation="PC",
        date_acquisition=date(2026, 3, 1),
        date_comptabilisation=date(2026, 2, 1),
        date_mise_en_service=None,
        quantite=1,
        compte_immobilisation="142041",
        duree_annees=5,
        taux=Decimal("20"),
        periodicite="annuel",
    )
    with pytest.raises(ValidationError, match="comptabilisation"):
        validate_immobilisation(immo, cat)


def test_apply_categorie_defaults_preserves_user_taux():
    cat = _categorie()
    immo = SimpleNamespace(
        compte_immobilisation=None,
        compte_amortissement=None,
        compte_dotation=None,
        duree_annees=None,
        duree_mois=0,
        taux=Decimal("12.5"),
        mode_amortissement="lineaire",
        periodicite="annuel",
        prorata_temporis=False,
    )
    apply_categorie_defaults(immo, cat, override_comptes=True, preserve_taux=True)
    assert immo.taux == Decimal("12.5")
    assert immo.compte_immobilisation == "142041"
    assert immo.periodicite == "trimestriel"
