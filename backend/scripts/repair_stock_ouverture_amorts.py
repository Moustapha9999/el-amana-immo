"""Réparation one-shot : seed stock_ouverture 2024-12 + dotation sur 2025-12."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

from app.db.session import AsyncSessionLocal, engine

logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


SQL_INSERT_N1 = text(
    """
    INSERT INTO amortissements (id, immobilisation_id, periode, montant, cumul, vnc, valide, annule, simule, created_at, updated_at)
    SELECT gen_random_uuid(),
           i.id,
           '2024-12',
           0,
           COALESCE((i.metadata_json->'bank'->>'amt_n1')::numeric, 0),
           ROUND(i.valeur_brute - COALESCE((i.metadata_json->'bank'->>'amt_n1')::numeric, 0), 2),
           true, false, false, now(), now()
    FROM immobilisations i
    WHERE i.deleted_at IS NULL
      AND i.metadata_json @> '{"source": "import_banque"}'::jsonb
      AND COALESCE(i.metadata_json->'bank'->>'seed_mode', 'stock_ouverture') <> 'arrete_courant'
      AND NOT EXISTS (
            SELECT 1 FROM amortissements a
            WHERE a.immobilisation_id = i.id AND a.periode = '2024-12'
      )
      AND NOT EXISTS (
            SELECT 1 FROM amortissements a
            WHERE a.immobilisation_id = i.id
              AND a.periode IN ('2026-06', '2026-12')
              AND a.annule IS false
      )
    ON CONFLICT DO NOTHING
    """
)

SQL_UPDATE_OUV = text(
    """
    UPDATE amortissements a
    SET montant = COALESCE((i.metadata_json->'bank'->>'dotation')::numeric, 0),
        cumul = COALESCE((i.metadata_json->'bank'->>'amt_fin')::numeric, a.cumul),
        vnc = COALESCE(
            (i.metadata_json->'bank'->>'vnc')::numeric,
            ROUND(i.valeur_brute - COALESCE((i.metadata_json->'bank'->>'amt_fin')::numeric, a.cumul), 2)
        ),
        updated_at = now()
    FROM immobilisations i
    WHERE a.immobilisation_id = i.id
      AND a.periode = '2025-12'
      AND a.annule IS false
      AND i.deleted_at IS NULL
      AND i.metadata_json @> '{"source": "import_banque"}'::jsonb
      AND COALESCE(i.metadata_json->'bank'->>'seed_mode', 'stock_ouverture') <> 'arrete_courant'
      AND NOT EXISTS (
            SELECT 1 FROM amortissements x
            WHERE x.immobilisation_id = i.id
              AND x.periode IN ('2026-06', '2026-12')
              AND x.annule IS false
      )
    """
)

SQL_SEED_MODE = text(
    """
    UPDATE immobilisations
    SET metadata_json = jsonb_set(
            COALESCE(metadata_json, '{}'::jsonb),
            '{bank,seed_mode}',
            '"stock_ouverture"',
            true
        ),
        updated_at = now()
    WHERE deleted_at IS NULL
      AND metadata_json @> '{"source": "import_banque"}'::jsonb
      AND metadata_json ? 'bank'
      AND COALESCE(metadata_json->'bank'->>'seed_mode', '') = ''
    """
)


async def main() -> None:
    async with AsyncSessionLocal() as db:
        r1 = await db.execute(SQL_INSERT_N1)
        r2 = await db.execute(SQL_UPDATE_OUV)
        r3 = await db.execute(SQL_SEED_MODE)
        await db.commit()
        print(f"insert 2024-12: {r1.rowcount}")
        print(f"update 2025-12: {r2.rowcount}")
        print(f"seed_mode: {r3.rowcount}")

    # Vérif Coffre 17/09/2015
    from app.services.comptes_par_nature import build_comptes_par_nature

    async with AsyncSessionLocal() as db:
        for annee in (2025, 2026):
            res = await build_comptes_par_nature(db, annee, compte="142097")
            g = res.groupes[0] if res.groupes else None
            if not g:
                continue
            for l in g.lignes:
                if l.date_acquisition and l.date_acquisition.isoformat() == "2015-09-17":
                    print(
                        f"{annee} {l.designation}: n1={l.amorts_cumules_n1} "
                        f"dot={l.dotations_annee} fin={l.amorts_cumules_n}"
                    )


if __name__ == "__main__":
    asyncio.run(main())
    asyncio.run(engine.dispose())
