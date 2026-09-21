"""Stock & Fournitures — catalogue, scopes, niveaux."""

from decimal import Decimal
from unittest.mock import MagicMock

from app.data.module_backup_scopes import ESPACE_MODULES, MODULE_BACKUP_SCOPES
from app.data.plateforme_catalogue import FUNCTIONAL_PERMISSIONS, PLATEFORME_ESPACES, PLATEFORME_MODULES
from app.services.mg_stock_service import MgStockService


def test_mg_espace_and_stock_module_in_catalogue():
    espaces = {e["code"]: e for e in PLATEFORME_ESPACES}
    assert "moyens-generaux" in espaces
    assert espaces["moyens-generaux"]["route"] == "/moyens-generaux"
    assert espaces["moyens-generaux"]["statut"] == "actif"

    modules = {m["code"]: m for m in PLATEFORME_MODULES}
    stock = modules["stock-fournitures"]
    assert stock["espace_code"] == "moyens-generaux"
    assert stock["entry_path"] == "/stock-fournitures/dashboard"
    assert stock["statut"] == "actif"
    for code in ("achats-appro", "notes-frais", "contrats-echeances", "archives-mg"):
        assert modules[code]["statut"] == "actif"
        assert modules[code]["espace_code"] == "moyens-generaux"


def test_mg_stock_permissions_in_catalogue():
    codes = {row[0] for row in FUNCTIONAL_PERMISSIONS}
    for p in (
        "mg.stock.view",
        "mg.stock.create",
        "mg.stock.entry",
        "mg.stock.exit",
        "mg.stock.adjust",
        "mg.stock.inventory",
        "mg.stock.approve",
        "mg.stock.export",
    ):
        assert p in codes


def test_mg_stock_backup_scope():
    assert "stock-fournitures" in MODULE_BACKUP_SCOPES
    scope = MODULE_BACKUP_SCOPES["stock-fournitures"]
    assert "mg_articles" in scope["exclusive_tables"]
    assert "mg_demandes_fourniture" in scope["exclusive_tables"]
    assert "mg_inventaires" in scope["exclusive_tables"]
    assert "mg_stock_parametres" in scope["exclusive_tables"]
    assert "users" in scope["shared_dependencies"]
    assert ESPACE_MODULES["moyens-generaux"][0] == "stock-fournitures"


def test_niveau_stock():
    svc = MgStockService(MagicMock())
    article = MagicMock()
    article.stock_actuel = Decimal("0")
    article.stock_min = Decimal("5")
    assert svc.niveau_stock(article) == "epuise"
    article.stock_actuel = Decimal("3")
    assert svc.niveau_stock(article) == "faible"
    article.stock_actuel = Decimal("10")
    assert svc.niveau_stock(article) == "normal"


def test_stock_nav_contract_routes():
    """Routes métier figées sous /stock-fournitures (pas /modules/...)."""
    from pathlib import Path

    routes = Path(__file__).resolve().parents[2] / "frontend" / "angular20" / "src" / "app" / "app.routes.ts"
    if not routes.is_file():
        import pytest

        pytest.skip("frontend hors contexte (image Docker backend)")
    text = routes.read_text(encoding="utf-8")
    assert "path: 'stock-fournitures'" in text
    assert "entrees" in text
    assert "sorties" in text
    assert "inventaires" in text
    assert "alertes" in text
    assert "parametres" in text
    assert "articles/:id" in text
