"""Répare les sorties Excel (lignes négatives) importées comme biens actifs.

Pour chaque immobilisation à VB négative encore « en service », cherche
l'acquisition positive unique (même compte, |VB|, |cumul ouverture|) et :
  - marque le bien positif SORTIE à la date de la ligne négative
  - annule les amortissements postérieurs à la sortie
  - supprime les écritures 681→148 associées
  - soft-delete la ligne négative et ses soldes d'ouverture
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import delete, select

from app.db.session import AsyncSessionLocal
from app.models import (
    Amortissement,
    EcritureComptable,
    Immobilisation,
    PeriodeAmortissement,
    SoldeOuvertureImmobilisation,
)
from app.models.enums import StatutImmobilisation


def _q(value: Decimal | None) -> Decimal:
    return Decimal(value or 0).quantize(Decimal("0.01"))


def _period_year(periode: str) -> int | None:
    try:
        return int(periode[:4])
    except (TypeError, ValueError):
        return None


async def _opening_cumul(db, immo_id: UUID) -> Decimal:
    solde = await db.execute(
        select(SoldeOuvertureImmobilisation)
        .where(SoldeOuvertureImmobilisation.immobilisation_id == immo_id)
        .order_by(SoldeOuvertureImmobilisation.annee.desc())
    )
    row = solde.scalars().first()
    if row is not None:
        return _q(row.cumul_148)

    amorts = await db.execute(
        select(Amortissement)
        .where(
            Amortissement.immobilisation_id == immo_id,
            Amortissement.annule.is_(False),
            Amortissement.simule.is_(False),
        )
        .order_by(Amortissement.periode)
    )
    rows = list(amorts.scalars().all())
    for preferred in ("2024-12", "2025-12"):
        for amort in rows:
            if amort.periode == preferred:
                return _q(amort.cumul if preferred == "2024-12" else amort.cumul - amort.montant)
    if rows:
        return _q(rows[0].cumul)
    return Decimal("0.00")


async def repair(apply: bool, only_code: str | None = None) -> int:
    async with AsyncSessionLocal() as db:
        negatives_q = await db.execute(
            select(Immobilisation)
            .where(
                Immobilisation.deleted_at.is_(None),
                Immobilisation.valeur_brute < 0,
                Immobilisation.statut == StatutImmobilisation.EN_SERVICE,
            )
            .order_by(Immobilisation.date_acquisition, Immobilisation.code_inventaire)
        )
        negatives = list(negatives_q.scalars().all())
        if only_code:
            negatives = [
                n
                for n in negatives
                if n.code_inventaire == only_code
                or only_code.lower() in (n.designation or "").lower()
            ]

        positives_q = await db.execute(
            select(Immobilisation).where(
                Immobilisation.deleted_at.is_(None),
                Immobilisation.valeur_brute > 0,
                Immobilisation.statut == StatutImmobilisation.EN_SERVICE,
                Immobilisation.date_fin.is_(None),
            )
        )
        positives = list(positives_q.scalars().all())
        cumul_cache: dict[UUID, Decimal] = {}

        async def cumul(immo_id: UUID) -> Decimal:
            if immo_id not in cumul_cache:
                cumul_cache[immo_id] = await _opening_cumul(db, immo_id)
            return cumul_cache[immo_id]

        fixed = 0
        for neg in negatives:
            if neg.date_acquisition is None or neg.categorie_id is None:
                print(f"SKIP {neg.code_inventaire}: date/catégorie manquante")
                continue
            abs_vb = abs(_q(neg.valeur_brute))
            abs_cumul = abs(await cumul(neg.id))
            matches = []
            for pos in positives:
                if pos.categorie_id != neg.categorie_id:
                    continue
                if pos.date_acquisition is None or pos.date_acquisition > neg.date_acquisition:
                    continue
                if _q(pos.valeur_brute) != abs_vb:
                    continue
                if abs(await cumul(pos.id)) != abs_cumul:
                    continue
                if int(pos.quantite or 0) != int(neg.quantite or 0) and int(neg.quantite or 0) > 0:
                    continue
                matches.append(pos)

            if len(matches) != 1:
                print(
                    f"SKIP {neg.code_inventaire} VB={neg.valeur_brute} "
                    f"cumul={-abs_cumul}: {len(matches)} match(s)"
                )
                continue

            pos = matches[0]
            print(
                f"MATCH {neg.code_inventaire} ({neg.date_acquisition}) "
                f"-> sortie de {pos.code_inventaire} ({pos.designation})"
            )
            fixed += 1

            if not apply:
                # Retirer le positif pour éviter un double matching en dry-run.
                positives = [p for p in positives if p.id != pos.id]
                continue

            pos.statut = StatutImmobilisation.SORTIE
            pos.date_fin = neg.date_acquisition
            meta = dict(pos.metadata_json or {})
            meta["sortie_excel"] = {
                "date": neg.date_acquisition.isoformat(),
                "negatif_code": neg.code_inventaire,
                "negatif_id": str(neg.id),
                "valeur_brute": str(neg.valeur_brute),
                "repaired_at": datetime.now(timezone.utc).isoformat(),
            }
            pos.metadata_json = meta

            amorts_q = await db.execute(
                select(Amortissement).where(
                    Amortissement.immobilisation_id == pos.id,
                    Amortissement.annule.is_(False),
                )
            )
            cancelled_by_period: dict[str, Decimal] = {}
            for amort in amorts_q.scalars().all():
                year = _period_year(amort.periode)
                # Après la date de sortie : plus aucune dotation (ex. campagnes 2026).
                if year is None or year <= neg.date_acquisition.year:
                    continue
                if _q(amort.montant) != 0:
                    cancelled_by_period[amort.periode] = (
                        cancelled_by_period.get(amort.periode, Decimal("0"))
                        + _q(amort.montant)
                    )
                amort.annule = True

            refs = [
                f"AMORT-{pos.code_inventaire}-{periode}"
                for periode in cancelled_by_period
            ]
            if refs:
                await db.execute(
                    delete(EcritureComptable).where(
                        EcritureComptable.immobilisation_id == pos.id,
                        EcritureComptable.reference.in_(refs),
                    )
                )

            # Ajuste les totaux de périodes trimestrielles déjà validées.
            for periode, montant in cancelled_by_period.items():
                if "-Q" not in periode:
                    continue
                annee = int(periode[:4])
                trimestre = int(periode.split("-Q")[1])
                period_q = await db.execute(
                    select(PeriodeAmortissement).where(
                        PeriodeAmortissement.annee == annee,
                        PeriodeAmortissement.trimestre == trimestre,
                    )
                )
                period = period_q.scalar_one_or_none()
                if period is None:
                    continue
                period.total_dotation = max(
                    Decimal("0.00"),
                    _q(period.total_dotation) - _q(montant),
                )
                period.nb_dotations = max(0, int(period.nb_dotations or 0) - 1)

            await db.execute(
                delete(SoldeOuvertureImmobilisation).where(
                    SoldeOuvertureImmobilisation.immobilisation_id.in_([pos.id, neg.id])
                )
            )

            now = datetime.now(timezone.utc)
            neg.deleted_at = now
            neg.is_active = False
            neg.statut = StatutImmobilisation.SORTIE
            neg.date_fin = neg.date_acquisition
            neg_meta = dict(neg.metadata_json or {})
            neg_meta["soft_deleted_as_excel_exit"] = {
                "matched_code": pos.code_inventaire,
                "matched_id": str(pos.id),
                "at": now.isoformat(),
            }
            neg.metadata_json = neg_meta

            # Retirer le positif de la liste pour éviter un double matching.
            positives = [p for p in positives if p.id != pos.id]

        if apply:
            await db.commit()
            print(f"Réparé : {fixed} sortie(s)")
        else:
            print(f"Dry-run : {fixed} sortie(s) seraient appliquées (relancer avec --apply)")
        return fixed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Appliquer les corrections")
    parser.add_argument(
        "--only",
        help="Limiter à un code inventaire négatif ou un fragment de désignation",
    )
    args = parser.parse_args()
    asyncio.run(repair(apply=args.apply, only_code=args.only))


if __name__ == "__main__":
    main()
