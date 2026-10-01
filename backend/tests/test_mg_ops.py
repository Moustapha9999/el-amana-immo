"""Tests smoke Moyens Généraux Phase 2 (catalogue + imports)."""

from app.data.plateforme_catalogue import FUNCTIONAL_PERMISSIONS, PLATEFORME_MODULES
from app.models.mg_ops import MgBonCommande, MgContrat, MgNoteFrais


def test_mg_phase2_modules_actifs():
    by_code = {m["code"]: m for m in PLATEFORME_MODULES}
    for code in ("achats-appro", "notes-frais", "contrats-echeances", "archives-mg"):
        assert by_code[code]["statut"] == "actif"
        assert by_code[code]["espace_code"] == "moyens-generaux"


def test_mg_phase2_permissions():
    codes = {row[0] for row in FUNCTIONAL_PERMISSIONS}
    for code in (
        "mg.purchase.view",
        "mg.purchase.create",
        "mg.purchase.approve",
        "mg.notes.view",
        "mg.notes.create",
        "mg.notes.approve",
        "mg.notes.control",
        "mg.notes.payment",
        "mg.notes.export",
        "mg.contrats.view",
        "mg.contrats.manage",
        "mg.archives.view",
    ):
        assert code in codes


def test_mg_ops_models_importable():
    assert MgBonCommande.__tablename__ == "mg_bons_commande"
    assert MgNoteFrais.__tablename__ == "mg_notes_frais"
    assert MgContrat.__tablename__ == "mg_contrats"
