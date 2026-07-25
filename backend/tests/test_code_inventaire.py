"""Numéros d'immobilisation PREFIX-YYYY-NNN."""

from app.services.code_inventaire import (
    PREFIX_BY_CATEGORIE,
    format_code_inventaire,
    parse_code_inventaire,
    prefix_from_categorie_code,
)


def test_prefixes_natures_officielles():
    assert prefix_from_categorie_code("TY-142010") == "AAI"
    assert prefix_from_categorie_code("TY-147530") == "Log"
    assert prefix_from_categorie_code("TY-147050") == "Frais"
    assert prefix_from_categorie_code("TY-142041") == "MatInfo"
    assert all(PREFIX_BY_CATEGORIE.values())


def test_format_and_parse():
    assert format_code_inventaire("AAI", 2026, 1) == "AAI-2026-001"
    assert format_code_inventaire("Log", 2026, 12) == "Log-2026-012"
    assert parse_code_inventaire("AAI-2026-001") == ("AAI", 2026, 1)
    assert parse_code_inventaire("Frais-2026-042") == ("Frais", 2026, 42)
    assert parse_code_inventaire("IMMO-T1") is None
