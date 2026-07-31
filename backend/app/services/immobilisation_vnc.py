from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models import Amortissement, Immobilisation
from app.services.amortissement_engine import (
    _annual_rate_fraction,
    _dotation_ytd,
    parse_period_end,
    point_depart_exercice,
    quarter_start,
    vnc_a_date,
)
from app.services.bank_immo_import import EXERCICE_CALCUL


def _q(value: Decimal | str | int | float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _bank_meta(immo: Immobilisation) -> dict:
    meta = immo.metadata_json if isinstance(immo.metadata_json, dict) else {}
    bank = meta.get("bank")
    return bank if isinstance(bank, dict) else {}


def cumul_ouverture_banque(immo: Immobilisation) -> Decimal | None:
    """Cumul fin exercice stock Excel (``bank.amt_fin``), si import banque."""
    bank = _bank_meta(immo)
    if bank.get("amt_fin") is None:
        return None
    return _q(bank["amt_fin"])


def cumul_cession_depuis_stock(
    immo: Immobilisation,
    date_limite: date,
    amorts_exercice: list[Amortissement] | None = None,
    *,
    annee_calcul: int = EXERCICE_CALCUL,
) -> Decimal:
    """Cumul à la cession pour un stock banque.

    Base = ``bank.amt_fin`` (ex. 2025 année entière = 120 000), puis uniquement
    les dotations de l'exercice de calcul (2026) :

    - lignes validées de l'exercice → font foi (y compris montant 0 = pas de dotation)
    - sinon → prorata théorique depuis le 01/01 de l'exercice
    """
    base = cumul_ouverture_banque(immo)
    if base is None:
        return vnc_a_date(immo, date_limite)[0]

    debut_annee = date(annee_calcul, 1, 1)
    if date_limite < debut_annee:
        return vnc_a_date(immo, date_limite)[0]

    vb = immo.valeur_brute.quantize(Decimal("0.01"))
    taux = _annual_rate_fraction(immo)
    start = immo.date_acquisition or debut_annee
    debut_exo = point_depart_exercice(start, annee_calcul)

    rows = [
        r
        for r in (amorts_exercice or [])
        if (not r.annule)
        and (not r.simule)
        and r.valide
        and parse_period_end(r.periode) is not None
        and parse_period_end(r.periode).year == annee_calcul  # type: ignore[union-attr]
    ]
    rows.sort(key=lambda r: r.periode)

    if not rows:
        ytd = _dotation_ytd(vb, taux, debut_exo, date_limite)
        return (base + ytd).quantize(Decimal("0.01"))

    running_add = Decimal("0.00")
    last_completed: date | None = None
    for row in rows:
        end = parse_period_end(row.periode)
        assert end is not None
        q_start = quarter_start(end)
        if date_limite < q_start:
            break
        montant = _q(row.montant)
        if date_limite >= end:
            running_add = (running_add + montant).quantize(Decimal("0.01"))
            last_completed = end
            continue
        # Cession en cours de période : une ligne validée à 0 fige (pas de prorata)
        if montant == 0:
            return (base + running_add).quantize(Decimal("0.01"))
        # Sinon prorata théorique de la période ouverte
        ytd_fin = _dotation_ytd(vb, taux, debut_exo, date_limite)
        ytd_avant = (
            _dotation_ytd(vb, taux, debut_exo, last_completed)
            if last_completed is not None and last_completed >= debut_exo
            else Decimal("0.00")
        )
        return (base + ytd_fin - ytd_avant).quantize(Decimal("0.01"))

    if last_completed is not None and date_limite > last_completed:
        ytd_fin = _dotation_ytd(vb, taux, debut_exo, date_limite)
        ytd_avant = _dotation_ytd(vb, taux, debut_exo, last_completed)
        reste = (ytd_fin - ytd_avant).quantize(Decimal("0.01"))
        if reste < 0:
            reste = Decimal("0.00")
        return (base + running_add + reste).quantize(Decimal("0.01"))

    return (base + running_add).quantize(Decimal("0.01"))


def vnc_depuis_cumul(immo: Immobilisation, cumul: Decimal) -> Decimal:
    vnc = (immo.valeur_brute - cumul).quantize(Decimal("0.01"))
    if vnc < 0:
        return Decimal("0.00")
    return vnc


async def compute_situation_comptable(
    db: AsyncSession,
    immobilisation_id: UUID,
) -> tuple[Immobilisation, Decimal, Decimal]:
    """Situation actuelle : cumul des amortissements déjà validés."""
    immo = await db.get(Immobilisation, immobilisation_id)
    if immo is None or immo.deleted_at is not None:
        raise NotFoundError("Immobilisation", str(immobilisation_id))

    result = await db.execute(
        select(func.coalesce(func.sum(Amortissement.montant), 0)).where(
            Amortissement.immobilisation_id == immobilisation_id,
            Amortissement.valide.is_(True),
            Amortissement.annule.is_(False),
            Amortissement.simule.is_(False),
        )
    )
    cumul = Decimal(str(result.scalar_one())).quantize(Decimal("0.01"))
    vnc = (immo.valeur_brute - cumul).quantize(Decimal("0.01"))
    return immo, cumul, vnc


def compute_situation_a_date(immo: Immobilisation, date_limite) -> tuple[Decimal, Decimal]:
    """Cumul + VNC calculés jusqu'à une date (prorata) — sans stock banque."""
    return vnc_a_date(immo, date_limite)


async def compute_situation_cession(
    db: AsyncSession,
    immo: Immobilisation,
    date_limite: date,
) -> tuple[Decimal, Decimal]:
    """Cumul + VNC pour aperçu / validation de cession.

    Stock banque : part de ``bank.amt_fin`` (cumul fin N-1 Excel) + exercice courant.
    """
    base = cumul_ouverture_banque(immo)
    if base is None:
        return vnc_a_date(immo, date_limite)

    result = await db.execute(
        select(Amortissement).where(
            Amortissement.immobilisation_id == immo.id,
            Amortissement.simule.is_(False),
            Amortissement.periode.like(f"{EXERCICE_CALCUL}-%"),
        )
    )
    amorts = list(result.scalars().all())
    cumul = cumul_cession_depuis_stock(immo, date_limite, amorts)
    return cumul, vnc_depuis_cumul(immo, cumul)
