"""Tests campagne batch amortissements (validation paramètres + règles métier)."""

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import ValidationError
from app.models.enums import ModeAmortissement
from app.services.amortissement_batch import AmortissementBatchService
from app.services.amortissement_engine import calcul_dotation_periode, period_bounds


class FakeImmo:
    id = uuid4()
    code_inventaire = "IMMO-001"
    designation = "Test"
    valeur_brute = Decimal("100000")
    valeur_residuelle = Decimal("0")
    duree_mois = 120
    duree_annees = 10
    date_acquisition = date(2026, 1, 1)
    date_mise_en_service = date(2026, 1, 1)
    periodicite = "trimestriel"
    prorata_temporis = True
    mode_amortissement = ModeAmortissement.LINEAIRE
    taux = Decimal("10")
    compte_dotation = "681211"
    compte_amortissement = "148211"
    categorie = None


@pytest.mark.asyncio
async def test_batch_mode_invalide():
    svc = AmortissementBatchService(MagicMock())
    with pytest.raises(ValidationError, match="simulation"):
        await svc.calculer(
            periodicite="trimestriel",
            annee=2026,
            periode_index=1,
            mode="brouillon",
        )


@pytest.mark.asyncio
async def test_batch_periodicite_invalide():
    svc = AmortissementBatchService(MagicMock())
    with pytest.raises(ValidationError, match="Périodicité"):
        await svc.calculer(
            periodicite="hebdo",
            annee=2026,
            periode_index=1,
            mode="simulation",
        )


@pytest.mark.asyncio
async def test_batch_simulation_ne_persiste_pas():
    """En simulation, aucune écriture / ligne n'est créée (pas d'appel persist)."""
    db = MagicMock()
    svc = AmortissementBatchService(db)
    immo = FakeImmo()

    svc._load_immobilisations = AsyncMock(return_value=[immo])
    svc._cumul_valide = AsyncMock(return_value=Decimal("0"))
    svc._existing_periode = AsyncMock(return_value=None)
    svc._persist_and_comptabiliser = AsyncMock()

    result = await svc.calculer(
        periodicite="trimestriel",
        annee=2026,
        periode_index=1,
        mode="simulation",
    )

    assert result.nb_calcules == 1
    assert result.total_dotations == Decimal("2500.00")
    assert result.lignes[0].vnc_apres == Decimal("97500.00")
    svc._persist_and_comptabiliser.assert_not_awaited()


@pytest.mark.asyncio
async def test_batch_ignore_vnc_zero():
    db = MagicMock()
    svc = AmortissementBatchService(db)
    immo = FakeImmo()

    svc._load_immobilisations = AsyncMock(return_value=[immo])
    svc._cumul_valide = AsyncMock(return_value=Decimal("100000"))
    svc._existing_periode = AsyncMock(return_value=None)
    svc._persist_and_comptabiliser = AsyncMock()

    result = await svc.calculer(
        periodicite="trimestriel",
        annee=2026,
        periode_index=1,
        mode="simulation",
    )

    assert result.nb_calcules == 0
    assert result.nb_ignores_vnc == 1
    assert result.ignores[0].statut == "ignore_vnc"
    svc._persist_and_comptabiliser.assert_not_awaited()


@pytest.mark.asyncio
async def test_batch_skip_deja_comptabilise():
    db = MagicMock()
    svc = AmortissementBatchService(db)
    immo = FakeImmo()
    existing = MagicMock()
    existing.valide = True
    existing.montant = Decimal("2500.00")
    existing.vnc = Decimal("97500.00")
    existing.cumul = Decimal("2500.00")

    svc._load_immobilisations = AsyncMock(return_value=[immo])
    svc._cumul_valide = AsyncMock(return_value=Decimal("2500"))
    svc._existing_periode = AsyncMock(return_value=existing)
    svc._persist_and_comptabiliser = AsyncMock()

    result = await svc.calculer(
        periodicite="trimestriel",
        annee=2026,
        periode_index=1,
        mode="validation",
    )

    assert result.nb_deja_comptabilises == 1
    assert result.nb_calcules == 0
    svc._persist_and_comptabiliser.assert_not_awaited()


def test_plafond_aligne_period_bounds_et_dotation():
    debut, fin, key = period_bounds("trimestriel", 2026, 1)
    assert key == "2026-Q1"
    immo = FakeImmo()
    result = calcul_dotation_periode(immo, debut, fin, Decimal("99950"))
    assert result is not None
    montant, _, vnc = result
    assert montant == Decimal("50.00")
    assert vnc == Decimal("0.00")
