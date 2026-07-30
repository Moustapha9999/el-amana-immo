"""Fusionne le reclassement construction 352 707 000 - 342 957 000."""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

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
    PeriodeAmortissementCategorie,
    SoldeOuvertureImmobilisation,
)
from app.models.enums import StatutImmobilisation

POSITIVE_CODE = "Const-2024-004"
NEGATIVE_CODE = "Const-2025-002"
VALEUR_NETTE = Decimal("9750000.00")
DOTATION_TRIMESTRIELLE = Decimal("97500.00")


async def repair() -> None:
    async with AsyncSessionLocal() as db:
        positive = (
            await db.execute(
                select(Immobilisation).where(
                    Immobilisation.code_inventaire == POSITIVE_CODE
                )
            )
        ).scalar_one()
        negative = (
            await db.execute(
                select(Immobilisation).where(
                    Immobilisation.code_inventaire == NEGATIVE_CODE
                )
            )
        ).scalar_one()

        if positive.valeur_brute == VALEUR_NETTE and negative.deleted_at is not None:
            print("Reclassement déjà réparé.")
            return

        valeur_avant = Decimal(positive.valeur_brute)
        positive.valeur_brute = VALEUR_NETTE
        meta = dict(positive.metadata_json or {})
        meta["reclassement_excel"] = {
            "date": negative.date_acquisition.isoformat(),
            "negatif_code": negative.code_inventaire,
            "negatif_id": str(negative.id),
            "valeur_avant": str(valeur_avant),
            "montant_reclasse": str(negative.valeur_brute),
            "valeur_apres": str(VALEUR_NETTE),
            "repaired_at": datetime.now(timezone.utc).isoformat(),
        }
        positive.metadata_json = meta

        soldes = await db.execute(
            select(SoldeOuvertureImmobilisation).where(
                SoldeOuvertureImmobilisation.immobilisation_id == positive.id
            )
        )
        for solde in soldes.scalars().all():
            solde.valeur_brute_142 = VALEUR_NETTE
            solde.vnc = max(
                Decimal("0.00"),
                VALEUR_NETTE - Decimal(solde.cumul_148 or 0),
            )

        amorts = await db.execute(
            select(Amortissement)
            .where(Amortissement.immobilisation_id == positive.id)
            .order_by(Amortissement.periode)
        )
        by_period = {row.periode: row for row in amorts.scalars().all()}
        for period in ("2024-12", "2025-12"):
            row = by_period.get(period)
            if row is not None:
                row.vnc = max(
                    Decimal("0.00"),
                    VALEUR_NETTE - Decimal(row.cumul or 0),
                )

        corrections = {
            "2026-Q1": (
                DOTATION_TRIMESTRIELLE,
                DOTATION_TRIMESTRIELLE,
                Decimal("9652500.00"),
            ),
            "2026-Q2": (
                DOTATION_TRIMESTRIELLE,
                Decimal("195000.00"),
                Decimal("9555000.00"),
            ),
        }
        for period, (montant, cumul, vnc) in corrections.items():
            row = by_period[period]
            old_montant = Decimal(row.montant)
            delta = old_montant - montant
            row.montant = montant
            row.cumul = cumul
            row.vnc = vnc
            row.annule = False

            ecriture = (
                await db.execute(
                    select(EcritureComptable).where(
                        EcritureComptable.immobilisation_id == positive.id,
                        EcritureComptable.reference
                        == f"AMORT-{positive.code_inventaire}-{period}",
                    )
                )
            ).scalar_one()
            ecriture.montant = montant

            trimestre = int(period[-1])
            periode = (
                await db.execute(
                    select(PeriodeAmortissement).where(
                        PeriodeAmortissement.annee == 2026,
                        PeriodeAmortissement.trimestre == trimestre,
                    )
                )
            ).scalar_one()
            periode.total_dotation = max(
                Decimal("0.00"),
                Decimal(periode.total_dotation or 0) - delta,
            )

            detail = (
                await db.execute(
                    select(PeriodeAmortissementCategorie).where(
                        PeriodeAmortissementCategorie.periode_id == periode.id,
                        PeriodeAmortissementCategorie.categorie_id
                        == positive.categorie_id,
                    )
                )
            ).scalar_one_or_none()
            if detail is not None and Decimal(detail.total_dotation or 0) >= delta:
                detail.total_dotation = (
                    Decimal(detail.total_dotation or 0) - delta
                )

        negative_amorts = await db.execute(
            select(Amortissement).where(
                Amortissement.immobilisation_id == negative.id
            )
        )
        for row in negative_amorts.scalars().all():
            row.annule = True

        await db.execute(
            delete(SoldeOuvertureImmobilisation).where(
                SoldeOuvertureImmobilisation.immobilisation_id == negative.id
            )
        )
        negative.statut = StatutImmobilisation.SORTIE
        negative.date_fin = negative.date_acquisition
        negative.is_active = False
        negative.deleted_at = datetime.now(timezone.utc)
        negative_meta = dict(negative.metadata_json or {})
        negative_meta["absorbe_par_reclassement"] = {
            "code": positive.code_inventaire,
            "id": str(positive.id),
            "valeur_nette": str(VALEUR_NETTE),
        }
        negative.metadata_json = negative_meta

        await db.commit()
        print(
            "Réparé : base amortissable 9 750 000, "
            "dotation Q1=97 500, Q2=97 500."
        )


if __name__ == "__main__":
    asyncio.run(repair())
