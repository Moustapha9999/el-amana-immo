"""Numéros d'immobilisation : ``PREFIX-YYYY-NNN`` par nature IMMO."""

from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models import CategorieImmobilisation, Immobilisation

# Préfixes courts par code catégorie (TY-…)
PREFIX_BY_CATEGORIE: dict[str, str] = {
    "TY-142010": "AAI",
    "TY-147530": "Log",
    "TY-147050": "Frais",
    "TY-147030": "FraisEmp",
    "TY-142060": "MatBur",
    "TY-142041": "MatInfo",
    "TY-142050": "MatTrans",
    "TY-142020": "Const",
    "TY-142097": "MatExp",
    "TY-142080": "Autres",
    "TY-142160": "AutCorp",
}

_CODE_RE = re.compile(r"^([A-Za-z][A-Za-z0-9]*)-(\d{4})-(\d+)$")


def prefix_from_categorie_code(categorie_code: str) -> str:
    code = (categorie_code or "").strip()
    if code in PREFIX_BY_CATEGORIE:
        return PREFIX_BY_CATEGORIE[code]
    # Fallback : TY-142010 → 142010
    return code.replace("TY-", "") or "IMMO"


def format_code_inventaire(prefix: str, annee: int, seq: int) -> str:
    if seq < 1:
        raise ValueError("seq doit être >= 1")
    width = 3 if seq < 1000 else len(str(seq))
    return f"{prefix}-{annee}-{seq:0{width}d}"


def parse_code_inventaire(code: str) -> tuple[str, int, int] | None:
    m = _CODE_RE.match((code or "").strip())
    if not m:
        return None
    return m.group(1), int(m.group(2)), int(m.group(3))


async def max_sequence(
    db: AsyncSession,
    prefix: str,
    annee: int,
    *,
    exclude_id: UUID | None = None,
) -> int:
    """Plus grand numéro déjà utilisé pour ``PREFIX-YYYY-…`` (0 si aucun)."""
    pattern = f"{prefix}-{annee}-%"
    stmt = select(Immobilisation.code_inventaire).where(
        Immobilisation.code_inventaire.like(pattern),
        Immobilisation.deleted_at.is_(None),
    )
    if exclude_id is not None:
        stmt = stmt.where(Immobilisation.id != exclude_id)
    codes = list((await db.execute(stmt)).scalars().all())
    max_seq = 0
    for code in codes:
        parsed = parse_code_inventaire(code)
        if parsed is None:
            continue
        p, y, seq = parsed
        if p == prefix and y == annee and seq > max_seq:
            max_seq = seq
    return max_seq


async def next_code_inventaire(
    db: AsyncSession,
    categorie_code: str,
    annee: int,
) -> str:
    if annee < 2000 or annee > 2100:
        raise ValidationError(f"Année invalide pour le N° immobilisation : {annee}")
    prefix = prefix_from_categorie_code(categorie_code)
    nxt = (await max_sequence(db, prefix, annee)) + 1
    return format_code_inventaire(prefix, annee, nxt)


async def next_code_for_categorie_id(
    db: AsyncSession,
    categorie_id: UUID,
    annee: int,
) -> str:
    cat = (
        await db.execute(
            select(CategorieImmobilisation).where(
                CategorieImmobilisation.id == categorie_id,
                CategorieImmobilisation.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if cat is None:
        raise NotFoundError("Catégorie", str(categorie_id))
    return await next_code_inventaire(db, cat.code, annee)


async def load_max_sequences_map(db: AsyncSession) -> dict[tuple[str, int], int]:
    """Carte ``(prefix, annee) → max seq`` pour accélérer un import batch."""
    codes = list(
        (
            await db.execute(
                select(Immobilisation.code_inventaire).where(Immobilisation.deleted_at.is_(None))
            )
        )
        .scalars()
        .all()
    )
    out: dict[tuple[str, int], int] = {}
    for code in codes:
        parsed = parse_code_inventaire(code)
        if parsed is None:
            continue
        prefix, annee, seq = parsed
        key = (prefix, annee)
        if seq > out.get(key, 0):
            out[key] = seq
    return out
