"""Stock MG — réception BC + workflow demandes (unitaires, sans DB)."""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.schemas.mg_stock import ReceptionBcIn, ReceptionLigneIn
from app.services.mg_stock_service import DEMANDE_STATUTS, MgStockService


def _user():
    u = MagicMock()
    u.id = uuid4()
    u.full_name = "Testeur MG"
    return u


def _ligne(
    *,
    quantite: Decimal = Decimal("10"),
    quantite_recue: Decimal = Decimal("0"),
    article_id=None,
    description: str = "Article test",
):
    return SimpleNamespace(
        id=uuid4(),
        description=description,
        quantite=quantite,
        quantite_recue=quantite_recue,
        article_id=article_id,
    )


def _bon(*, statut: str = "VALIDE", lignes=None):
    return SimpleNamespace(
        id=uuid4(),
        reference="BC-TEST-001",
        statut=statut,
        deleted_at=None,
        lignes=lignes or [],
    )


def _article(*, stock: Decimal = Decimal("0")):
    return SimpleNamespace(
        id=uuid4(),
        code="ART-001",
        deleted_at=None,
        agence_id=None,
        stock_actuel=stock,
    )


@pytest.mark.asyncio
async def test_receive_from_bc_refuse_statut_brouillon():
    db = MagicMock()
    svc = MgStockService(db)
    bon = _bon(statut="BROUILLON", lignes=[])
    db.scalar = AsyncMock(return_value=bon)
    data = ReceptionBcIn(
        lignes=[ReceptionLigneIn(ligne_id=uuid4(), quantite=Decimal("1"))]
    )
    with pytest.raises(HTTPException) as exc:
        await svc.receive_from_bc(bon.id, data, _user())
    assert exc.value.status_code == 400
    assert "incompatible" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_receive_from_bc_partiel():
    db = MagicMock()
    svc = MgStockService(db)
    article = _article()
    ligne = _ligne(quantite=Decimal("10"), article_id=article.id)
    bon = _bon(statut="VALIDE", lignes=[ligne])
    # 1) load bon  2) lock article  3) reload bon
    db.scalar = AsyncMock(side_effect=[bon, article, bon])
    db.commit = AsyncMock()
    svc._apply_mouvement = AsyncMock()

    data = ReceptionBcIn(
        lignes=[ReceptionLigneIn(ligne_id=ligne.id, quantite=Decimal("4"))]
    )
    result = await svc.receive_from_bc(bon.id, data, _user())

    assert result["mouvements_count"] == 1
    assert ligne.quantite_recue == Decimal("4")
    assert bon.statut == "PARTIEL"
    svc._apply_mouvement.assert_awaited_once()
    call_kw = svc._apply_mouvement.await_args.kwargs
    assert call_kw["type_mouvement"] == "ENTREE"
    assert call_kw["source_type"] == "bon_commande"
    assert call_kw["source_id"] == bon.id
    assert call_kw["quantite"] == Decimal("4")


@pytest.mark.asyncio
async def test_receive_from_bc_complet_statut_recu():
    db = MagicMock()
    svc = MgStockService(db)
    article = _article()
    ligne = _ligne(quantite=Decimal("5"), quantite_recue=Decimal("2"), article_id=article.id)
    bon = _bon(statut="PARTIEL", lignes=[ligne])
    db.scalar = AsyncMock(side_effect=[bon, article, bon])
    db.commit = AsyncMock()
    svc._apply_mouvement = AsyncMock()

    data = ReceptionBcIn(
        lignes=[ReceptionLigneIn(ligne_id=ligne.id, quantite=Decimal("3"))]
    )
    result = await svc.receive_from_bc(bon.id, data, _user())

    assert result["mouvements_count"] == 1
    assert ligne.quantite_recue == Decimal("5")
    assert bon.statut == "RECU"


