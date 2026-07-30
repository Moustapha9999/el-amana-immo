"""Vérifie l'aller-retour ORM du statut d'exercice (valeurs en minuscules)."""

import asyncio

from sqlalchemy import select, text

from app.db.session import AsyncSessionLocal
from app.models import ExerciceComptable
from app.models.enums import StatutExercice


async def main() -> None:
    async with AsyncSessionLocal() as session:
        exo = ExerciceComptable(annee=1991, statut=StatutExercice.CLOTURE)
        session.add(exo)
        await session.flush()

        raw = (
            await session.execute(
                text("SELECT statut FROM exercices_comptables WHERE annee = 1991")
            )
        ).scalar()
        loaded = (
            await session.execute(
                select(ExerciceComptable).where(ExerciceComptable.annee == 1991)
            )
        ).scalar_one()

        print("valeur stockée :", raw)
        print("valeur relue   :", loaded.statut, "->", loaded.statut.value)
        assert raw == "cloture", raw
        assert loaded.statut is StatutExercice.CLOTURE
        await session.rollback()
        print("OK — aller-retour cohérent")


if __name__ == "__main__":
    asyncio.run(main())
