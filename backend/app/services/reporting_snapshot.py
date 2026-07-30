"""Rapports figés pour exercices clôturés — lecture depuis Archives (snapshot)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.data.el_amana_referentiel import PLAN_COMPTABLE_EL_AMANA, TYPES_IMMOBILISATION_EL_AMANA
from app.models import ArchiveDossier, ArchiveFichier, ArchiveLigne
from app.services.archive_service import KIND_CLOTURE
from app.services.comptes_par_nature import (
    CompteNatureGroupe,
    CompteNatureLigne,
    CompteOption,
    ComptesParNatureResult,
    _totaux_ligne,
)
from app.services.exercice_guard import annee_est_cloturee
from app.services.recap_amortissement import (
    RecapAmortDetailImmo,
    RecapAmortissementResult,
    RecapAmortLigne,
    _libelles_comptes_immo,
    _q,
    _zero,
)
from app.services.soldes_148_68 import SoldeNatureLigne, Soldes14868Result


def _libelles_plan() -> dict[str, str]:
    return {str(row["numero"]): str(row["libelle"]) for row in PLAN_COMPTABLE_EL_AMANA}


def _nature_meta_by_code() -> dict[str, dict]:
    return {str(t["code"]): t for t in TYPES_IMMOBILISATION_EL_AMANA}


async def _load_cloture_lignes(db: AsyncSession, annee: int) -> list[ArchiveLigne] | None:
    """Charge les lignes du snapshot de clôture, ou None si absent."""
    result = await db.execute(
        select(ArchiveDossier)
        .where(ArchiveDossier.annee == annee)
        .options(selectinload(ArchiveDossier.fichiers).selectinload(ArchiveFichier.lignes))
    )
    dossier = result.scalar_one_or_none()
    if dossier is None:
        return None
    lignes: list[ArchiveLigne] = []
    for fichier in dossier.fichiers or []:
        if fichier.kind != KIND_CLOTURE:
            continue
        lignes.extend(fichier.lignes or [])
    return lignes or None


async def build_recap_from_snapshot(
    db: AsyncSession, annee: int
) -> RecapAmortissementResult | None:
    lignes_src = await _load_cloture_lignes(db, annee)
    if not lignes_src:
        return None

    libelles = _libelles_comptes_immo()
    nature_meta = _nature_meta_by_code()
    by_compte: dict[str, dict] = defaultdict(
        lambda: {
            "valeur_brute": _zero(),
            "amorts_cumules_n1": _zero(),
            "cessions_annee": _zero(),
            "dotations_annee": _zero(),
            "amorts_cumules_n": _zero(),
            "vnc": _zero(),
            "compte_amortissement": None,
        }
    )
    details: list[RecapAmortDetailImmo] = []

    for row in lignes_src:
        meta = nature_meta.get(row.categorie_code or "") or {}
        compte = str(meta.get("compte_immobilisation") or "")
        if not compte:
            continue
        bucket = by_compte[compte]
        bucket["valeur_brute"] = _q(bucket["valeur_brute"] + Decimal(row.valeur_brute or 0))
        bucket["amorts_cumules_n1"] = _q(bucket["amorts_cumules_n1"] + Decimal(row.amt_n1 or 0))
        bucket["dotations_annee"] = _q(bucket["dotations_annee"] + Decimal(row.dotation or 0))
        bucket["amorts_cumules_n"] = _q(bucket["amorts_cumules_n"] + Decimal(row.amt_fin or 0))
        bucket["vnc"] = _q(bucket["vnc"] + Decimal(row.vnc or 0))
        if meta.get("compte_amortissement"):
            bucket["compte_amortissement"] = str(meta["compte_amortissement"])
        raw = row.raw_json if isinstance(row.raw_json, dict) else {}
        details.append(
            RecapAmortDetailImmo(
                immobilisation_id=str(raw.get("immobilisation_id") or ""),
                code_inventaire=str(raw.get("code_inventaire") or ""),
                designation=str(row.designation or ""),
                compte_immobilisation=compte,
                valeur_brute=_q(Decimal(row.valeur_brute or 0)),
                amorts_cumules_n1=_q(Decimal(row.amt_n1 or 0)),
                cessions_annee=_zero(),
                dotations_annee=_q(Decimal(row.dotation or 0)),
                amorts_cumules_n=_q(Decimal(row.amt_fin or 0)),
                vnc=_q(Decimal(row.vnc or 0)),
            )
        )

    lignes: list[RecapAmortLigne] = []
    for compte, b in sorted(by_compte.items()):
        lignes.append(
            RecapAmortLigne(
                compte_immobilisation=compte,
                intitule=libelles.get(compte) or compte,
                valeur_brute=b["valeur_brute"],
                compte_amortissement=b["compte_amortissement"],
                amorts_cumules_n1=b["amorts_cumules_n1"],
                cessions_annee=b["cessions_annee"],
                dotations_annee=b["dotations_annee"],
                amorts_cumules_n=b["amorts_cumules_n"],
                vnc=b["vnc"],
            )
        )

    totaux = RecapAmortLigne(
        compte_immobilisation="",
        intitule="Total",
        valeur_brute=_q(sum((l.valeur_brute for l in lignes), _zero())),
        compte_amortissement=None,
        amorts_cumules_n1=_q(sum((l.amorts_cumules_n1 for l in lignes), _zero())),
        cessions_annee=_q(sum((l.cessions_annee for l in lignes), _zero())),
        dotations_annee=_q(sum((l.dotations_annee for l in lignes), _zero())),
        amorts_cumules_n=_q(sum((l.amorts_cumules_n for l in lignes), _zero())),
        vnc=_q(sum((l.vnc for l in lignes), _zero())),
    )
    return RecapAmortissementResult(
        annee=annee,
        date_arrete=date(annee, 12, 31),
        lignes=lignes,
        details=details,
        totaux=totaux,
    )


async def build_soldes_from_snapshot(db: AsyncSession, annee: int) -> Soldes14868Result | None:
    lignes_src = await _load_cloture_lignes(db, annee)
    if not lignes_src:
        return None

    libelles = _libelles_plan()
    nature_meta = _nature_meta_by_code()
    buckets: dict[str, dict] = {}
    for t in TYPES_IMMOBILISATION_EL_AMANA:
        if not t.get("amortissable"):
            continue
        if not (t.get("compte_amortissement") or t.get("compte_dotation")):
            continue
        ci = str(t["compte_immobilisation"])
        ca = str(t["compte_amortissement"]) if t.get("compte_amortissement") else None
        cd = str(t["compte_dotation"]) if t.get("compte_dotation") else None
        buckets[str(t["code"])] = {
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

    for row in lignes_src:
        code = row.categorie_code or ""
        if code not in buckets:
            continue
        b = buckets[code]
        b["solde_148"] = _q(b["solde_148"] + Decimal(row.amt_fin or 0))
        b["solde_148_n1"] = _q(b["solde_148_n1"] + Decimal(row.amt_n1 or 0))
        b["solde_68"] = _q(b["solde_68"] + Decimal(row.dotation or 0))
        b["valeur_brute"] = _q(b["valeur_brute"] + Decimal(row.valeur_brute or 0))
        b["vnc"] = _q(b["vnc"] + Decimal(row.vnc or 0))
        b["nb_biens"] += 1

    lignes = [
        SoldeNatureLigne(
            nature_code=b["nature_code"],
            nature=b["nature"],
            compte_immobilisation=b["compte_immobilisation"],
            compte_amortissement=b["compte_amortissement"],
            libelle_amortissement=b["libelle_amortissement"],
            solde_148=b["solde_148"],
            solde_148_n1=b["solde_148_n1"],
            compte_dotation=b["compte_dotation"],
            libelle_dotation=b["libelle_dotation"],
            solde_68=b["solde_68"],
            valeur_brute=b["valeur_brute"],
            vnc=b["vnc"],
            nb_biens=b["nb_biens"],
        )
        for b in buckets.values()
        if b["nb_biens"] > 0
    ]
    lignes.sort(key=lambda x: x.compte_immobilisation)
    return Soldes14868Result(
        annee=annee,
        date_arrete=date(annee, 12, 31),
        lignes=lignes,
        total_148=_q(sum((l.solde_148 for l in lignes), _zero())),
        total_148_n1=_q(sum((l.solde_148_n1 for l in lignes), _zero())),
        total_68=_q(sum((l.solde_68 for l in lignes), _zero())),
        total_valeur_brute=_q(sum((l.valeur_brute for l in lignes), _zero())),
        total_vnc=_q(sum((l.vnc for l in lignes), _zero())),
        nb_biens=sum((l.nb_biens for l in lignes), 0),
    )


async def build_comptes_from_snapshot(
    db: AsyncSession,
    annee: int,
    *,
    compte: str | None = None,
) -> ComptesParNatureResult | None:
    lignes_src = await _load_cloture_lignes(db, annee)
    if not lignes_src:
        return None

    libelles = _libelles_comptes_immo()
    nature_meta = _nature_meta_by_code()
    by_compte: dict[str, list[CompteNatureLigne]] = defaultdict(list)

    for row in lignes_src:
        meta = nature_meta.get(row.categorie_code or "") or {}
        ci = str(meta.get("compte_immobilisation") or "")
        if not ci:
            continue
        if compte and ci != compte.strip():
            continue
        raw = row.raw_json if isinstance(row.raw_json, dict) else {}
        by_compte[ci].append(
            CompteNatureLigne(
                immobilisation_id=str(raw.get("immobilisation_id") or ""),
                code_inventaire=str(raw.get("code_inventaire") or ""),
                date_acquisition=row.date_acquisition,
                quantite=int(row.quantite or 1),
                designation=str(row.designation or ""),
                valeur_acquisition=_q(Decimal(row.valeur_brute or 0)),
                taux=row.taux,
                amorts_cumules_n1=_q(Decimal(row.amt_n1 or 0)),
                dotations_annee=_q(Decimal(row.dotation or 0)),
                amorts_cumules_n=_q(Decimal(row.amt_fin or 0)),
                vnc=_q(Decimal(row.vnc or 0)),
                agence_code=row.agence_label,
                agence_libelle=row.agence_label,
            )
        )

    groupes: list[CompteNatureGroupe] = []
    all_lignes: list[CompteNatureLigne] = []
    for ci, lignes in sorted(by_compte.items()):
        tot = _totaux_ligne(lignes, designation=f"Total {ci}")
        groupes.append(
            CompteNatureGroupe(
                compte_immobilisation=ci,
                intitule=libelles.get(ci) or ci,
                lignes=lignes,
                totaux=tot,
            )
        )
        all_lignes.extend(lignes)

    comptes_disponibles = [
        CompteOption(numero=ci, libelle=libelles.get(ci) or ci) for ci in sorted(by_compte)
    ]
    return ComptesParNatureResult(
        annee=annee,
        date_arrete=date(annee, 12, 31),
        groupes=groupes,
        totaux=_totaux_ligne(all_lignes),
        compte_filtre=compte,
        comptes_disponibles=comptes_disponibles,
    )


async def resolve_recap(db: AsyncSession, annee: int) -> RecapAmortissementResult:
    from app.services.recap_amortissement import build_recap_amortissement

    if await annee_est_cloturee(db, annee):
        snap = await build_recap_from_snapshot(db, annee)
        if snap is not None:
            return snap
    return await build_recap_amortissement(db, annee)


async def resolve_soldes(db: AsyncSession, annee: int) -> Soldes14868Result:
    from app.services.soldes_148_68 import build_soldes_148_68

    if await annee_est_cloturee(db, annee):
        snap = await build_soldes_from_snapshot(db, annee)
        if snap is not None:
            return snap
    return await build_soldes_148_68(db, annee)


async def resolve_consultation_soldes(
    db: AsyncSession,
    *,
    annee: int,
    famille_compte: str = "148",
    agence_id=None,
    categorie_id=None,
    date_debut=None,
    date_fin=None,
    search: str | None = None,
):
    from app.services.soldes_148_68 import build_consultation_compte

    return await build_consultation_compte(
        db,
        annee=annee,
        famille_compte=famille_compte,
        agence_id=agence_id,
        categorie_id=categorie_id,
        date_debut=date_debut,
        date_fin=date_fin,
        search=search,
    )


async def resolve_comptes(
    db: AsyncSession, annee: int, *, compte: str | None = None
) -> ComptesParNatureResult:
    from app.services.comptes_par_nature import build_comptes_par_nature

    if await annee_est_cloturee(db, annee):
        snap = await build_comptes_from_snapshot(db, annee, compte=compte)
        if snap is not None:
            return snap
    return await build_comptes_par_nature(db, annee, compte=compte)
