"""Actionnariat multi-niveaux et bénéficiaires effectifs (fiches PM : « au moins 10 % »).

Participation effective d'une personne physique = somme, sur chaque chaîne de détention
qui remonte jusqu'au client, du produit des pourcentages (A 60 % → B 70 % → X : 42 %).
Un pourcentage inconnu sur une chaîne rend le résultat de cette personne A_VERIFIER :
le moteur ne conclut jamais à partir d'une donnée absente.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal

CENT = Decimal(100)
TOLERANCE = Decimal("0.01")


@dataclass(frozen=True)
class Detention:
    detenteur_id: str
    detenu_id: str
    pourcentage: Decimal | None


@dataclass(frozen=True)
class ProblemeStructure:
    code: str
    message: str
    partie_id: str | None = None


@dataclass(frozen=True)
class Beneficiaire:
    partie_id: str
    pourcentage: Decimal
    statut: str  # CERTAIN | A_VERIFIER
    chemins: tuple[tuple[str, ...], ...]
    pourcentage_inconnu: bool = False


@dataclass
class ResultatBE:
    seuil: Decimal
    beneficiaires: list[Beneficiaire] = field(default_factory=list)
    a_verifier: list[Beneficiaire] = field(default_factory=list)
    problemes: list[ProblemeStructure] = field(default_factory=list)

    @property
    def complet(self) -> bool:
        return not self.a_verifier and not self.problemes

    @property
    def aucun_be_au_seuil(self) -> bool:
        return self.complet and not self.beneficiaires


def _detenteurs(detentions: Iterable[Detention]) -> dict[str, list[Detention]]:
    par_detenu: dict[str, list[Detention]] = defaultdict(list)
    for d in detentions:
        par_detenu[d.detenu_id].append(d)
    return par_detenu


def verifier_structure(client_id: str, detentions: Iterable[Detention],
                       natures: Mapping[str, str]) -> list[ProblemeStructure]:
    """natures : partie_id → "PP" | "PM"."""
    detentions = list(detentions)
    problemes: list[ProblemeStructure] = []
    par_detenu = _detenteurs(detentions)

    for d in detentions:
        if natures.get(d.detenteur_id) not in ("PP", "PM"):
            problemes.append(ProblemeStructure("NATURE_INCONNUE", "Actionnaire sans nature PP / PM",
                                               d.detenteur_id))
        if d.detenteur_id == d.detenu_id:
            problemes.append(ProblemeStructure("AUTO_DETENTION", "Une entité ne peut pas se détenir elle-même",
                                               d.detenteur_id))
        if d.pourcentage is not None and not (Decimal(0) < d.pourcentage <= CENT):
            problemes.append(ProblemeStructure("POURCENTAGE_INVALIDE",
                                               f"Pourcentage hors ]0 ; 100] : {d.pourcentage}", d.detenteur_id))
        if natures.get(d.detenu_id) == "PP":
            problemes.append(ProblemeStructure("PP_DETENUE", "Une personne physique ne peut pas être détenue",
                                               d.detenu_id))

    for detenu, liste in par_detenu.items():
        total = sum((d.pourcentage for d in liste if d.pourcentage is not None), Decimal(0))
        if total > CENT + TOLERANCE:
            problemes.append(ProblemeStructure("TOTAL_SUPERIEUR_100",
                                               f"Total des participations {total} % > 100 %", detenu))

    if not par_detenu.get(client_id):
        problemes.append(ProblemeStructure("ACTIONNARIAT_ABSENT", "Aucun actionnaire déclaré pour le client",
                                           client_id))

    vus: set[str] = set()
    pile: list[tuple[str, tuple[str, ...]]] = [(client_id, (client_id,))]
    while pile:
        noeud, chemin = pile.pop()
        for d in par_detenu.get(noeud, []):
            if d.detenteur_id in chemin:
                problemes.append(ProblemeStructure("CYCLE", "Détention circulaire : " + " → ".join(
                    (*chemin, d.detenteur_id)), d.detenteur_id))
                continue
            if d.detenteur_id in vus:
                continue
            vus.add(d.detenteur_id)
            if natures.get(d.detenteur_id) == "PM" and not par_detenu.get(d.detenteur_id):
                problemes.append(ProblemeStructure(
                    "PM_SANS_ACTIONNAIRES",
                    "Entité actionnaire sans actionnariat déclaré : chaîne à compléter jusqu'aux personnes physiques",
                    d.detenteur_id))
            pile.append((d.detenteur_id, (*chemin, d.detenteur_id)))
    return problemes


def calculer_beneficiaires(client_id: str, detentions: Iterable[Detention], natures: Mapping[str, str],
                           seuil: Decimal | int | str) -> ResultatBE:
    seuil = Decimal(str(seuil))
    detentions = list(detentions)
    resultat = ResultatBE(seuil=seuil, problemes=verifier_structure(client_id, detentions, natures))
    par_detenu = _detenteurs(detentions)

    cumul: dict[str, Decimal] = defaultdict(Decimal)
    inconnu: dict[str, bool] = defaultdict(bool)
    chemins: dict[str, list[tuple[str, ...]]] = defaultdict(list)

    def parcourir(noeud: str, fraction: Decimal | None, chemin: tuple[str, ...]) -> None:
        for d in par_detenu.get(noeud, []):
            if d.detenteur_id in chemin:
                continue
            f = None if fraction is None or d.pourcentage is None else fraction * d.pourcentage / CENT
            nouveau = (*chemin, d.detenteur_id)
            if natures.get(d.detenteur_id) == "PP":
                chemins[d.detenteur_id].append(tuple(reversed(nouveau)))
                if f is None:
                    inconnu[d.detenteur_id] = True
                else:
                    cumul[d.detenteur_id] += f
            else:
                parcourir(d.detenteur_id, f, nouveau)

    parcourir(client_id, Decimal(1), (client_id,))

    for pp in chemins:
        pct = (cumul[pp] * CENT).quantize(Decimal("0.01"))
        if inconnu[pp] and pct < seuil:
            resultat.a_verifier.append(Beneficiaire(pp, pct, "A_VERIFIER", tuple(chemins[pp]), True))
        elif pct >= seuil:
            resultat.beneficiaires.append(Beneficiaire(pp, pct, "CERTAIN", tuple(chemins[pp]), inconnu[pp]))
    resultat.beneficiaires.sort(key=lambda b: (-b.pourcentage, b.partie_id))
    resultat.a_verifier.sort(key=lambda b: b.partie_id)
    return resultat
