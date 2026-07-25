"""Aligne amortissements.montant (2026-06) sur metadata bank.dotation (= Exer. En C)."""

from __future__ import annotations

import asyncio
import sys
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.models import Amortissement, Immobilisation, entities  # noqa: E402, F401
from app.services.bank_immo_import import PERIODE_ARRETE, _q  # noqa: E402
from app.services.soldes_148_68 import build_soldes_148_68  # noqa: E402


async def main() -> None:
    async with AsyncSessionLocal() as session:
        immos = list((await session.execute(select(Immobilisation))).scalars().all())
        updated = 0
        for immo in immos:
            meta = immo.metadata_json or {}
            bank = meta.get("bank") if isinstance(meta, dict) else None
            if not isinstance(bank, dict) or bank.get("dotation") is None:
                continue
            dot = _q(Decimal(str(bank["dotation"])))
            rows = list(
                (
                    await session.execute(
                        select(Amortissement).where(
                            Amortissement.immobilisation_id == immo.id,
                            Amortissement.periode == PERIODE_ARRETE,
                        )
                    )
                )
                .scalars()
                .all()
            )
            if not rows:
                if dot == 0:
                    continue
                fin = _q(Decimal(str(bank.get("amt_fin") or 0)))
                vnc = _q(Decimal(str(bank.get("vnc") or 0)))
                session.add(
                    Amortissement(
                        immobilisation_id=immo.id,
                        periode=PERIODE_ARRETE,
                        montant=dot,
                        cumul=fin,
                        vnc=vnc,
                        valide=True,
                        annule=False,
                        simule=False,
                    )
                )
                updated += 1
                continue
            row = rows[0]
            if row.montant != dot:
                row.montant = dot
                updated += 1
        await session.commit()
        soldes = await build_soldes_148_68(session, 2026)
        print(f"Lignes maj: {updated}")
        print(f"Total 68 apres fix: {soldes.total_68}")
        print("Banque Excel:        7527802.99")
        print(f"Ecart: {Decimal('7527802.99') - soldes.total_68}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
