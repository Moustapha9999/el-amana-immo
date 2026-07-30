"""Consultation des comptes 142 / 148 / 68 liés aux immobilisations.

Vue synthétique (solde, volumes) + détail par immobilisation, avec filtres
exercice / agence / catégorie / période / recherche.
La synthèse par nature (référentiel El Amana) est conservée.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.data.el_amana_referentiel import PLAN_COMPTABLE_EL_AMANA, TYPES_IMMOBILISATION_EL_AMANA
from app.models import Agence, Amortissement, EcritureComptable, Immobilisation
from app.services.amortissement_engine import parse_period_end
from app.services.recap_amortissement import (
    _dotations_par_immo,
    _historique_banque_par_immo,
    _is_import_banque,
    _mouvements_immo,
    _periode_appartient_exercice,
    _q,
    _zero,
)
from app.services.ventilation_amortissements_agence import list_exercices_disponibles

FAMILLES_COMPTE = ("142", "148", "68")

_FAMILLE_META: dict[str, tuple[str, str]] = {
    "142": ("142", "Immobilisations"),
    "148": ("148", "Amortissements cumulés"),
    "68": ("68", "Dotations aux amortissements"),
}


def _libelles_plan() -> dict[str, str]:
    return {str(row["numero"]): str(row["libelle"]) for row in PLAN_COMPTABLE_EL_AMANA}


def _digits(value: str | None) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _compte_matches_famille(compte: str | None, famille: str) -> bool:
    digits = _digits(compte)
    if not digits:
        return False
    if famille == "142":
        # Périmètre immobilisations El Amana : 142xxx à 147xxx
        return digits.startswith("142") or digits.startswith("147")
    if famille == "148":
        return digits.startswith("148")
    if famille == "68":
        return digits.startswith("68")
    return False


def _immo_in_famille(immo: Immobilisation, famille: str) -> bool:
    if famille == "142":
        return _compte_matches_famille(immo.compte_immobilisation, "142")
    if famille == "148":
        return _compte_matches_famille(immo.compte_amortissement, "148") or (
            _compte_matches_famille(immo.compte_immobilisation, "142")
            and bool((immo.compte_amortissement or "").strip())
        )
    if famille == "68":
        return _compte_matches_famille(immo.compte_dotation, "68") or (
            _compte_matches_famille(immo.compte_immobilisation, "142")
            and bool((immo.compte_dotation or "").strip())
        )
    return False


@dataclass
class SoldeNatureLigne:
    nature_code: str
    nature: str
    compte_immobilisation: str
    compte_amortissement: str | None
    libelle_amortissement: str | None
    solde_148: Decimal
    solde_148_n1: Decimal
    compte_dotation: str | None
    libelle_dotation: str | None
    solde_68: Decimal
    valeur_brute: Decimal
    vnc: Decimal
    nb_biens: int


@dataclass
class Soldes14868Result:
    annee: int
    date_arrete: date
    lignes: list[SoldeNatureLigne]
    total_148: Decimal
    total_148_n1: Decimal
    total_68: Decimal
    total_valeur_brute: Decimal
    total_vnc: Decimal
    nb_biens: int


@dataclass
class ConsultationDetailLigne:
    immobilisation_id: str
    date_mvt: date | None
    reference: str
    designation: str
    categorie: str | None
    valeur_brute: Decimal
    dotation: Decimal
    amortissement_cumule: Decimal
    amortissement_cumule_n1: Decimal
    vnc: Decimal
    agence_code: str | None
    agence_libelle: str | None
    exercice: int
    compte_immobilisation: str | None
    compte_amortissement: str | None
    compte_dotation: str | None


@dataclass
class ConsultationCompteResult:
    famille_compte: str
    compte_numero: str
    compte_intitule: str
    annee: int
    date_arrete: date
    date_debut: date | None
    date_fin: date | None
    periode_label: str
    solde_total: Decimal
    nb_immobilisations: int
    nb_mouvements: int
    total_valeur_brute: Decimal
    total_dotation: Decimal
    total_amortissement_cumule: Decimal
    total_amortissement_cumule_n1: Decimal
    total_vnc: Decimal
    lignes: list[SoldeNatureLigne]
    detail: list[ConsultationDetailLigne]
    exercices_disponibles: list[int] = field(default_factory=list)
    # Compat anciens totaux globaux (toutes natures, famille courante)
    total_148: Decimal = field(default_factory=_zero)
    total_148_n1: Decimal = field(default_factory=_zero)
    total_68: Decimal = field(default_factory=_zero)
    nb_biens: int = 0


async def _dotations_detail_par_immo(
    db: AsyncSession,
    annee: int,
    *,
    date_debut: date | None = None,
    date_fin: date | None = None,
) -> dict[UUID, list[tuple[str, Decimal, date | None]]]:
    """Dotations comptabilisées (periode, montant, fin_periode) par immobilisation."""
    result = await db.execute(
        select(Amortissement.immobilisation_id, Amortissement.montant, Amortissement.periode).where(
            Amortissement.annule.is_(False),
            Amortissement.simule.is_(False),
            Amortissement.valide.is_(True),
            Amortissement.periode.like(f"{annee}-%"),
        )
    )
    out: dict[UUID, list[tuple[str, Decimal, date | None]]] = defaultdict(list)
    for immo_id, montant, periode in result.all():
        per = str(periode or "")
        if not _periode_appartient_exercice(per, annee):
            continue
        fin = parse_period_end(per)
        if date_debut and fin and fin < date_debut:
            continue
        if date_fin and fin and fin > date_fin:
            continue
        out[immo_id].append((per, Decimal(montant), fin))
    return out


async def _count_ecritures_mouvements(
    db: AsyncSession,
    *,
    immo_ids: list[UUID],
    famille: str,
    date_debut: date | None,
    date_fin: date | None,
) -> int:
    if not immo_ids:
        return 0
    filters = [EcritureComptable.immobilisation_id.in_(immo_ids)]
    if date_debut is not None:
        filters.append(EcritureComptable.date_ecriture >= date_debut)
    if date_fin is not None:
        filters.append(EcritureComptable.date_ecriture <= date_fin)

    if famille == "142":
        filters.append(
            or_(
                EcritureComptable.compte_debit.like("142%"),
                EcritureComptable.compte_debit.like("147%"),
                EcritureComptable.compte_credit.like("142%"),
                EcritureComptable.compte_credit.like("147%"),
            )
        )
    elif famille == "148":
        filters.append(
            or_(
                EcritureComptable.compte_debit.like("148%"),
                EcritureComptable.compte_credit.like("148%"),
            )
        )
    else:
        filters.append(
            or_(
                EcritureComptable.compte_debit.like("68%"),
                EcritureComptable.compte_credit.like("68%"),
            )
        )

    result = await db.execute(select(EcritureComptable.id).where(*filters))
    return len(result.all())


def _empty_nature_buckets(libelles: dict[str, str]) -> dict[str, dict]:
    natures = [
        t
        for t in TYPES_IMMOBILISATION_EL_AMANA
        if t.get("amortissable") and (t.get("compte_amortissement") or t.get("compte_dotation"))
    ]
    buckets: dict[str, dict] = {}
    for t in natures:
        ci = str(t["compte_immobilisation"])
        ca = str(t["compte_amortissement"]) if t.get("compte_amortissement") else None
        cd = str(t["compte_dotation"]) if t.get("compte_dotation") else None
        buckets[ci] = {
            "nature_code": str(t["code"]),
            "nature": str(t["famille"]),
            "compte_immobilisation": ci,
            "compte_amortissement": ca,
            "libelle_amortissement": libelles.get(ca) if ca else None,
            "compte_dotation": cd,
            "libelle_dotation": libelles.get(cd) if cd else None,
            "solde_148": _zero(),
            "solde_148_n1": _zero(),
            "solde_68": _zero(),
            "valeur_brute": _zero(),
            "vnc": _zero(),
            "nb_biens": 0,
        }
    return buckets


async def build_soldes_148_68(db: AsyncSession, annee: int) -> Soldes14868Result:
    """Synthèse historique par nature (compat clôture / export)."""
    consultation = await build_consultation_compte(db, annee=annee, famille_compte="148")
    return Soldes14868Result(
        annee=consultation.annee,
        date_arrete=consultation.date_arrete,
        lignes=consultation.lignes,
        total_148=consultation.total_148,
        total_148_n1=consultation.total_148_n1,
        total_68=consultation.total_68,
        total_valeur_brute=consultation.total_valeur_brute,
        total_vnc=consultation.total_vnc,
        nb_biens=consultation.nb_biens,
    )


async def build_consultation_compte(
    db: AsyncSession,
    *,
    annee: int,
    famille_compte: str = "148",
    agence_id: UUID | None = None,
    categorie_id: UUID | None = None,
    date_debut: date | None = None,
    date_fin: date | None = None,
    search: str | None = None,
) -> ConsultationCompteResult:
    if annee < 1900 or annee > 2100:
        raise ValueError("Année invalide")

    famille = (famille_compte or "148").strip()
    if famille not in FAMILLES_COMPTE:
        raise ValueError("Compte invalide (142, 148 ou 68).")

    if date_debut and date_fin and date_debut > date_fin:
        raise ValueError("La date de début doit être antérieure ou égale à la date de fin.")

    numero, intitule = _FAMILLE_META[famille]
    libelles = _libelles_plan()
    date_arrete = date(annee, 12, 31)
    debut_eff = date_debut or date(annee, 1, 1)
    fin_eff = date_fin or date_arrete
    periode_label = f"Du {debut_eff.strftime('%d/%m/%Y')} au {fin_eff.strftime('%d/%m/%Y')}"

    period_filter_active = date_debut is not None or date_fin is not None

    stmt = (
        select(Immobilisation)
        .options(selectinload(Immobilisation.categorie))
        .where(Immobilisation.deleted_at.is_(None))
        .order_by(Immobilisation.code_inventaire.asc())
    )
    if agence_id is not None:
        stmt = stmt.where(Immobilisation.agence_id == agence_id)
    if categorie_id is not None:
        stmt = stmt.where(Immobilisation.categorie_id == categorie_id)
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Immobilisation.code_inventaire.ilike(pattern),
                Immobilisation.designation.ilike(pattern),
                Immobilisation.compte_immobilisation.ilike(pattern),
                Immobilisation.compte_amortissement.ilike(pattern),
                Immobilisation.compte_dotation.ilike(pattern),
            )
        )

    result = await db.execute(stmt)
    immos = list(result.scalars().all())

    # Dotations : montants année (vue standard) + détail filtré période
    dotations_db = await _dotations_par_immo(db, annee)
    dotations_detail = await _dotations_detail_par_immo(
        db, annee, date_debut=date_debut, date_fin=date_fin
    )
    hist_banque = await _historique_banque_par_immo(db, annee)

    agence_ids = {i.agence_id for i in immos if i.agence_id}
    agences_map: dict[UUID, Agence] = {}
    if agence_ids:
        ag_rows = await db.execute(select(Agence).where(Agence.id.in_(agence_ids)))
        agences_map = {a.id: a for a in ag_rows.scalars().all()}

    buckets = _empty_nature_buckets(libelles)
    order_keys = list(buckets.keys())
    detail: list[ConsultationDetailLigne] = []
    total_vb = _zero()
    total_dot = _zero()
    total_amt = _zero()
    total_amt_n1 = _zero()
    total_vnc = _zero()
    nb_mvt_amort = 0
    kept_ids: list[UUID] = []

    for immo in immos:
        if not _immo_in_famille(immo, famille):
            continue

        # Filtre période sur date d'acquisition (hors compte 68 avec filtre période amort.)
        if period_filter_active and famille != "68":
            if immo.date_acquisition is None:
                continue
            if date_debut and immo.date_acquisition < date_debut:
                continue
            if date_fin and immo.date_acquisition > date_fin:
                continue

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

        periode_dots = dotations_detail.get(immo.id, [])
        if period_filter_active and famille == "68":
            # Ne garder que les biens ayant une dotation dans la période
            if not periode_dots and not (_is_import_banque(immo) and mvts["dotations_annee"]):
                continue
            dotation = _q(sum((m for _, m, _ in periode_dots), _zero()))
            if not periode_dots and _is_import_banque(immo):
                # Stock banque sans découpage périodique : garder la dotation annuelle
                # uniquement si la période couvre tout l'exercice
                if date_debut and date_debut > date(annee, 1, 1):
                    continue
                if date_fin and date_fin < date_arrete:
                    continue
                dotation = mvts["dotations_annee"]
        else:
            dotation = mvts["dotations_annee"]

        nb_mvt_amort += len(periode_dots) if period_filter_active and famille == "68" else len(
            dotations_db.get(immo.id, [])
        )

        compte = (immo.compte_immobilisation or "").strip()
        if compte not in buckets:
            ca = (immo.compte_amortissement or "").strip() or None
            cd = (immo.compte_dotation or "").strip() or None
            buckets[compte] = {
                "nature_code": "",
                "nature": (immo.categorie.famille if immo.categorie else None)
                or libelles.get(compte)
                or compte,
                "compte_immobilisation": compte,
                "compte_amortissement": ca,
                "libelle_amortissement": libelles.get(ca) if ca else None,
                "compte_dotation": cd,
                "libelle_dotation": libelles.get(cd) if cd else None,
                "solde_148": _zero(),
                "solde_148_n1": _zero(),
                "solde_68": _zero(),
                "valeur_brute": _zero(),
                "vnc": _zero(),
                "nb_biens": 0,
            }

        b = buckets[compte]
        if immo.compte_amortissement:
            b["compte_amortissement"] = immo.compte_amortissement.strip()
            b["libelle_amortissement"] = libelles.get(b["compte_amortissement"])
        if immo.compte_dotation:
            b["compte_dotation"] = immo.compte_dotation.strip()
            b["libelle_dotation"] = libelles.get(b["compte_dotation"])

        b["solde_148"] = _q(b["solde_148"] + mvts["amorts_cumules_n"])
        b["solde_148_n1"] = _q(b["solde_148_n1"] + mvts["amorts_cumules_n1"])
        b["solde_68"] = _q(b["solde_68"] + dotation)
        b["valeur_brute"] = _q(b["valeur_brute"] + mvts["valeur_brute"])
        b["vnc"] = _q(b["vnc"] + mvts["vnc"])
        b["nb_biens"] += 1

        agence = agences_map.get(immo.agence_id) if immo.agence_id else None
        cat_label = immo.categorie.famille if immo.categorie else None
        date_mvt = immo.date_acquisition
        if famille == "68" and periode_dots:
            fins = [f for _, _, f in periode_dots if f]
            if fins:
                date_mvt = max(fins)

        detail.append(
            ConsultationDetailLigne(
                immobilisation_id=str(immo.id),
                date_mvt=date_mvt,
                reference=immo.code_inventaire or "",
                designation=immo.designation or "",
                categorie=cat_label,
                valeur_brute=_q(mvts["valeur_brute"]),
                dotation=_q(dotation),
                amortissement_cumule=_q(mvts["amorts_cumules_n"]),
                amortissement_cumule_n1=_q(mvts["amorts_cumules_n1"]),
                vnc=_q(mvts["vnc"]),
                agence_code=agence.code if agence else None,
                agence_libelle=agence.libelle if agence else None,
                exercice=annee,
                compte_immobilisation=(immo.compte_immobilisation or "").strip() or None,
                compte_amortissement=(immo.compte_amortissement or "").strip() or None,
                compte_dotation=(immo.compte_dotation or "").strip() or None,
            )
        )
        kept_ids.append(immo.id)
        total_vb = _q(total_vb + mvts["valeur_brute"])
        total_dot = _q(total_dot + dotation)
        total_amt = _q(total_amt + mvts["amorts_cumules_n"])
        total_amt_n1 = _q(total_amt_n1 + mvts["amorts_cumules_n1"])
        total_vnc = _q(total_vnc + mvts["vnc"])

    if famille == "142":
        solde_total = total_vb
    elif famille == "148":
        solde_total = total_amt
    else:
        solde_total = total_dot

    extra = sorted(c for c in buckets if c not in order_keys)
    lignes: list[SoldeNatureLigne] = []
    for key in order_keys + extra:
        b = buckets[key]
        if b["nb_biens"] == 0 and key not in order_keys:
            continue
        # En mode filtré, masquer les natures vides du référentiel
        if b["nb_biens"] == 0 and (
            agence_id or categorie_id or (search and search.strip()) or period_filter_active
        ):
            continue
        lignes.append(
            SoldeNatureLigne(
                nature_code=b["nature_code"],
                nature=b["nature"],
                compte_immobilisation=b["compte_immobilisation"],
                compte_amortissement=b["compte_amortissement"],
                libelle_amortissement=b["libelle_amortissement"],
                solde_148=_q(b["solde_148"]),
                solde_148_n1=_q(b["solde_148_n1"]),
                compte_dotation=b["compte_dotation"],
                libelle_dotation=b["libelle_dotation"],
                solde_68=_q(b["solde_68"]),
                valeur_brute=_q(b["valeur_brute"]),
                vnc=_q(b["vnc"]),
                nb_biens=int(b["nb_biens"]),
            )
        )

    nb_ecritures = await _count_ecritures_mouvements(
        db,
        immo_ids=kept_ids,
        famille=famille,
        date_debut=debut_eff if period_filter_active else date(annee, 1, 1),
        date_fin=fin_eff if period_filter_active else date_arrete,
    )
    nb_mouvements = max(nb_mvt_amort, nb_ecritures) if famille == "68" else nb_ecritures
    if nb_mouvements == 0:
        nb_mouvements = len(detail)

    exercices = await list_exercices_disponibles(db)

    return ConsultationCompteResult(
        famille_compte=famille,
        compte_numero=numero,
        compte_intitule=intitule,
        annee=annee,
        date_arrete=date_arrete,
        date_debut=debut_eff,
        date_fin=fin_eff,
        periode_label=periode_label,
        solde_total=solde_total,
        nb_immobilisations=len(detail),
        nb_mouvements=nb_mouvements,
        total_valeur_brute=total_vb,
        total_dotation=total_dot,
        total_amortissement_cumule=total_amt,
        total_amortissement_cumule_n1=total_amt_n1,
        total_vnc=total_vnc,
        lignes=lignes,
        detail=detail,
        exercices_disponibles=exercices,
        total_148=total_amt,
        total_148_n1=total_amt_n1,
        total_68=total_dot,
        nb_biens=len(detail),
    )
