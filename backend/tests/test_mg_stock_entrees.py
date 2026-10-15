"""Entrée de stock : provenance exclusive, quantité, fournisseur, idempotence (sans DB)."""

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.exceptions import AppError
from app.schemas.mg_stock import EntreeCreate
from app.services import mg_stock_entrees as E


def _entree(**kw) -> EntreeCreate:
    base = {
        "article_id": uuid4(),
        "quantite": 5,
        "provenance_type": "FOURNISSEUR",
        "fournisseur_id": uuid4(),
        "motif_id": uuid4(),
    }
    base.update(kw)
    return EntreeCreate(**base)


def _code(exc: pytest.ExceptionInfo) -> str:
    return exc.value.code


# ------------------------------------------------------------------- provenance
def test_fournisseur_ignore_les_champs_masques():
    f = uuid4()
    p = E.normaliser_provenance(_entree(fournisseur_id=f, departement_id=uuid4(), agence_id=uuid4()))
    assert (p.type, p.fournisseur_id, p.departement_id, p.service_id, p.agence_id) == (
        "FOURNISSEUR", f, None, None, None
    )


def test_retour_departement_ignore_fournisseur_et_agence():
    dep, srv = uuid4(), uuid4()
    p = E.normaliser_provenance(
        _entree(provenance_type="RETOUR_DEPARTEMENT", departement_id=dep, service_id=srv, agence_id=uuid4())
    )
    assert (p.fournisseur_id, p.departement_id, p.service_id, p.agence_id) == (None, dep, srv, None)


def test_retour_agence_ignore_departement_et_service():
    ag = uuid4()
    p = E.normaliser_provenance(
        _entree(provenance_type="RETOUR_AGENCE", agence_id=ag, departement_id=uuid4(), service_id=uuid4())
    )
    assert (p.fournisseur_id, p.departement_id, p.service_id, p.agence_id) == (None, None, None, ag)


def test_autre_ne_garde_aucune_contrepartie():
    p = E.normaliser_provenance(_entree(provenance_type="AUTRE", agence_id=uuid4()))
    assert (p.fournisseur_id, p.departement_id, p.agence_id) == (None, None, None)


@pytest.mark.parametrize(
    "kw, code",
    [
        ({"fournisseur_id": None}, "FOURNISSEUR_OBLIGATOIRE"),
        ({"provenance_type": "RETOUR_DEPARTEMENT"}, "DEPARTEMENT_OBLIGATOIRE"),
        ({"provenance_type": "RETOUR_AGENCE"}, "AGENCE_OBLIGATOIRE"),
    ],
)
def test_provenance_incomplete(kw, code):
    with pytest.raises(AppError) as exc:
        E.normaliser_provenance(_entree(**kw))
    assert _code(exc) == code


def test_provenance_inconnue_refusee_par_le_schema():
    with pytest.raises(ValidationError):
        _entree(provenance_type="ACHAT")


def test_quantite_entiere_pour_article_a_l_unite():
    with pytest.raises(AppError) as exc:
        E.verifier_quantite_entree(Decimal("2.5"), "U")
    assert _code(exc) == "QUANTITE_ENTIERE"
    E.verifier_quantite_entree(Decimal("2.5"), "L")


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
        id=uuid4(), code="PAP-A4", uom="U", stock_actuel=Decimal("0"),
        deleted_at=None, is_active=True, stockable=True,
    )
    for k, v in kw.items():
        setattr(a, k, v)
    return a


def _service(db, *, obs_obligatoire=False):
    svc = E.MgStockEntreeService(db)
    svc._motif = AsyncMock(return_value=SimpleNamespace(
        id=uuid4(), libelle="Achat direct", observation_obligatoire=obs_obligatoire
    ))
    fournisseur = SimpleNamespace(id=uuid4(), raison_sociale="SOMELEC Fournitures")
    svc._fournisseur = AsyncMock(return_value=fournisseur)
    svc._verifier_departement = AsyncMock(return_value=(None, None))
    svc._agence = AsyncMock()
    return svc, fournisseur


