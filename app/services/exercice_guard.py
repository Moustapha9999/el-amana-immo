"""Garde d'écriture sur les exercices clôturés."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.models import ExerciceComptable
from app.models.enums import StatutExercice


async def annee_est_cloturee(db: AsyncSession, annee: int) -> bool:
    result = await db.execute(
        select(ExerciceComptable.statut).where(ExerciceComptable.annee == annee)
    )
    statut = result.scalar_one_or_none()
    return statut == StatutExercice.CLOTURE


async def ensure_exercice_ouvert_pour_date(db: AsyncSession, d: date | None, *, contexte: str) -> None:
    """Refuse toute mutation datée dans un exercice déjà clôturé."""
    if d is None:
        return
    if await annee_est_cloturee(db, d.year):
        raise ValidationError(
            f"{contexte} : l'exercice {d.year} est clôturé définitivement. "
            "Aucune écriture ni modification n'est autorisée."
        )


async def ensure_exercice_ouvert(db: AsyncSession, annee: int, *, contexte: str) -> None:
    if await annee_est_cloturee(db, annee):
        raise ValidationError(
            f"{contexte} : l'exercice {annee} est clôturé définitivement."
        )


async def get_or_none_exercice(db: AsyncSession, annee: int) -> ExerciceComptable | None:
    result = await db.execute(select(ExerciceComptable).where(ExerciceComptable.annee == annee))
    return result.scalar_one_or_none()
