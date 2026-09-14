"""Soldes Orion — natures non amortissables en famille 142."""

from decimal import Decimal

from app.data.el_amana_referentiel import COMPTES_NON_AMORTISSABLES_EL_AMANA
from app.services.solde_compte_orion import COMPTES_ORION_142, ensure_compte_orion_autorise
from app.services.soldes_148_68 import _compte_matches_famille, _empty_nature_buckets


def test_comptes_orion_alignes():
    assert set(COMPTES_ORION_142) == set(COMPTES_NON_AMORTISSABLES_EL_AMANA)


def test_ensure_compte_orion():
    assert ensure_compte_orion_autorise("142000") == "142000"


def test_famille_142_inclut_orion_comptes():
    assert _compte_matches_famille("140000", "142")
    assert _compte_matches_famille("142000", "142")
    assert _compte_matches_famille("145300", "142")
    assert _compte_matches_famille("142010", "142")
    assert not _compte_matches_famille("140000", "148")


def test_buckets_orion_en_famille_142():
    buckets = _empty_nature_buckets({}, include_orion=True)
    for compte in COMPTES_ORION_142:
        assert compte in buckets
        assert buckets[compte]["compte_amortissement"] is None
    buckets_std = _empty_nature_buckets({}, include_orion=False)
    assert "140000" not in buckets_std
