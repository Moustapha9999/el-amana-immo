"""Tests — ventilation amortissements par agence."""

from app.services.ventilation_amortissements_agence import (
    _label_periode,
    _periodes_cibles,
    _periode_sort_key,
)


def test_periodes_trimestriel_t2():
    assert _periodes_cibles("trimestriel", 2026, 2) == ["2026-Q2"]


def test_periodes_mensuel():
    assert _periodes_cibles("mensuel", 2026, 6) == ["2026-06"]


def test_periodes_annuel_contient_t1_t4():
    keys = _periodes_cibles("annuel", 2026, None)
    assert "2026-Q1" in keys
    assert "2026-Q4" in keys
    assert "2026" in keys
    assert "2026-06" in keys


def test_label_periode_t1():
    label = _label_periode("trimestriel", 2026, 1)
    assert "T1" in label
    assert "2026" in label


def test_periode_sort():
    assert _periode_sort_key("2026-Q1") < _periode_sort_key("2026-Q2")
    assert _periode_sort_key("2026-03") < _periode_sort_key("2026-Q2")
