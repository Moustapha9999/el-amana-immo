"""Health / version endpoints (no secrets)."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health_includes_version(client: AsyncClient):
    r = await client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "service" in body
    assert "version" in body
    assert "git_sha" in body
    assert "password" not in body
    assert "secret" not in body


@pytest.mark.asyncio
async def test_version_endpoint(client: AsyncClient):
    r = await client.get("/version")
    assert r.status_code == 200
    body = r.json()
    assert "version" in body
    assert "git_sha" in body
    assert "env" in body
    assert "SECRET_KEY" not in body
    assert "database" not in body
