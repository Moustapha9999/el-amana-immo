"""Charge le référentiel EER initial (insère l'absent, ne réécrit jamais)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import AsyncSessionLocal
from app.services.eer_referentiel_service import initialiser_referentiel


async def main() -> None:
    async with AsyncSessionLocal() as session:
        ajouts = await initialiser_referentiel(session)
        await session.commit()
    print("EER — ajoutés :", ajouts)


if __name__ == "__main__":
    asyncio.run(main())
