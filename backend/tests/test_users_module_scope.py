"""API `/users` du module Immobilisations : périmètre limité aux habilités actifs.

Tout se déroule dans une transaction jamais validée (rollback final) : aucune donnée persistée.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import insert, select, text
from sqlalchemy.exc import IntegrityError

from app.api.v1.endpoints import users as users_endpoint
from app.db.session import AsyncSessionLocal, engine, get_db
from app.main import app
from app.models import User
from app.models.associations import user_module_acces_table
from app.models.immobilisation import Immobilisation
from app.models.plateforme import PlateformeModule
from app.services.auth_service import AuthService

MODULE = "immobilisations"


async def _db_ready() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest.fixture
async def session():
    # Le pool global garde des connexions liées à la boucle asyncio du test précédent.
    await engine.dispose()
    if not await _db_ready():
        pytest.skip("Base PostgreSQL indisponible")
    async with AsyncSessionLocal() as s:
        immo = await s.scalar(select(PlateformeModule).where(PlateformeModule.code == MODULE))
        if immo is None:
            pytest.skip("Catalogue plateforme sans module immobilisations")
        try:
            yield s
        finally:
            await s.rollback()


async def _module_id(s, code: str):
    return await s.scalar(select(PlateformeModule.id).where(PlateformeModule.code == code))


async def _other_module_code(s) -> str | None:
    return await s.scalar(
        select(PlateformeModule.code).where(PlateformeModule.code != MODULE).order_by(PlateformeModule.code)
    )


async def _user(s, tag: str, label: str) -> User:
    user = User(
        email=f"scope-{label}-{tag}@el-amana.mr",
        full_name=f"Scope {tag} {label}",
        hashed_password="x",
        is_superuser=False,
        is_active=True,
        totp_enabled=False,
    )
    s.add(user)
    await s.flush()
    return user


async def _grant(s, user: User, module_code: str, status: str = "actif") -> None:
    await s.execute(
        insert(user_module_acces_table).values(
            user_id=user.id, module_id=await _module_id(s, module_code), status=status
        )
    )
    await s.flush()


@pytest.fixture
async def scoped_users(session):
    tag = uuid4().hex[:8]
    sans = await _user(session, tag, "sans")
    actif = await _user(session, tag, "actif")
    revoque = await _user(session, tag, "revoque")
    await _grant(session, actif, MODULE, "actif")
    await _grant(session, revoque, MODULE, "revoque")
    return tag, sans, actif, revoque


@pytest.mark.asyncio
async def test_service_list_users_filtre_par_acces_module(session, scoped_users):
    tag, sans, actif, revoque = scoped_users
    svc = AuthService(session)

    items, total = await svc.list_users(1, 100, search=tag, module_access=MODULE)
    ids = {u.id for u in items}
    assert actif.id in ids
    assert sans.id not in ids
    assert revoque.id not in ids
    assert total == 1

    all_items, all_total = await svc.list_users(1, 100, search=tag)
    assert {sans.id, actif.id, revoque.id} <= {u.id for u in all_items}
    assert all_total == 3

    assert await svc.has_module_access(actif.id, MODULE) is True
    assert await svc.has_module_access(sans.id, MODULE) is False
    assert await svc.has_module_access(revoque.id, MODULE) is False


@pytest.fixture
async def api(session):
    async def _db():
        yield session

    async def _admin():
        return User(email="test@el-amana.mr", full_name="Test", is_superuser=True)

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[users_endpoint._require_users_admin] = _admin
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(users_endpoint._require_users_admin, None)


@pytest.mark.asyncio
async def test_endpoint_users_ne_liste_que_les_habilites(api, scoped_users):
    tag, sans, actif, revoque = scoped_users
    res = await api.get("/api/v1/users", params={"search": tag, "size": 100})
    assert res.status_code == 200, res.text
    ids = {row["id"] for row in res.json()["items"]}
    assert ids == {str(actif.id)}


@pytest.mark.asyncio
async def test_endpoint_users_lecture_unitaire_hors_module(api, scoped_users):
    _, sans, _, _ = scoped_users
    res = await api.get(f"/api/v1/users/{sans.id}")
    assert res.status_code == 200, res.text


@pytest.mark.asyncio
async def test_endpoint_users_modification_hors_module_refusee(api, scoped_users):
    _, sans, _, revoque = scoped_users
    for target in (sans, revoque):
        res = await api.patch(f"/api/v1/users/{target.id}", json={"full_name": "Interdit"})
        assert res.status_code == 403, res.text


@pytest.mark.asyncio
async def test_endpoint_users_patch_conserve_les_autres_modules(api, session, scoped_users):
    other = await _other_module_code(session)
    if other is None:
        pytest.skip("Aucun autre module au catalogue")
    _, _, actif, _ = scoped_users
    await _grant(session, actif, other)
    res = await api.patch(f"/api/v1/users/{actif.id}", json={"module_codes": [MODULE]})
    assert res.status_code == 200, res.text
    assert set(res.json()["module_codes"]) >= {MODULE, other}


@pytest.mark.asyncio
async def test_endpoint_users_suppression_refusee_si_autres_modules(api, session, scoped_users):
    other = await _other_module_code(session)
    if other is None:
        pytest.skip("Aucun autre module au catalogue")
    _, _, actif, _ = scoped_users
    await _grant(session, actif, other)
    res = await api.delete(f"/api/v1/users/{actif.id}")
    assert res.status_code == 400, res.text
    assert (await session.get(User, actif.id)).deleted_at is None


@pytest.mark.asyncio
async def test_fk_users_intactes(session, scoped_users):
    tag, sans, _, _ = scoped_users

    fks = {
        (row.table, row.column)
        for row in (
            await session.execute(
                text(
                    """
                    SELECT c.conrelid::regclass::text AS "table", a.attname AS "column"
                    FROM pg_constraint c
                    JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
                    WHERE c.contype = 'f' AND c.confrelid = 'public.users'::regclass
                    """
                )
            )
        ).all()
    }
    for expected in (
        ("immobilisations", "responsable_id"),
        ("pieces_jointes", "uploaded_by_id"),
        ("inventaire_scans", "scanned_by_id"),
        ("user_module_acces", "user_id"),
    ):
        assert expected in fks, f"FK manquante : {expected}"

    immo = Immobilisation(
        code_inventaire=f"TEST-SCOPE-{tag}",
        designation="Test FK responsable",
        date_acquisition=date(2026, 1, 1),
        valeur_brute=Decimal("1000"),
        responsable_id=sans.id,
    )
    session.add(immo)
    await session.flush()
    loaded = await session.get(Immobilisation, immo.id)
    assert loaded.responsable_id == sans.id
    assert (await session.get(User, loaded.responsable_id)).full_name == sans.full_name

    nested = await session.begin_nested()
    session.add(
        Immobilisation(
            code_inventaire=f"TEST-SCOPE-KO-{tag}",
            designation="FK invalide",
            date_acquisition=date(2026, 1, 1),
            valeur_brute=Decimal("1000"),
            responsable_id=uuid4(),
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()
    await nested.rollback()
