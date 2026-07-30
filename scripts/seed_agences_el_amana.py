"""Charge les agences Banque El Amana (idempotent).

Usage (depuis backend/) :
  .\\.venv\\Scripts\\python scripts/seed_agences_el_amana.py

Appliquer d'abord la migration Alembic :
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

from app.db.session import AsyncSessionLocal, engine
from app.models import entities  # noqa: F401
from app.services.agences_seed import seed_agences_el_amana


async def main() -> None:
    async with AsyncSessionLocal() as session:
        stats = await seed_agences_el_amana(session)
        await session.commit()
        print("Agences El Amana :")
        for key, value in stats.items():
            print(f"  {key}: {value}")


if __name__ == "__main__":

    async def _run() -> None:
        await main()
        await engine.dispose()

    asyncio.run(_run())
