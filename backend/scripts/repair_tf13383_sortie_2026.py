"""Const-2024-003 (TF 13383) : sortie 2026 sans dotation.

Remet l'immo visible (EN_SERVICE) et fige 2026-Q1/Q2 à 0 €
pour que le batch « Calculer » ne recrée pas de dotation
(déjà comptabilisé = 0). Metadata banque alignée (dotation=0,
amt_n1=amt_fin=120 000, VNC=2 880 000).
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from decimal import Decimal
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

CODE = "Const-2024-003"
AMT_N1 = Decimal("120000.00")
VNC = Decimal("2880000.00")


async def main() -> None:
    async with AsyncSessionLocal() as session:
        immo = (
            await session.execute(
                text(
                    """
                    SELECT id::text AS id, code_inventaire, designation, statut::text AS statut,
                           valeur_brute,
                           coalesce((metadata_json->'bank'->>'dotation')::numeric, 0) AS meta_dot,
                           coalesce((metadata_json->'bank'->>'amt_n1')::numeric, 0) AS meta_n1,
                           coalesce((metadata_json->'bank'->>'amt_fin')::numeric, 0) AS meta_fin
                    FROM immobilisations
                    WHERE code_inventaire = :code
                    """
                ),
                {"code": CODE},
            )
        ).mappings().one()
        print(
            f"Avant: {immo['code_inventaire']} statut={immo['statut']} "
            f"meta_dot={immo['meta_dot']} n1={immo['meta_n1']} fin={immo['meta_fin']}"
        )

        # 1) Remettre EN_SERVICE + metadata banque (dotation 0, cumul figé à N-1)
        await session.execute(
            text(
                """
                UPDATE immobilisations
                SET statut = 'EN_SERVICE',
                    metadata_json = jsonb_set(
                      jsonb_set(
                        jsonb_set(
                          jsonb_set(
                            coalesce(metadata_json, '{}'::jsonb),
                            '{bank,dotation}',
                            '0'::jsonb,
                            true
                          ),
                          '{bank,amt_n1}',
                          to_jsonb(CAST(:amt_n1 AS numeric)),
                          true
                        ),
                        '{bank,amt_fin}',
                        to_jsonb(CAST(:amt_n1 AS numeric)),
                        true
                      ),
                      '{bank,vnc}',
                      to_jsonb(CAST(:vnc AS numeric)),
                      true
                    ),
                    updated_at = now()
                WHERE id = CAST(:id AS uuid)
                """
            ),
            {"id": immo["id"], "amt_n1": str(AMT_N1), "vnc": str(VNC)},
        )

        # 2) Figé 2026-Q1 / Q2 à 0 (valide, non annulé) → batch ne recalcule pas
        res = await session.execute(
            text(
                """
                UPDATE amortissements
                SET montant = 0,
                    cumul = CAST(:amt_n1 AS numeric),
                    vnc = CAST(:vnc AS numeric),
                    valide = TRUE,
                    annule = FALSE,
                    simule = FALSE,
                    updated_at = now()
                WHERE immobilisation_id = CAST(:id AS uuid)
                  AND periode IN ('2026-Q1', '2026-Q2')
                RETURNING periode, montant, cumul, vnc, valide, annule
                """
            ),
            {"id": immo["id"], "amt_n1": str(AMT_N1), "vnc": str(VNC)},
        )
        updated = res.fetchall()
        print(
            f"Amortissements 2026 figés à 0: "
            f"{[(r.periode, r.montant, r.cumul, r.vnc, r.valide, r.annule) for r in updated]}"
        )

        # 3) Supprimer écritures 2026 de dotation (si encore présentes)
        del_res = await session.execute(
            text(
                """
                DELETE FROM ecritures_comptables
                WHERE immobilisation_id = CAST(:id AS uuid)
                  AND date_ecriture >= DATE '2026-01-01'
                  AND (
                    reference ILIKE 'AMORT-%2026-Q%'
                    OR libelle ILIKE 'Dotation amortissement%'
                  )
                RETURNING reference, montant, date_ecriture
                """
            ),
            {"id": immo["id"]},
        )
        deleted = del_res.fetchall()
        print(f"Écritures supprimées: {len(deleted)}")
        for d in deleted:
            print(f"  {d.date_ecriture} {d.reference} {d.montant}")

        await session.commit()

        after = (
            await session.execute(
                text(
                    """
                    SELECT statut::text AS statut,
                           coalesce((metadata_json->'bank'->>'dotation')::numeric, 0) AS meta_dot,
                           coalesce((metadata_json->'bank'->>'amt_n1')::numeric, 0) AS meta_n1,
                           coalesce((metadata_json->'bank'->>'amt_fin')::numeric, 0) AS meta_fin,
                           coalesce((metadata_json->'bank'->>'vnc')::numeric, 0) AS meta_vnc
                    FROM immobilisations WHERE id = CAST(:id AS uuid)
                    """
                ),
                {"id": immo["id"]},
            )
        ).mappings().one()
        am = (
            await session.execute(
                text(
                    """
                    SELECT periode, montant, cumul, vnc, valide, annule
                    FROM amortissements
                    WHERE immobilisation_id = CAST(:id AS uuid)
                    ORDER BY periode
                    """
                ),
                {"id": immo["id"]},
            )
        ).fetchall()
        print(
            f"Après: statut={after['statut']} meta_dot={after['meta_dot']} "
            f"n1={after['meta_n1']} fin={after['meta_fin']} vnc={after['meta_vnc']}"
        )
        for a in am:
            print(
                f"  {a.periode} montant={a.montant} cumul={a.cumul} "
                f"vnc={a.vnc} valide={a.valide} annule={a.annule}"
            )

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
