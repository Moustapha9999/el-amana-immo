"""Soldes des comptes 148 (amortissements) et 68 (dotations) par nature d'immobilisation.

Pour chaque nature du référentiel Banque El Amana :
  • solde 148 = amortissements cumulés fin exercice N
  • solde 68  = dotations de l'exercice N
  • total 68 global = somme des dotations de toutes les natures
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.el_amana_referentiel import PLAN_COMPTABLE_EL_AMANA, TYPES_IMMOBILISATION_EL_AMANA
from app.models import Immobilisation
from app.services.recap_amortissement import (
    _dotations_par_immo,
    _historique_banque_par_immo,
    _is_import_banque,
    _mouvements_immo,
    _q,
    _zero,
)


def _libelles_plan() -> dict[str, str]:
    return {str(row["numero"]): str(row["libelle"]) for row in PLAN_COMPTABLE_EL_AMANA}


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


async def build_soldes_148_68(db: AsyncSession, annee: int) -> Soldes14868Result:
    if annee < 1900 or annee > 2100:
        raise ValueError("Année invalide")

    libelles = _libelles_plan()
    # Nature officielle → comptes 148 / 68
    natures: list[dict] = [
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

    dotations_db = await _dotations_par_immo(db, annee)
    hist_banque = await _historique_banque_par_immo(db, annee)

    result = await db.execute(
        select(Immobilisation)
        .where(Immobilisation.deleted_at.is_(None))
        .order_by(Immobilisation.compte_immobilisation.asc())
    )
    immos = list(result.scalars().all())

    for immo in immos:
        compte = (immo.compte_immobilisation or "").strip()
        if compte not in buckets:
            # Bien hors référentiel officiel amortissable — rattacher si on connaît 148/68 sur l'immo
            ca = (immo.compte_amortissement or "").strip() or None
            cd = (immo.compte_dotation or "").strip() or None
            if not ca and not cd:
                continue
            buckets[compte] = {
                "nature_code": "",
                "nature": libelles.get(compte) or compte,
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

        b = buckets[compte]
        # Préférer les comptes portés par le bien s'ils sont renseignés
        if immo.compte_amortissement:
            b["compte_amortissement"] = immo.compte_amortissement.strip()
            b["libelle_amortissement"] = libelles.get(b["compte_amortissement"])
        if immo.compte_dotation:
            b["compte_dotation"] = immo.compte_dotation.strip()
            b["libelle_dotation"] = libelles.get(b["compte_dotation"])

        b["solde_148"] = _q(b["solde_148"] + mvts["amorts_cumules_n"])
        b["solde_148_n1"] = _q(b["solde_148_n1"] + mvts["amorts_cumules_n1"])
        b["solde_68"] = _q(b["solde_68"] + mvts["dotations_annee"])
        b["valeur_brute"] = _q(b["valeur_brute"] + mvts["valeur_brute"])
        b["vnc"] = _q(b["vnc"] + mvts["vnc"])
        b["nb_biens"] += 1

    # Ordre = référentiel officiel, puis comptes hors référentiel
    order = [str(t["compte_immobilisation"]) for t in natures]
    extra = sorted(c for c in buckets if c not in order)
    ordered_keys = order + extra

    lignes: list[SoldeNatureLigne] = []
    total_148 = _zero()
    total_148_n1 = _zero()
    total_68 = _zero()
    total_vb = _zero()
    total_vnc = _zero()
    nb = 0

    for key in ordered_keys:
        b = buckets[key]
        # Afficher toute nature du référentiel, même à zéro
        if b["nb_biens"] == 0 and key not in order:
            continue
        ligne = SoldeNatureLigne(
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
        lignes.append(ligne)
        total_148 = _q(total_148 + ligne.solde_148)
        total_148_n1 = _q(total_148_n1 + ligne.solde_148_n1)
        total_68 = _q(total_68 + ligne.solde_68)
        total_vb = _q(total_vb + ligne.valeur_brute)
        total_vnc = _q(total_vnc + ligne.vnc)
        nb += ligne.nb_biens

    return Soldes14868Result(
        annee=annee,
        date_arrete=date(annee, 12, 31),
        lignes=lignes,
        total_148=total_148,
        total_148_n1=total_148_n1,
        total_68=total_68,
        total_valeur_brute=total_vb,
        total_vnc=total_vnc,
        nb_biens=nb,
    )
