"""Calcul central des délais : sélection de la règle, échéance, situation d'un dossier.

Une seule définition, partagée par la fiche, les listes, les indicateurs, les exports et les
alertes (fonctions Python pour un dossier chargé, expressions SQL pour filtrer et compter).

- Seule une règle **validée**, active et en vigueur à la date de première réception produit une
  échéance. Une règle en attente de validation n'est jamais appliquée.
- Priorité du plus spécifique au plus général : sous-motif (8) > motif (4) > type (2) > priorité (1).
  Deux règles validées de même spécificité aux paramètres différents = conflit : aucune échéance
  n'est inventée, le dossier est signalé « Règles contradictoires ».
- La règle retenue est celle en vigueur pour la période du dossier : une nouvelle version à date
  d'effet ne modifie pas les échéances déjà calculées.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import and_, case, func, or_

from app.models import Reclamation, ReclamationRegleDelai
from app.services.reclamations import constantes as C

POIDS = (("sous_motif_id", 8), ("motif_id", 4), ("type_id", 2), ("priorite", 1))
SITUATIONS = ("DANS_DELAI", "ECHEANCE_PROCHE", "EN_RETARD", "RESPECTE", "DEPASSE", "NON_CALCULABLE")


def _ouvre(j: date, feries: set[date]) -> bool:
    return j.weekday() < 5 and j not in feries


def ajouter_jours(depart: datetime, n: int, unite: str, feries: set[date]) -> datetime:
    """Échéance = départ + durée. Jours ouvrés : lundi–vendredi hors jours fériés, fin de journée."""
    if n <= 0:
        return depart
    if unite == "HEURES":
        return depart + timedelta(hours=n)
    if unite != "JOURS_OUVRES":
        return depart + timedelta(days=n)
    j, reste = depart.date(), n
    while reste:
        j += timedelta(days=1)
        if _ouvre(j, feries):
            reste -= 1
    return datetime.combine(j, datetime.max.time().replace(microsecond=0), tzinfo=depart.tzinfo)


def retrancher(echeance: datetime, n: int, unite: str, feries: set[date]) -> datetime:
    """Début de la zone d'alerte : échéance − seuil, exprimé dans l'unité de la règle."""
    if n <= 0:
        return echeance
    if unite == "HEURES":
        return echeance - timedelta(hours=n)
    if unite != "JOURS_OUVRES":
        return echeance - timedelta(days=n)
    j, reste = echeance.date(), n
    while reste:
        j -= timedelta(days=1)
        if _ouvre(j, feries):
            reste -= 1
    return datetime.combine(j, echeance.timetz())


def signature(regle: ReclamationRegleDelai) -> tuple:
    return (regle.duree, regle.unite_duree, regle.point_depart, regle.point_arrivee or "CLOTURE")


def portee(regle: ReclamationRegleDelai) -> tuple:
    return (regle.type_id, regle.motif_id, regle.sous_motif_id, regle.priorite)


def specificite(regle: ReclamationRegleDelai) -> int:
    return sum(p for champ, p in POIDS if getattr(regle, champ))


def en_vigueur(regle: ReclamationRegleDelai, jour: date) -> bool:
    return regle.date_effet <= jour and (regle.date_fin is None or jour <= regle.date_fin)


def correspond(regle: ReclamationRegleDelai, r: Reclamation) -> bool:
    if not regle.actif or regle.statut_validation == "REJETEE":
        return False
    if not en_vigueur(regle, r.date_premiere_reception.date()):
        return False
    return all(not getattr(regle, champ) or getattr(regle, champ) == getattr(r, champ) for champ, _ in POIDS)


@dataclass
class Selection:
    etat: str
    regle: ReclamationRegleDelai | None = None
    conflit: list[ReclamationRegleDelai] = field(default_factory=list)
    en_attente: list[ReclamationRegleDelai] = field(default_factory=list)


def selectionner(regles: list[ReclamationRegleDelai], r: Reclamation) -> Selection:
    candidates = [g for g in regles if correspond(g, r)]
    validees = [g for g in candidates if g.statut_validation == "VALIDEE"]
    attente = [g for g in candidates if g.statut_validation != "VALIDEE"]
    if not validees:
        return Selection("EN_ATTENTE_VALIDATION" if attente else "NON_CONFIGURE", en_attente=attente)
    top = max(specificite(g) for g in validees)
    meilleures = [g for g in validees if specificite(g) == top]
    if len({signature(g) for g in meilleures}) > 1:
        return Selection("CONFLIT", conflit=meilleures, en_attente=attente)
    meilleures.sort(key=lambda g: (g.date_effet, str(g.id)))
    return Selection("CALCULE", regle=meilleures[-1], en_attente=attente)


def poser(r: Reclamation, sel: Selection, feries: set[date]) -> None:
    """Reporte la sélection sur le dossier : échéance seulement si une règle validée s'applique."""
    regle = sel.regle
    r.date_alerte = None
    if regle is None:
        r.etat_delai, r.regle_delai_id, r.echeance = sel.etat, None, None
        return
    depart = r.date_reception_sr if regle.point_depart == "RECEPTION_SR" else r.date_premiere_reception
    r.regle_delai_id = regle.id
    if depart is None:
        r.etat_delai, r.echeance = "SANS_DEPART", None
        return
    r.echeance = ajouter_jours(depart, regle.duree, regle.unite_duree, feries)
    r.etat_delai = "CALCULE"
    if regle.seuil_alerte is not None:
        r.date_alerte = retrancher(r.echeance, regle.seuil_alerte, regle.unite_duree, feries)
    if r.echeance_initiale is None:
        r.echeance_initiale = r.echeance


