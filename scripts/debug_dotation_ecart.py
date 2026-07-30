"""Explique l'écart Total 68 (app) vs solde banque 7 527 802,99."""

from __future__ import annotations

import asyncio
import sys
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.models import entities  # noqa: F401, E402
from app.services.soldes_148_68 import build_soldes_148_68  # noqa: E402

BANK_DOT = Decimal("7527802.99")
APP_SHOWN = Decimal("7527799.93")


async def main() -> None:
    async with AsyncSessionLocal() as session:
        soldes = await build_soldes_148_68(session, 2026)
        print(f"App total_68 (service) = {soldes.total_68}")
        print(f"Banque Excel           = {BANK_DOT}")
        print(f"Ecart banque - app     = {BANK_DOT - soldes.total_68}")
        print(f"UI affichee            = {APP_SHOWN}")
        print(f"Ecart banque - UI      = {BANK_DOT - APP_SHOWN}")

        for ligne in soldes.lignes:
            if ligne.compte_immobilisation == "142010" or ligne.nature == "AAI":
                print(
                    f"Ligne AAI: 68={ligne.solde_68} 148={ligne.solde_148} "
                    f"compte_dot={ligne.compte_dotation} nb={ligne.nb_biens}"
                )

        meta = (
            await session.execute(
                text(
                    """
                    SELECT coalesce(sum((metadata_json->'bank'->>'dotation')::numeric), 0)
                    FROM immobilisations
                    """
                )
            )
        ).scalar()
        amort = (
            await session.execute(
                text(
                    """
                    SELECT coalesce(sum(montant), 0)
                    FROM amortissements
                    WHERE periode = '2026-06'
                      AND valide IS TRUE
                      AND annule IS FALSE
                      AND simule IS FALSE
                    """
                )
            )
        ).scalar()
        print(f"Sum metadata bank.dotation = {meta}")
        print(f"Sum amortissements 2026-06 = {amort}")
        print(f"Banque - meta  = {BANK_DOT - Decimal(str(meta))}")
        print(f"Banque - amort = {BANK_DOT - Decimal(str(amort))}")

        diffs = (
            await session.execute(
                text(
                    """
                    SELECT i.code_inventaire,
                           left(i.designation, 45) AS des,
                           coalesce((i.metadata_json->'bank'->>'dotation')::numeric, 0) AS meta_dot,
                           coalesce(a.montant, 0) AS amort_dot,
                           coalesce((i.metadata_json->'bank'->>'dotation')::numeric, 0)
                             - coalesce(a.montant, 0) AS delta
                    FROM immobilisations i
                    LEFT JOIN amortissements a
                      ON a.immobilisation_id = i.id
                     AND a.periode = '2026-06'
                     AND a.valide IS TRUE
                     AND a.annule IS FALSE
                    WHERE coalesce((i.metadata_json->'bank'->>'dotation')::numeric, 0)
                          <> coalesce(a.montant, 0)
                    ORDER BY abs(
                      coalesce((i.metadata_json->'bank'->>'dotation')::numeric, 0)
                      - coalesce(a.montant, 0)
                    ) DESC
                    LIMIT 25
                    """
                )
            )
        ).fetchall()
        print(f"Lignes meta != amort: {len(diffs)}")
        for d in diffs:
            print(f"  {d.code_inventaire} | {d.des} | meta={d.meta_dot} amort={d.amort_dot} delta={d.delta}")

        # Ecarts amt_fin - amt_n1 vs colonne Exer En C (cause probable)
        recalc = (
            await session.execute(
                text(
                    """
                    SELECT left(designation, 45) AS des,
                           (metadata_json->'bank'->>'amt_n1')::numeric AS n1,
                           (metadata_json->'bank'->>'dotation')::numeric AS dot,
                           (metadata_json->'bank'->>'amt_fin')::numeric AS fin,
                           (metadata_json->'bank'->>'amt_fin')::numeric
                             - (metadata_json->'bank'->>'amt_n1')::numeric AS fin_moins_n1,
                           (metadata_json->'bank'->>'dotation')::numeric
                             - (
                               (metadata_json->'bank'->>'amt_fin')::numeric
                               - (metadata_json->'bank'->>'amt_n1')::numeric
                             ) AS ecart_dot_vs_fin_n1
                    FROM immobilisations
                    WHERE metadata_json->'bank'->>'dotation' IS NOT NULL
                      AND (
                        (metadata_json->'bank'->>'dotation')::numeric
                        <> (
                          (metadata_json->'bank'->>'amt_fin')::numeric
                          - (metadata_json->'bank'->>'amt_n1')::numeric
                        )
                      )
                    ORDER BY abs(
                      (metadata_json->'bank'->>'dotation')::numeric
                      - (
                        (metadata_json->'bank'->>'amt_fin')::numeric
                        - (metadata_json->'bank'->>'amt_n1')::numeric
                      )
                    ) DESC
                    LIMIT 30
                    """
                )
            )
        ).fetchall()
        print(f"Lignes ou Exer.En.C != Fin - N-1: {len(recalc)}")
        total_ecart = Decimal("0")
        for r in recalc:
            total_ecart += Decimal(str(r.ecart_dot_vs_fin_n1))
            print(
                f"  {r.des} | dot={r.dot} fin-n1={r.fin_moins_n1} ecart={r.ecart_dot_vs_fin_n1}"
            )
        print(f"Somme ecarts (dot - (fin-n1)) = {total_ecart}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
