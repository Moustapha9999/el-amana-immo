"""Moteur de conformité : décision par axe (physique, système, cohérence) + décision globale.

- NON_CONFORME : un élément obligatoire manquant / non conforme sans dérogation acceptée,
  ou une anomalie bloquante ouverte ;
- INCOMPLET : il reste des éléments obligatoires non contrôlés ou à vérifier ;
- CONFORME sinon. Chaque décision est expliquée élément par élément.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from app.services.eer.checklist_engine import CleElement, Element
from app.services.eer.constantes import (
    ANOMALIES_OUVERTES,
    Axe,
    GraviteAnomalie,
    ResultatAxe,
    StatutAnomalie,
    StatutElement,
)

_EN_ATTENTE = frozenset({StatutElement.NON_CONTROLE, StatutElement.EN_COURS, StatutElement.A_VERIFIER})
_EN_ECHEC = frozenset({StatutElement.MANQUANT, StatutElement.NON_CONFORME})


@dataclass(frozen=True)
class Anomalie:
    code: str
    gravite: GraviteAnomalie
    statut: StatutAnomalie
    element: CleElement | None = None
    libelle: str = ""

    @property
    def ouverte(self) -> bool:
        return self.statut in ANOMALIES_OUVERTES


@dataclass
class DecisionAxe:
    axe: Axe
    resultat: ResultatAxe
    raisons: list[str] = field(default_factory=list)


@dataclass
class Decision:
    resultat: ResultatAxe
    axes: dict[Axe, DecisionAxe]
    explication: list[str]


def _libelle(cle: CleElement) -> str:
    return cle[0] if cle[1] is None else f"{cle[0]} ({cle[1]})"


def decider(elements: Iterable[Element], anomalies: Iterable[Anomalie] = ()) -> Decision:
    elements = list(elements)
    anomalies = list(anomalies)
    axes: dict[Axe, DecisionAxe] = {}
    for axe in Axe:
        echecs, attente = [], []
        for e in elements:
            if e.axe != axe or not e.obligatoire or e.statut == StatutElement.NON_APPLICABLE:
                continue
            if e.statut in _EN_ECHEC and not e.derogation_acceptee:
                echecs.append(f"{_libelle(e.cle)} : {e.statut}" + (f" — {e.motif}" if e.motif else ""))
            elif e.statut in _EN_ATTENTE:
                attente.append(f"{_libelle(e.cle)} : {e.statut}")
        if echecs:
            axes[axe] = DecisionAxe(axe, ResultatAxe.NON_CONFORME, echecs)
        elif attente:
            axes[axe] = DecisionAxe(axe, ResultatAxe.INCOMPLET, attente)
        else:
            axes[axe] = DecisionAxe(axe, ResultatAxe.CONFORME)

    bloquantes = [a for a in anomalies if a.ouverte and a.gravite == GraviteAnomalie.BLOQUANTE]
    explication = [f"Anomalie bloquante ouverte : {a.libelle or a.code}" for a in bloquantes]
    for d in axes.values():
        explication.extend(f"[{d.axe}] {r}" for r in d.raisons)

    resultats = {d.resultat for d in axes.values()}
    if bloquantes or ResultatAxe.NON_CONFORME in resultats:
        global_ = ResultatAxe.NON_CONFORME
    elif ResultatAxe.INCOMPLET in resultats:
        global_ = ResultatAxe.INCOMPLET
    else:
        global_ = ResultatAxe.CONFORME
        explication.append("Tous les éléments obligatoires applicables sont conformes")
    return Decision(global_, axes, explication)


@dataclass(frozen=True)
class AnomalieProposee:
    element: CleElement
    gravite: GraviteAnomalie
    libelle: str


def proposer_anomalies(elements: Iterable[Element], anomalies: Iterable[Anomalie]) -> list[AnomalieProposee]:
    """Une anomalie par élément en échec qui n'en a pas déjà une ouverte.
    Gravité proposée (modifiable par l'agent) : obligatoire → BLOQUANTE, sinon MINEURE."""
    deja = {a.element for a in anomalies if a.ouverte and a.element is not None}
    propositions = []
    for e in elements:
        if e.statut in _EN_ECHEC and not e.derogation_acceptee and e.cle not in deja:
            gravite = GraviteAnomalie.BLOQUANTE if e.obligatoire else GraviteAnomalie.MINEURE
            motif = "manquant" if e.statut == StatutElement.MANQUANT else (e.motif or "non conforme")
            propositions.append(AnomalieProposee(e.cle, gravite, f"{_libelle(e.cle)} : {motif}"))
    return propositions
