"""Charge le plan comptable et les types d'immobilisation El Amana (idempotent).

Usage (depuis backend/) :
  .\\.venv\\Scripts\\python scripts/seed_plan_comptable_el_amana.py

Appliquer d'abord la migration Alembic si la base existe déjà :
  .\\.venv\\Scripts\\alembic upgrade head
"""

import asyncio
import sys
from pathlib import Path

_backend_root = Path(__file__).resolve().parents[1]
if not _backend_root.joinpath("app").is_dir():
    sys.exit("Exécuter depuis le répertoire backend (dossier app/ introuvable).")
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

from sqlalchemy import select

from app.db.session import AsyncSessionLocal, engine
from app.models import ComptePlanComptable
from app.models import entities  # noqa: F401
from app.services.plan_comptable_seed import seed_plan_comptable_el_amana


async def main() -> None:
    async with AsyncSessionLocal() as session:
        marker = await session.execute(select(ComptePlanComptable.numero).where(ComptePlanComptable.numero == "142010"))
        had_el_amana = marker.scalar_one_or_none() is not None
        stats = await seed_plan_comptable_el_amana(session)
        await session.commit()
        action = "mis à jour" if had_el_amana else "initialisé"
        print(f"Plan comptable El Amana {action}:")
        for key, value in stats.items():
            print(f"  {key}: {value}")


if __name__ == "__main__":

    async def _run() -> None:
        await main()
        await engine.dispose()

    asyncio.run(_run())
