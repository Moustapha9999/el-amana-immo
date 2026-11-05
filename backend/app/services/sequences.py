"""Numéros séquentiels partagés (ENT-2026-00001, DEM-2026-000001).

Un verrou PostgreSQL de transaction empêche deux processus uvicorn d'attribuer
le même numéro. Le rang retenu est le plus grand suffixe numérique déjà présent
(pas un COUNT : une suppression ne réattribue pas un numéro).
"""

from __future__ import annotations

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession


async def prochain_numero(db: AsyncSession, colonne, *, prefix: str, annee: int, largeur: int) -> str:
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"bea.seq.{prefix}.{annee}"})
    dernier = await db.scalar(select(func.max(colonne)).where(colonne.like(f"{prefix}-{annee}-%")))
    n = 0
    if dernier:
        suffixe = str(dernier).rsplit("-", 1)[-1]
        if suffixe.isdigit():
            n = int(suffixe)
    return f"{prefix}-{annee}-{n + 1:0{largeur}d}"
