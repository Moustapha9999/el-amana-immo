"""Stock — périodes, écarts, report, idempotence (tests métier 1–10)."""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.data.plateforme_catalogue import FUNCTIONAL_PERMISSIONS, ROLE_PERMISSIONS
from app.services.mg_stock_periodes import (
    compute_theorique,
    month_bounds,
    nature_ecart,
    next_year_month,
    periode_libelle,
    stock_final_from_solde,
)
from app.services.mg_stock_service import MgStockService


def test_formule_stock_theorique_cas_1():
    """TEST 1 : 100 + 50 − 30 + 0 = 120."""
    assert compute_theorique(Decimal("100"), Decimal("50"), Decimal("30"), Decimal("0")) == Decimal("120")


def test_formule_inventaire_cas_2():
    """TEST 2 : théorique 120, physique 115, écart −5, final 115."""
    theo = Decimal("120")
    phys = Decimal("115")
    ecart = phys - theo
    assert ecart == Decimal("-5")
    assert nature_ecart(ecart) == "MANQUANT"
    ajustement = ecart
    final = theo + ajustement
    assert final == Decimal("115")


def test_report_periode_cas_3():
    """TEST 3 : stock final sept. = stock initial oct. sans ENTREE."""
    final_sept = Decimal("115")
    initial_oct = final_sept
    entrees = sorties = ajustements = Decimal("0")
    assert compute_theorique(initial_oct, entrees, sorties, ajustements) == Decimal("115")


def test_entree_octobre_cas_4():
    assert compute_theorique(Decimal("115"), Decimal("20"), Decimal("0"), Decimal("0")) == Decimal("135")


def test_sortie_octobre_cas_5():
    assert compute_theorique(Decimal("115"), Decimal("20"), Decimal("15"), Decimal("0")) == Decimal("120")


def test_nature_ecarts():
    assert nature_ecart(Decimal("0")) == "CONFORME"
    assert nature_ecart(Decimal("3")) == "SURPLUS"
    assert nature_ecart(Decimal("-2")) == "MANQUANT"
    assert nature_ecart(None) is None


def test_next_month_et_libelle():
    assert next_year_month(2026, 9) == (2026, 10)
    assert next_year_month(2026, 12) == (2027, 1)
    assert periode_libelle(2026, 9) == "Septembre 2026"
    debut, fin = month_bounds(2026, 9)
    assert str(debut) == "2026-09-01"
    assert str(fin) == "2026-09-30"


def test_stock_final_prefere_physique():
    solde = SimpleNamespace(stock_physique=Decimal("115"), stock_theorique=Decimal("120"))
    assert stock_final_from_solde(solde) == Decimal("115")
    solde2 = SimpleNamespace(stock_physique=None, stock_theorique=Decimal("120"))
    assert stock_final_from_solde(solde2) == Decimal("120")


@pytest.mark.asyncio
async def test_servir_deuxieme_clic_bloque_cas_6():
    db = MagicMock()
    svc = MgStockService(db)
    demande = SimpleNamespace(id=uuid4(), statut="SERVIE", lignes=[])
    svc.get_demande = AsyncMock(return_value=demande)
    svc._sortie_from_demande = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await svc.transition_demande(demande.id, "servir", MagicMock(), None)
    assert exc.value.status_code == 400
    svc._sortie_from_demande.assert_not_awaited()


@pytest.mark.asyncio
async def test_reception_credit_qte_recue_cas_7():
    from app.schemas.mg_stock import ReceptionBcIn, ReceptionLigneIn

    db = MagicMock()
    svc = MgStockService(db)
    article = SimpleNamespace(id=uuid4(), code="A4", deleted_at=None, agence_id=None, stockable=True, stock_actuel=Decimal("0"))
    ligne = SimpleNamespace(
        id=uuid4(),
        description="Papier",
        quantite=Decimal("200"),
        quantite_recue=Decimal("0"),
        article_id=article.id,
    )
    bon = SimpleNamespace(id=uuid4(), reference="BC-1", statut="VALIDE", deleted_at=None, lignes=[ligne])
    db.scalar = AsyncMock(side_effect=[bon, article, bon])
    db.commit = AsyncMock()
    svc._apply_mouvement = AsyncMock()
    data = ReceptionBcIn(lignes=[ReceptionLigneIn(ligne_id=ligne.id, quantite=Decimal("180"))])
    result = await svc.receive_from_bc(bon.id, data, MagicMock())
    assert result["mouvements_count"] == 1
    assert ligne.quantite_recue == Decimal("180")
    assert svc._apply_mouvement.await_args.kwargs["quantite"] == Decimal("180")


@pytest.mark.asyncio
async def test_double_reception_bloquee_cas_8():
    from app.schemas.mg_stock import ReceptionBcIn, ReceptionLigneIn

    db = MagicMock()
    svc = MgStockService(db)
    article_id = uuid4()
    ligne = SimpleNamespace(
        id=uuid4(),
        description="Papier",
        quantite=Decimal("200"),
        quantite_recue=Decimal("180"),
        article_id=article_id,
    )
    bon = SimpleNamespace(id=uuid4(), reference="BC-1", statut="PARTIEL", deleted_at=None, lignes=[ligne])
    db.scalar = AsyncMock(return_value=bon)
    data = ReceptionBcIn(lignes=[ReceptionLigneIn(ligne_id=ligne.id, quantite=Decimal("30"))])
    with pytest.raises(HTTPException) as exc:
        await svc.receive_from_bc(bon.id, data, MagicMock())
    assert exc.value.status_code == 400
    assert "reste" in exc.value.detail.lower()


def test_permissions_periode_au_catalogue_cas_9_10():
    codes = {row[0] for row in FUNCTIONAL_PERMISSIONS}
    assert "mg.stock.period.close" in codes
    assert "mg.stock.period.reopen" in codes
    assert "mg.stock.period.reopen" in ROLE_PERMISSIONS["stock-fournitures.admin"]
    assert "mg.stock.period.reopen" not in ROLE_PERMISSIONS["stock-fournitures.magasinier"]
    assert "mg.stock.period.close" not in ROLE_PERMISSIONS["stock-fournitures.lecteur"]


def test_backup_scope_periodes():
    from app.data.module_backup_scopes import MODULE_BACKUP_SCOPES

    tables = MODULE_BACKUP_SCOPES["stock-fournitures"]["exclusive_tables"]
    assert "mg_stock_periodes" in tables
    assert "mg_stock_soldes" in tables
