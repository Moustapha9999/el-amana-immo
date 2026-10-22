"""Option « Autre » pour le département et le service (sorties et retours d'entrée), sans DB."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.exceptions import AppError
from app.schemas.mg_stock import EntreeCreate, SortieCreate
from app.services import mg_stock_entrees as E
from app.services import mg_stock_sorties as S
from app.services.mg_stock_reporting import LIBELLE_SAISIE_LIBRE, agreger_consommation


def _sortie(**kw) -> SortieCreate:
    base = {
        "article_id": uuid4(),
        "quantite": 1,
        "destination_type": "DEPARTEMENT",
        "motif_id": uuid4(),
        "demandeur_nom": "Mohamed Salem",
    }
    base.update(kw)
    return SortieCreate(**base)


def _code(exc) -> str:
    return exc.value.code


# ------------------------------------------------------------ normalisation
def test_departement_et_service_du_referentiel_inchanges():
    dep, srv = uuid4(), uuid4()
    d = S.normaliser_destination(_sortie(departement_id=dep, service_id=srv))
    assert (d.departement_id, d.service_id, d.departement_autre, d.service_autre) == (dep, srv, None, None)


def test_autre_departement_nettoye():
    d = S.normaliser_destination(_sortie(departement_autre="  Cellule   Projets  BEA "))
    assert d.departement_id is None and d.departement_autre == "Cellule Projets BEA"


def test_autre_service_avec_departement_du_referentiel():
    dep = uuid4()
    d = S.normaliser_destination(_sortie(departement_id=dep, service_autre=" Pool  courrier "))
    assert (d.departement_id, d.service_id, d.service_autre) == (dep, None, "Pool courrier")


def test_autre_pour_les_deux_champs():
    d = S.normaliser_destination(_sortie(departement_autre="Cellule Projets", service_autre="Pool A"))
    assert (d.departement_id, d.service_id, d.departement_autre, d.service_autre) == (
        None, None, "Cellule Projets", "Pool A",
    )


@pytest.mark.parametrize("valeur", ["", "   ", "\t\n"])
def test_autre_departement_vide_refuse(valeur):
    with pytest.raises(AppError) as exc:
        S.normaliser_destination(_sortie(departement_autre=valeur))
    assert _code(exc) == "DEPARTEMENT_AUTRE_VIDE"


def test_autre_service_vide_refuse():
    with pytest.raises(AppError) as exc:
        S.normaliser_destination(_sortie(departement_id=uuid4(), service_autre="  "))
    assert _code(exc) == "SERVICE_AUTRE_VIDE"


def test_liste_et_autre_ensemble_refuses():
    with pytest.raises(AppError) as exc:
        S.normaliser_destination(_sortie(departement_id=uuid4(), departement_autre="X"))
    assert _code(exc) == "DEPARTEMENT_AUTRE_AMBIGU"
    with pytest.raises(AppError) as exc:
        S.normaliser_destination(_sortie(departement_id=uuid4(), service_id=uuid4(), service_autre="Y"))
    assert _code(exc) == "SERVICE_AUTRE_AMBIGU"


def test_service_du_referentiel_refuse_sous_un_departement_saisi():
    with pytest.raises(AppError) as exc:
        S.normaliser_destination(_sortie(departement_autre="Cellule Projets", service_id=uuid4()))
    assert _code(exc) == "SERVICE_HORS_DEPARTEMENT"


def test_departement_toujours_obligatoire():
    with pytest.raises(AppError) as exc:
        S.normaliser_destination(_sortie())
    assert _code(exc) == "DEPARTEMENT_OBLIGATOIRE"


def test_destination_agence_ignore_les_saisies_autre_masquees():
    ag = uuid4()
    d = S.normaliser_destination(
        _sortie(destination_type="AGENCE", agence_id=ag, departement_autre="X", service_autre="Y")
    )
    assert (d.agence_id, d.departement_autre, d.service_autre) == (ag, None, None)


def test_longueur_maximale_par_le_schema():
    with pytest.raises(ValidationError):
        _sortie(departement_autre="x" * 121)


def test_retour_departement_autre_en_entree():
    data = EntreeCreate(
        article_id=uuid4(), quantite=1, provenance_type="RETOUR_DEPARTEMENT", motif_id=uuid4(),
        departement_autre=" Cellule  Projets ", service_autre="Pool A",
    )
    p = E.normaliser_provenance(data)
    assert (p.departement_id, p.departement_autre, p.service_autre) == (None, "Cellule Projets", "Pool A")


# ------------------------------------------------------ référentiel non modifié
def _db(scalars=None):
    db = MagicMock()
    db.scalar = AsyncMock(side_effect=scalars or [])
    db.get = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.mark.asyncio
async def test_autre_deja_dans_le_referentiel_refuse():
    existante = SimpleNamespace(libelle="Département Comptable")
    db = _db([uuid4()])
    db.get = AsyncMock(return_value=existante)
    dest = S.Destination("DEPARTEMENT", None, None, None, "departement comptable", None)
    with pytest.raises(AppError) as exc:
        await S.MgStockSortieService(db)._verifier_departement(dest)
    assert _code(exc) == "DEPARTEMENT_EXISTANT"
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_autre_inconnu_accepte_sans_creer_d_entite():
    db = _db([None, None])
    dest = S.Destination("DEPARTEMENT", None, None, None, "Cellule Projets", "Pool A")
    assert await S.MgStockSortieService(db)._verifier_departement(dest) == (None, None)
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_sortie_autre_enregistre_libelles_et_drapeaux():
    article = SimpleNamespace(id=uuid4(), code="PAP-A4", uom="U", stock_actuel=Decimal("10"),
                              deleted_at=None, is_active=True, stockable=True)
    db = _db([article])
    svc = S.MgStockSortieService(db)
    svc._motif = AsyncMock(return_value=SimpleNamespace(id=uuid4(), libelle="Consommation",
                                                        observation_obligatoire=False))
    svc._verifier_departement = AsyncMock(return_value=(None, None))
    svc._demandeur = AsyncMock(return_value=(None, "Mohamed Salem"))
    with patch.object(S.MgStockService, "_apply_mouvement", new=AsyncMock(return_value=SimpleNamespace())) as apply:
        await svc.creer(_sortie(departement_autre="Cellule Projets", service_autre="Pool A"), MagicMock())
    kw = apply.await_args.kwargs
    assert kw["departement"] == "Cellule Projets"
    assert kw["extra"]["org_entite_id"] is None and kw["extra"]["service_id"] is None
    assert kw["extra"]["departement_autre"] is True and kw["extra"]["service_autre"] is True
    assert kw["extra"]["service_libelle"] == "Pool A"


@pytest.mark.asyncio
async def test_sortie_referentiel_drapeaux_a_faux():
    article = SimpleNamespace(id=uuid4(), code="PAP-A4", uom="U", stock_actuel=Decimal("10"),
                              deleted_at=None, is_active=True, stockable=True)
    db = _db([article])
    svc = S.MgStockSortieService(db)
    svc._motif = AsyncMock(return_value=SimpleNamespace(id=uuid4(), libelle="Consommation",
                                                        observation_obligatoire=False))
    dep = SimpleNamespace(id=uuid4(), libelle="Département Comptable")
    svc._verifier_departement = AsyncMock(return_value=(dep, None))
    svc._demandeur = AsyncMock(return_value=(None, "Mohamed Salem"))
    with patch.object(S.MgStockService, "_apply_mouvement", new=AsyncMock(return_value=SimpleNamespace())) as apply:
        await svc.creer(_sortie(departement_id=dep.id), MagicMock())
    extra = apply.await_args.kwargs["extra"]
    assert (extra["departement_autre"], extra["service_autre"], extra["service_libelle"]) == (False, False, None)


# ---------------------------------------------------------------- restitution
def _ligne(**kw):
    base = {
        "destination_type": "DEPARTEMENT", "org_entite_id": None, "service_id": None, "agence_id": None,
        "demandeur_id": None, "demandeur_nom": "X", "article_id": uuid4(), "article_code": "A",
        "article": "Article", "departement": "Cellule Projets", "quantite": Decimal("2"), "nb": 1,
        "derniere": None, "departement_autre": True, "service_autre": True, "service_libelle": "Pool A",
    }
    base.update(kw)
    return base


def test_rapport_par_departement_garde_la_saisie_autre():
    rows, _ = agreger_consommation([_ligne()], axe="departement", detail=False, entites={}, agences={}, users={})
    assert len(rows) == 1
    assert LIBELLE_SAISIE_LIBRE in str(rows[0]) and "Cellule Projets" in str(rows[0])


def test_rapport_par_service_garde_la_saisie_autre():
    rows, _ = agreger_consommation([_ligne()], axe="service", detail=False, entites={}, agences={}, users={})
    assert len(rows) == 1 and "Pool A" in str(rows[0])


def test_export_mouvements_signale_la_saisie_autre():
    from app.api.v1.endpoints.mg_stock import _destination_export

    assert _destination_export({"destination_libelle": "Cellule Projets › Pool A", "departement_autre": True}) == (
        "Cellule Projets › Pool A (saisie « Autre »)"
    )
    assert _destination_export({"destination_libelle": "Département Comptable"}) == "Département Comptable"


def test_migration_autorise_autre_sans_org_entite_uniquement_avec_libelle():
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "20261022_mg_stock_alertes.py"
    text = path.read_text(encoding="utf-8")
    assert "(departement_autre AND btrim(COALESCE(departement, '')) <> '')" in text
    assert "ck_mg_stock_mvt_autre" in text
