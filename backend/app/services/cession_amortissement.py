"""Arrêt / rattrapage des amortissements pour une cession (note banque)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Amortissement, Immobilisation
from app.services.amortissement_engine import (
    JOURS_AN_COMMERCIAL,
    _annual_rate_fraction,
    build_amortissement_schedule,
    calcul_amortissement,
    days_360,
    parse_period_end,
    quarter_start,
    vnc_a_date,
)


async def preparer_amortissements_cession(
    db: AsyncSession,
    immo: Immobilisation,
    date_cession: date,
) -> tuple[Decimal, Decimal]:
    """Calcule les amortissements jusqu'à la date de cession et arrête le plan.

    - Recalcule / ajuste les lignes jusqu'à ``date_cession`` (prorata inclus)
    - Marque ces lignes comme validées (rattrapage)
    - Annule les périodes strictement postérieures
    - Retourne (cumul, vnc) à la date de cession
    """
    cumul_cible, vnc = vnc_a_date(immo, date_cession)

    # Charger les lignes existantes (hors simulations)
    result = await db.execute(
        select(Amortissement).where(
            Amortissement.immobilisation_id == immo.id,
            Amortissement.simule.is_(False),
        )
    )
    existing = {row.periode: row for row in result.scalars().all()}

    schedule_full = build_amortissement_schedule(immo)
    taux = _annual_rate_fraction(immo)
    vb = immo.valeur_brute.quantize(Decimal("0.01"))
    start = immo.date_acquisition
    fin_excl_cession = date_cession + timedelta(days=1)

    running = Decimal("0.00")
    for periode, montant_plein in schedule_full:
        q_end = parse_period_end(periode)
        if q_end is None or start is None:
            continue
        q_start = quarter_start(q_end)

        if date_cession < max(start, q_start):
            # Période entièrement après la cession → annuler
            row = existing.get(periode)
            if row is not None:
                row.annule = True
                row.valide = False
            continue

        debut = max(start, q_start)
        if date_cession >= q_end:
            montant = montant_plein
        else:
            # Prorata jusqu'à la date de cession
            jours = days_360(debut, fin_excl_cession)
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
        # Plafonner au cumul cible (arrondis)
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
            # Périodes suivantes du plan → annuler
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

    # Annuler toute ligne restante après la date de cession
    for periode, row in existing.items():
        end = parse_period_end(periode)
        if end is not None and quarter_start(end) > date_cession:
            row.annule = True
            row.valide = False

    await db.flush()
    return cumul_cible, vnc
