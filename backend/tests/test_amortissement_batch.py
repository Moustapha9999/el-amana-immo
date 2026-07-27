"""Tests campagne batch amortissements (validation paramètres + règles métier)."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
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
    svc._prefetch_amortissements = AsyncMock(return_value={})
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
    opening = SimpleNamespace(
        periode="2025-12",
        montant=Decimal("100000"),
        cumul=Decimal("100000"),
        vnc=Decimal("0"),
        valide=True,
    )

    svc._load_immobilisations = AsyncMock(return_value=[immo])
    svc._prefetch_amortissements = AsyncMock(return_value={immo.id: [opening]})
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
    existing = SimpleNamespace(
        periode="2026-Q1",
        montant=Decimal("2500.00"),
        vnc=Decimal("97500.00"),
        cumul=Decimal("2500.00"),
        valide=True,
    )

    svc._load_immobilisations = AsyncMock(return_value=[immo])
    svc._prefetch_amortissements = AsyncMock(return_value={immo.id: [existing]})
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


@pytest.mark.asyncio
async def test_batch_t2_part_du_cumul_t1_pas_du_plan_futur():
    """T2 doit partir du cumul T1 validé, sans prendre en compte Q3/Q4 du plan."""
    db = MagicMock()
    svc = AmortissementBatchService(db)
    immo = FakeImmo()
    immo.date_acquisition = date(2025, 6, 1)
    rows = [
        SimpleNamespace(
            periode="2025-12",
            montant=Decimal("0.00"),
            cumul=Decimal("50000.00"),
            vnc=Decimal("50000.00"),
            valide=True,
        ),
        SimpleNamespace(
            periode="2026-Q1",
            montant=Decimal("2500.00"),
            cumul=Decimal("52500.00"),
            vnc=Decimal("47500.00"),
            valide=True,
        ),
        # Plan futur non encore « échu » mais déjà en base (valide à tort) :
        # ne doit pas gonfler le cumul avant T2.
        SimpleNamespace(
            periode="2026-Q3",
            montant=Decimal("2500.00"),
            cumul=Decimal("57500.00"),
            vnc=Decimal("42500.00"),
            valide=True,
        ),
    ]

    svc._load_immobilisations = AsyncMock(return_value=[immo])
    svc._prefetch_amortissements = AsyncMock(return_value={immo.id: rows})
    svc._persist_and_comptabiliser = AsyncMock()

    result = await svc.calculer(
        periodicite="trimestriel",
        annee=2026,
        periode_index=2,
        mode="simulation",
    )

    assert result.nb_calcules == 1
    assert result.lignes[0].cumul_avant == Decimal("52500.00")
    assert result.lignes[0].dotation == Decimal("2500.00")
    assert result.lignes[0].cumul_apres == Decimal("55000.00")


@pytest.mark.asyncio
async def test_batch_ignore_acquisition_apres_arrete():
    db = MagicMock()
    svc = AmortissementBatchService(db)
    immo = FakeImmo()
    immo.date_acquisition = date(2026, 4, 6)  # après T1

    svc._load_immobilisations = AsyncMock(return_value=[immo])
    svc._prefetch_amortissements = AsyncMock(return_value={})
    svc._persist_and_comptabiliser = AsyncMock()

    result = await svc.calculer(
        periodicite="trimestriel",
        annee=2026,
        periode_index=1,
        mode="simulation",
    )

    assert result.nb_calcules == 0
    assert result.nb_ignores_vnc == 1
    assert "postérieure" in (result.ignores[0].message or "").lower()


def test_plafond_aligne_period_bounds_et_dotation():
    debut, fin, key = period_bounds("trimestriel", 2026, 1)
    assert key == "2026-Q1"
    immo = FakeImmo()
    result = calcul_dotation_periode(immo, debut, fin, Decimal("99950"))
    assert result is not None
    montant, _, vnc = result
    assert montant == Decimal("50.00")
    assert vnc == Decimal("0.00")


def test_cumul_avant_periode_helper():
    rows = [
        SimpleNamespace(periode="2025-12", montant=Decimal("0"), cumul=Decimal("65700"), valide=True),
        SimpleNamespace(periode="2026-Q1", montant=Decimal("2500"), cumul=Decimal("68200"), valide=True),
        SimpleNamespace(periode="2026-Q2", montant=Decimal("2500"), cumul=Decimal("70700"), valide=False),
    ]
    assert AmortissementBatchService._cumul_avant_periode(rows, date(2026, 1, 1)) == Decimal("65700")
    assert AmortissementBatchService._cumul_avant_periode(rows, date(2026, 4, 1)) == Decimal("68200")
