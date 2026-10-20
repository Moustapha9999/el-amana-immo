"""Déclaration « retour arrière » des migrations (scripts/migrations_retour.py)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_CHEMIN = Path(__file__).resolve().parent.parent / "scripts" / "migrations_retour.py"
_spec = importlib.util.spec_from_file_location("migrations_retour", _CHEMIN)
mr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mr)


def test_toute_nouvelle_migration_declare_le_retour_arriere():
    assert mr.verifier() == 0


def test_aucune_migration_depuis_la_head(capsys):
    head = mr._scripts().get_current_head()
    assert mr.analyser(head) == 0
    assert capsys.readouterr().out.strip().endswith("RETOUR_ARRIERE=aucune_migration")


def test_migration_anterieure_non_declaree_exige_restauration(capsys):
    sd = mr._scripts()
    parent = sd.get_revision(mr.REFERENCE).down_revision
    assert mr.analyser(parent) == 0
    sortie = capsys.readouterr().out
    assert f"{mr.REFERENCE} : non déclarée" in sortie
    assert sortie.strip().endswith("RETOUR_ARRIERE=restauration")


def test_revision_inconnue_exige_restauration(capsys):
    assert mr.analyser("revision_inexistante") == 2
    assert capsys.readouterr().out.strip().endswith("RETOUR_ARRIERE=restauration")
