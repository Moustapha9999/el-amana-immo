"""Analyse rapide 6 mois vs 12 mois sur les dotations importées."""

from __future__ import annotations

import asyncio
import sys
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.models import Amortissement, Immobilisation, entities  # noqa: E402, F401
from app.services.bank_immo_import import PERIODE_ARRETE, _q  # noqa: E402


async def main() -> None:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Immobilisation, Amortissement)
                .join(Amortissement, Amortissement.immobilisation_id == Immobilisation.id)
                .where(
                    Amortissement.periode == PERIODE_ARRETE,
                    Immobilisation.valeur_brute > 0,
                    Immobilisation.taux > 0,
                )
            )
        ).all()
        n6 = n12 = n_other = n_prorata_2026 = 0
        samples_6: list[str] = []
        samples_12: list[str] = []
        total_dot = Decimal("0.00")
        for immo, a in rows:
            annual = _q(immo.valeur_brute * (immo.taux or 0) / Decimal("100"))
            if annual <= 0:
                continue
            ratio = float(a.montant / annual)
            total_dot += a.montant
            if immo.date_acquisition and immo.date_acquisition.year >= 2026:
                n_prorata_2026 += 1
                continue
            if 0.45 <= ratio <= 0.55:
                n6 += 1
                if len(samples_6) < 5:
                    samples_6.append(
                        f"{immo.designation[:40]} dot={a.montant} annual={annual} ratio={ratio:.2f}"
                    )
            elif 0.95 <= ratio <= 1.05:
                n12 += 1
                if len(samples_12) < 5:
                    samples_12.append(
                        f"{immo.designation[:40]} dot={a.montant} annual={annual} ratio={ratio:.2f}"
                    )
            else:
                n_other += 1

        tot_vb = (
            await session.execute(select(func.coalesce(func.sum(Immobilisation.valeur_brute), 0)))
        ).scalar()
        n_immo = (await session.execute(select(func.count()).select_from(Immobilisation))).scalar()
        reports = (
            await session.execute(
                select(Immobilisation.designation, Immobilisation.valeur_brute).where(
                    Immobilisation.designation.ilike("%REPORT%")
                )
            )
        ).all()
        print(f"Immobilisations: {n_immo}  VB={tot_vb}")
        print(f"Reports: {reports}")
        print(f"Total dotation periode 2026-06: {total_dot}")
        print(f"Biens <2026 ratio ~6 mois: {n6}")
        print(f"Biens <2026 ratio ~12 mois: {n12}")
        print(f"Biens <2026 autre ratio: {n_other}")
        print(f"Biens 2026 (prorata): {n_prorata_2026}")
        for s in samples_6:
            print("  [6m]", s)
        for s in samples_12:
            print("  [12m]", s)
        if n6 >= n12:
            print("VERDICT: 6 mois (H1 jusqu'au 30/06)")
        elif n12 > n6:
            print("VERDICT: 12 mois (annee pleine)")
        else:
            print("VERDICT: mixte")

        # Solde banque attendu
        print("Solde banque 30/06/2026 attendu:")
        print("  VB=165185262.94  amt_fin=73244042.64  VNC=91941220.30  dot=7527802.99")
        amt_fin = (
            await session.execute(
                select(func.coalesce(func.max(Amortissement.cumul), 0)).select_from(Amortissement)
            )
        )
        # Sum last cumul per immo via subquery-like approach
        from sqlalchemy import text

        sums = (
            await session.execute(
                text(
                    """
                    SELECT coalesce(sum(valeur_brute),0) AS vb,
                           coalesce(sum((metadata_json->'bank'->>'amt_fin')::numeric),0) AS amt_fin,
                           coalesce(sum((metadata_json->'bank'->>'vnc')::numeric),0) AS vnc,
                           coalesce(sum((metadata_json->'bank'->>'dotation')::numeric),0) AS dot
                    FROM immobilisations
                    """
                )
            )
        ).one()
        print(f"Totaux import metadata bank: VB={sums.vb} amt_fin={sums.amt_fin} VNC={sums.vnc} dot={sums.dot}")
        print(f"Ecart VB vs solde: {Decimal('165185262.94') - Decimal(str(sums.vb))}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
