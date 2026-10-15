"""Sortie de stock : destination exclusive, quantité, demandeur, idempotence (sans DB)."""

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.exceptions import AppError
from app.schemas.mg_stock import SortieCreate
from app.services import mg_stock_sorties as S


def _sortie(**kw) -> SortieCreate:
    base = {
        "article_id": uuid4(),
        "quantite": 1,
        "destination_type": "DEPARTEMENT",
        "departement_id": uuid4(),
        "motif_id": uuid4(),
        "demandeur_nom": "Mohamed Salem",
    }
    base.update(kw)
    return SortieCreate(**base)


def _code(exc: pytest.ExceptionInfo) -> str:
    return exc.value.code


# ------------------------------------------------------------------ destination
def test_destination_departement_ignore_agence_masquee():
    dep, srv, ag = uuid4(), uuid4(), uuid4()
    d = S.normaliser_destination(_sortie(departement_id=dep, service_id=srv, agence_id=ag))
    assert (d.type, d.departement_id, d.service_id, d.agence_id) == ("DEPARTEMENT", dep, srv, None)


def test_destination_agence_ignore_departement_et_service_masques():
    ag = uuid4()
    d = S.normaliser_destination(
        _sortie(destination_type="AGENCE", agence_id=ag, departement_id=uuid4(), service_id=uuid4())
    )
    assert (d.type, d.departement_id, d.service_id, d.agence_id) == ("AGENCE", None, None, ag)


def test_destination_departement_obligatoire():
    with pytest.raises(AppError) as exc:
        S.normaliser_destination(_sortie(departement_id=None))
    assert _code(exc) == "DEPARTEMENT_OBLIGATOIRE"


def test_destination_agence_obligatoire():
    with pytest.raises(AppError) as exc:
        S.normaliser_destination(_sortie(destination_type="AGENCE", departement_id=None))
    assert _code(exc) == "AGENCE_OBLIGATOIRE"


def test_destination_type_inconnu_refuse_par_le_schema():
    with pytest.raises(ValidationError):
        _sortie(destination_type="DIRECTION")


# --------------------------------------------------------------------- quantité
@pytest.mark.parametrize("q", [0, -1, "0"])
def test_quantite_nulle_ou_negative_refusee_par_le_schema(q):
    with pytest.raises(ValidationError):
        _sortie(quantite=q)


def test_quantite_entiere_pour_article_a_l_unite():
    with pytest.raises(AppError) as exc:
        S.verifier_quantite(Decimal("1.5"), "U", Decimal("10"))
    assert _code(exc) == "QUANTITE_ENTIERE"
    S.verifier_quantite(Decimal("1.5"), "kg", Decimal("10"))


def test_stock_insuffisant_message_metier():
    with pytest.raises(AppError) as exc:
        S.verifier_quantite(Decimal("6"), "U", Decimal("4"))
    assert _code(exc) == "STOCK_INSUFFISANT"
    assert exc.value.message == "Stock insuffisant. Stock disponible : 4 unités. Quantité demandée : 6 unités."


def test_quantite_egale_au_stock_acceptee():
    S.verifier_quantite(Decimal("4"), "U", Decimal("4"))


def test_demandeur_libre_parametre():
    assert S.demandeur_libre_autorise(None) is True
    assert S.demandeur_libre_autorise("1") is True
    assert S.demandeur_libre_autorise("0") is False
    assert S.demandeur_libre_autorise("non") is False


# ------------------------------------------------------------------- service DB
def _db(scalars: list):
    db = MagicMock()
    db.scalar = AsyncMock(side_effect=scalars)
    db.get = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


def _article(**kw):
    a = SimpleNamespace(
        id=uuid4(), code="PAP-A4", uom="U", stock_actuel=Decimal("10"),
        deleted_at=None, is_active=True, stockable=True,
    )
    for k, v in kw.items():
        setattr(a, k, v)
    return a


@pytest.mark.asyncio
async def test_meme_cle_idempotence_ne_decremente_pas_deux_fois():
    existante = SimpleNamespace(id=uuid4(), reference="SOR-2026-00001")
    db = _db([_article(), existante])
    with patch.object(S.MgStockService, "_apply_mouvement", new=AsyncMock()) as apply:
        mvt, rejoue = await S.MgStockSortieService(db).creer(_sortie(), MagicMock(), cle_idempotence="bea-1")
    assert rejoue is True and mvt is existante
    apply.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_article_desactive_refuse():
    db = _db([_article(is_active=False)])
    with pytest.raises(AppError) as exc:
        await S.MgStockSortieService(db).creer(_sortie(), MagicMock())
    assert _code(exc) == "ARTICLE_INACTIF"


