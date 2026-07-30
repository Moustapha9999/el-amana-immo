"""Tests du verrouillage chronologique T1 → T4."""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import ValidationError
from app.models.enums import StatutPeriodeAmortissement
from app.services.periode_amortissement_service import PeriodeAmortissementService


def _period(trimestre: int, statut: StatutPeriodeAmortissement):
    return SimpleNamespace(
        id=uuid4(),
        trimestre=trimestre,
        annee=2026,
        code=f"2026-Q{trimestre}",
        statut=statut,
        calcule_at=None,
        valide_at=None,
        valide_by_id=None,
        total_dotation=Decimal("0"),
        nb_dotations=0,
    )


@pytest.mark.asyncio
async def test_t2_refusee_tant_que_t1_non_validee():
    db = MagicMock()
    svc = PeriodeAmortissementService(db)
    rows = [
        _period(1, StatutPeriodeAmortissement.OUVERTE),
        _period(2, StatutPeriodeAmortissement.EN_ATTENTE),
        _period(3, StatutPeriodeAmortissement.EN_ATTENTE),
        _period(4, StatutPeriodeAmortissement.EN_ATTENTE),
    ]
    svc.ensure_periodes = AsyncMock(return_value=rows)

    with pytest.raises(ValidationError, match="T1"):
        await svc.assert_validation_autorisee(2026, 2)


@pytest.mark.asyncio
async def test_validation_t1_ouvre_t2():
    db = MagicMock()
    db.flush = AsyncMock()
    svc = PeriodeAmortissementService(db)
    rows = [
        _period(1, StatutPeriodeAmortissement.OUVERTE),
        _period(2, StatutPeriodeAmortissement.EN_ATTENTE),
        _period(3, StatutPeriodeAmortissement.EN_ATTENTE),
        _period(4, StatutPeriodeAmortissement.EN_ATTENTE),
    ]
    svc.ensure_periodes = AsyncMock(return_value=rows)
    svc._amortissable_category_ids = AsyncMock(return_value=set())
    svc._active_amortissable_category_ids = AsyncMock(return_value=set())
    svc._details = AsyncMock(return_value=[])

    await svc.enregistrer_validation(
        periode=rows[0],
        categorie_ids=None,
        total_dotation=Decimal("12500"),
        nb_dotations=10,
    )

    assert rows[0].statut == StatutPeriodeAmortissement.VALIDEE
    assert rows[0].total_dotation == Decimal("12500")
    assert rows[1].statut == StatutPeriodeAmortissement.OUVERTE


@pytest.mark.asyncio
async def test_validation_partielle_reste_calculee():
    db = MagicMock()
    db.flush = AsyncMock()
    svc = PeriodeAmortissementService(db)
    t1 = _period(1, StatutPeriodeAmortissement.OUVERTE)
    selected = uuid4()
    another = uuid4()
    svc._amortissable_category_ids = AsyncMock(return_value={selected, another})
    svc._active_amortissable_category_ids = AsyncMock(return_value={selected, another})
    svc._details = AsyncMock(return_value=[])

    await svc.enregistrer_validation(
        periode=t1,
        categorie_ids=[selected],
        total_dotation=Decimal("100"),
        nb_dotations=2,
    )

    assert t1.statut == StatutPeriodeAmortissement.CALCULEE
    assert t1.valide_at is None


@pytest.mark.asyncio
async def test_t2_autorisee_pour_categorie_validee_en_t1():
    db = MagicMock()
    svc = PeriodeAmortissementService(db)
    categorie_id = uuid4()
    rows = [
        _period(1, StatutPeriodeAmortissement.CALCULEE),
        _period(2, StatutPeriodeAmortissement.EN_ATTENTE),
        _period(3, StatutPeriodeAmortissement.EN_ATTENTE),
        _period(4, StatutPeriodeAmortissement.EN_ATTENTE),
    ]
    detail = SimpleNamespace(
        categorie_id=categorie_id,
        statut=StatutPeriodeAmortissement.VALIDEE,
    )
    svc.ensure_periodes = AsyncMock(return_value=rows)
    svc._details = AsyncMock(side_effect=[[], [detail]])

    current = await svc.assert_validation_autorisee(
        2026, 2, categorie_ids=[categorie_id]
    )

    assert current.statut == StatutPeriodeAmortissement.OUVERTE


@pytest.mark.asyncio
async def test_t2_refusee_pour_categorie_non_validee_en_t1():
    db = MagicMock()
    svc = PeriodeAmortissementService(db)
    categorie_id = uuid4()
    rows = [
        _period(1, StatutPeriodeAmortissement.CALCULEE),
        _period(2, StatutPeriodeAmortissement.EN_ATTENTE),
        _period(3, StatutPeriodeAmortissement.EN_ATTENTE),
        _period(4, StatutPeriodeAmortissement.EN_ATTENTE),
    ]
    svc.ensure_periodes = AsyncMock(return_value=rows)
    svc._details = AsyncMock(return_value=[])
    svc._category_labels = AsyncMock(return_value=["MAT-BUREAU"])

    with pytest.raises(ValidationError, match="MAT-BUREAU"):
        await svc.assert_validation_autorisee(
            2026, 2, categorie_ids=[categorie_id]
        )


@pytest.mark.asyncio
async def test_periode_deja_validee_refuse_double_comptabilisation():
    db = MagicMock()
    svc = PeriodeAmortissementService(db)
    rows = [
        _period(1, StatutPeriodeAmortissement.VALIDEE),
        _period(2, StatutPeriodeAmortissement.OUVERTE),
        _period(3, StatutPeriodeAmortissement.EN_ATTENTE),
        _period(4, StatutPeriodeAmortissement.EN_ATTENTE),
    ]
    svc.ensure_periodes = AsyncMock(return_value=rows)

    with pytest.raises(ValidationError, match="déjà comptabilisée"):
        await svc.assert_validation_autorisee(2026, 1)


@pytest.mark.asyncio
async def test_cloture_refusee_avant_validation_t4():
    db = MagicMock()
    svc = PeriodeAmortissementService(db)
    rows = [
        _period(1, StatutPeriodeAmortissement.VALIDEE),
        _period(2, StatutPeriodeAmortissement.VALIDEE),
        _period(3, StatutPeriodeAmortissement.VALIDEE),
        _period(4, StatutPeriodeAmortissement.OUVERTE),
    ]
    svc.ensure_periodes = AsyncMock(return_value=rows)

    with pytest.raises(ValidationError, match="T4"):
        await svc.assert_cloture_autorisee(2026)
