"""Tableau récapitulatif des immobilisations (variation VB par compte de nature).

Colonnes (exercice N) :
  • Valeurs au 31/12/N-1 — VB des biens détenus à cette date
  • Acquisitions N — VB des biens acquis durant N
  • Cessions N — VB des biens cédés durant N
  • Valeurs au 31/12/N = ouverture + acquisitions − cessions
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Cession, Immobilisation
from app.models.enums import StatutImmobilisation
from app.services.recap_amortissement import _compte_num, _libelles_comptes_immo, _q, _zero, compte_immo_in_scope

STATUTS_CESSION = frozenset(
    {
        StatutImmobilisation.CEDEE,
        StatutImmobilisation.CESSION,
    }
)


@dataclass
class RecapImmoLigne:
    compte: str
    intitule: str
    valeurs_ouverture: Decimal
    acquisitions: Decimal
    cessions: Decimal
    valeurs_cloture: Decimal


@dataclass
class RecapImmobilisationsResult:
    annee: int
    annee_ouverture: int
    date_ouverture: date
    date_cloture: date
    lignes: list[RecapImmoLigne]
    totaux: RecapImmoLigne


def _detenue_a_date(immo: Immobilisation, d: date) -> bool:
    if immo.date_acquisition is None or immo.date_acquisition > d:
        return False
    if immo.date_fin is not None and immo.date_fin <= d:
        return False
    return True


def _vb(immo: Immobilisation) -> Decimal:
    return _q(Decimal(immo.valeur_brute or 0))


def _compte(immo: Immobilisation) -> str:
    return (immo.compte_immobilisation or "").strip()


async def _cession_vb_par_immo(db: AsyncSession, annee: int) -> dict[UUID, Decimal]:
    """VB des immobilisations cédées durant l'exercice (table cessions + date_fin)."""
    debut = date(annee, 1, 1)
    fin = date(annee, 12, 31)
    out: dict[UUID, Decimal] = {}

    rows = await db.execute(
        select(Cession.immobilisation_id, Immobilisation.valeur_brute)
        .join(Immobilisation, Immobilisation.id == Cession.immobilisation_id)
        .where(
            Cession.date_cession >= debut,
            Cession.date_cession <= fin,
            Immobilisation.deleted_at.is_(None),
        )
    )
    for immo_id, vb in rows.all():
        out[immo_id] = _q(Decimal(vb or 0))

    result = await db.execute(
        select(Immobilisation).where(
            Immobilisation.deleted_at.is_(None),
            Immobilisation.date_fin.is_not(None),
            Immobilisation.date_fin >= debut,
            Immobilisation.date_fin <= fin,
            Immobilisation.statut.in_(tuple(STATUTS_CESSION)),
        )
    )
    for immo in result.scalars().all():
        if immo.id not in out and compte_immo_in_scope(_compte(immo)):
            out[immo.id] = _vb(immo)

    return out


async def build_recap_immobilisations(db: AsyncSession, annee: int) -> RecapImmobilisationsResult:
    if annee < 1901 or annee > 2100:
        raise ValueError("Année invalide")

    annee_ouverture = annee - 1
    date_ouverture = date(annee_ouverture, 12, 31)
    date_cloture = date(annee, 12, 31)
    debut_mouvements = date(annee, 1, 1)

    libelles = _libelles_comptes_immo()
    cessions_par_immo = await _cession_vb_par_immo(db, annee)

    result = await db.execute(
        select(Immobilisation)
        .where(Immobilisation.deleted_at.is_(None))
        .order_by(Immobilisation.compte_immobilisation.asc())
    )
    immos = list(result.scalars().all())

    ouverture: dict[str, Decimal] = defaultdict(_zero)
    acquisitions: dict[str, Decimal] = defaultdict(_zero)
    cessions: dict[str, Decimal] = defaultdict(_zero)

    for immo in immos:
        compte = _compte(immo)
        if not compte_immo_in_scope(compte):
            continue

        vb = _vb(immo)

        if _detenue_a_date(immo, date_ouverture):
            ouverture[compte] = _q(ouverture[compte] + vb)

        if (
            immo.date_acquisition is not None
            and debut_mouvements <= immo.date_acquisition <= date_cloture
        ):
            acquisitions[compte] = _q(acquisitions[compte] + vb)

        if immo.id in cessions_par_immo:
            cessions[compte] = _q(cessions[compte] + cessions_par_immo[immo.id])

    comptes_ordonnes = sorted(
        set(libelles.keys()) | set(ouverture.keys()) | set(acquisitions.keys()) | set(cessions.keys()),
        key=lambda c: (_compte_num(c) or 0, c),
    )

    lignes: list[RecapImmoLigne] = []
    for compte in comptes_ordonnes:
        v0 = ouverture.get(compte, _zero())
        acq = acquisitions.get(compte, _zero())
        ces = cessions.get(compte, _zero())
        v1 = _q(v0 + acq - ces)
        if v0 == 0 and acq == 0 and ces == 0 and v1 == 0:
            continue
        lignes.append(
            RecapImmoLigne(
                compte=compte,
                intitule=libelles.get(compte) or compte,
                valeurs_ouverture=v0,
                acquisitions=acq,
                cessions=ces,
                valeurs_cloture=v1,
            )
        )

    totaux = RecapImmoLigne(
        compte="",
        intitule="Total",
        valeurs_ouverture=_q(sum((l.valeurs_ouverture for l in lignes), _zero())),
        acquisitions=_q(sum((l.acquisitions for l in lignes), _zero())),
        cessions=_q(sum((l.cessions for l in lignes), _zero())),
        valeurs_cloture=_q(sum((l.valeurs_cloture for l in lignes), _zero())),
    )

    return RecapImmobilisationsResult(
        annee=annee,
        annee_ouverture=annee_ouverture,
        date_ouverture=date_ouverture,
        date_cloture=date_cloture,
        lignes=lignes,
        totaux=totaux,
    )
