"""Soldes Orion agrégés par compte (natures non amortissables — famille 142).

Saisie unique : après enregistrement, l'exercice est verrouillé
et la zone de saisie disparaît de Soldes 142.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.data.el_amana_referentiel import (
    COMPTES_NON_AMORTISSABLES_EL_AMANA,
    PLAN_COMPTABLE_EL_AMANA,
    TYPES_IMMOBILISATION_EL_AMANA,
)
from app.models.exercice import SoldeCompteOrion

# Ordre d'affichage métier
COMPTES_ORION_142: tuple[str, ...] = ("140000", "142000", "145300")


def _libelle_compte(compte: str) -> str:
    for row in TYPES_IMMOBILISATION_EL_AMANA:
        if str(row.get("compte_immobilisation")) == compte:
            return str(row.get("famille") or compte)
    for row in PLAN_COMPTABLE_EL_AMANA:
        if str(row.get("numero")) == compte:
            return str(row.get("libelle") or compte)
    return compte


def _nature_code_for_compte(compte: str) -> str:
    for row in TYPES_IMMOBILISATION_EL_AMANA:
        if str(row.get("compte_immobilisation")) == compte:
            return str(row.get("code") or "")
    return f"TY-{compte}"


def ensure_compte_orion_autorise(compte: str) -> str:
    c = (compte or "").strip()
    if c not in COMPTES_NON_AMORTISSABLES_EL_AMANA:
        raise ValidationError(
            f"Compte Orion invalide. Autorisés : {', '.join(sorted(COMPTES_NON_AMORTISSABLES_EL_AMANA))}."
        )
    return c


async def is_orion_verrouille(db: AsyncSession, annee: int) -> bool:
    result = await db.execute(
        select(SoldeCompteOrion.id).where(
            SoldeCompteOrion.annee == annee,
            SoldeCompteOrion.verrouille_at.is_not(None),
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def list_soldes_orion(db: AsyncSession, annee: int) -> dict:
    if annee < 1900 or annee > 2100:
        raise ValidationError("Année invalide")
    result = await db.execute(
        select(SoldeCompteOrion).where(SoldeCompteOrion.annee == annee)
    )
    by_compte = {row.compte_immobilisation: row for row in result.scalars().all()}
    verrouille = any(row.verrouille_at is not None for row in by_compte.values())
    lignes: list[dict] = []
    for compte in COMPTES_ORION_142:
        row = by_compte.get(compte)
        lignes.append(
            {
                "annee": annee,
                "compte_immobilisation": compte,
                "nature_code": _nature_code_for_compte(compte),
                "libelle": (row.libelle if row and row.libelle else _libelle_compte(compte)),
                "valeur_brute": Decimal(row.valeur_brute) if row else Decimal("0.00"),
                "source": row.source if row else "orion",
            }
        )
    return {"annee": annee, "verrouille": verrouille, "lignes": lignes}


async def upsert_soldes_orion(
    db: AsyncSession,
    *,
    annee: int,
    lignes: list[dict],
    user_id: UUID | None = None,
) -> dict:
    if annee < 1900 or annee > 2100:
        raise ValidationError("Année invalide")
    if not lignes:
        raise ValidationError("Au moins une ligne de solde Orion est requise.")

    if await is_orion_verrouille(db, annee):
        raise ValidationError(
            "Les soldes Orion de cet exercice sont déjà enregistrés et verrouillés. "
            "Ils ne peuvent plus être modifiés."
        )

    result = await db.execute(
        select(SoldeCompteOrion).where(SoldeCompteOrion.annee == annee)
    )
    existing = {row.compte_immobilisation: row for row in result.scalars().all()}
    now = datetime.now(timezone.utc)

    for raw in lignes:
        compte = ensure_compte_orion_autorise(str(raw.get("compte_immobilisation") or ""))
        try:
            vb = Decimal(str(raw.get("valeur_brute") if raw.get("valeur_brute") is not None else "0"))
        except Exception as exc:  # noqa: BLE001
            raise ValidationError(f"Valeur brute invalide pour le compte {compte}.") from exc
        if vb < 0:
            raise ValidationError(f"La valeur brute du compte {compte} ne peut pas être négative.")
        vb = vb.quantize(Decimal("0.01"))
        libelle = _libelle_compte(compte)
        row = existing.get(compte)
        if row is None:
            row = SoldeCompteOrion(
                id=uuid4(),
                annee=annee,
                compte_immobilisation=compte,
                valeur_brute=vb,
                source="orion",
                libelle=libelle,
                verrouille_at=now,
                updated_by_id=user_id,
            )
            db.add(row)
            existing[compte] = row
        else:
            row.valeur_brute = vb
            row.libelle = libelle
            row.source = "orion"
            row.verrouille_at = now
            row.updated_by_id = user_id

    # Verrouille aussi les comptes non fournis (pour bloquer toute saisie ultérieure)
    for compte in COMPTES_ORION_142:
        row = existing.get(compte)
        if row is None:
            row = SoldeCompteOrion(
                id=uuid4(),
                annee=annee,
                compte_immobilisation=compte,
                valeur_brute=Decimal("0.00"),
                source="orion",
                libelle=_libelle_compte(compte),
                verrouille_at=now,
                updated_by_id=user_id,
            )
            db.add(row)
            existing[compte] = row
        elif row.verrouille_at is None:
            row.verrouille_at = now

    await db.flush()
    return await list_soldes_orion(db, annee)


async def map_soldes_orion_par_compte(db: AsyncSession, annee: int) -> dict[str, Decimal]:
    """Compte → valeur brute Orion (> 0 uniquement)."""
    result = await db.execute(
        select(SoldeCompteOrion).where(
            SoldeCompteOrion.annee == annee,
            SoldeCompteOrion.valeur_brute > 0,
        )
    )
    return {
        row.compte_immobilisation: Decimal(row.valeur_brute).quantize(Decimal("0.01"))
        for row in result.scalars().all()
        if row.compte_immobilisation in COMPTES_NON_AMORTISSABLES_EL_AMANA
    }
