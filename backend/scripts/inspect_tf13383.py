"""Inspect / fix TF 13383 construction sortie 2026 — remove dotation."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))

for env_path in (REPO / ".env", ROOT / ".env"):
    if not env_path.exists():
        continue
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

from app.db.session import AsyncSessionLocal, engine  # noqa: E402


async def main() -> None:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT i.id::text AS id,
                           i.code_inventaire,
                           i.designation,
                           i.date_acquisition,
                           i.valeur_brute,
                           i.taux,
                           i.statut::text AS statut,
                           c.code AS categorie,
                           coalesce((i.metadata_json->'bank'->>'dotation')::numeric, 0) AS meta_dot,
                           coalesce((i.metadata_json->'bank'->>'amt_n1')::numeric, 0) AS meta_n1,
                           coalesce((i.metadata_json->'bank'->>'amt_fin')::numeric, 0) AS meta_fin
                    FROM immobilisations i
                    LEFT JOIN categories_immobilisation c ON c.id = i.categorie_id
                    WHERE i.designation ILIKE '%13383%'
                       OR i.designation ILIKE '%TF%13383%'
                    ORDER BY i.date_acquisition
                    """
                )
            )
        ).fetchall()
        print(f"Found {len(rows)} immobilisation(s)")
        for r in rows:
            print(
                f"  {r.code_inventaire} | {r.designation} | acq={r.date_acquisition} "
                f"vb={r.valeur_brute} taux={r.taux} statut={r.statut} cat={r.categorie} "
                f"meta_dot={r.meta_dot} n1={r.meta_n1} fin={r.meta_fin}"
            )
            am = (
                await session.execute(
                    text(
                        """
                        SELECT periode, montant, cumul, vnc, valide, annule, simule
                        FROM amortissements
                        WHERE immobilisation_id = CAST(:id AS uuid)
                        ORDER BY periode
                        """
                    ),
                    {"id": r.id},
                )
            ).fetchall()
            print(f"  amortissements ({len(am)}):")
            for a in am:
                print(
                    f"    {a.periode} montant={a.montant} cumul={a.cumul} vnc={a.vnc} "
                    f"valide={a.valide} annule={a.annule} simule={a.simule}"
                )

            # Related sorties / cessions / rebuts if tables exist
            for table, date_col in (
                ("cessions", "date_cession"),
                ("rebuts", "date_rebut"),
                ("operations_sortie", "date_operation"),
            ):
                exists = (
                    await session.execute(
                        text(
                            """
                            SELECT 1 FROM information_schema.tables
                            WHERE table_schema = 'public' AND table_name = :t
                            """
                        ),
                        {"t": table},
                    )
                ).scalar()
                if not exists:
                    continue
                ops = (
                    await session.execute(
                        text(
                            f"""
                            SELECT * FROM {table}
                            WHERE immobilisation_id = CAST(:id AS uuid)
                            LIMIT 5
                            """
                        ),
                        {"id": r.id},
                    )
                ).mappings().all()
                print(f"  {table}: {len(ops)}")
                for op in ops:
                    print(f"    {dict(op)}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
