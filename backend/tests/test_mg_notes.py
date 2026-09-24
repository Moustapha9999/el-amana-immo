"""Notes de frais — catalogue, transitions, scopes."""

from app.data.module_backup_scopes import MODULE_BACKUP_SCOPES
from app.data.plateforme_catalogue import FUNCTIONAL_PERMISSIONS, PLATEFORME_MODULES, ROLE_PERMISSIONS
from app.models.mg_ops import (
    MgNoteFrais,
    MgNoteFraisCategorie,
    MgNoteFraisHistorique,
    MgNoteFraisLigne,
    MgNoteFraisParametre,
)
from app.services.mg_notes_service import NOTE_TRANSITIONS


def test_notes_module_catalogue():
    modules = {m["code"]: m for m in PLATEFORME_MODULES}
    notes = modules["notes-frais"]
    assert notes["espace_code"] == "moyens-generaux"
    assert notes["statut"] == "actif"
    assert notes["entry_path"] == "/notes-frais"


def test_notes_permissions_extended():
    codes = {row[0] for row in FUNCTIONAL_PERMISSIONS}
    for p in (
        "mg.notes.view",
        "mg.notes.create",
        "mg.notes.control",
        "mg.notes.approve",
        "mg.notes.reject",
        "mg.notes.payment",
        "mg.notes.archive",
        "mg.notes.export",
        "mg.notes.settings",
    ):
        assert p in codes


def test_notes_role_grants():
    assert "mg.notes.control" in ROLE_PERMISSIONS["notes-frais.valideur"]
    assert "mg.notes.payment" in ROLE_PERMISSIONS["notes-frais.admin"]
    assert "mg.notes.settings" in ROLE_PERMISSIONS["notes-frais.admin"]


def test_notes_backup_scope():
    scope = MODULE_BACKUP_SCOPES["notes-frais"]
    for t in (
        "mg_notes_frais",
        "mg_note_frais_lignes",
        "mg_note_frais_categories",
        "mg_note_frais_historique",
        "mg_note_frais_parametres",
    ):
        assert t in scope["exclusive_tables"]


def test_notes_models():
    assert MgNoteFrais.__tablename__ == "mg_notes_frais"
    assert MgNoteFraisLigne.__tablename__ == "mg_note_frais_lignes"
    assert MgNoteFraisCategorie.__tablename__ == "mg_note_frais_categories"
    assert MgNoteFraisHistorique.__tablename__ == "mg_note_frais_historique"
    assert MgNoteFraisParametre.__tablename__ == "mg_note_frais_parametres"


def test_notes_workflow_map():
    assert NOTE_TRANSITIONS["soumettre"][1] == "SOUMIS"
    assert NOTE_TRANSITIONS["prendre_controle"][1] == "EN_CONTROLE"
    assert NOTE_TRANSITIONS["demander_correction"][1] == "CORRECTION_REQUISE"
    assert "SOUMIS" in NOTE_TRANSITIONS["demander_correction"][0]
    assert NOTE_TRANSITIONS["visa_mg"][0] == {"EN_CONTROLE"}
    assert NOTE_TRANSITIONS["visa_dr"][1] == "VISA_DR"
    assert NOTE_TRANSITIONS["valider"][1] == "VALIDEE"
    assert "SOUMIS" in NOTE_TRANSITIONS["valider"][0]
    assert NOTE_TRANSITIONS["mettre_en_paiement"][1] == "MISE_EN_PAIEMENT"
    assert NOTE_TRANSITIONS["archiver"][1] == "ARCHIVEE"


def test_notes_front_routes():
    from pathlib import Path

    routes = Path(__file__).resolve().parents[2] / "frontend" / "angular20" / "src" / "app" / "app.routes.ts"
    if not routes.is_file():
        import pytest

        pytest.skip("frontend hors contexte")
    text = routes.read_text(encoding="utf-8")
    assert "path: 'notes-frais'" in text
    assert "NotesDashboardComponent" in text
    assert "NotesRapportsComponent" in text
    assert "NotesParametresComponent" in text
