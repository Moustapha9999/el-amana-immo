"""Fenêtres d'analyse (fuseau Africa/Nouakchott).

La déclaration BCM officielle est mensuelle. Les autres périodes sont des simulations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.data.clientele_indicateurs import PERIODES_ANALYSE, TypePeriode

TZ = ZoneInfo("Africa/Nouakchott")

LIBELLES_PERIODES: dict[str, str] = {
    "aujourd_hui": "Aujourd'hui",
    "7j": "7 jours",
    "10j": "10 jours",
    "30j": "30 jours",
    "mois_courant": "Mois courant",
    "mois_precedent": "Mois précédent",
    "3mois": "3 mois",
    "6mois": "6 mois",
    "annee": "Année",
    "personnalisee": "Personnalisée",
}

MOIS_FR = (
    "",
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
)


@dataclass(frozen=True)
class Fenetre:
    code: str
    date_debut: date
    date_fin: date
    type_applique: TypePeriode
    simulation: bool
    bcm_officielle: bool

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "date_debut": self.date_debut.isoformat(),
            "date_fin": self.date_fin.isoformat(),
            "type": self.type_applique,
            "simulation": self.simulation,
            "bcm_officielle": self.bcm_officielle,
        }


def aujourd_hui(maintenant: datetime | None = None) -> date:
    return (maintenant or datetime.now(TZ)).astimezone(TZ).date()


def premier_du_mois(d: date) -> date:
    return d.replace(day=1)


def dernier_du_mois(d: date) -> date:
    if d.month == 12:
        return date(d.year, 12, 31)
    return date(d.year, d.month + 1, 1) - timedelta(days=1)


def ajouter_mois(d: date, n: int) -> date:
    y, m = d.year, d.month + n
    while m <= 0:
        m += 12
        y -= 1
    while m > 12:
        m -= 12
        y += 1
    return date(y, m, 1)


def _mois_clos(debut: date, fin: date, ref: date) -> bool:
    return debut.day == 1 and fin == dernier_du_mois(debut) and fin < ref


def resoudre(
    code: str,
    *,
    date_debut: date | None = None,
    date_fin: date | None = None,
    aujourdhui: date | None = None,
) -> Fenetre:
    if code not in PERIODES_ANALYSE:
        raise ValueError(f"Période inconnue : {code}")
    today = aujourdhui or aujourd_hui()
    if code == "aujourd_hui":
        debut, fin = today, today
    elif code == "7j":
        debut, fin = today - timedelta(days=6), today
    elif code == "10j":
        debut, fin = today - timedelta(days=9), today
    elif code == "30j":
        debut, fin = today - timedelta(days=29), today
    elif code == "mois_courant":
        debut, fin = premier_du_mois(today), today
    elif code == "mois_precedent":
        fin = premier_du_mois(today) - timedelta(days=1)
        debut = premier_du_mois(fin)
    elif code == "3mois":
        debut, fin = ajouter_mois(premier_du_mois(today), -2), today
    elif code == "6mois":
        debut, fin = ajouter_mois(premier_du_mois(today), -5), today
    elif code == "annee":
        debut, fin = date(today.year, 1, 1), today
    else:
        if date_debut is None or date_fin is None:
            raise ValueError("Période personnalisée : date_debut et date_fin obligatoires")
        if date_debut > date_fin:
            raise ValueError("date_debut doit précéder date_fin")
        debut, fin = date_debut, date_fin
    officielle = _mois_clos(debut, fin, today)
    return Fenetre(
        code=code,
        date_debut=debut,
        date_fin=fin,
        type_applique="INTERVALLE",
        simulation=not officielle,
        bcm_officielle=officielle,
    )


def appliquer(fenetre: Fenetre, type_periode: TypePeriode) -> Fenetre:
    """Ajuste la fenêtre au type de l'indicateur (POINT / INTERVALLE / MOIS / YTD)."""
    if type_periode == "POINT":
        debut, fin = fenetre.date_fin, fenetre.date_fin
    elif type_periode == "YTD":
        debut, fin = date(fenetre.date_fin.year, 1, 1), fenetre.date_fin
    elif type_periode == "MOIS":
        if fenetre.code == "mois_precedent" or (
            fenetre.date_debut.day == 1 and fenetre.date_fin == dernier_du_mois(fenetre.date_debut)
        ):
            debut, fin = fenetre.date_debut, fenetre.date_fin
        else:
            debut = premier_du_mois(fenetre.date_fin)
            fin = min(fenetre.date_fin, dernier_du_mois(fenetre.date_fin))
    else:
        debut, fin = fenetre.date_debut, fenetre.date_fin
    return Fenetre(
        code=fenetre.code,
        date_debut=debut,
        date_fin=fin,
        type_applique=type_periode,
        simulation=fenetre.simulation,
        bcm_officielle=fenetre.bcm_officielle and type_periode in ("MOIS", "POINT", "YTD"),
    )


def fin_mois_precedent(debut_mois: date) -> date:
    return premier_du_mois(debut_mois) - timedelta(days=1)


def fenetre_mois_bcm(annee: int, mois: int, *, aujourdhui: date | None = None) -> Fenetre:
    """Période officielle d'une déclaration : 1er → dernier jour du mois calendaire."""
    if mois < 1 or mois > 12:
        raise ValueError("Le mois doit être compris entre 1 et 12")
    if annee < 2000 or annee > 2100:
        raise ValueError("Année invalide")
    debut = date(annee, mois, 1)
    fin = dernier_du_mois(debut)
    today = aujourdhui or aujourd_hui()
    officielle = fin < today
    return Fenetre(
        code="personnalisee",
        date_debut=debut,
        date_fin=fin,
        type_applique="MOIS",
        simulation=not officielle,
        bcm_officielle=officielle,
    )
