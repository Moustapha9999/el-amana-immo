"""Règle Banque El Amana — comptes / natures non amortissables."""

from app.data.el_amana_referentiel import (
    COMPTES_NON_AMORTISSABLES_EL_AMANA,
    MESSAGE_NON_AMORTISSABLE_EL_AMANA,
    NATURE_IMMO_CODES_OFFICIELS,
    TYPES_IMMOBILISATION_EL_AMANA,
)
from app.services.nature_immo_referentiel import (
    is_compte_non_amortissable,
    is_immobilisation_amortissable,
)


def test_comptes_non_amortissables_officiels():
    assert COMPTES_NON_AMORTISSABLES_EL_AMANA == frozenset({"140000", "142000", "145300"})
    assert is_compte_non_amortissable("142000")
    assert is_compte_non_amortissable("140000")
    assert is_compte_non_amortissable("145300")
    assert not is_compte_non_amortissable("142010")
    assert not is_compte_non_amortissable(None)


def test_natures_non_amortissables_dans_referentiel():
    by_code = {row["code"]: row for row in TYPES_IMMOBILISATION_EL_AMANA}
    for code, compte in (
        ("TY-140000", "140000"),
        ("TY-142000", "142000"),
        ("TY-145300", "145300"),
    ):
        assert code in NATURE_IMMO_CODES_OFFICIELS
        row = by_code[code]
        assert row["compte_immobilisation"] == compte
        assert row["amortissable"] is False
        assert row["compte_amortissement"] is None
        assert row["compte_dotation"] is None


def test_autres_natures_restent_amortissables():
    for row in TYPES_IMMOBILISATION_EL_AMANA:
        if row["compte_immobilisation"] in COMPTES_NON_AMORTISSABLES_EL_AMANA:
            continue
        assert row["amortissable"] is True


class _FakeCat:
    def __init__(self, compte: str, amortissable: bool):
        self.compte_immobilisation = compte
        self.amortissable = amortissable


class _FakeImmo:
    def __init__(self, compte: str | None, categorie=None):
        self.compte_immobilisation = compte
        self.categorie = categorie


def test_is_immobilisation_amortissable_par_compte():
    cat = _FakeCat("142000", True)  # flag incohérent : le compte prime
    immo = _FakeImmo("142000", cat)
    assert not is_immobilisation_amortissable(immo, cat)
    assert MESSAGE_NON_AMORTISSABLE_EL_AMANA.startswith("Cette immobilisation appartient")


def test_is_immobilisation_amortissable_ok():
    cat = _FakeCat("142010", True)
    immo = _FakeImmo("142010", cat)
    assert is_immobilisation_amortissable(immo, cat)
