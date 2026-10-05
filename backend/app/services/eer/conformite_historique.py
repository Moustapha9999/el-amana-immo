"""Compatibilité avec le suivi Excel historique du Service Conformité (feuilles FLUX / SYNTHESE).

Deux résultats coexistent sur un dossier, sans jamais se mélanger :

- **Référence Excel** [FORMULE EXCEL], reproduite telle quelle :
  M = conformité physique (``conformite_physique``), N = conformité données systèmes
  (``conformite_systeme``) ;
  S = IF(M="Conforme", IF(N="Conforme", 1, 0), 0) ;
  T = IF(M="Non conforme", 1, IF(N="Non conforme", 1, 0)) ;
  S = T = 0 → dossier non classé (``NON_EVALUE``), jamais transformé en non conforme.
  L'axe cohérence et les anomalies bloquantes n'y entrent pas : ce sont des contrôles
  BEA-DIGITAL, absents de l'Excel.
- **Décision BEA-DIGITAL** : ``decision_globale`` du moteur (``conformite_engine``), qui
  ajoute la cohérence et les anomalies bloquantes ; elle seule pilote le workflow.

S et T sont toujours dérivés, jamais saisis : ils ne peuvent pas valoir 1 tous les deux.

Taux historique = S / (S + T) : les dossiers non classés sont HORS du dénominateur
(100 dossiers dont 20 conformes, 30 non conformes, 50 non classés → 40 %, pas 20 %).
Aucun dossier classé → ``None`` (l'Excel affichait #DIV/0!), jamais 0 %.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from sqlalchemy import case, or_
from sqlalchemy.sql.elements import ColumnElement

from app.data.eer_referentiel import TYPES_CLIENT
from app.services.eer.constantes import TYPES_PERSONNE_MORALE, ResultatAxe, TypeClient


class Classement(StrEnum):
    CONFORME = "CONFORME"
    NON_CONFORME = "NON_CONFORME"
    NON_EVALUE = "NON_EVALUE"


# Valeur de cellule Excel correspondant à un résultat d'axe ; INCOMPLET ou absent = cellule vide.
CELLULE_EXCEL = {ResultatAxe.CONFORME: "Conforme", ResultatAxe.NON_CONFORME: "Non conforme"}

# Colonne E « PROFIL » de l'Excel = type client BEA-DIGITAL (libellés historiques inchangés).
LIBELLE_EXCEL_PROFIL: dict[str, str] = {code: d["libelle_excel"] for code, d in TYPES_CLIENT.items()}


@dataclass(frozen=True)
class ResultatExcel:
    classement: Classement
    code_conforme: int
    code_non_conforme: int
    cellule_m: str | None
    cellule_n: str | None


def cellule(resultat_axe: str | None) -> str | None:
    return CELLULE_EXCEL.get(resultat_axe) if resultat_axe else None


def axe_depuis_cellule(valeur: object) -> str | None:
    """Cellule M ou N de l'Excel → résultat d'axe. Comme l'opérateur « = » d'Excel : insensible
    à la casse, mais sensible aux espaces (« Conforme  » n'est pas « Conforme »)."""
    if not isinstance(valeur, str):
        return None
    for axe, texte in CELLULE_EXCEL.items():
        if valeur.casefold() == texte.casefold():
            return axe
    return None


def classer_excel(physique: str | None, systeme: str | None) -> ResultatExcel:
    m, n = cellule(physique), cellule(systeme)
    s = 1 if m == "Conforme" and n == "Conforme" else 0
    t = 1 if m == "Non conforme" or n == "Non conforme" else 0
    classement = Classement.CONFORME if s else Classement.NON_CONFORME if t else Classement.NON_EVALUE
    return ResultatExcel(classement, s, t, m, n)


def classer_bea(decision_globale: str | None) -> Classement:
    """``INCOMPLET`` ou pas encore décidé → non évalué (hors du taux, comme l'Excel)."""
    if decision_globale == ResultatAxe.CONFORME:
        return Classement.CONFORME
    if decision_globale == ResultatAxe.NON_CONFORME:
        return Classement.NON_CONFORME
    return Classement.NON_EVALUE


def taux(conformes: int, non_conformes: int) -> Decimal | None:
    """Taux historique en pourcentage (2 décimales) ; ``None`` = non calculable."""
    classes = conformes + non_conformes
    if classes == 0:
        return None
    return (Decimal(conformes) * 100 / Decimal(classes)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Compteurs:
    total: int
    conformes: int
    non_conformes: int

    @property
    def non_evalues(self) -> int:
        return self.total - self.conformes - self.non_conformes

    @property
    def taux(self) -> Decimal | None:
        return taux(self.conformes, self.non_conformes)

    def to_dict(self) -> dict:
        return {"total": self.total, "conformes": self.conformes, "non_conformes": self.non_conformes,
                "non_evalues": self.non_evalues, "taux": self.taux}


def compter(classements: Iterable[Classement]) -> Compteurs:
    liste = list(classements)
    return Compteurs(len(liste), liste.count(Classement.CONFORME), liste.count(Classement.NON_CONFORME))


def profil_technique(type_client: str | None) -> str | None:
    """Colonne U de l'Excel (PP / PM), dérivée du type client — jamais du nom du client."""
    if type_client == TypeClient.PP:
        return "PP"
    if type_client in TYPES_PERSONNE_MORALE:
        return "PM"
    return None


def expliquer_ecart(*, physique: str | None, systeme: str | None, coherence: str | None,
                    decision_globale: str | None, anomalies_bloquantes: Iterable[str] = ()) -> list[str]:
    """Pourquoi la référence Excel et la décision BEA-DIGITAL diffèrent (liste vide si accord)."""
    excel, bea = classer_excel(physique, systeme).classement, classer_bea(decision_globale)
    if excel == bea:
        return []
    raisons = [f"Référence Excel : {excel} ; décision BEA-DIGITAL : {bea}"]
    if coherence == ResultatAxe.NON_CONFORME:
        raisons.append("Axe cohérence non conforme (contrôle BEA-DIGITAL, absent de l'Excel)")
    elif coherence == ResultatAxe.INCOMPLET:
        raisons.append("Axe cohérence encore incomplet (contrôle BEA-DIGITAL, absent de l'Excel)")
    raisons.extend(f"Anomalie bloquante ouverte : {a} (règle BEA-DIGITAL, absente de l'Excel)"
                   for a in anomalies_bloquantes)
    if decision_globale is None and excel != Classement.NON_EVALUE:
        raisons.append("Décision BEA-DIGITAL remise à zéro (complément reçu) : nouvelle évaluation attendue")
    return raisons


# --- Expressions SQL (mêmes règles, pour le reporting en base) ---------------------------

def sql_code_conforme(physique: ColumnElement, systeme: ColumnElement) -> ColumnElement:
    return case(((physique == ResultatAxe.CONFORME) & (systeme == ResultatAxe.CONFORME), 1), else_=0)


def sql_code_non_conforme(physique: ColumnElement, systeme: ColumnElement) -> ColumnElement:
    return case((or_(physique == ResultatAxe.NON_CONFORME, systeme == ResultatAxe.NON_CONFORME), 1), else_=0)


def sql_classement_excel(physique: ColumnElement, systeme: ColumnElement) -> ColumnElement:
    return case(
        ((physique == ResultatAxe.CONFORME) & (systeme == ResultatAxe.CONFORME), Classement.CONFORME.value),
        (or_(physique == ResultatAxe.NON_CONFORME, systeme == ResultatAxe.NON_CONFORME),
         Classement.NON_CONFORME.value),
        else_=Classement.NON_EVALUE.value)


def sql_classement_bea(decision_globale: ColumnElement) -> ColumnElement:
    return case(
        (decision_globale == ResultatAxe.CONFORME, Classement.CONFORME.value),
        (decision_globale == ResultatAxe.NON_CONFORME, Classement.NON_CONFORME.value),
        else_=Classement.NON_EVALUE.value)
