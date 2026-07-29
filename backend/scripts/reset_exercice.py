"""Remet à zéro l'état d'un ou plusieurs exercices comptables (maintenance).

Supprime uniquement les lignes de suivi d'exercice (`exercices_comptables` et,
par cascade, `soldes_ouverture_immobilisations`). Les immobilisations, les
amortissements et les dossiers Archives ne sont pas touchés.

Usage :
    python scripts/reset_exercice.py 2025 2026
"""

import asyncio
import sys

from sqlalchemy import text

from app.db.session import engine


async def main(annees: list[int]) -> None:
    async with engine.begin() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT annee, statut FROM exercices_comptables "
                    "WHERE annee = ANY(:annees) ORDER BY annee"
                ),
                {"annees": annees},
            )
        ).fetchall()
        if not rows:
            print("Aucun exercice à réinitialiser.")
            return

        for annee, statut in rows:
            nb = (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM soldes_ouverture_immobilisations WHERE annee = :a"
                    ),
                    {"a": annee},
                )
            ).scalar()
            print(f"  - exercice {annee} ({statut}) — {nb} solde(s) d'ouverture")

        await conn.execute(
            text("DELETE FROM exercices_comptables WHERE annee = ANY(:annees)"),
            {"annees": annees},
        )
        print(f"Réinitialisé : {', '.join(str(a) for a, _ in rows)}")


if __name__ == "__main__":
    args = [int(a) for a in sys.argv[1:]]
    if not args:
        print("Indiquez au moins une année : python scripts/reset_exercice.py 2025")
        raise SystemExit(1)
    asyncio.run(main(args))
