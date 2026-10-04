"""Checklist dynamique : génération depuis les règles, régénération, pointage, contrôle.

Présence ≠ conformité : l'agent pointe d'abord ce qui est disponible (``presence``), la
conformité de chaque élément présent est décidée ensuite (``statut``).
Un élément n'est jamais supprimé : devenu inapplicable, il passe NON_APPLICABLE avec motif.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from app.services.eer import conditions
from app.services.eer.constantes import (
    Axe,
    NatureElement,
    Presence,
    RoleDossier,
    StatutElement,
    TypeControle,
)
from app.services.eer.faits import PartieDossier, faits_partie

CleElement = tuple[str, str | None]


class ErreurChecklist(ValueError):
    pass


@dataclass(frozen=True)
class Regle:
    code: str
    libelle: str
    categorie: str
    axe: Axe
    nature: NatureElement
    condition: Mapping[str, Any] | None = None
    portee: str = "DOSSIER"
    role_cible: RoleDossier | None = None
    obligatoire: bool = True
    ordre: int = 0
    type_controle: TypeControle = TypeControle.MANUEL
    document_type: str | None = None
    version: int = 1
    actif: bool = True

    def __post_init__(self) -> None:
        if self.portee not in ("DOSSIER", "PARTIE"):
            raise ErreurChecklist(f"Portée inconnue : {self.portee}")
        if self.portee == "PARTIE" and self.role_cible is None:
            raise ErreurChecklist(f"Règle {self.code} : portée PARTIE sans rôle cible")
        conditions.valider(self.condition)

    @classmethod
    def depuis_dict(cls, data: Mapping[str, Any]) -> Regle:
        return cls(**data)


@dataclass(frozen=True)
class ElementAttendu:
    regle: Regle
    partie_id: str | None
    explication: tuple[str, ...]

    @property
    def cle(self) -> CleElement:
        return (self.regle.code, self.partie_id)


def generer(regles: Iterable[Regle], faits: Mapping[str, Any],
            parties: Sequence[PartieDossier]) -> list[ElementAttendu]:
    attendus: list[ElementAttendu] = []
    for regle in sorted((r for r in regles if r.actif), key=lambda r: (r.ordre, r.code)):
        if regle.portee == "DOSSIER":
            if conditions.evaluer(regle.condition, faits):
                attendus.append(ElementAttendu(regle, None, tuple(conditions.expliquer(regle.condition, faits))))
            continue
        for partie in parties:
            if partie.role != regle.role_cible:
                continue
            fp = faits_partie(faits, partie)
            if conditions.evaluer(regle.condition, fp):
                raison = (f"rôle {partie.role}", *conditions.expliquer(regle.condition, fp))
                attendus.append(ElementAttendu(regle, partie.partie_id, raison))
    return attendus


@dataclass(frozen=True)
class Element:
    """État d'un élément de checklist (miroir de ``eer_checklist_items``)."""

    regle_code: str
    partie_id: str | None
    axe: Axe
    nature: NatureElement
    obligatoire: bool
    statut: StatutElement = StatutElement.NON_CONTROLE
    presence: Presence | None = None
    motif: str | None = None
    neutralise_auto: bool = False
    derogation_acceptee: bool = False

    @property
    def cle(self) -> CleElement:
        return (self.regle_code, self.partie_id)

    @classmethod
    def depuis_attendu(cls, attendu: ElementAttendu) -> Element:
        r = attendu.regle
        return cls(r.code, attendu.partie_id, r.axe, r.nature, r.obligatoire)


@dataclass
class PlanRegeneration:
    a_creer: list[ElementAttendu] = field(default_factory=list)
    a_neutraliser: list[tuple[CleElement, str]] = field(default_factory=list)
    a_reactiver: list[CleElement] = field(default_factory=list)
    inchanges: list[CleElement] = field(default_factory=list)

    @property
    def modifie(self) -> bool:
        return bool(self.a_creer or self.a_neutraliser or self.a_reactiver)


def regenerer(existants: Iterable[Element], attendus: Iterable[ElementAttendu]) -> PlanRegeneration:
    """Compare la checklist en base aux éléments attendus après changement des faits."""
    plan = PlanRegeneration()
    par_cle = {e.cle: e for e in existants}
    cles_attendues = set()
    for attendu in attendus:
        cles_attendues.add(attendu.cle)
        existant = par_cle.get(attendu.cle)
        if existant is None:
            plan.a_creer.append(attendu)
        elif existant.statut == StatutElement.NON_APPLICABLE and existant.neutralise_auto:
            plan.a_reactiver.append(attendu.cle)
        else:
            plan.inchanges.append(attendu.cle)
    for cle, existant in par_cle.items():
        if cle not in cles_attendues and existant.statut != StatutElement.NON_APPLICABLE:
            plan.a_neutraliser.append((cle, "Condition de la règle plus remplie après mise à jour du dossier"))
    return plan


def appliquer_plan(existants: Iterable[Element], plan: PlanRegeneration) -> list[Element]:
    par_cle = {e.cle: e for e in existants}
    motifs = dict(plan.a_neutraliser)
    resultat: list[Element] = []
    for cle, e in par_cle.items():
        if cle in motifs:
            e = replace(e, statut=StatutElement.NON_APPLICABLE, motif=motifs[cle], neutralise_auto=True)
        elif cle in plan.a_reactiver:
            e = replace(e, statut=StatutElement.NON_CONTROLE, presence=None, motif=None, neutralise_auto=False)
        resultat.append(e)
    resultat.extend(Element.depuis_attendu(a) for a in plan.a_creer)
    return resultat


def pointer(element: Element, presence: Presence, motif: str | None = None) -> Element:
    """Étape checklist : l'agent coche ce qui est disponible."""
    if element.statut == StatutElement.NON_APPLICABLE and element.neutralise_auto:
        raise ErreurChecklist("Élément neutralisé par le système : non pointable")
    if presence == Presence.ABSENT:
        return replace(element, presence=presence, statut=StatutElement.MANQUANT, motif=motif)
    if presence == Presence.SANS_OBJET:
        if not (motif and motif.strip()):
            raise ErreurChecklist("Motif obligatoire pour un élément sans objet")
        return replace(element, presence=presence, statut=StatutElement.NON_APPLICABLE, motif=motif.strip())
    return replace(element, presence=presence, statut=StatutElement.NON_CONTROLE, motif=None)


def controler(element: Element, conforme: bool, motif: str | None = None) -> Element:
    """Étape contrôles : conformité d'un élément présent."""
    if element.presence != Presence.PRESENT:
        raise ErreurChecklist("Seul un élément présent peut être contrôlé")
    if conforme:
        return replace(element, statut=StatutElement.CONFORME, motif=None)
    if not (motif and motif.strip()):
        raise ErreurChecklist("Motif de non-conformité obligatoire")
    return replace(element, statut=StatutElement.NON_CONFORME, motif=motif.strip())


def a_verifier(element: Element, motif: str) -> Element:
    return replace(element, statut=StatutElement.A_VERIFIER, motif=motif)


def elements_non_pointes(elements: Iterable[Element]) -> list[CleElement]:
    """Bloque la validation de la checklist tant qu'un élément applicable n'est pas pointé."""
    return [e.cle for e in elements if e.statut != StatutElement.NON_APPLICABLE and e.presence is None]
