"""Notifications cloisonnées par espace (module + département, CORE ADMIN, plateforme), sans DB.

Le périmètre est déduit de la session authentifiée (``get_notification_context``) et appliqué dans
les requêtes SQL : aucun paramètre de requête ne permet de lire un autre espace.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.api import deps
from app.api.v1.endpoints import notifications as endpoints
from app.data import notification_routing as routing
from app.models import Notification
from app.services.notification_service import NotificationScope, NotificationService

STOCK = NotificationScope.module("stock-fournitures", "moyens-generaux")


def _sql(scope: NotificationScope) -> str:
    stmt = select(Notification.id).where(*NotificationService._base_filters(uuid4(), scope))
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


# --------------------------------------------------------------- filtres SQL
def test_espace_module_filtre_module_departement_et_portee():
    sql = _sql(STOCK)
    assert "notifications.portee = 'module'" in sql
    assert "notifications.module_code IN ('stock-fournitures')" in sql
    assert "notifications.espace_code = 'moyens-generaux'" in sql
    assert "notifications.user_id = " in sql


def test_notification_d_un_autre_module_exclue():
    sql = _sql(STOCK)
    assert "achats-appro" not in sql and "immobilisations" not in sql


def test_notification_d_un_autre_departement_exclue():
    """Même code module mais autre département : la condition espace_code l'écarte."""
    autre = NotificationScope.module("stock-fournitures", "comptabilite")
    assert "notifications.espace_code = 'comptabilite'" in _sql(autre)
    assert "notifications.espace_code = 'moyens-generaux'" not in _sql(autre)


def test_core_admin_hors_des_espaces_modules_et_plateforme():
    assert "notifications.portee = 'core_admin'" in _sql(NotificationScope.core_admin())
    assert "core_admin" not in _sql(STOCK)
    assert "core_admin" not in _sql(NotificationScope.plateforme())


def test_plateforme_ne_voit_aucune_notification_de_module():
    sql = _sql(NotificationScope.plateforme())
    assert "notifications.portee = 'plateforme'" in sql
    assert "notifications.module_code IS NULL" in sql


def test_espace_module_incomplet_ne_voit_rien():
    sql = _sql(NotificationScope.module("stock-fournitures", None))
    assert "notifications.id IS NULL" in sql


def test_alias_historique_immobilisations():
    sql = _sql(NotificationScope.module("immobilisations", "comptabilite"))
    assert "notifications.module_code IN ('immobilisations', 'immos')" in sql


# ------------------------------------------------------------ création / routage
def test_portee_par_defaut():
    assert routing.portee_par_defaut("stock-fournitures") == "module"
    assert routing.portee_par_defaut("core") == "core_admin"
    assert routing.portee_par_defaut(None) == "plateforme"


def _db():
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.get = AsyncMock(return_value=None)
    return db


@pytest.mark.asyncio
async def test_creation_rattache_portee_module_et_departement():
    db = _db()
    row = await NotificationService(db).create(
        user_id=uuid4(), type_notification="SYSTEME", titre="Stock faible", message="x",
        espace_code="moyens-generaux", module_code="stock-fournitures",
    )
    assert (row.portee, row.module_code, row.espace_code) == ("module", "stock-fournitures", "moyens-generaux")


@pytest.mark.asyncio
async def test_portee_module_sans_module_refusee():
    with pytest.raises(ValueError):
        await NotificationService(_db()).create(
            user_id=uuid4(), type_notification="SYSTEME", titre="t", message="m", portee="module"
        )


@pytest.mark.asyncio
async def test_portee_inconnue_refusee():
    with pytest.raises(ValueError):
        await NotificationService(_db()).create(
            user_id=uuid4(), type_notification="SYSTEME", titre="t", message="m",
            module_code="stock-fournitures", portee="partout",
        )


@pytest.mark.asyncio
async def test_diffusion_multi_espaces_refusee_sans_route_configuree():
    with pytest.raises(ValueError):
        await NotificationService(_db()).create_multi_espaces(
            source_module="stock-fournitures",
            destinations=[("moyens-generaux", "achats-appro")],
            user_id=uuid4(), type_notification="SYSTEME", titre="t", message="m",
        )


