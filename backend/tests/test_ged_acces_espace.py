"""API `/ged/documents` : anti-IDOR par département (espace) et niveau de confidentialité.

Transaction jamais validée (rollback final) : aucune donnée persistée.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

from app.api.deps import get_current_user
from app.db.session import AsyncSessionLocal, engine, get_db
from app.main import app
from app.models import User
from app.models.ged import GedDocument
from app.models.plateforme import PlateformeEspace
from app.services.auth_service import AuthService
from app.services.plateforme_access_service import PlateformeAccessService

ESPACE_DOC = "moyens-generaux"


@pytest.fixture
async def session():
    await engine.dispose()
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("Base PostgreSQL indisponible")
    async with AsyncSessionLocal() as s:
        if await s.scalar(select(PlateformeEspace.id).where(PlateformeEspace.code == ESPACE_DOC)) is None:
            pytest.skip(f"Espace {ESPACE_DOC} absent du catalogue")
        try:
            yield s
        finally:
            await s.rollback()


async def _user_ged(s, tag: str, label: str, espaces: list[str]) -> User:
    svc = AuthService(s)
    user = User(
        email=f"ged-{label}-{tag}@el-amana.mr",
        full_name=f"GED {label}",
        hashed_password="x",
        is_superuser=False,
        is_active=True,
        totp_enabled=False,
    )
    user.roles = await svc._roles_by_codes(["administrateur"])
    s.add(user)
    await s.flush()
    await PlateformeAccessService(s).set_user_access(user, espaces, [])
    return await svc.get_by_id(user.id)


@pytest.fixture
async def contexte(session):
    tag = uuid4().hex[:8]
    doc = GedDocument(
        espace_code=ESPACE_DOC,
        module_code="contrats-echeances",
        entity="contrat",
        entity_id=f"test-{tag}",
        filename="contrat.pdf",
        stored_path=f"tests/{tag}/absent.pdf",
        mime_type="application/pdf",
        size_bytes=10,
    )
    session.add(doc)
    await session.flush()
    hors = await _user_ged(session, tag, "hors", ["comptabilite"])
    dedans = await _user_ged(session, tag, "dedans", [ESPACE_DOC])
    return doc, hors, dedans


async def _client(session, user: User) -> AsyncClient:
    async def _db():
        yield session

    async def _user():
        return user

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture(autouse=True)
def _nettoyage():
    yield
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_download_refuse_hors_espace(session, contexte):
    doc, hors, dedans = contexte
    async with await _client(session, hors) as ac:
        res = await ac.get(f"/api/v1/ged/documents/{doc.id}/download")
    assert res.status_code == 403, res.text

    async with await _client(session, dedans) as ac:
        res = await ac.get(f"/api/v1/ged/documents/{doc.id}/download")
    # Contrôle d'accès franchi : le fichier de test n'existe pas sur disque.
    assert res.status_code == 404, res.text
    assert "Fichier introuvable" in res.text


@pytest.mark.asyncio
async def test_liste_masque_les_documents_hors_espace(session, contexte):
    doc, hors, dedans = contexte
    params = {"module_code": doc.module_code, "entity": doc.entity, "entity_id": doc.entity_id}
    async with await _client(session, hors) as ac:
        res = await ac.get("/api/v1/ged/documents", params=params)
    assert res.status_code == 200, res.text
    assert res.json()["items"] == []

    async with await _client(session, dedans) as ac:
        res = await ac.get("/api/v1/ged/documents", params=params)
    assert [d["id"] for d in res.json()["items"]] == [str(doc.id)]


@pytest.mark.asyncio
async def test_upload_refuse_hors_espace(session, contexte):
    _, hors, _ = contexte
    async with await _client(session, hors) as ac:
        res = await ac.post(
            "/api/v1/ged/documents",
            data={"espace_code": ESPACE_DOC, "module_code": "contrats-echeances", "entity": "contrat", "entity_id": "x"},
            files={"file": ("a.pdf", b"%PDF-1.4 test", "application/pdf")},
        )
    assert res.status_code == 403, res.text
