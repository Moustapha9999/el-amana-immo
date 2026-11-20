"""Tests — récapitulatif immobilisations (ouverture Orion + mouvements fiches)."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.models.enums import StatutImmobilisation
from app.services.nature_immo_referentiel import is_compte_non_amortissable
from app.services.recap_immobilisations import (
    appliquer_ouverture_orion,
    build_recap_immobilisations,
)
from app.services.solde_compte_orion import COMPTES_ORION_142


RAN_142000 = Decimal("329172220.00")
ACQ_2026 = Decimal("52857824.00")
CUMUL = Decimal("382030044.00")


def test_terrain_non_amortissable():
    assert is_compte_non_amortissable("142000")
    assert is_compte_non_amortissable("140000")
    assert is_compte_non_amortissable("145300")
    assert not is_compte_non_amortissable("142041")


def test_appliquer_orion_142000_seul():
    ouverture, alertes = appliquer_ouverture_orion({}, {"142000": RAN_142000})
    assert ouverture["142000"] == RAN_142000
    assert alertes == []


def test_appliquer_orion_trois_comptes():
    orion = {
        "140000": Decimal("1000.00"),
        "142000": RAN_142000,
        "145300": Decimal("2500.50"),
    }
    ouverture, alertes = appliquer_ouverture_orion({}, orion)
    assert ouverture["140000"] == Decimal("1000.00")
    assert ouverture["142000"] == RAN_142000
    assert ouverture["145300"] == Decimal("2500.50")
    assert alertes == []
    assert set(COMPTES_ORION_142) == {"140000", "142000", "145300"}


def test_appliquer_orion_sans_double_comptage():
    """Orion + fiches historiques → ouverture = Orion seul + alerte."""
    fiches = {"142000": Decimal("100000.00"), "142041": Decimal("50000.00")}
    orion = {"142000": RAN_142000}
    ouverture, alertes = appliquer_ouverture_orion(fiches, orion)
    assert ouverture["142000"] == RAN_142000
    assert ouverture["142000"] != Decimal("329272220.00")  # pas Orion + fiches
    assert ouverture["142041"] == Decimal("50000.00")  # autre nature inchangée
    assert len(alertes) == 1
    assert "142000" in alertes[0]
    assert "Orion" in alertes[0]


def test_appliquer_orion_nul_conserve_fiches():
    fiches = {"142000": Decimal("10.00")}
    ouverture, alertes = appliquer_ouverture_orion(fiches, {"142000": Decimal("0")})
    assert ouverture["142000"] == Decimal("10.00")
    assert alertes == []


def test_appliquer_orion_n_affecte_pas_autres_comptes():
    fiches = {"142041": Decimal("999.00"), "147030": Decimal("1.00")}
    ouverture, alertes = appliquer_ouverture_orion(
        fiches, {"142000": RAN_142000, "140000": Decimal("5.00")}
    )
    assert ouverture["142041"] == Decimal("999.00")
    assert ouverture["147030"] == Decimal("1.00")
    assert ouverture["142000"] == RAN_142000
    assert ouverture["140000"] == Decimal("5.00")
    assert alertes == []


def _immo(**kwargs):
    base = dict(
        id=uuid4(),
        date_acquisition=date(2026, 6, 1),
        date_fin=None,
        valeur_brute=Decimal("1000.00"),
        compte_immobilisation="142000",
        deleted_at=None,
        statut=StatutImmobilisation.EN_SERVICE,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_build_recap_orion_ouverture_et_mouvements_2026():
    """142000 : ouverture Orion + acq/cessions fiches ; clôture = O + A − C."""
    immo_acq = _immo(
        date_acquisition=date(2026, 3, 15),
        valeur_brute=ACQ_2026,
        statut=StatutImmobilisation.EN_SERVICE,
    )
    immo_autre = _immo(
        id=uuid4(),
        date_acquisition=date(2026, 1, 10),
        valeur_brute=Decimal("20000.00"),
        compte_immobilisation="142041",
    )
    cession_id = uuid4()
    immo_cedee = _immo(
        id=cession_id,
        date_acquisition=date(2026, 10, 20),
        date_fin=date(2026, 10, 20),
        valeur_brute=Decimal("23570000.00"),
        statut=StatutImmobilisation.CEDEE,
    )

    db = AsyncMock()

    async def _map_orion(_db, annee):
        assert annee == 2026
        return {"142000": RAN_142000, "140000": Decimal("100.00")}

    with (
        patch(
            "app.services.recap_immobilisations.map_soldes_orion_par_compte",
            new=_map_orion,
        ),
        patch(
            "app.services.recap_immobilisations._cession_vb_par_immo",
            new=AsyncMock(
                return_value={cession_id: Decimal("23570000.00")},
            ),
        ),
    ):
        # select Immobilisation → scalars().all()
        result_immos = SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: [immo_acq, immo_autre, immo_cedee])
        )
        db.execute = AsyncMock(return_value=result_immos)

        result = await build_recap_immobilisations(db, 2026)

    by_compte = {lg.compte: lg for lg in result.lignes}
    lg142 = by_compte["142000"]
    assert lg142.valeurs_ouverture == RAN_142000
    # acq = 52 857 824 + 23 570 000 (cédée la même année compte aussi en acquisition)
    assert lg142.acquisitions == ACQ_2026 + Decimal("23570000.00")
    assert lg142.cessions == Decimal("23570000.00")
    # Clôture = O + A − C ; la VB cédée est en A et en C → stock = RAN + acq. encore détenues
    assert lg142.valeurs_cloture == RAN_142000 + ACQ_2026
    assert lg142.valeurs_cloture == CUMUL

    lg140 = by_compte["140000"]
    assert lg140.valeurs_ouverture == Decimal("100.00")
    assert lg140.acquisitions == Decimal("0.00")

    lg_autre = by_compte["142041"]
    assert lg_autre.valeurs_ouverture == Decimal("0.00")
    assert lg_autre.acquisitions == Decimal("20000.00")
    assert result.alertes == []


@pytest.mark.asyncio
async def test_build_recap_alerte_fiches_et_orion():
    historique = _immo(
        date_acquisition=date(2024, 5, 1),
        valeur_brute=Decimal("50000.00"),
        compte_immobilisation="142000",
    )
    db = AsyncMock()
    result_immos = SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: [historique])
    )
    db.execute = AsyncMock(return_value=result_immos)

    async def _map_orion(_db, annee):
        return {"142000": RAN_142000}

    with (
        patch(
            "app.services.recap_immobilisations.map_soldes_orion_par_compte",
            new=_map_orion,
        ),
        patch(
            "app.services.recap_immobilisations._cession_vb_par_immo",
            new=AsyncMock(return_value={}),
        ),
    ):
        result = await build_recap_immobilisations(db, 2026)

    lg = next(x for x in result.lignes if x.compte == "142000")
    assert lg.valeurs_ouverture == RAN_142000
    assert len(result.alertes) == 1
    assert "142000" in result.alertes[0]


@pytest.mark.asyncio
async def test_build_recap_cloture_formule():
    """Clôture = ouverture + acquisitions − cessions."""
    acq = _immo(valeur_brute=Decimal("100.00"), date_acquisition=date(2026, 2, 1))
    ced = _immo(
        id=uuid4(),
        valeur_brute=Decimal("40.00"),
        date_acquisition=date(2026, 3, 1),
        date_fin=date(2026, 4, 1),
        statut=StatutImmobilisation.CEDEE,
    )
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [acq, ced]))
    )

    with (
        patch(
            "app.services.recap_immobilisations.map_soldes_orion_par_compte",
            new=AsyncMock(return_value={"142000": Decimal("1000.00")}),
        ),
        patch(
            "app.services.recap_immobilisations._cession_vb_par_immo",
            new=AsyncMock(return_value={ced.id: Decimal("40.00")}),
        ),
    ):
        result = await build_recap_immobilisations(db, 2026)

    lg = next(x for x in result.lignes if x.compte == "142000")
    assert lg.valeurs_ouverture == Decimal("1000.00")
    assert lg.acquisitions == Decimal("140.00")
    assert lg.cessions == Decimal("40.00")
    assert lg.valeurs_cloture == Decimal("1100.00")