def _service_valide(db, article):
    svc = S.MgStockSortieService(db)
    svc._motif = AsyncMock(return_value=SimpleNamespace(id=uuid4(), libelle="Consommation courante",
                                                        observation_obligatoire=False))
    departement = SimpleNamespace(id=uuid4(), libelle="Département Comptable")
    svc._verifier_departement = AsyncMock(return_value=(departement, None))
    svc._demandeur = AsyncMock(return_value=(None, "Mohamed Salem"))
    return svc, departement


@pytest.mark.asyncio
async def test_stock_modifie_depuis_l_ouverture_du_formulaire():
    article = _article(stock_actuel=Decimal("8"))
    svc, _ = _service_valide(_db([article]), article)
    with pytest.raises(AppError) as exc:
        await svc.creer(_sortie(stock_attendu=10), MagicMock())
    assert _code(exc) == "STOCK_MODIFIE"


@pytest.mark.asyncio
async def test_sortie_departement_enregistre_destination_demandeur_et_executant():
    article = _article()
    db = _db([article, None])
    svc, departement = _service_valide(db, article)
    user = MagicMock()
    mvt = SimpleNamespace(id=uuid4())
    with patch.object(S.MgStockService, "_apply_mouvement", new=AsyncMock(return_value=mvt)) as apply:
        res, rejoue = await svc.creer(_sortie(quantite=10, agence_id=uuid4()), user, cle_idempotence="bea-2")
    assert res is mvt and rejoue is False
    kw = apply.await_args.kwargs
    assert kw["type_mouvement"] == "SORTIE" and kw["quantite"] == Decimal("10")
    assert kw["agence_id"] is None
    assert kw["initiateur"] is user
    assert kw["departement"] == departement.libelle
    assert kw["extra"]["destination_type"] == "DEPARTEMENT"
    assert kw["extra"]["org_entite_id"] == departement.id
    assert kw["extra"]["demandeur_nom"] == "Mohamed Salem"
    assert kw["extra"]["cle_idempotence"] == "bea-2"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_observation_obligatoire_selon_motif():
    article = _article()
    svc, _ = _service_valide(_db([article]), article)
    svc._motif = AsyncMock(return_value=SimpleNamespace(id=uuid4(), libelle="Autre motif",
                                                        observation_obligatoire=True))
    with pytest.raises(AppError) as exc:
        await svc.creer(_sortie(observation="  "), MagicMock())
    assert _code(exc) == "OBSERVATION_OBLIGATOIRE"


@pytest.mark.asyncio
async def test_demandeur_libre_desactive_exige_un_utilisateur_reference():
    db = _db(["0"])
    with pytest.raises(AppError) as exc:
        await S.MgStockSortieService(db)._demandeur(_sortie(demandeur_nom="Personne Externe"))
    assert _code(exc) == "DEMANDEUR_REFERENCE_REQUIS"


@pytest.mark.asyncio
async def test_demandeur_obligatoire():
    with pytest.raises(AppError) as exc:
        await S.MgStockSortieService(_db([]))._demandeur(_sortie(demandeur_nom=" "))
    assert _code(exc) == "DEMANDEUR_OBLIGATOIRE"


@pytest.mark.asyncio
async def test_service_hors_departement_refuse():
    dep = SimpleNamespace(id=uuid4(), libelle="Département Comptable", deleted_at=None, is_active=True,
                          type_entite="DEPARTEMENT")
    srv = SimpleNamespace(id=uuid4(), libelle="Service Crédit", deleted_at=None, is_active=True,
                          type_entite="SERVICE")
    db = _db([])
    db.get = AsyncMock(side_effect=[dep, srv])
    dest = S.Destination("DEPARTEMENT", dep.id, srv.id, None)
    with patch.object(S.org, "sous_arbre", new=AsyncMock(return_value={dep.id})):
        with pytest.raises(AppError) as exc:
            await S.MgStockSortieService(db)._verifier_departement(dest)
    assert _code(exc) == "SERVICE_HORS_DEPARTEMENT"


# ------------------------------------------------------------- garanties en base
def test_migration_garantit_l_exclusion_des_destinations():
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "20261015_mg_stock_sorties.py"
    text = path.read_text(encoding="utf-8")
    assert "ck_mg_stock_mvt_destination" in text
    assert "destination_type = 'DEPARTEMENT' AND org_entite_id IS NOT NULL AND agence_id IS NULL" in text
    assert "destination_type = 'AGENCE' AND agence_id IS NOT NULL AND org_entite_id IS NULL" in text
    assert "uq_mg_stock_mouvements_cle_idempotence" in text