@pytest.mark.asyncio
async def test_receive_from_bc_refuse_quantite_superieure_reste():
    db = MagicMock()
    svc = MgStockService(db)
    article = _article()
    ligne = _ligne(quantite=Decimal("10"), quantite_recue=Decimal("8"), article_id=article.id)
    bon = _bon(statut="PARTIEL", lignes=[ligne])
    db.scalar = AsyncMock(return_value=bon)

    data = ReceptionBcIn(
        lignes=[ReceptionLigneIn(ligne_id=ligne.id, quantite=Decimal("5"))]
    )
    with pytest.raises(HTTPException) as exc:
        await svc.receive_from_bc(bon.id, data, _user())
    assert exc.value.status_code == 400
    assert "reste" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_receive_from_bc_exige_article():
    db = MagicMock()
    svc = MgStockService(db)
    ligne = _ligne(article_id=None)
    bon = _bon(statut="VALIDE", lignes=[ligne])
    db.scalar = AsyncMock(return_value=bon)

    data = ReceptionBcIn(
        lignes=[ReceptionLigneIn(ligne_id=ligne.id, quantite=Decimal("1"))]
    )
    with pytest.raises(HTTPException) as exc:
        await svc.receive_from_bc(bon.id, data, _user())
    assert exc.value.status_code == 400
    assert "article" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_visa_mg_passe_en_preparation_sans_sortie():
    db = MagicMock()
    svc = MgStockService(db)
    ligne = SimpleNamespace(
        designation="Stylos",
        quantite_demandee=Decimal("3"),
        quantite_accordee=None,
    )
    demande = SimpleNamespace(
        id=uuid4(),
        statut="VISA_AGENCE",
        lignes=[ligne],
        visa_mg_at=None,
        visa_mg_by=None,
    )
    svc.get_demande = AsyncMock(return_value=demande)
    svc._sortie_from_demande = AsyncMock()
    db.commit = AsyncMock()

    out = await svc.transition_demande(demande.id, "visa_mg", _user(), None)
    assert out.statut == "PREPARATION"
    assert ligne.quantite_accordee == Decimal("3")
    svc._sortie_from_demande.assert_not_awaited()


@pytest.mark.asyncio
async def test_servir_depuis_preparation_fait_sortie():
    db = MagicMock()
    svc = MgStockService(db)
    demande = SimpleNamespace(id=uuid4(), statut="PREPARATION", lignes=[])
    svc.get_demande = AsyncMock(return_value=demande)
    svc._sortie_from_demande = AsyncMock()
    db.commit = AsyncMock()

    out = await svc.transition_demande(demande.id, "servir", _user(), None)
    assert out.statut == "SERVIE"
    svc._sortie_from_demande.assert_awaited_once()


@pytest.mark.asyncio
async def test_servir_compat_accordee():
    db = MagicMock()
    svc = MgStockService(db)
    demande = SimpleNamespace(id=uuid4(), statut="ACCORDEE", lignes=[])
    svc.get_demande = AsyncMock(return_value=demande)
    svc._sortie_from_demande = AsyncMock()
    db.commit = AsyncMock()

    out = await svc.transition_demande(demande.id, "servir", _user(), None)
    assert out.statut == "SERVIE"


@pytest.mark.asyncio
async def test_archiver_depuis_servie():
    db = MagicMock()
    svc = MgStockService(db)
    demande = SimpleNamespace(id=uuid4(), statut="SERVIE", lignes=[])
    svc.get_demande = AsyncMock(return_value=demande)
    db.commit = AsyncMock()

    out = await svc.transition_demande(demande.id, "archiver", _user(), None)
    assert out.statut == "ARCHIVEE"


@pytest.mark.asyncio
async def test_servir_refuse_si_brouillon():
    db = MagicMock()
    svc = MgStockService(db)
    demande = SimpleNamespace(id=uuid4(), statut="BROUILLON", lignes=[])
    svc.get_demande = AsyncMock(return_value=demande)

    with pytest.raises(HTTPException) as exc:
        await svc.transition_demande(demande.id, "servir", _user(), None)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_archiver_refuse_si_preparation():
    db = MagicMock()
    svc = MgStockService(db)
    demande = SimpleNamespace(id=uuid4(), statut="PREPARATION", lignes=[])
    svc.get_demande = AsyncMock(return_value=demande)

    with pytest.raises(HTTPException) as exc:
        await svc.transition_demande(demande.id, "archiver", _user(), None)
    assert exc.value.status_code == 400


def test_demande_statuts_incluent_workflow_v3():
    for s in ("PREPARATION", "SERVIE", "ARCHIVEE", "ACCORDEE", "CLOTUREE"):
        assert s in DEMANDE_STATUTS


def test_stock_routes_fiche_article():
    from pathlib import Path

    routes = Path(__file__).resolve().parents[2] / "frontend" / "angular20" / "src" / "app" / "app.routes.ts"
    if not routes.is_file():
        pytest.skip("frontend hors contexte (image Docker backend)")
    text = routes.read_text(encoding="utf-8")
    assert "articles/:id" in text
    assert "StockArticleFicheComponent" in text
