"""Rapport — ventilation des amortissements (compte 68) par agence.

Requêtes SQL (PostgreSQL) — principe :

```sql
-- Dotations comptabilisées de la période, jointure immo / agence
SELECT
  i.agence_id,
  ag.code          AS agence_code,
  ag.libelle       AS agence_libelle,
  i.id             AS immobilisation_id,
  i.code_inventaire,
  i.designation,
  i.date_acquisition,
  i.valeur_brute,
  i.taux,
  i.categorie_id,
  am.periode,
  am.montant       AS dotation,
  am.cumul,
  am.vnc
FROM amortissements am
JOIN immobilisations i
  ON i.id = am.immobilisation_id
 AND i.deleted_at IS NULL
LEFT JOIN agences ag
  ON ag.id = i.agence_id
 AND ag.deleted_at IS NULL
WHERE am.valide IS TRUE
  AND am.annule IS FALSE
  AND am.simule IS FALSE
  AND am.periode = ANY(:periodes)          -- ex. {'2026-Q2'} ou {'2026-01'..}
  AND (:agence_id IS NULL OR i.agence_id = :agence_id)
  AND (:categorie_id IS NULL OR i.categorie_id = :categorie_id)
ORDER BY COALESCE(ag.libelle, 'Sans agence'), i.designation;

-- Totaux par agence (règle métier : somme agences = total général 68)
SELECT
  i.agence_id,
  COALESCE(ag.libelle, 'Sans agence') AS agence,
  COUNT(DISTINCT i.id)                AS nb_immobilisations,
  SUM(am.montant)                     AS total_dotations
FROM amortissements am
JOIN immobilisations i ON i.id = am.immobilisation_id AND i.deleted_at IS NULL
LEFT JOIN agences ag ON ag.id = i.agence_id AND ag.deleted_at IS NULL
WHERE am.valide AND NOT am.annule AND NOT am.simule
  AND am.periode = ANY(:periodes)
GROUP BY i.agence_id, ag.libelle
ORDER BY ag.libelle NULLS LAST;
```
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Agence, Amortissement, Immobilisation
from app.services.amortissement_engine import period_bounds, parse_period_end


def _q(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"))


def _zero() -> Decimal:
    return Decimal("0.00")


def _periodes_cibles(periodicite: str, annee: int, periode_index: int | None) -> list[str]:
    """Clés ``Amortissement.periode`` correspondant aux filtres."""
    per = (periodicite or "trimestriel").strip().lower()
    if per == "annuel":
        return [f"{annee}-Q1", f"{annee}-Q2", f"{annee}-Q3", f"{annee}-Q4", str(annee)] + [
            f"{annee}-{m:02d}" for m in range(1, 13)
        ]
    if periode_index is None:
        raise ValueError("periode_index est requis pour une périodicité mensuelle ou trimestrielle.")
    _, _, key = period_bounds(per, annee, periode_index)
    return [key]


def _label_periode(periodicite: str, annee: int, periode_index: int | None) -> str:
    per = (periodicite or "trimestriel").strip().lower()
    if per == "annuel":
        return f"Exercice {annee} (annuel)"
    if periode_index is None:
        return f"Exercice {annee}"
    _, fin, key = period_bounds(per, annee, periode_index)
    if per == "trimestriel":
        return f"T{periode_index} {annee} — arrêté {fin.strftime('%d/%m/%Y')} ({key})"
    return f"{fin.strftime('%m/%Y')} — arrêté {fin.strftime('%d/%m/%Y')}"


def _periode_sort_key(periode: str) -> tuple[int, int]:
    """Ordre chronologique approximatif des clés de période."""
    end = parse_period_end(periode)
    if end is None:
        return (9999, 99)
    return (end.year, end.month)


@dataclass
class VentilationLigne:
    immobilisation_id: str
    code_inventaire: str
    designation: str
    date_acquisition: date | None
    valeur_brute: Decimal
    taux: Decimal | None
    amortissement_cumule: Decimal
    dotation_periode: Decimal
    vnc: Decimal
    agence_id: str | None
    agence_code: str | None
    agence_libelle: str


@dataclass
class VentilationAgenceGroupe:
    agence_id: str | None
    agence_code: str | None
    agence_libelle: str
    total_dotations: Decimal
    nb_immobilisations: int
    lignes: list[VentilationLigne] = field(default_factory=list)


@dataclass
class VentilationAmortissementsAgenceResult:
    annee: int
    periodicite: str
    periode_index: int | None
    periode_label: str
    date_arrete: date
    agence_filtre_id: str | None
    categorie_filtre_id: str | None
    total_compte_68: Decimal
    nb_immobilisations: int
    total_dotations: Decimal
    groupes: list[VentilationAgenceGroupe]
    exercices_disponibles: list[int]


async def list_exercices_disponibles(db: AsyncSession) -> list[int]:
    """Années présentes dans les amortissements (+ année civile courante)."""
    result = await db.execute(select(Amortissement.periode).distinct())
    years: set[int] = {date.today().year}
    for (periode,) in result.all():
        raw = str(periode or "").strip()
        if len(raw) >= 4 and raw[:4].isdigit():
            years.add(int(raw[:4]))
    return sorted(years)


async def build_ventilation_amortissements_agence(
    db: AsyncSession,
    *,
    annee: int,
    periodicite: str = "trimestriel",
    periode_index: int | None = None,
    agence_id: UUID | None = None,
    categorie_id: UUID | None = None,
) -> VentilationAmortissementsAgenceResult:
    if annee < 2000 or annee > 2100:
        raise ValueError("Année invalide")

    per = (periodicite or "trimestriel").strip().lower()
    if per not in {"mensuel", "trimestriel", "annuel"}:
        raise ValueError("Périodicité invalide (mensuel, trimestriel, annuel).")

    if per == "annuel":
        periode_index_eff: int | None = None
        date_arrete = date(annee, 12, 31)
    else:
        if periode_index is None:
            # Défaut : dernier trimestre / mois de l'exercice
            periode_index = 4 if per == "trimestriel" else 12
        _, date_arrete, _ = period_bounds(per, annee, periode_index)
        periode_index_eff = periode_index

    periodes = _periodes_cibles(per, annee, periode_index_eff)
    periodes_set = set(periodes)

    stmt = (
        select(Amortissement, Immobilisation, Agence)
        .join(Immobilisation, Immobilisation.id == Amortissement.immobilisation_id)
        .outerjoin(Agence, Agence.id == Immobilisation.agence_id)
        .where(
            Immobilisation.deleted_at.is_(None),
            Amortissement.annule.is_(False),
            Amortissement.simule.is_(False),
            Amortissement.valide.is_(True),
            Amortissement.periode.in_(periodes),
        )
        .order_by(Immobilisation.designation.asc())
    )
    if agence_id is not None:
        stmt = stmt.where(Immobilisation.agence_id == agence_id)
    if categorie_id is not None:
        stmt = stmt.where(Immobilisation.categorie_id == categorie_id)

    rows = (await db.execute(stmt)).all()

    # Agrégation par immobilisation : somme des dotations de la période ;
    # cumul / VNC = dernière ligne chronologique de la période filtrée.
    by_immo: dict[UUID, dict] = {}
    for am, immo, agence in rows:
        periode = str(am.periode or "")
        if periode not in periodes_set:
            continue
        bucket = by_immo.get(immo.id)
        if bucket is None:
            bucket = {
                "immo": immo,
                "agence": agence,
                "dotation": _zero(),
                "cumul": _q(Decimal(am.cumul)),
                "vnc": _q(Decimal(am.vnc)),
                "periode_max": periode,
            }
            by_immo[immo.id] = bucket
        bucket["dotation"] = _q(bucket["dotation"] + Decimal(am.montant))
        if _periode_sort_key(periode) >= _periode_sort_key(bucket["periode_max"]):
            bucket["periode_max"] = periode
            bucket["cumul"] = _q(Decimal(am.cumul))
            bucket["vnc"] = _q(Decimal(am.vnc))

    groupes_map: dict[str | None, VentilationAgenceGroupe] = {}

    for data in by_immo.values():
        immo: Immobilisation = data["immo"]
        agence: Agence | None = data["agence"]
        dotation = data["dotation"]
        if dotation <= 0:
            continue

        ag_key = str(agence.id) if agence else None
        if ag_key not in groupes_map:
            groupes_map[ag_key] = VentilationAgenceGroupe(
                agence_id=ag_key,
                agence_code=agence.code if agence else None,
                agence_libelle=agence.libelle if agence else "Sans agence",
                total_dotations=_zero(),
                nb_immobilisations=0,
                lignes=[],
            )
        groupe = groupes_map[ag_key]
        ligne = VentilationLigne(
            immobilisation_id=str(immo.id),
            code_inventaire=immo.code_inventaire or "",
            designation=immo.designation or "",
            date_acquisition=immo.date_acquisition,
            valeur_brute=_q(Decimal(immo.valeur_brute)),
            taux=_q(Decimal(immo.taux)) if immo.taux is not None else None,
            amortissement_cumule=data["cumul"],
            dotation_periode=dotation,
            vnc=data["vnc"],
            agence_id=ag_key,
            agence_code=agence.code if agence else None,
            agence_libelle=groupe.agence_libelle,
        )
        groupe.lignes.append(ligne)
        groupe.total_dotations = _q(groupe.total_dotations + dotation)
        groupe.nb_immobilisations += 1

    # Tri agences (libellé), « Sans agence » en dernier
    def _agence_sort(g: VentilationAgenceGroupe) -> tuple[int, str]:
        if g.agence_id is None:
            return (1, g.agence_libelle.lower())
        return (0, g.agence_libelle.lower())

    groupes = sorted(groupes_map.values(), key=_agence_sort)
    for g in groupes:
        g.lignes.sort(key=lambda L: (L.designation.lower(), L.code_inventaire))

    total_dotations = _q(sum((g.total_dotations for g in groupes), _zero()))
    nb = sum(g.nb_immobilisations for g in groupes)

    exercices = await list_exercices_disponibles(db)
    if annee not in exercices:
        exercices = sorted({*exercices, annee})

    return VentilationAmortissementsAgenceResult(
        annee=annee,
        periodicite=per,
        periode_index=periode_index_eff,
        periode_label=_label_periode(per, annee, periode_index_eff),
        date_arrete=date_arrete,
        agence_filtre_id=str(agence_id) if agence_id else None,
        categorie_filtre_id=str(categorie_id) if categorie_id else None,
        total_compte_68=total_dotations,
        nb_immobilisations=nb,
        total_dotations=total_dotations,
        groupes=groupes,
        exercices_disponibles=exercices,
    )
