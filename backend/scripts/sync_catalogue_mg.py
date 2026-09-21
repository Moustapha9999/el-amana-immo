"""Force sync catalogue plateforme (espace MG + permissions + rôles)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models import Permission, PlateformeEspace, PlateformeModule, Role
from app.services.plateforme_access_service import PlateformeAccessService


async def main() -> None:
    async with AsyncSessionLocal() as session:
        access = PlateformeAccessService(session)
        await access.ensure_catalogue()
        await session.commit()

        espaces = (await session.execute(select(PlateformeEspace.code, PlateformeEspace.statut))).all()
        modules = (
            await session.execute(select(PlateformeModule.code, PlateformeModule.statut))
        ).all()
        perms = await session.scalar(select(Permission.id).where(Permission.code == "mg.stock.view"))
        roles = await session.scalar(
            select(Role.id).where(Role.code == "stock-fournitures.admin")
        )
        print("Espaces:", sorted(espaces))
        print("Modules:", sorted(modules))
        print("mg.stock.view:", "ok" if perms else "MISSING")
        print("stock-fournitures.admin:", "ok" if roles else "MISSING")


if __name__ == "__main__":
    asyncio.run(main())
