"""Opérations concernées par une réclamation (référence + montant MRU), relation 1-N.

Les totaux sont toujours calculés par dossier (``GROUP BY reclamation_id``) : un dossier à
plusieurs opérations compte pour **un** dossier, et chaque montant n'est additionné qu'une fois.
"""

from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ReclamationOperation
from app.services.reclamations import constantes as C
from app.services.reclamations.outils import erreur, propre

CENTIME = Decimal("0.01")
MONTANT_MAX = Decimal("9999999999999999.99")


def _montant(valeur: Any, rang: int) -> Decimal:
    try:
        m = Decimal(str(valeur))
    except (InvalidOperation, ValueError):
        raise erreur(f"Opération {rang} : montant non numérique", "MONTANT_INVALIDE") from None
    if not m.is_finite() or m <= 0:
        raise erreur(f"Opération {rang} : le montant doit être strictement positif", "MONTANT_INVALIDE")
    if m != m.quantize(CENTIME):
        raise erreur(f"Opération {rang} : deux décimales au plus", "MONTANT_INVALIDE")
    if m > MONTANT_MAX:
        raise erreur(f"Opération {rang} : montant trop élevé", "MONTANT_INVALIDE")
    return m.quantize(CENTIME)


def normaliser(lignes: list[dict] | None) -> list[tuple[str, Decimal]]:
    """Référence obligatoire et unique dans le dossier, montant > 0 à deux décimales au plus."""
    lignes = lignes or []
    if len(lignes) > C.MAX_OPERATIONS:
        raise erreur(f"{C.MAX_OPERATIONS} opérations au plus par réclamation", "TROP_D_OPERATIONS")
    vues: set[str] = set()
    sortie: list[tuple[str, Decimal]] = []
    for rang, ligne in enumerate(lignes, start=1):
        reference = propre(ligne.get("reference"))
        if not reference:
            raise erreur(f"Opération {rang} : la référence est obligatoire", "OPERATION_REFERENCE_OBLIGATOIRE")
        if len(reference) > 120:
            raise erreur(f"Opération {rang} : référence trop longue (120 caractères)", "OPERATION_REFERENCE_INVALIDE")
        if ligne.get("montant") in (None, ""):
            raise erreur(f"Opération {rang} : le montant est obligatoire", "MONTANT_OBLIGATOIRE")
        cle = reference.casefold()
        if cle in vues:
            raise erreur(f"Opération « {reference} » saisie deux fois", "OPERATION_DOUBLON")
        vues.add(cle)
        sortie.append((reference, _montant(ligne["montant"], rang)))
    return sortie


def inserer(db: AsyncSession, reclamation_id: uuid.UUID, lignes: list[tuple[str, Decimal]],
            user_id: uuid.UUID | None) -> None:
    for ordre, (reference, montant) in enumerate(lignes, start=1):
        db.add(ReclamationOperation(reclamation_id=reclamation_id, ordre=ordre, reference=reference,
                                    montant=montant, devise=C.DEVISE, created_by_id=user_id))


async def lister(db: AsyncSession, reclamation_id: uuid.UUID) -> list[ReclamationOperation]:
    return list((await db.scalars(select(ReclamationOperation).where(
        ReclamationOperation.reclamation_id == reclamation_id).order_by(
        ReclamationOperation.ordre, ReclamationOperation.created_at))).all())


def en_dict(o: ReclamationOperation) -> dict:
    return {"id": str(o.id), "ordre": o.ordre, "reference": o.reference,
            "montant": str(o.montant) if o.montant is not None else None, "devise": o.devise}


def total(montants: list[Decimal | None]) -> Decimal | None:
    connus = [m for m in montants if m is not None]
    return sum(connus, Decimal("0")) if connus else None


async def resumes(db: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[int, Decimal | None]]:
    """Nombre d'opérations et montant total par dossier."""
    if not ids:
        return {}
    rows = (await db.execute(
        select(ReclamationOperation.reclamation_id, func.count(), func.sum(ReclamationOperation.montant))
        .where(ReclamationOperation.reclamation_id.in_(ids))
        .group_by(ReclamationOperation.reclamation_id))).all()
    return {rid: (n, somme) for rid, n, somme in rows}


def montant_str(m: Decimal | None) -> str | None:
    return str(m) if m is not None else None