def fin_delai(r: Reclamation, regle: ReclamationRegleDelai | None) -> datetime | None:
    """Instant où le délai s'arrête (événement de fin de la règle ; clôture par défaut)."""
    if regle is not None and regle.point_arrivee == "REPONSE_CLIENT" and r.date_reponse_client:
        return r.date_reponse_client
    if r.statut in C.STATUTS_TERMINAUX:
        return r.date_cloture
    return None


def calcule(r: Reclamation) -> bool:
    return r.echeance is not None and r.etat_delai in (None, "CALCULE")


def situation(r: Reclamation, now: datetime) -> str:
    if not calcule(r):
        return "NON_CALCULABLE"
    fin = r.date_fin_delai or (r.date_cloture if r.statut in C.STATUTS_TERMINAUX else None)
    if fin is not None:
        return "RESPECTE" if fin <= r.echeance else "DEPASSE"
    if now > r.echeance:
        return "EN_RETARD"
    if r.date_alerte is not None and now >= r.date_alerte:
        return "ECHEANCE_PROCHE"
    return "DANS_DELAI"


def etat_dossier(r: Reclamation) -> str:
    if r.etat_delai:
        return r.etat_delai
    return "CALCULE" if r.echeance is not None else "NON_CONFIGURE"


# ---------------------------------------------------------------- expressions SQL (mêmes règles)
def sql_calcule():
    return and_(Reclamation.echeance.is_not(None),
                or_(Reclamation.etat_delai.is_(None), Reclamation.etat_delai == "CALCULE"))


def sql_fin():
    return func.coalesce(Reclamation.date_fin_delai, case(
        (Reclamation.statut.in_(C.STATUTS_TERMINAUX), Reclamation.date_cloture), else_=None))


def sql_situation(code: str, now: datetime):
    fin = sql_fin()
    ouvert = and_(sql_calcule(), fin.is_(None))
    if code == "EN_RETARD":
        return and_(ouvert, Reclamation.echeance < now)
    if code == "ECHEANCE_PROCHE":
        return and_(ouvert, Reclamation.echeance >= now, Reclamation.date_alerte <= now)
    if code == "DANS_DELAI":
        return and_(ouvert, Reclamation.echeance >= now,
                    or_(Reclamation.date_alerte.is_(None), Reclamation.date_alerte > now))
    if code == "RESPECTE":
        return and_(sql_calcule(), fin.is_not(None), fin <= Reclamation.echeance)
    if code == "DEPASSE":
        return and_(sql_calcule(), fin > Reclamation.echeance)
    return ~sql_calcule()
