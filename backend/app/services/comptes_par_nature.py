"""État des comptes d'immobilisation par nature — détail des biens.

Colonnes :
  Date · Qté · Désignation · Valeur d'acquisition · Taux ·
  Amt cumulés fin ex. préc. · Dotation · Montant amt fin exercice ·
  Valeur nette comptable · Agence
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Agence, Immobilisation
from app.services.recap_amortissement import (
    _dotations_par_immo,
    _historique_banque_par_immo,
    _is_import_banque,
    _libelles_comptes_immo,
    _mouvements_immo,
    _q,
    _zero,
)


@dataclass
class CompteNatureLigne:
    immobilisation_id: str
    code_inventaire: str
    date_acquisition: date | None
    quantite: int
    designation: str
    valeur_acquisition: Decimal
    taux: Decimal | None
    amorts_cumules_n1: Decimal
    dotations_annee: Decimal
    amorts_cumules_n: Decimal
    vnc: Decimal
    agence_code: str | None
    agence_libelle: str | None


@dataclass
class CompteNatureGroupe:
    compte_immobilisation: str
    intitule: str
    lignes: list[CompteNatureLigne]
    totaux: CompteNatureLigne


@dataclass
class CompteOption:
    numero: str
    libelle: str


@dataclass
class ComptesParNatureResult:
    annee: int
    date_arrete: date
    groupes: list[CompteNatureGroupe]
    totaux: CompteNatureLigne
    compte_filtre: str | None
    comptes_disponibles: list[CompteOption]


def _totaux_ligne(lignes: list[CompteNatureLigne], *, designation: str = "Total") -> CompteNatureLigne:
    return CompteNatureLigne(
        immobilisation_id="",
        code_inventaire="",
        date_acquisition=None,
        quantite=sum((ligne.quantite for ligne in lignes), 0),
        designation=designation,
        valeur_acquisition=_q(sum((ligne.valeur_acquisition for ligne in lignes), _zero())),
        taux=None,
        amorts_cumules_n1=_q(sum((ligne.amorts_cumules_n1 for ligne in lignes), _zero())),
        dotations_annee=_q(sum((ligne.dotations_annee for ligne in lignes), _zero())),
        amorts_cumules_n=_q(sum((ligne.amorts_cumules_n for ligne in lignes), _zero())),
        vnc=_q(sum((ligne.vnc for ligne in lignes), _zero())),
        agence_code=None,
        agence_libelle=None,
    )


async def build_comptes_par_nature(
    db: AsyncSession,
    annee: int,
    *,
    compte: str | None = None,
) -> ComptesParNatureResult:
    if annee < 1900 or annee > 2100:
        raise ValueError("Année invalide")

    libelles = _libelles_comptes_immo()
    compte_filtre = (compte or "").strip() or None
    if compte_filtre and compte_filtre not in libelles:
        # Accepte aussi un compte présent uniquement sur des immobilisations
        pass

    comptes_disponibles = [
        CompteOption(numero=numero, libelle=libelle)
        for numero, libelle in sorted(libelles.items(), key=lambda x: x[0])
    ]

    dotations_db = await _dotations_par_immo(db, annee)
    hist_banque = await _historique_banque_par_immo(db, annee)

    agences_rows = await db.execute(select(Agence).where(Agence.deleted_at.is_(None)))
    agences: dict[UUID, Agence] = {a.id: a for a in agences_rows.scalars().all()}

    result = await db.execute(
        select(Immobilisation)
        .where(Immobilisation.deleted_at.is_(None))
        .order_by(
            Immobilisation.compte_immobilisation.asc(),
            Immobilisation.date_acquisition.asc(),
            Immobilisation.code_inventaire.asc(),
        )
    )
    immos = list(result.scalars().all())

    by_compte: dict[str, list[CompteNatureLigne]] = defaultdict(list)

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

        compte_immo = (immo.compte_immobilisation or "").strip()
        if compte_filtre and compte_immo != compte_filtre:
            continue

        agence = agences.get(immo.agence_id) if immo.agence_id else None
        valeur_acquisition = _q(immo.valeur_brute)

        date_n = date(annee, 12, 31)
        detenue_fin_n = immo.date_fin is None or immo.date_fin > date_n

        if detenue_fin_n:
            montant_amt = mvts["amorts_cumules_n"]
            vnc = mvts["vnc"]
            if not _is_import_banque(immo):
                vnc = _q(valeur_acquisition - montant_amt)
                if vnc < 0:
                    vnc = _zero()
        else:
            # Bien sorti dans l'exercice : montant amt = cumul à la sortie, VNC nulle
            montant_amt = mvts["cessions_annee"]
            vnc = _zero()

        by_compte[compte_immo].append(
            CompteNatureLigne(
                immobilisation_id=str(immo.id),
                code_inventaire=immo.code_inventaire,
                date_acquisition=immo.date_acquisition,
                quantite=int(immo.quantite or 1),
                designation=immo.designation,
                valeur_acquisition=valeur_acquisition,
                taux=Decimal(immo.taux) if immo.taux is not None else None,
                amorts_cumules_n1=mvts["amorts_cumules_n1"],
                dotations_annee=mvts["dotations_annee"],
                amorts_cumules_n=montant_amt,
                vnc=vnc,
                agence_code=agence.code if agence else None,
                agence_libelle=agence.libelle if agence else None,
            )
        )

    # Compléter la liste déroulante avec d'éventuels comptes hors référentiel
    known = {c.numero for c in comptes_disponibles}
    for numero in by_compte:
        if numero and numero not in known:
            comptes_disponibles.append(CompteOption(numero=numero, libelle=libelles.get(numero) or numero))
            known.add(numero)
    comptes_disponibles.sort(key=lambda c: c.numero)

    groupes: list[CompteNatureGroupe] = []
    for compte_key in sorted(by_compte.keys(), key=lambda c: (c or "")):
        lignes = by_compte[compte_key]
        if not lignes:
            continue
        groupes.append(
            CompteNatureGroupe(
                compte_immobilisation=compte_key,
                intitule=libelles.get(compte_key) or compte_key,
                lignes=lignes,
                totaux=_totaux_ligne(lignes, designation=f"Total {compte_key}"),
            )
        )

    # Compte choisi sans mouvement : groupe vide pour afficher l'intitulé
    if compte_filtre and not groupes:
        groupes.append(
            CompteNatureGroupe(
                compte_immobilisation=compte_filtre,
                intitule=libelles.get(compte_filtre) or compte_filtre,
                lignes=[],
                totaux=_totaux_ligne([], designation=f"Total {compte_filtre}"),
            )
        )

    all_lignes = [ligne for g in groupes for ligne in g.lignes]
    return ComptesParNatureResult(
        annee=annee,
        date_arrete=date(annee, 12, 31),
        groupes=groupes,
        totaux=_totaux_ligne(all_lignes, designation="Total général"),
        compte_filtre=compte_filtre,
        comptes_disponibles=comptes_disponibles,
    )