@pytest.mark.asyncio
async def test_diffusion_multi_espaces_acceptee_si_route_explicite(monkeypatch):
    monkeypatch.setattr(routing, "ROUTES_AUTORISEES", frozenset({("stock-fournitures", "achats-appro")}))
    rows = await NotificationService(_db()).create_multi_espaces(
        source_module="stock-fournitures",
        destinations=[("moyens-generaux", "stock-fournitures"), ("moyens-generaux", "achats-appro")],
        user_id=uuid4(), type_notification="SYSTEME", titre="t", message="m",
    )
    assert [(r.module_code, r.portee) for r in rows] == [
        ("stock-fournitures", "module"),
        ("achats-appro", "module"),
    ]


# ------------------------------------------------------------- lecture / écriture
@pytest.mark.asyncio
async def test_marquer_lue_hors_perimetre_introuvable():
    db = _db()
    db.scalar = AsyncMock(return_value=None)
    assert await NotificationService(db).mark_read(uuid4(), uuid4(), scope=STOCK) is None
    sql = str(db.scalar.await_args.args[0].compile(dialect=postgresql.dialect(),
                                                    compile_kwargs={"literal_binds": True}))
    assert "notifications.module_code IN ('stock-fournitures')" in sql


@pytest.mark.asyncio
async def test_compteur_non_lues_propre_a_l_espace():
    db = _db()
    db.scalar = AsyncMock(return_value=3)
    assert await NotificationService(db).count_unread(uuid4(), scope=STOCK) == 3
    sql = str(db.scalar.await_args.args[0].compile(dialect=postgresql.dialect(),
                                                    compile_kwargs={"literal_binds": True}))
    assert "notifications.lu IS false" in sql and "'stock-fournitures'" in sql


def test_endpoints_n_acceptent_aucun_parametre_d_espace():
    """Ni module_code, ni espace_code, ni portee en paramètre : seul le contexte de session compte."""
    for fn in (
        endpoints.list_notifications,
        endpoints.unread_count,
        endpoints.mark_notification_read,
        endpoints.mark_all_read,
    ):
        params = set(inspect.signature(fn).parameters)
        assert not params & {"module_code", "espace_code", "portee", "user_id"}, fn.__name__


# ------------------------------------------------------------- contexte de session
@pytest.mark.asyncio
async def test_contexte_session_module_donne_l_espace_du_module():
    user = SimpleNamespace(id=uuid4())
    session = SimpleNamespace(kind="module", module_code="Stock-Fournitures", parent_session_id=uuid4(), id=uuid4())
    module = SimpleNamespace(espace=SimpleNamespace(code="moyens-generaux"))
    with patch.object(deps, "_load_user_and_session", new=AsyncMock(return_value=(user, session, None))), \
         patch.object(deps, "_verify_module_session", new=AsyncMock(return_value=module)) as verify, \
         patch.object(deps, "_bind_request_session"):
        u, scope = await deps.get_notification_context(MagicMock(), None, MagicMock())
    assert u is user
    assert scope == NotificationScope("module", "stock-fournitures", "moyens-generaux")
    assert verify.await_args.args[3] == "stock-fournitures"


@pytest.mark.asyncio
async def test_contexte_session_plateforme():
    user = SimpleNamespace(id=uuid4())
    session = SimpleNamespace(kind="platform", module_code=None, id=uuid4())
    with patch.object(deps, "_load_user_and_session", new=AsyncMock(return_value=(user, session, None))), \
         patch.object(deps, "_bind_request_session"):
        _, scope = await deps.get_notification_context(MagicMock(), None, MagicMock())
    assert scope == NotificationScope.plateforme()


# ----------------------------------------------------------------- historique
def test_migration_rattache_l_historique_sur_origine_certaine():
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "20261022_notifications_01_portee.py"
    text = path.read_text(encoding="utf-8")
    assert "SET portee = 'core_admin'" in text
    assert "entity IN ('plateforme_module', 'platform_restore', 'api_error_events')" in text
    assert "SET espace_code = 'comptabilite', module_code = 'immobilisations' " in text
    assert "WHERE entity = 'immobilisation' AND module_code IS NULL AND espace_code IS NULL" in text
    assert "SET portee = 'plateforme' WHERE portee = 'module' AND module_code IS NULL" in text
    assert "DELETE" not in text.upper()
