"""Recalcule les dotations importées à l'arrêté 30/06/2026 en prorata (pas 12 mois).

Règle :
  • début = max(date_acquisition, 01/01/2026)
  • fin   = 30/06/2026 (Excel DAYS360)
  • dotation = VB × taux × jours_360 / 360, plafonnée à la VNC restante
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import delete, func, select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.models import Amortissement, EcritureComptable, Immobilisation, entities  # noqa: E402, F401
from app.services.amortissement_engine import days_360  # noqa: E402
from app.services.bank_immo_import import (  # noqa: E402
    DATE_ARRETE_PRORATA_EXCL,
    EXERCICE_CALCUL,
    PERIODE_ARRETE,
    PERIODE_OUVERTURE,
    _q,
)


def dotation_jusqu_arrete(
    vb: Decimal,
    taux_pct: Decimal | None,
    d_acq: date,
    cumul_n1: Decimal,
) -> Decimal:
    if not taux_pct or taux_pct <= 0 or vb <= 0:
        return Decimal("0.00")
    debut = max(d_acq, date(EXERCICE_CALCUL, 1, 1))
    jours = days_360(debut, DATE_ARRETE_PRORATA_EXCL)
    if jours <= 0:
        return Decimal("0.00")
    dot = _q(vb * (taux_pct / Decimal("100")) * (Decimal(jours) / Decimal("360")))
    restant = _q(vb - cumul_n1)
    if restant <= 0:
        return Decimal("0.00")
    return min(dot, restant)


async def main() -> None:
    async with AsyncSessionLocal() as session:
        n_q3 = (
            await session.execute(delete(Amortissement).where(Amortissement.periode == "2026-Q3"))
        ).rowcount
        n_ann = (
            await session.execute(delete(Amortissement).where(Amortissement.periode == "2026-12"))
        ).rowcount
        n_ecr = (await session.execute(delete(EcritureComptable))).rowcount
        print(f"Nettoyage — Q3={n_q3} periode_2026-12={n_ann} ecritures={n_ecr}")

        immos = list((await session.execute(select(Immobilisation))).scalars().all())
        total_dot = Decimal("0.00")
        with_dot = 0
        for immo in immos:
            if immo.date_acquisition is None:
                continue
            rows = list(
                (
                    await session.execute(
                        select(Amortissement).where(Amortissement.immobilisation_id == immo.id)
                    )
                )
                .scalars()
                .all()
            )
            by_per = {r.periode: r for r in rows}
            ouv = by_per.get(PERIODE_OUVERTURE)
            arr = by_per.get(PERIODE_ARRETE)
            cumul_n1 = ouv.cumul if ouv is not None else Decimal("0.00")
            vb = immo.valeur_brute
            taux = immo.taux

            dot = dotation_jusqu_arrete(vb, taux, immo.date_acquisition, cumul_n1)
            amt_fin = _q(cumul_n1 + dot)
            vnc = _q(vb - amt_fin)
            if vnc < 0:
                vnc = Decimal("0.00")
                amt_fin = vb
                dot = max(_q(vb - cumul_n1), Decimal("0.00"))

            if ouv is None:
                session.add(
                    Amortissement(
                        immobilisation_id=immo.id,
                        periode=PERIODE_OUVERTURE,
                        montant=cumul_n1,
                        cumul=cumul_n1,
                        vnc=_q(vb - cumul_n1),
                        valide=True,
                        annule=False,
                        simule=False,
                    )
                )
            else:
                ouv.montant = cumul_n1
                ouv.cumul = cumul_n1
                ouv.vnc = _q(vb - cumul_n1)

            if dot == 0:
                if arr is not None:
                    await session.delete(arr)
            else:
                if arr is None:
                    session.add(
                        Amortissement(
                            immobilisation_id=immo.id,
                            periode=PERIODE_ARRETE,
                            montant=dot,
                            cumul=amt_fin,
                            vnc=vnc,
                            valide=True,
                            annule=False,
                            simule=False,
                        )
                    )
                else:
                    arr.montant = dot
                    arr.cumul = amt_fin
                    arr.vnc = vnc
                total_dot += dot
                with_dot += 1

            meta = dict(immo.metadata_json or {})
            bank = dict(meta.get("bank") or {})
            bank.update(
                {
                    "amt_n1": str(cumul_n1),
                    "dotation": str(dot),
                    "amt_fin": str(amt_fin if dot else cumul_n1),
                    "vnc": str(vnc if dot else _q(vb - cumul_n1)),
                    "prorata_arrete": "2026-06",
                    "duree": "prorata_acquisition_ou_01_01_jusqu_30_06",
                }
            )
            meta["bank"] = bank
            immo.metadata_json = meta

        await session.commit()
        print(f"Recalcul OK — biens avec dotation H1={with_dot} total_dotation={total_dot}")

        # Exemples de contrôle
        samples = (
            await session.execute(
                select(Immobilisation, Amortissement)
                .join(Amortissement, Amortissement.immobilisation_id == Immobilisation.id)
                .where(Amortissement.periode == PERIODE_ARRETE)
                .order_by(Immobilisation.valeur_brute.desc())
                .limit(5)
            )
        ).all()
        for immo, a in samples:
            annual = _q(immo.valeur_brute * (immo.taux or 0) / Decimal("100"))
            ratio = (a.montant / annual) if annual else None
            print(
                f"  {immo.date_acquisition} | {immo.designation[:40]:40} | "
                f"dot={a.montant} annual={annual} ratio={ratio}"
            )

        tot = (
            await session.execute(
                select(func.coalesce(func.sum(Amortissement.montant), 0)).where(
                    Amortissement.periode == PERIODE_ARRETE
                )
            )
        ).scalar()
        print(f"SUM dotation periode 2026-06 = {tot}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
