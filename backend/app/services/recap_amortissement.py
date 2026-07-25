"""Récapitulatif tableau d'amortissement — arrêté au 31/12/N.

Agrégation par compte d'immobilisation (142000 → 147530).

Colonnes (formule banque) :
  • Compte immo / Intitulé
  • VB au 31/12/N
  • Compte d'amortissement
  • Amorts cumulés N-1 (au 31/12/N-1)
  • Cessions de l'année N (cumul amort des biens sortis)
  • Dotations de l'année N = somme des dotations comptabilisées de l'exercice N
  • Amorts cumulés N = cumul N-1 − cessions + dotations
  • VNC au 31/12/N = VB − cumul N
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.el_amana_referentiel import PLAN_COMPTABLE_EL_AMANA, TYPES_IMMOBILISATION_EL_AMANA
from app.models import Amortissement, Immobilisation
from app.models.enums import TypeComptePlan
from app.services.amortissement_engine import (
    build_amortissement_schedule,
    cumul_amortissement_a_date,
    parse_period_end,
)

COMPTE_IMMO_MIN = 142000
# Inclut frais immobilisés (147050) et logiciels (147530)
COMPTE_IMMO_MAX = 147530


def _compte_num(compte: str | None) -> int | None:
    if not compte:
        return None
    digits = "".join(ch for ch in str(compte).strip() if ch.isdigit())
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def compte_immo_in_scope(compte: str | None) -> bool:
    n = _compte_num(compte)
    return n is not None and COMPTE_IMMO_MIN <= n <= COMPTE_IMMO_MAX


def _libelles_comptes_immo() -> dict[str, str]:
    out: dict[str, str] = {}
    for row in PLAN_COMPTABLE_EL_AMANA:
        if row.get("type_compte") != TypeComptePlan.IMMOBILISATION:
            continue
        numero = str(row["numero"])
        if compte_immo_in_scope(numero):
            out[numero] = str(row["libelle"])
    return out


def _compte_amort_par_immo() -> dict[str, str]:
    out: dict[str, str] = {}
    for row in TYPES_IMMOBILISATION_EL_AMANA:
        ci = row.get("compte_immobilisation")
        ca = row.get("compte_amortissement")
        if ci and ca:
            out[str(ci)] = str(ca)
    return out


@dataclass
class RecapAmortDetailImmo:
    immobilisation_id: str
    code_inventaire: str
    designation: str
    compte_immobilisation: str
    valeur_brute: Decimal
    amorts_cumules_n1: Decimal
    cessions_annee: Decimal
    dotations_annee: Decimal
    amorts_cumules_n: Decimal
    vnc: Decimal


@dataclass
class RecapAmortLigne:
    compte_immobilisation: str
    intitule: str
    valeur_brute: Decimal
    compte_amortissement: str | None
    amorts_cumules_n1: Decimal
    cessions_annee: Decimal
    dotations_annee: Decimal
    amorts_cumules_n: Decimal
    vnc: Decimal


@dataclass
class RecapAmortissementResult:
    annee: int
    date_arrete: date
    lignes: list[RecapAmortLigne]
    details: list[RecapAmortDetailImmo]
    totaux: RecapAmortLigne


def _zero() -> Decimal:
    return Decimal("0.00")


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def _periode_appartient_exercice(periode: str, annee: int) -> bool:
    p = (periode or "").strip().upper()
    return p.startswith(f"{annee}-Q") or p.startswith(f"{annee}-")


def dotation_exercice(
    immo: Immobilisation,
    annee: int,
    *,
    montants_db: list[Decimal] | None = None,
    date_limite: date | None = None,
    uniquement_comptabilisees: bool = False,
) -> Decimal:
    """Somme des dotations d'amortissement de l'exercice ``annee``.

    Si ``uniquement_comptabilisees`` : uniquement les lignes ``valide`` en base
    (0 si aucune période n'est encore comptabilisée).

    Sinon :
    1. Lignes plan en base (non annulées / non simulées) pour l'année
    2. Sinon plan théorique (VB × taux × durée) limité à ``date_limite`` (sortie)
    """
    if uniquement_comptabilisees:
        return _q(sum(montants_db or [], _zero()))

    if montants_db:
        return _q(sum(montants_db, _zero()))

    limite = date_limite or date(annee, 12, 31)
    total = _zero()
    for periode, montant in build_amortissement_schedule(immo):
        if not _periode_appartient_exercice(periode, annee):
            continue
        fin_periode = parse_period_end(periode)
        if fin_periode is None:
            continue
        if fin_periode > limite:
            continue
        total = _q(total + Decimal(montant))

    if date_limite is not None and date_limite.year == annee:
        date_n1 = date(annee - 1, 12, 31)
        if immo.date_acquisition and immo.date_acquisition <= date_n1:
            base = cumul_amortissement_a_date(immo, date_n1)
        else:
            base = _zero()
        cible = cumul_amortissement_a_date(immo, date_limite)
        theorique = _q(cible - base)
        if theorique < 0:
            theorique = _zero()
        if theorique > total:
            return theorique

    return total


def _is_import_banque(immo: Immobilisation) -> bool:
    meta = getattr(immo, "metadata_json", None) or {}
    return isinstance(meta, dict) and meta.get("source") == "import_banque"


def _mouvements_immo(
    immo: Immobilisation,
    annee: int,
    *,
    montants_dotation_db: list[Decimal] | None = None,
    cumul_n1_db: Decimal | None = None,
    cumul_fin_n_db: Decimal | None = None,
    vnc_fin_n_db: Decimal | None = None,
) -> dict[str, Decimal] | None:
    """Calcule les montants d'une immo pour l'exercice ``annee``, ou None si hors périmètre."""
    if immo.date_acquisition is None:
        return None
    if not compte_immo_in_scope(immo.compte_immobilisation):
        return None

    date_n = date(annee, 12, 31)
    date_n1 = date(annee - 1, 12, 31)
    debut_n = date(annee, 1, 1)

    if immo.date_acquisition > date_n:
        return None

    date_fin = immo.date_fin
    if date_fin is not None and date_fin < debut_n:
        return None

    sorti_en_n = date_fin is not None and debut_n <= date_fin <= date_n
    detenue_fin_n = date_fin is None or date_fin > date_n

    vb = _q(immo.valeur_brute) if detenue_fin_n else _zero()
    use_bank = _is_import_banque(immo)

    if use_bank and cumul_n1_db is not None:
        cumul_n1 = _q(cumul_n1_db)
    elif immo.date_acquisition <= date_n1 and (date_fin is None or date_fin > date_n1):
        cumul_n1 = cumul_amortissement_a_date(immo, date_n1)
    else:
        cumul_n1 = _zero()

    if sorti_en_n:
        assert date_fin is not None
        if use_bank and cumul_fin_n_db is not None:
            cession = _q(cumul_fin_n_db)
        else:
            cession = cumul_amortissement_a_date(immo, date_fin)
        dotation = dotation_exercice(
            immo,
            annee,
            montants_db=montants_dotation_db,
            date_limite=date_fin,
            uniquement_comptabilisees=True,
        )
    else:
        cession = _zero()
        dotation = dotation_exercice(
            immo,
            annee,
            montants_db=montants_dotation_db,
            date_limite=None,
            uniquement_comptabilisees=True,
        )

    # Import banque : conserver le signe des dotations (reclassements négatifs)
    if not use_bank and dotation < 0:
        dotation = _zero()

    if use_bank and detenue_fin_n and cumul_fin_n_db is not None:
        cumul_n = _q(cumul_fin_n_db)
    else:
        cumul_n = _q(cumul_n1 - cession + dotation)
        if not use_bank and cumul_n < 0:
            cumul_n = _zero()

    if use_bank and detenue_fin_n and vnc_fin_n_db is not None:
        vnc = _q(vnc_fin_n_db)
    elif detenue_fin_n:
        vnc = _q(vb - cumul_n)
        if not use_bank and vnc < 0:
            vnc = _zero()
    else:
        vnc = _zero()

    return {
        "valeur_brute": vb,
        "amorts_cumules_n1": cumul_n1,
        "cessions_annee": cession,
        "dotations_annee": _q(dotation),
        "amorts_cumules_n": cumul_n,
        "vnc": vnc,
    }


async def _historique_banque_par_immo(
    db: AsyncSession, annee: int
) -> dict[UUID, dict[str, Decimal]]:
    """Cumul N-1 / fin N / VNC issus des amortissements validés (import banque).

    - cumul_n1 : dernier cumul des périodes strictement antérieures à ``annee``
    - cumul_fin / vnc_fin : dernière période de ``annee``, sinon reprise de l'ouverture
    """
    result = await db.execute(
        select(
            Amortissement.immobilisation_id,
            Amortissement.periode,
            Amortissement.cumul,
            Amortissement.vnc,
        )
        .where(
            Amortissement.annule.is_(False),
            Amortissement.simule.is_(False),
            Amortissement.valide.is_(True),
        )
        .order_by(Amortissement.periode.asc())
    )
    out: dict[UUID, dict[str, Decimal | bool]] = {}
    for immo_id, periode, cumul, vnc in result.all():
        p = str(periode or "")
        year_s = p[:4]
        try:
            year = int(year_s)
        except ValueError:
            continue
        bucket = out.setdefault(
            immo_id,
            {
                "cumul_n1": _zero(),
                "cumul_fin": _zero(),
                "vnc_fin": _zero(),
                "has_n": False,
            },
        )
        if year < annee:
            bucket["cumul_n1"] = _q(Decimal(cumul))
            if not bucket["has_n"]:
                bucket["cumul_fin"] = _q(Decimal(cumul))
                bucket["vnc_fin"] = _q(Decimal(vnc))
        elif year == annee:
            bucket["cumul_fin"] = _q(Decimal(cumul))
            bucket["vnc_fin"] = _q(Decimal(vnc))
            bucket["has_n"] = True

    cleaned: dict[UUID, dict[str, Decimal]] = {}
    for immo_id, bucket in out.items():
        cleaned[immo_id] = {
            "cumul_n1": Decimal(bucket["cumul_n1"]),  # type: ignore[arg-type]
            "cumul_fin": Decimal(bucket["cumul_fin"]),  # type: ignore[arg-type]
            "vnc_fin": Decimal(bucket["vnc_fin"]),  # type: ignore[arg-type]
        }
    return cleaned


async def _dotations_par_immo(db: AsyncSession, annee: int) -> dict[UUID, list[Decimal]]:
    """Montants des dotations COMPTABILISÉES de l'exercice, par immobilisation."""
    result = await db.execute(
        select(Amortissement.immobilisation_id, Amortissement.montant, Amortissement.periode)
        .where(
            Amortissement.annule.is_(False),
            Amortissement.simule.is_(False),
            Amortissement.valide.is_(True),
            Amortissement.periode.like(f"{annee}-%"),
        )
    )
    out: dict[UUID, list[Decimal]] = defaultdict(list)
    for immo_id, montant, periode in result.all():
        if not _periode_appartient_exercice(str(periode), annee):
            continue
        out[immo_id].append(Decimal(montant))
    return out


async def build_recap_amortissement(db: AsyncSession, annee: int) -> RecapAmortissementResult:
    if annee < 1900 or annee > 2100:
        raise ValueError("Année invalide")

    libelles = _libelles_comptes_immo()
    amort_map = _compte_amort_par_immo()
    dotations_db = await _dotations_par_immo(db, annee)
    hist_banque = await _historique_banque_par_immo(db, annee)

    result = await db.execute(
        select(Immobilisation)
        .where(Immobilisation.deleted_at.is_(None))
        .order_by(Immobilisation.compte_immobilisation.asc(), Immobilisation.code_inventaire.asc())
    )
    immos = list(result.scalars().all())

    buckets: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: {
            "valeur_brute": _zero(),
            "amorts_cumules_n1": _zero(),
            "cessions_annee": _zero(),
            "dotations_annee": _zero(),
            "amorts_cumules_n": _zero(),
            "vnc": _zero(),
        }
    )
    compte_amort_votes: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    details: list[RecapAmortDetailImmo] = []

    for immo in immos:
        hist = hist_banque.get(immo.id) if _is_import_banque(immo) else None
        mvts = _mouvements_immo(
            immo,
            annee,
            montants_dotation_db=dotations_db.get(immo.id, []),
            cumul_n1_db=hist["cumul_n1"] if hist else None,
            cumul_fin_n_db=hist["cumul_fin"] if hist else None,
            vnc_fin_n_db=hist["vnc_fin"] if hist else None,
        )
        if mvts is None:
            continue
        compte = (immo.compte_immobilisation or "").strip()
        for key, val in mvts.items():
            buckets[compte][key] = _q(buckets[compte][key] + val)
        ca = (immo.compte_amortissement or amort_map.get(compte) or "").strip()
        if ca:
            compte_amort_votes[compte][ca] += 1

        details.append(
            RecapAmortDetailImmo(
                immobilisation_id=str(immo.id),
                code_inventaire=immo.code_inventaire,
                designation=immo.designation,
                compte_immobilisation=compte,
                valeur_brute=mvts["valeur_brute"],
                amorts_cumules_n1=mvts["amorts_cumules_n1"],
                cessions_annee=mvts["cessions_annee"],
                dotations_annee=mvts["dotations_annee"],
                amorts_cumules_n=mvts["amorts_cumules_n"],
                vnc=mvts["vnc"],
            )
        )

    details.sort(key=lambda d: (d.compte_immobilisation, d.code_inventaire))

    comptes_ordonnes = sorted(set(libelles.keys()) | set(buckets.keys()), key=lambda c: (_compte_num(c) or 0, c))

    lignes: list[RecapAmortLigne] = []
    for compte in comptes_ordonnes:
        data = buckets.get(compte)
        if data is None:
            continue
        if all(data[k] == 0 for k in data):
            continue

        votes = compte_amort_votes.get(compte) or {}
        if votes:
            compte_amort = max(votes.items(), key=lambda x: x[1])[0]
        else:
            compte_amort = amort_map.get(compte)

        cumul_n = _q(data["amorts_cumules_n1"] - data["cessions_annee"] + data["dotations_annee"])
        if cumul_n < 0:
            cumul_n = _zero()
        vb = data["valeur_brute"]
        vnc = _q(vb - cumul_n)
        if vnc < 0:
            vnc = _zero()

        lignes.append(
            RecapAmortLigne(
                compte_immobilisation=compte,
                intitule=libelles.get(compte) or compte,
                valeur_brute=vb,
                compte_amortissement=compte_amort,
                amorts_cumules_n1=data["amorts_cumules_n1"],
                cessions_annee=data["cessions_annee"],
                dotations_annee=data["dotations_annee"],
                amorts_cumules_n=cumul_n,
                vnc=vnc,
            )
        )

    totaux = RecapAmortLigne(
        compte_immobilisation="",
        intitule="Total",
        valeur_brute=_q(sum((ligne.valeur_brute for ligne in lignes), _zero())),
        compte_amortissement=None,
        amorts_cumules_n1=_q(sum((ligne.amorts_cumules_n1 for ligne in lignes), _zero())),
        cessions_annee=_q(sum((ligne.cessions_annee for ligne in lignes), _zero())),
        dotations_annee=_q(sum((ligne.dotations_annee for ligne in lignes), _zero())),
        amorts_cumules_n=_q(sum((ligne.amorts_cumules_n for ligne in lignes), _zero())),
        vnc=_q(sum((ligne.vnc for ligne in lignes), _zero())),
    )

    return RecapAmortissementResult(
        annee=annee,
        date_arrete=date(annee, 12, 31),
        lignes=lignes,
        details=details,
        totaux=totaux,
    )
