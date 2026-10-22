"""Alertes de stock bas : franchissement du seuil (5), épisode unique, suivi et suppression (sans DB)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.exceptions import AppError
from app.services import mg_stock_alertes as A
from app.services.mg_stock_service import MgStockService


class _Memoire(A.MgStockAlerteService):
    """Service branché sur une liste en mémoire : episodes ouverts / fermés, notifications émises."""

    def __init__(self, seuil: Decimal | None = Decimal("5")):
        db = MagicMock()
        db.add = MagicMock(side_effect=self._ajouter)
        db.flush = AsyncMock()
        super().__init__(db)
        self._seuil_cache = (seuil,)
        self.episodes: list = []
        self.notifications: list[tuple[str, str]] = []
        self.traces: list[str] = []
        self._n = 0

    def _ajouter(self, obj):
        obj.id = obj.id or uuid4()
        if getattr(obj, "deleted_at", None) is None:
            obj.deleted_at = None
        self.episodes.append(obj)

    async def _episode_ouvert(self, article_id):
        ouverts = [e for e in self.episodes if e.article_id == article_id and e.retour_normal_at is None]
        assert len(ouverts) <= 1, "un seul épisode ouvert par article"
        return ouverts[0] if ouverts else None

    async def _prochaine_reference(self, now):
        self._n += 1
        return f"ALS-{now.year}-{self._n:06d}"

    async def _tracer(self, user, action, a, *, before=None, after=None):
        self.traces.append(action)

    async def _notifier(self, episode, article):
        self.notifications.append((episode.type_alerte, episode.reference))


def _article(stock, **kw):
    a = SimpleNamespace(
        id=uuid4(), code="PAP-A4", designation="Papier A4", uom="U", stock_actuel=Decimal(stock),
        agence_id=None, emplacement=None, stockable=True, deleted_at=None, is_active=True,
    )
    for k, v in kw.items():
        setattr(a, k, v)
    return a


async def _passer(svc, article, stock):
    article.stock_actuel = Decimal(stock)
    return await svc.evaluer(article, mouvement_reference="MVT")


# ---------------------------------------------------------------- règle pure
@pytest.mark.parametrize(
    "q, attendu",
    [("6", None), ("5", "STOCK_FAIBLE"), ("4", "STOCK_FAIBLE"), ("0", "RUPTURE"), ("-1", "RUPTURE")],
)
def test_niveau_alerte_seuil_5(q, attendu):
    assert A.niveau_alerte(Decimal(q), Decimal("5")) == attendu


def test_parametres():
    assert A.seuil_depuis_parametre(None) == Decimal("5")
    assert A.seuil_depuis_parametre("3") == Decimal("3")
    assert A.seuil_depuis_parametre("abc") == Decimal("5")
    assert A.alertes_activees(None) and A.alertes_activees("5")
    assert not A.alertes_activees("0") and not A.alertes_activees("non")


# --------------------------------------------------------------- transitions
@pytest.mark.asyncio
async def test_6_vers_5_cree_une_alerte_et_une_notification():
    svc, art = _Memoire(), _article("6")
    assert await svc.evaluer(art) is None
    assert await _passer(svc, art, "5") == "OUVERTE"
    (ep,) = svc.episodes
    assert (ep.type_alerte, ep.statut, ep.seuil, ep.quantite_detection) == ("STOCK_FAIBLE", "NOUVELLE", Decimal("5"), Decimal("5"))
    assert svc.notifications == [("STOCK_FAIBLE", ep.reference)]


@pytest.mark.asyncio
async def test_5_vers_4_ne_recree_pas_de_notification():
    svc, art = _Memoire(), _article("6")
    await _passer(svc, art, "5")
    assert await _passer(svc, art, "4") is None
    assert await _passer(svc, art, "4") is None
    assert len(svc.episodes) == 1 and len(svc.notifications) == 1
    assert svc.episodes[0].quantite_actuelle == Decimal("4")


@pytest.mark.asyncio
async def test_4_vers_6_retour_normal_puis_nouveau_franchissement():
    svc, art = _Memoire(), _article("6")
    await _passer(svc, art, "5")
    await _passer(svc, art, "4")
    assert await _passer(svc, art, "6") == "RETOUR"
    premier = svc.episodes[0]
    assert premier.retour_normal_at is not None and premier.quantite_retour == Decimal("6")
    assert premier.statut == "RESOLUE"
    assert await _passer(svc, art, "5") == "OUVERTE"
    assert len(svc.episodes) == 2 and len(svc.notifications) == 2


@pytest.mark.asyncio
async def test_6_vers_0_rupture_directe():
    svc, art = _Memoire(), _article("6")
    assert await _passer(svc, art, "0") == "OUVERTE"
    (ep,) = svc.episodes
    assert ep.type_alerte == "RUPTURE" and ep.rupture_at is not None
    assert svc.notifications == [("RUPTURE", ep.reference)]


@pytest.mark.asyncio
async def test_aggravation_en_rupture_notifiee_une_seule_fois():
    svc, art = _Memoire(), _article("6")
    await _passer(svc, art, "3")
    assert await _passer(svc, art, "0") == "RUPTURE"
    assert await _passer(svc, art, "0") is None
    assert await _passer(svc, art, "2") is None
    assert [t for t, _ in svc.notifications] == ["STOCK_FAIBLE", "RUPTURE"]
    assert len(svc.episodes) == 1


@pytest.mark.asyncio
async def test_alertes_desactivees_ou_article_non_suivi():
    svc = _Memoire(seuil=None)
    assert await _passer(svc, _article("6"), "1") is None
    svc = _Memoire()
    assert await _passer(svc, _article("6", stockable=False), "1") is None
    assert await _passer(svc, _article("6", is_active=False), "1") is None
    assert svc.episodes == []


@pytest.mark.asyncio
async def test_perimetres_distincts_jamais_additionnes():
    """Deux lignes article (agences différentes) : chaque stock est jugé seul."""
    svc = _Memoire()
    central, agence = _article("20"), _article("6", agence_id=uuid4())
    await _passer(svc, agence, "2")
    assert await svc.evaluer(central) is None
    (ep,) = svc.episodes
    assert ep.article_id == agence.id and ep.agence_id == agence.agence_id


# ----------------------------------------------------------- contrôle initial
@pytest.mark.asyncio
async def test_controle_initial_idempotent_stock_deja_bas():
    svc = _Memoire()
    articles = [_article("3"), _article("0"), _article("12")]
    svc.db.scalars = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=articles)))
    with patch("app.services.mg_stock_events.audit_stock", new=AsyncMock()):
        r1 = await svc.controle()
        r2 = await svc.controle()
    assert (r1["ouvertes"], r1["articles"]) == (2, 3)
    assert r2["ouvertes"] == 0
    assert len(svc.episodes) == 2 and len(svc.notifications) == 2
    assert {e.origine for e in svc.episodes} == {"CONTROLE"}


# --------------------------------------------------------------- suppression
@pytest.mark.asyncio
async def test_suppression_ne_relance_pas_de_detection():
    svc, art = _Memoire(), _article("6")
    await _passer(svc, art, "4")
    ep = svc.episodes[0]
    ep.deleted_at = datetime.now(timezone.utc)
    ep.motif_suppression = "Doublon"
    assert await _passer(svc, art, "3") is None
    assert await _passer(svc, art, "0") == "RUPTURE"
    assert len(svc.episodes) == 1
    assert len(svc.notifications) == 1, "pas de notification pour une alerte supprimée"
    assert art.stock_actuel == Decimal("0"), "la suppression ne touche pas au stock"


@pytest.mark.asyncio
async def test_suppression_exige_un_motif():
    with pytest.raises(AppError) as exc:
        await _Memoire().supprimer([uuid4()], "  ", MagicMock())
    assert exc.value.code == "ALERTE_MOTIF_SUPPRESSION"


@pytest.mark.asyncio
async def test_suppression_en_masse_refusee_si_une_alerte_manque():
    svc = _Memoire()
    svc.db.scalars = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    with pytest.raises(AppError) as exc:
        await svc.supprimer([uuid4(), uuid4()], "Doublons", MagicMock())
    assert exc.value.code == "ALERTE_INTROUVABLE"


# --------------------------------------------------------- statut de traitement
def test_transitions_de_statut():
    A.verifier_transition("NOUVELLE", "EN_COURS", episode_ouvert=True)
    A.verifier_transition("EN_COURS", "CLOTUREE", episode_ouvert=True)
    A.verifier_transition("EN_COURS", "RESOLUE", episode_ouvert=False)
    with pytest.raises(AppError) as exc:
        A.verifier_transition("EN_COURS", "RESOLUE", episode_ouvert=True)
    assert exc.value.code == "ALERTE_STOCK_TOUJOURS_BAS"
    with pytest.raises(AppError) as exc:
        A.verifier_transition("CLOTUREE", "NOUVELLE", episode_ouvert=True)
    assert exc.value.code == "ALERTE_TRANSITION_INVALIDE"


def _alerte_ouverte(svc):
    alerte = SimpleNamespace(
        id=uuid4(), reference="ALS-2026-000001", article_id=uuid4(), type_alerte="STOCK_FAIBLE",
        statut="NOUVELLE", seuil=Decimal("5"), quantite_actuelle=Decimal("4"), responsable_id=None,
        commentaire=None, retour_normal_at=None, deleted_at=None, motif_suppression=None,
        traite_par=None, traite_at=None,
    )
    svc.get = AsyncMock(return_value=alerte)
    return alerte


@pytest.mark.asyncio
async def test_responsable_hors_module_refuse():
    svc = _Memoire()
    alerte = _alerte_ouverte(svc)
    membre = uuid4()
    svc.responsables = AsyncMock(return_value=[{"id": membre, "nom": "Magasinier"}])
    with pytest.raises(AppError) as exc:
        await svc.modifier(alerte.id, {"responsable_id": uuid4()}, MagicMock(id=uuid4()))
    assert exc.value.code == "ALERTE_RESPONSABLE_INVALIDE"
    assert alerte.responsable_id is None

    await svc.modifier(alerte.id, {"responsable_id": membre, "commentaire": "  Commande lancée  "}, MagicMock(id=uuid4()))
    assert alerte.responsable_id == membre and alerte.commentaire == "Commande lancée"
    assert svc.traces == ["update"]


@pytest.mark.asyncio
async def test_responsables_limites_aux_roles_du_module():
    svc = _Memoire()
    role = lambda code: SimpleNamespace(code=code)  # noqa: E731
    users = [
        SimpleNamespace(id=uuid4(), full_name="Magasinier", email="m@x", roles=[role("stock-fournitures.magasinier")]),
        SimpleNamespace(id=uuid4(), full_name="Comptable", email="c@x", roles=[role("immobilisations.comptable")]),
    ]
    svc.db.scalars = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=users)))
    assert [r["nom"] for r in await svc.responsables()] == ["Magasinier"]


# ------------------------------------------------- branchement sur les mouvements
@pytest.mark.asyncio
async def test_mouvement_valide_declenche_l_evaluation_sur_le_stock_reel():
    svc = MgStockService(MagicMock())
    article = _article("5")
    with patch.object(A.MgStockAlerteService, "evaluer", new=AsyncMock(return_value="OUVERTE")) as ev:
        await svc._suivre_seuil(article, mouvement_id=None, mouvement_reference="SOR-1")
        await svc._suivre_seuil(article, mouvement_reference="SOR-2")
    assert ev.await_count == 2
    assert ev.await_args.args[0] is article
    assert ev.await_args.kwargs["mouvement_reference"] == "SOR-2"


def test_les_trois_points_de_modification_du_stock_sont_suivis():
    src = (Path(__file__).resolve().parents[1] / "app" / "services" / "mg_stock_service.py").read_text(encoding="utf-8")
    # _apply_mouvement, _appliquer_effet (modification / suppression), _supprimer_force
    assert src.count("await self._suivre_seuil(") == 3


def test_migration_un_seul_episode_ouvert_par_article():
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "20261022_mg_stock_alertes.py"
    text = path.read_text(encoding="utf-8")
    assert "uq_mg_stock_alertes_episode_ouvert" in text
    assert 'postgresql_where=sa.text("retour_normal_at IS NULL")' in text
    assert "alerte_seuil_unites" in text and "'5'" in text
