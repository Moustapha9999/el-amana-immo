"""Applique les sorties de constructions identifiées par le métier.

Chaque groupe associe une ou plusieurs acquisitions positives à la ligne
Excel négative qui les solde. Pour chaque acquisition : statut SORTIE +
date_fin, annulation des dotations postérieures, suppression des écritures
681 -> 148. La ligne négative est ensuite retirée.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models import (
    Amortissement,
    EcritureComptable,
    Immobilisation,
    PeriodeAmortissement,
    PeriodeAmortissementCategorie,
    SoldeOuvertureImmobilisation,
)
from app.models.enums import StatutImmobilisation

# (codes acquisitions, code ligne négative, date de sortie)
GROUPES: list[tuple[list[str], str, date]] = [
    (["Const-2013-002"], "Const-2023-001", date(2023, 1, 9)),
    (["Const-2017-003"], "Const-2018-002", date(2018, 6, 6)),
    (["Const-2019-004"], "Const-2019-007", date(2019, 11, 5)),
    (["Const-2016-003"], "Const-2021-003", date(2021, 1, 21)),
    (["Const-2018-001"], "Const-2019-006", date(2019, 12, 12)),
    (["Const-2021-001"], "Const-2021-008", date(2021, 3, 15)),
    (["Const-2021-002"], "Const-2022-003", date(2022, 10, 20)),
    (["Const-2021-004"], "Const-2022-002", date(2022, 10, 20)),
    (["Const-2021-005"], "Const-2021-009", date(2021, 4, 13)),
    # 30/11/2006 Immeuble PO → sortie 17/08/2007 (montant Excel 2 610 930,40)
    (["Const-2006-006"], "Const-2007-002", date(2007, 8, 17)),
    # 19/12/2024 TF 10523 + TF 10696 (1 500 000 × 2) → sortie 03/11/2025 (−3 000 000)
    (["Const-2024-001", "Const-2024-002"], "Const-2025-004", date(2025, 11, 3)),
]


def _q(value: Decimal | None) -> Decimal:
    return Decimal(value or 0).quantize(Decimal("0.01"))


def _period_year(periode: str) -> int | None:
    try:
        return int(periode[:4])
    except (TypeError, ValueError):
        return None


async def _immo(db: AsyncSession, code: str) -> Immobilisation | None:
    result = await db.execute(
        select(Immobilisation).where(Immobilisation.code_inventaire == code)
    )
    return result.scalar_one_or_none()


async def _apply_sortie_positive(
    db: AsyncSession,
    positive: Immobilisation,
    *,
    negative: Immobilisation,
    date_sortie: date,
) -> None:
    positive.statut = StatutImmobilisation.SORTIE
    positive.date_fin = date_sortie
    meta = dict(positive.metadata_json or {})
    meta["sortie_excel"] = {
        "date": date_sortie.isoformat(),
        "negatif_code": negative.code_inventaire,
        "negatif_id": str(negative.id),
        "valeur_brute": str(negative.valeur_brute),
        "repaired_at": datetime.now(timezone.utc).isoformat(),
    }
    positive.metadata_json = meta

    amorts = await db.execute(
        select(Amortissement).where(
            Amortissement.immobilisation_id == positive.id,
            Amortissement.annule.is_(False),
        )
    )
    annulees: dict[str, Decimal] = {}
    for amort in amorts.scalars().all():
        annee = _period_year(amort.periode)
        if annee is None or annee <= date_sortie.year:
            continue
        if _q(amort.montant) != 0:
            annulees[amort.periode] = (
                annulees.get(amort.periode, Decimal("0")) + _q(amort.montant)
            )
        amort.annule = True

    if annulees:
        await db.execute(
            delete(EcritureComptable).where(
                EcritureComptable.immobilisation_id == positive.id,
                EcritureComptable.reference.in_(
                    [
                        f"AMORT-{positive.code_inventaire}-{periode}"
                        for periode in annulees
                    ]
                ),
            )
        )

    for periode_code, montant in annulees.items():
        if "-Q" not in periode_code:
            continue
        annee = int(periode_code[:4])
        trimestre = int(periode_code.split("-Q")[1])
        periode = (
            await db.execute(
                select(PeriodeAmortissement).where(
                    PeriodeAmortissement.annee == annee,
                    PeriodeAmortissement.trimestre == trimestre,
                )
            )
        ).scalar_one_or_none()
        if periode is None:
            continue
        periode.total_dotation = max(
            Decimal("0.00"), _q(periode.total_dotation) - _q(montant)
        )
        periode.nb_dotations = max(0, int(periode.nb_dotations or 0) - 1)

        detail = (
            await db.execute(
                select(PeriodeAmortissementCategorie).where(
                    PeriodeAmortissementCategorie.periode_id == periode.id,
                    PeriodeAmortissementCategorie.categorie_id
                    == positive.categorie_id,
                )
            )
        ).scalar_one_or_none()
        if detail is not None:
            detail.total_dotation = max(
                Decimal("0.00"), _q(detail.total_dotation) - _q(montant)
            )
            detail.nb_dotations = max(0, int(detail.nb_dotations or 0) - 1)


async def repair(apply: bool) -> None:
    async with AsyncSessionLocal() as db:
        traites = 0
        for codes_pos, code_neg, date_sortie in GROUPES:
            negatives_deleted = False
            positives: list[Immobilisation] = []
            for code in codes_pos:
                immo = await _immo(db, code)
                if immo is None:
                    print(f"SKIP {code}: introuvable")
                    positives = []
                    break
                positives.append(immo)
            if not positives:
                continue

            negative = await _immo(db, code_neg)
            if negative is None:
                print(f"SKIP {codes_pos} / {code_neg}: négatif introuvable")
                continue

            deja = all(p.date_fin is not None for p in positives) and (
                negative.deleted_at is not None
            )
            if deja:
                print(f"OK   {', '.join(codes_pos)}: sortie déjà appliquée")
                continue

            total_pos = sum((_q(p.valeur_brute) for p in positives), Decimal("0"))
            if total_pos != -_q(negative.valeur_brute):
                print(
                    f"SKIP {codes_pos}: montants incohérents "
                    f"({total_pos} / {negative.valeur_brute})"
                )
                continue

            labels = ", ".join(
                f"{p.code_inventaire} ({(p.designation or '')[:30]})" for p in positives
            )
            print(f"SORTIE {labels} au {date_sortie} via {code_neg}")
            traites += 1
            if not apply:
                continue

            for positive in positives:
                await _apply_sortie_positive(
                    db,
                    positive,
                    negative=negative,
                    date_sortie=date_sortie,
                )

            negative_amorts = await db.execute(
                select(Amortissement).where(
                    Amortissement.immobilisation_id == negative.id
                )
            )
            for row in negative_amorts.scalars().all():
                row.annule = True

            ids = [p.id for p in positives] + [negative.id]
            await db.execute(
                delete(SoldeOuvertureImmobilisation).where(
                    SoldeOuvertureImmobilisation.immobilisation_id.in_(ids)
                )
            )

            now = datetime.now(timezone.utc)
            negative.statut = StatutImmobilisation.SORTIE
            negative.date_fin = date_sortie
            negative.is_active = False
            negative.deleted_at = now
            negative_meta = dict(negative.metadata_json or {})
            negative_meta["soft_deleted_as_excel_exit"] = {
                "matched_codes": [p.code_inventaire for p in positives],
                "matched_ids": [str(p.id) for p in positives],
                "at": now.isoformat(),
            }
            negative.metadata_json = negative_meta
            negatives_deleted = True
            _ = negatives_deleted

        if apply:
            await db.commit()
            print(f"Appliqué : {traites} groupe(s)")
        else:
            print(f"Dry-run : {traites} groupe(s) (relancer avec --apply)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Appliquer les corrections")
    args = parser.parse_args()
    asyncio.run(repair(apply=args.apply))


if __name__ == "__main__":
    main()
