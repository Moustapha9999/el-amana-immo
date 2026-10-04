"""Workflow EER (docs/conformite/eer-matrices.md §5) — garde pure, appelée par le service backend.

Pas d'état REJETE : un dossier non conforme ou un avis défavorable repart en complément sur
le même dossier. Un dossier jamais régularisé finit ABANDONNE (motif), jamais supprimé.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field
from enum import StrEnum

from app.services.eer.constantes import ResultatAxe


class Statut(StrEnum):
    BROUILLON = "BROUILLON"
    SOUMIS = "SOUMIS"
    A_AFFECTER = "A_AFFECTER"
    AFFECTE = "AFFECTE"
    EN_CONTROLE = "EN_CONTROLE"
    CONFORME = "CONFORME"
    NON_CONFORME = "NON_CONFORME"
    A_COMPLETER = "A_COMPLETER"
    RESOUMIS = "RESOUMIS"
    AVIS_CONFORMITE = "AVIS_CONFORMITE"
    VALIDE = "VALIDE"
    CLOTURE = "CLOTURE"
    ARCHIVE = "ARCHIVE"
    ABANDONNE = "ABANDONNE"


class Etape(StrEnum):
    """Étapes internes de EN_CONTROLE (reprise au point d'arrêt)."""

    CHECKLIST = "CHECKLIST"
    CHECKLIST_VALIDEE = "CHECKLIST_VALIDEE"
    FICHES = "FICHES"
    CONTROLES = "CONTROLES"


ETATS_FINAUX = frozenset({Statut.ARCHIVE, Statut.ABANDONNE})

# (origine, cible) → permission ; None = transition système.
TRANSITIONS: dict[tuple[Statut, Statut], str | None] = {
    (Statut.BROUILLON, Statut.SOUMIS): "eer.submit",
    (Statut.SOUMIS, Statut.A_AFFECTER): None,
    (Statut.A_AFFECTER, Statut.AFFECTE): "eer.assign",
    (Statut.AFFECTE, Statut.EN_CONTROLE): "eer.control",
    (Statut.EN_CONTROLE, Statut.CONFORME): "eer.control",
    (Statut.EN_CONTROLE, Statut.NON_CONFORME): "eer.control",
    (Statut.NON_CONFORME, Statut.A_COMPLETER): "eer.complement.request",
    (Statut.A_COMPLETER, Statut.RESOUMIS): "eer.complement.receive",
    (Statut.RESOUMIS, Statut.EN_CONTROLE): "eer.control",
    (Statut.A_COMPLETER, Statut.ABANDONNE): "eer.validate",
    (Statut.CONFORME, Statut.AVIS_CONFORMITE): "eer.control",
    (Statut.CONFORME, Statut.VALIDE): "eer.validate",
    (Statut.AVIS_CONFORMITE, Statut.VALIDE): "eer.avis",
    (Statut.AVIS_CONFORMITE, Statut.A_COMPLETER): "eer.avis",
    (Statut.VALIDE, Statut.CLOTURE): "eer.archive",
    (Statut.CLOTURE, Statut.ARCHIVE): "eer.archive",
}


class TransitionRefusee(PermissionError):
    def __init__(self, raisons: list[str]):
        super().__init__("; ".join(raisons))
        self.raisons = raisons


@dataclass(frozen=True)
class EtatDossier:
    statut: Statut
    createur_id: str | None = None
    analyste_id: str | None = None
    controleur_id: str | None = None
    etape: Etape | None = None
    decision: ResultatAxe | None = None
    avis_requis: bool = False
    nb_relances: int = 0
    champs_socle_manquants: tuple[str, ...] = ()
    elements_non_pointes: int = 0


@dataclass(frozen=True)
class Demande:
    cible: Statut
    acteur_id: str | None
    permissions: Collection[str] = field(default_factory=frozenset)
    motif: str | None = None
    elements_cibles: int = 0
    elements_cibles_fournis: bool = False
    avis_favorable: bool | None = None
    analyste_cible_id: str | None = None
    separation_roles: bool = True
    systeme: bool = False


def _motif(d: Demande) -> bool:
    return bool(d.motif and d.motif.strip())


def raisons_refus(etat: EtatDossier, d: Demande) -> list[str]:
    origine, cible = etat.statut, d.cible
    if (origine, cible) not in TRANSITIONS:
        return [f"Transition {origine} → {cible} non autorisée"]
    permission = TRANSITIONS[(origine, cible)]
    if permission is None:
        return [] if d.systeme else [f"Transition {origine} → {cible} réservée au système"]
    raisons: list[str] = []
    if permission not in d.permissions:
        raisons.append(f"Permission requise : {permission}")
    sep = d.separation_roles

    if cible == Statut.SOUMIS and etat.champs_socle_manquants:
        raisons.append("Champs obligatoires manquants : " + ", ".join(etat.champs_socle_manquants))
    if cible == Statut.AFFECTE:
        if not d.analyste_cible_id:
            raisons.append("Analyste à affecter non précisé")
        elif sep and d.analyste_cible_id == etat.createur_id:
            raisons.append("Séparation des rôles : le créateur du dossier ne peut pas le contrôler")
    if origine in (Statut.AFFECTE, Statut.RESOUMIS) and cible == Statut.EN_CONTROLE:
        if etat.analyste_id and d.acteur_id != etat.analyste_id:
            raisons.append("Seul l'analyste affecté peut contrôler le dossier")
    if origine == Statut.EN_CONTROLE:
        if etat.etape != Etape.CONTROLES:
            raisons.append("La checklist doit être validée et les fiches complétées avant la décision")
        if etat.decision is None or etat.decision == ResultatAxe.INCOMPLET:
            raisons.append("Décision incomplète : des éléments obligatoires restent à contrôler")
        elif etat.decision.value != cible.value:
            raisons.append(f"La décision calculée est {etat.decision}, pas {cible}")
    if cible == Statut.A_COMPLETER and origine == Statut.NON_CONFORME and d.elements_cibles < 1:
        raisons.append("Au moins un élément à compléter doit être ciblé")
    if cible == Statut.RESOUMIS and not d.elements_cibles_fournis:
        raisons.append("Les éléments demandés n'ont pas tous été fournis")
    if cible == Statut.ABANDONNE and not _motif(d):
        raisons.append("Motif d'abandon obligatoire")
    if origine == Statut.CONFORME:
        if cible == Statut.AVIS_CONFORMITE and not etat.avis_requis:
            raisons.append("Avis Conformité KYC non requis pour ce dossier")
        if cible == Statut.VALIDE and etat.avis_requis:
            raisons.append("Avis Conformité KYC obligatoire avant validation")
    if cible in (Statut.VALIDE, Statut.A_COMPLETER) and origine in (Statut.CONFORME, Statut.AVIS_CONFORMITE):
        if sep and d.acteur_id and d.acteur_id in (etat.controleur_id, etat.createur_id):
            raisons.append("Séparation des rôles : l'avis / la validation doit venir d'un autre agent")
    if origine == Statut.AVIS_CONFORMITE:
        if d.avis_favorable is None:
            raisons.append("Sens de l'avis (favorable / défavorable) obligatoire")
        elif cible == Statut.VALIDE and not d.avis_favorable:
            raisons.append("Un avis défavorable renvoie le dossier en complément")
        elif cible == Statut.A_COMPLETER:
            if d.avis_favorable:
                raisons.append("Un avis favorable valide le dossier")
            if not _motif(d) or d.elements_cibles < 1:
                raisons.append("Avis défavorable : motif et éléments à compléter obligatoires")
    return raisons


def verifier(etat: EtatDossier, demande: Demande) -> None:
    raisons = raisons_refus(etat, demande)
    if raisons:
        raise TransitionRefusee(raisons)


def peut_relancer(etat: EtatDossier, permissions: Collection[str]) -> list[str]:
    """Relance du demandeur : action sur A_COMPLETER, le statut ne change pas."""
    raisons = []
    if etat.statut != Statut.A_COMPLETER:
        raisons.append("Relance possible uniquement sur un dossier à compléter")
    if "eer.complement.request" not in permissions:
        raisons.append("Permission requise : eer.complement.request")
    return raisons


ORDRE_ETAPES = (Etape.CHECKLIST, Etape.CHECKLIST_VALIDEE, Etape.FICHES, Etape.CONTROLES)


def avancer_etape(etape: Etape | None, *, elements_non_pointes: int = 0, champs_bloquants: int = 0) -> Etape:
    """Passe à l'étape suivante si l'étape courante est terminée."""
    if etape is None:
        return Etape.CHECKLIST
    if etape == Etape.CHECKLIST:
        if elements_non_pointes:
            raise TransitionRefusee([f"{elements_non_pointes} élément(s) de checklist non pointé(s)"])
        return Etape.CHECKLIST_VALIDEE
    if etape == Etape.CHECKLIST_VALIDEE:
        return Etape.FICHES
    if etape == Etape.FICHES:
        if champs_bloquants:
            raise TransitionRefusee([f"{champs_bloquants} champ(s) de fiche à compléter ou confirmer"])
        return Etape.CONTROLES
    return Etape.CONTROLES


def etape_reprise(*, checklist_modifiee: bool, champs_bloquants: int) -> Etape:
    """Après complément, le contrôle reprend là où il s'était arrêté — pas depuis le début."""
    if checklist_modifiee:
        return Etape.CHECKLIST
    if champs_bloquants:
        return Etape.FICHES
    return Etape.CONTROLES
