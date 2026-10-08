"""Département Audit, Contrôle & Conformité — domaines, module EER, CORE ADMIN."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.data.module_backup_scopes import ESPACE_MODULES, MODULE_BACKUP_SCOPES
from app.data.plateforme_catalogue import (
    ACC_ESPACE_CODE,
    EER_MODULE_CODE,
    FUNCTIONAL_PERMISSIONS,
    PLATEFORME_DOMAINES,
    PLATEFORME_ESPACES,
    PLATEFORME_MODULES,
    RBAC_ROLES,
    ROLE_PERMISSIONS,
)
from app.db.session import engine
from app.main import app


def test_catalogue_acc_coherent():
    espace = next(e for e in PLATEFORME_ESPACES if e["code"] == ACC_ESPACE_CODE)
    # /audit est un segment réservé Immobilisations.
    assert espace["route"] == f"/{ACC_ESPACE_CODE}"
    codes = {d["code"] for d in PLATEFORME_DOMAINES}
    for d in PLATEFORME_DOMAINES:
        assert d["espace_code"] == ACC_ESPACE_CODE
        if d.get("parent_code"):
            assert d["parent_code"] in codes
    eer = next(m for m in PLATEFORME_MODULES if m["code"] == EER_MODULE_CODE)
    assert eer["domaine_code"] == "kyc"
    assert eer["entry_path"].startswith("/eer/")
    # Pas de fausse fonctionnalité : le module n'est pas ouvert tant qu'il n'est pas livré.
    assert eer["statut"] != "actif"


def test_permissions_et_roles_eer():
    perms = {code for code, _l, module in FUNCTIONAL_PERMISSIONS if module == "eer"}
    assert {"eer.view", "eer.control", "eer.validate", "eer.document.download"} <= perms
    roles = {code for code, _l, _d in RBAC_ROLES}
    assert {"eer.lecteur", "eer.analyste", "eer.superviseur", "eer.admin"} <= roles
    for role in ("eer.lecteur", "eer.analyste", "eer.superviseur", "eer.admin"):
        granted = ROLE_PERMISSIONS[role]
        assert all(p in perms for p in granted)
        # Pièces KYC : jamais via la GED générique / Archive Générale.
        assert not any(p.startswith("ged.") for p in granted)
    assert "eer.validate" not in ROLE_PERMISSIONS["eer.analyste"]
    assert "eer.validate" in ROLE_PERMISSIONS["eer.superviseur"]
    assert ESPACE_MODULES[ACC_ESPACE_CODE] == ["eer", "formation", "clientele"]
    assert "eer" in MODULE_BACKUP_SCOPES


async def _db_ready() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1 FROM plateforme_domaines LIMIT 1"))
        return True
    except Exception:
        return False


@pytest.fixture
async def client():
    if not await _db_ready():
        pytest.skip("Base PostgreSQL indisponible ou migration 20261003_acc_departement absente")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _headers(client: AsyncClient) -> dict[str, str]:
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "admin@el-amana.mr",
            "password": os.environ.get("BEA_TEST_PASSWORD", "Admin@2026"),
        },
    )
    if login.status_code != 200:
        pytest.skip("Compte admin seed indisponible")
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_hub_expose_domaines_et_module_eer(client: AsyncClient):
    headers = await _headers(client)
    res = await client.get("/api/v1/plateforme/espaces", headers=headers)
    assert res.status_code == 200, res.text
    acc = next((e for e in res.json() if e["id"] == ACC_ESPACE_CODE), None)
    if acc is None:
        pytest.skip("Département ACC retiré via CORE ADMIN")
    domaines = {d["id"]: d for d in acc["domaines"]}
    assert domaines["kyc"]["parent_id"] == "conformite-securite-financiere"
    assert domaines["audit-interne"]["statut"] == "bientot"
    eer = next(m for m in acc["modules"] if m["id"] == EER_MODULE_CODE)
    assert eer["domaine_id"] == "kyc"
    if eer["statut"] != "actif":
        assert eer["accessible"] is False
        assert eer["entry_path"] is None


@pytest.mark.asyncio
async def test_core_admin_domaines_crud(client: AsyncClient):
    headers = await _headers(client)
    suffix = uuid4().hex[:8]
    dept_id = other_dept_id = mod_id = None
    created: list[str] = []
    try:
        dept = await client.post(
            "/api/v1/plateforme/admin/departments",
            headers=headers,
            json={"code": f"t-acc-{suffix}", "label": "Test domaines", "statut": "actif", "icon": "shield"},
        )
        assert dept.status_code == 201, dept.text
        dept_id = dept.json()["id"]
        assert dept.json()["icon"] == "shield"
        other = await client.post(
            "/api/v1/plateforme/admin/departments",
            headers=headers,
            json={"code": f"t-acc-o-{suffix}", "label": "Autre", "statut": "bientot"},
        )
        other_dept_id = other.json()["id"]

        root = await client.post(
            "/api/v1/plateforme/admin/domaines",
            headers=headers,
            json={
                "code": f"t-dom-{suffix}",
                "espace_id": dept_id,
                "label": "Domaine test",
                "icon": "shield",
                "statut": "actif",
            },
        )
        assert root.status_code == 201, root.text
        root_id = root.json()["id"]
        created.append(root_id)

        sub = await client.post(
            "/api/v1/plateforme/admin/domaines",
            headers=headers,
            json={
                "code": f"t-sub-{suffix}",
                "espace_id": dept_id,
                "parent_id": root_id,
                "label": "Sous-domaine test",
                "statut": "actif",
            },
        )
        assert sub.status_code == 201, sub.text
        sub_id = sub.json()["id"]
        created.insert(0, sub_id)
        assert sub.json()["parent_code"] == f"t-dom-{suffix}"

        third = await client.post(
            "/api/v1/plateforme/admin/domaines",
            headers=headers,
            json={"code": f"t-3-{suffix}", "espace_id": dept_id, "parent_id": sub_id, "label": "Niveau 3"},
        )
        assert third.status_code == 400

        bad_icon = await client.patch(
            f"/api/v1/plateforme/admin/domaines/{root_id}", headers=headers, json={"icon": "<svg>"}
        )
        assert bad_icon.status_code == 422

        mod = await client.post(
            "/api/v1/plateforme/admin/modules",
            headers=headers,
            json={
                "code": f"t-mod-{suffix}",
                "espace_id": dept_id,
                "domaine_id": sub_id,
                "label": "Module test",
                "statut": "bientot",
                "icon": "badge",
            },
        )
        assert mod.status_code == 201, mod.text
        mod_id = mod.json()["id"]
        assert mod.json()["domaine_code"] == f"t-sub-{suffix}"

        cross = await client.patch(
            f"/api/v1/plateforme/admin/modules/{mod_id}",
            headers=headers,
            json={"espace_id": other_dept_id, "domaine_id": sub_id},
        )
        assert cross.status_code == 400

        assert (await client.delete(f"/api/v1/plateforme/admin/domaines/{root_id}", headers=headers)).status_code == 400
        assert (await client.delete(f"/api/v1/plateforme/admin/domaines/{sub_id}", headers=headers)).status_code == 400

        hub = await client.get("/api/v1/plateforme/espaces", headers=headers)
        espace = next(e for e in hub.json() if e["id"] == f"t-acc-{suffix}")
        assert any(m["id"] == f"t-mod-{suffix}" and m["domaine_id"] == f"t-sub-{suffix}" for m in espace["modules"])

        off = await client.post(f"/api/v1/plateforme/admin/domaines/{root_id}/deactivate", headers=headers)
        assert off.status_code == 200 and off.json()["statut"] == "inactif"
        hub = await client.get("/api/v1/plateforme/espaces", headers=headers)
        espace = next(e for e in hub.json() if e["id"] == f"t-acc-{suffix}")
        # Domaine désactivé : ses sous-domaines et modules disparaissent du hub.
        assert espace["domaines"] == []
        assert not any(m["id"] == f"t-mod-{suffix}" for m in espace["modules"])

        fiche = await client.get(f"/api/v1/plateforme/admin/departments/{dept_id}", headers=headers)
        assert {d["id"] for d in fiche.json()["domaines"]} == {root_id, sub_id}
        assert (await client.delete(f"/api/v1/plateforme/admin/departments/{dept_id}", headers=headers)).status_code == 400

        detach = await client.patch(
            f"/api/v1/plateforme/admin/modules/{mod_id}", headers=headers, json={"domaine_id": None}
        )
        assert detach.status_code == 200 and detach.json()["domaine_id"] is None
    finally:
        if mod_id:
            await client.delete(f"/api/v1/plateforme/admin/modules/{mod_id}", headers=headers)
        for dom_id in created:
            await client.delete(f"/api/v1/plateforme/admin/domaines/{dom_id}", headers=headers)
        for d in (dept_id, other_dept_id):
            if d:
                await client.delete(f"/api/v1/plateforme/admin/departments/{d}", headers=headers)


@pytest.mark.asyncio
async def test_login_module_eer_refuse_tant_que_non_actif(client: AsyncClient):
    headers = await _headers(client)
    mods = await client.get(f"/api/v1/plateforme/admin/modules?search={EER_MODULE_CODE}", headers=headers)
    eer = next((m for m in mods.json()["items"] if m["code"] == EER_MODULE_CODE), None)
    if eer is None or eer["statut"] == "actif":
        pytest.skip("Module EER absent ou déjà ouvert")
    res = await client.post(
        f"/api/v1/auth/modules/{EER_MODULE_CODE}/login",
        json={"email": "admin@el-amana.mr", "password": os.environ.get("BEA_TEST_PASSWORD", "Admin@2026")},
        headers=headers,
    )
    assert res.status_code in (400, 403, 423), res.text
