"""Arrêt / rattrapage des amortissements pour une cession (note banque)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Amortissement, Immobilisation
from app.services.amortissement_engine import (
    JOURS_AN_COMMERCIAL,
    _annual_rate_fraction,
    build_amortissement_schedule,
    calcul_amortissement,
    jours_commerciaux_periode,
    parse_period_end,
    period_key,
    quarter_end,
    quarter_start,
    vnc_a_date,
)
from app.services.bank_immo_import import EXERCICE_CALCUL
from app.services.immobilisation_vnc import (
    cumul_cession_depuis_stock,
    cumul_ouverture_banque,
    vnc_depuis_cumul,
)


async def preparer_amortissements_cession(
    db: AsyncSession,
    immo: Immobilisation,
    date_cession: date,
) -> tuple[Decimal, Decimal]:
    """Calcule les amortissements jusqu'à la date de cession et arrête le plan.

    - Stock banque : base = ``bank.amt_fin`` (ex. 120 000 fin 2025), puis exercice courant
    - Recalcule / ajuste les lignes jusqu'à ``date_cession`` (prorata inclus)
    - Marque ces lignes comme validées (rattrapage)
    - Annule les périodes strictement postérieures
    - Retourne (cumul, vnc) à la date de cession
    """
    result = await db.execute(
        select(Amortissement).where(
            Amortissement.immobilisation_id == immo.id,
            Amortissement.simule.is_(False),
        )
    )
    existing = {row.periode: row for row in result.scalars().all()}
    amorts_exo = [
        row
        for row in existing.values()
        if (parse_period_end(row.periode) or date.min).year == EXERCICE_CALCUL
    ]

    base_banque = cumul_ouverture_banque(immo)
    if base_banque is not None:
        cumul_cible = cumul_cession_depuis_stock(immo, date_cession, amorts_exo)
        vnc = vnc_depuis_cumul(immo, cumul_cible)
        await _arreter_plan_stock_banque(
            db,
            immo,
            date_cession,
            existing=existing,
            base_banque=base_banque,
            cumul_cible=cumul_cible,
            vnc=vnc,
        )
        return cumul_cible, vnc

    cumul_cible, vnc = vnc_a_date(immo, date_cession)
    await _arreter_plan_theorique(
        db,
        immo,
        date_cession,
        existing=existing,
        cumul_cible=cumul_cible,
    )
    return cumul_cible, vnc


async def _arreter_plan_stock_banque(
    db: AsyncSession,
    immo: Immobilisation,
    date_cession: date,
    *,
    existing: dict[str, Amortissement],
    base_banque: Decimal,
    cumul_cible: Decimal,
    vnc: Decimal,
) -> None:
    """Conserve l'historique stock ; fige l'exercice courant sur ``cumul_cible``."""
    q_start_cession = quarter_start(date_cession)
    q_end_cession = quarter_end(date_cession)
    periode_cession = period_key(q_end_cession)

    running = base_banque
    for periode in sorted(p for p in existing if (parse_period_end(p) or date.min).year == EXERCICE_CALCUL):
        end = parse_period_end(periode)
        assert end is not None
        row = existing[periode]
        if end > q_end_cession:
            row.annule = True
            row.valide = False
            continue
        if end < q_start_cession:
            m = (row.montant or Decimal("0")).quantize(Decimal("0.01"))
            running = (running + m).quantize(Decimal("0.01"))
            row.cumul = running
            row.vnc = vnc_depuis_cumul(immo, running)
            row.valide = True
            row.annule = False
            row.simule = False

    montant_cession = (cumul_cible - running).quantize(Decimal("0.01"))
    if montant_cession < 0:
        montant_cession = Decimal("0.00")

    row = existing.get(periode_cession)
    if row is None:
        row = Amortissement(
            immobilisation_id=immo.id,
            periode=periode_cession,
            montant=montant_cession,
            cumul=cumul_cible,
            vnc=vnc,
            simule=False,
            valide=True,
            annule=False,
        )
        db.add(row)
    else:
        row.montant = montant_cession
        row.cumul = cumul_cible
        row.vnc = vnc
        row.valide = True
        row.annule = False
        row.simule = False

    await db.flush()


async def _arreter_plan_theorique(
    db: AsyncSession,
    immo: Immobilisation,
    date_cession: date,
    *,
    existing: dict[str, Amortissement],
    cumul_cible: Decimal,
) -> None:
    schedule_full = build_amortissement_schedule(immo)
    taux = _annual_rate_fraction(immo)
    vb = immo.valeur_brute.quantize(Decimal("0.01"))
    start = immo.date_acquisition
    running = Decimal("0.00")

    for periode, montant_plein in schedule_full:
        q_end = parse_period_end(periode)
        if q_end is None or start is None:
            continue
        q_start = quarter_start(q_end)

        if date_cession < max(start, q_start):
            row = existing.get(periode)
            if row is not None:
                row.annule = True
                row.valide = False
            continue

        debut = max(start, q_start)
        if date_cession >= q_end:
            montant = montant_plein
        else:
            jours = jours_commerciaux_periode(debut, q_start, date_cession)
            duree = Decimal(jours) / JOURS_AN_COMMERCIAL if jours > 0 else Decimal("0")
            montant = calcul_amortissement(vb, taux, duree)
            if montant > montant_plein:
                montant = montant_plein

        if montant <= 0:
            row = existing.get(periode)
            if row is not None and date_cession < q_end:
                row.annule = True
                row.valide = False
            continue

        running = (running + montant).quantize(Decimal("0.01"))
        if running > cumul_cible:
            montant = (montant - (running - cumul_cible)).quantize(Decimal("0.01"))
            running = cumul_cible

        vnc_ligne = (vb - running).quantize(Decimal("0.01"))
        row = existing.get(periode)
        if row is None:
            row = Amortissement(
                immobilisation_id=immo.id,
                periode=periode,
                montant=montant,
                cumul=running,
                vnc=vnc_ligne,
                simule=False,
                valide=True,
                annule=False,
            )
            db.add(row)
            existing[periode] = row
        else:
            row.montant = montant
            row.cumul = running
            row.vnc = vnc_ligne
            row.valide = True
            row.annule = False
            row.simule = False

        if date_cession < q_end:
            for p2, _ in schedule_full:
                if p2 == periode:
                    continue
                end2 = parse_period_end(p2)
                if end2 is not None and end2 > q_end:
                    r2 = existing.get(p2)
                    if r2 is not None:
                        r2.annule = True
                        r2.valide = False
            break

    for periode, row in existing.items():
        end = parse_period_end(periode)
        if end is not None and quarter_start(end) > date_cession:
            row.annule = True
            row.valide = False

    await db.flush()