@pytest.mark.asyncio
async def test_meme_cle_idempotence_n_incremente_pas_deux_fois():
    existante = SimpleNamespace(id=uuid4())
    db = _db([_article(), existante])
    with patch.object(E.MgStockService, "_apply_mouvement", new=AsyncMock()) as apply:
        mvt, rejoue = await E.MgStockEntreeService(db).creer(_entree(), MagicMock(), cle_idempotence="k-1")
    assert rejoue is True and mvt is existante
    apply.assert_not_awaited()


@pytest.mark.asyncio
async def test_article_desactive_refuse():
    with pytest.raises(AppError) as exc:
        await E.MgStockEntreeService(_db([_article(is_active=False)])).creer(_entree(), MagicMock())
    assert _code(exc) == "ARTICLE_INACTIF"


@pytest.mark.asyncio
async def test_entree_fournisseur_enregistre_piece_et_incremente_via_apply():
    article = _article()
    db = _db([article, None])
    svc, fournisseur = _service(db)
    user = MagicMock()
    mvt = SimpleNamespace(id=uuid4())
    with patch.object(E.MgStockService, "_apply_mouvement", new=AsyncMock(return_value=mvt)) as apply:
        res, rejoue = await svc.creer(
            _entree(quantite=12, piece_reference="  BL 2026 / 041 ", remis_par=" Livreur  SOMELEC "),
            user, cle_idempotence="k-2",
        )
    assert res is mvt and rejoue is False
    kw = apply.await_args.kwargs
    assert kw["type_mouvement"] == "ENTREE" and kw["quantite"] == Decimal("12")
    assert kw["agence_id"] is None and kw["departement"] is None
    assert kw["initiateur"] is user
    assert kw["source_type"] == E.SOURCE_ENTREE
    extra = kw["extra"]
    assert extra["provenance_type"] == "FOURNISSEUR"
    assert extra["fournisseur_id"] == fournisseur.id
    assert extra["piece_reference"] == "BL 2026 / 041"
    assert extra["demandeur_nom"] == "Livreur SOMELEC"
    assert extra["org_entite_id"] is None and extra["service_id"] is None
    assert extra["cle_idempotence"] == "k-2"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_provenance_autre_exige_une_observation():
    article = _article()
    svc, _ = _service(_db([article]))
    with pytest.raises(AppError) as exc:
        await svc.creer(_entree(provenance_type="AUTRE", observation=" "), MagicMock())
    assert _code(exc) == "OBSERVATION_OBLIGATOIRE"


@pytest.mark.asyncio
async def test_stock_modifie_depuis_l_ouverture():
    article = _article(stock_actuel=Decimal("3"))
    svc, _ = _service(_db([article]))
    with pytest.raises(AppError) as exc:
        await svc.creer(_entree(stock_attendu=0), MagicMock())
    assert _code(exc) == "STOCK_MODIFIE"


@pytest.mark.asyncio
async def test_motif_de_sortie_refuse_pour_une_entree():
    db = _db([])
    db.get = AsyncMock(return_value=SimpleNamespace(
        id=uuid4(), libelle="Consommation", deleted_at=None, is_active=True, sens="SORTIE"
    ))
    with pytest.raises(AppError) as exc:
        await E.MgStockEntreeService(db)._motif(uuid4(), "ENTREE")
    assert _code(exc) == "MOTIF_INVALIDE"


@pytest.mark.asyncio
async def test_fournisseur_desactive_refuse():
    db = _db([])
    db.get = AsyncMock(return_value=SimpleNamespace(id=uuid4(), deleted_at=None, is_active=False))
    with pytest.raises(AppError) as exc:
        await E.MgStockEntreeService(db)._fournisseur(uuid4())
    assert _code(exc) == "FOURNISSEUR_INVALIDE"


def test_migration_contrainte_provenance():
    src = (Path(__file__).parents[1] / "alembic" / "versions" / "20261015_mg_stock_entrees.py").read_text(
        encoding="utf-8"
    )
    assert "ck_mg_stock_mvt_provenance" in src
    assert 'down_revision: Union[str, None] = "20261015_mg_stock_sorties"' in src
