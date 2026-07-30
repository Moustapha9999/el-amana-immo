"""Diagnostic ponctuel : état des exercices et des dossiers archives."""

import asyncio

from sqlalchemy import text

from app.db.session import engine

QUERIES = {
    "exercices": "SELECT annee, statut, archive_dossier_id, message FROM exercices_comptables ORDER BY annee",
    "soldes_ouverture": "SELECT annee, count(*) FROM soldes_ouverture_immobilisations GROUP BY annee ORDER BY annee",
    "dossiers": "SELECT annee, libelle FROM archive_dossiers ORDER BY annee",
    "fichiers_par_kind": "SELECT d.annee, f.kind, count(*) FROM archive_dossiers d JOIN archive_fichiers f ON f.dossier_id = d.id GROUP BY d.annee, f.kind ORDER BY d.annee, f.kind",
    "immos_par_annee": "SELECT extract(year FROM date_acquisition) AS a, count(*) FROM immobilisations WHERE deleted_at IS NULL GROUP BY a ORDER BY a",
    "amorts_periodes": "SELECT periode, count(*), sum(montant) FROM amortissements GROUP BY periode ORDER BY periode",
}


async def main() -> None:
    async with engine.connect() as conn:
        for label, sql in QUERIES.items():
            rows = (await conn.execute(text(sql))).fetchall()
            print(f"== {label} ==")
            for row in rows:
                print("  ", tuple(row))
            if not rows:
                print("   (vide)")


if __name__ == "__main__":
    asyncio.run(main())
