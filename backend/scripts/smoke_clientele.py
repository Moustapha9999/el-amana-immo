"""Smoke test : appelle toutes les routes GET /clientele avec un superuser, sur la base configurée."""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from sqlalchemy import delete, select, text
from sqlalchemy.orm import selectinload

from app.core.security import new_jti
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models import User
from app.models.auth import SESSION_KIND_MODULE, SESSION_KIND_PLATFORM, AuthSession
from app.services.auth_session_service import AuthSessionService

EXPORTS = Path("/tmp/smoke_exports")


async def premier(sql: str) -> str | None:
    async with AsyncSessionLocal() as s:
        return (await s.execute(text(sql))).scalar()


async def main() -> int:
    # Sessions créées à la main : issue_module_tokens révoquerait celles des utilisateurs connectés.
    expire = datetime.now(UTC) + timedelta(minutes=30)
    async with AsyncSessionLocal() as s:
        user = (await s.execute(
            select(User).options(selectinload(User.roles)).where(User.is_superuser.is_(True)).limit(1)
        )).scalar_one()
        parent = AuthSession(user_id=user.id, refresh_jti=new_jti(), expires_at=expire,
                             kind=SESSION_KIND_PLATFORM, user_agent="smoke_clientele")
        s.add(parent)
        await s.flush()
        jti = new_jti()
        module = AuthSession(user_id=user.id, refresh_jti=jti, expires_at=expire, kind=SESSION_KIND_MODULE,
                             module_code="clientele", parent_session_id=parent.id, user_agent="smoke_clientele")
        s.add(module)
        await s.flush()
        token = AuthSessionService(s)._pair_for(user, module, jti).access_token
        ids_sessions = [module.id, parent.id]
        await s.commit()
    try:
        return await _appeler(token)
    finally:
        async with AsyncSessionLocal() as s:
            await s.execute(delete(AuthSession).where(AuthSession.id.in_(ids_sessions)))
            await s.commit()


async def _appeler(token: str) -> int:
    ids = {
        "racine": await premier("SELECT racine_client FROM clientele_clients ORDER BY racine_client LIMIT 1"),
        "iid": await premier("SELECT id::text FROM clientele_imports ORDER BY created_at DESC LIMIT 1"),
        "aid": await premier("SELECT id::text FROM clientele_alertes LIMIT 1"),
        "did": await premier("SELECT id::text FROM clientele_declarations_bcm LIMIT 1"),
        "rid": await premier("SELECT id::text FROM clientele_rapprochements LIMIT 1"),
    }
    remplacements = {
        "{racine}": ids["racine"], "{iid}": ids["iid"], "{aid}": ids["aid"], "{did}": ids["did"],
        "{rid}": ids["rid"], "{code}": "cli.stock",
    }

    echecs = 0
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test",
                                 headers={"Authorization": f"Bearer {token}"}, timeout=120) as client:
        for route in app.routes:
            path = getattr(route, "path", "")
            if "GET" not in getattr(route, "methods", set()) or "/clientele" not in path:
                continue
            url = path
            manquant = False
            for cle in [p for p in url.split("/") if p.startswith("{")]:
                valeur = remplacements.get(cle)
                if valeur is None:
                    manquant = True
                    break
                url = url.replace(cle, valeur)
            if manquant:
                print(f"SKIP {path} (aucune donnée)")
                continue
            r = await client.get(url)
            ok = r.status_code < 500
            echecs += 0 if ok else 1
            print(f"{'OK ' if ok else 'ERR'} {r.status_code} {url}")
            if r.status_code == 200 and url.endswith((".xlsx", ".pdf")):
                EXPORTS.mkdir(parents=True, exist_ok=True)
                (EXPORTS / url.strip("/").replace("/", "_")).write_bytes(r.content)
            if not ok:
                print("    ", r.text[:300])
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
