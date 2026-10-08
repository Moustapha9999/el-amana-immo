"""Fiches KYC pré-remplies : vues sur les données uniques du dossier.

Une fiche ne stocke rien : chaque champ pointe un ``chemin`` dans les données source
(dossier, client, partie, rôle). Deux fiches qui partagent un chemin affichent la même
valeur — l'information n'est saisie qu'une fois. Seul l'état du champ est conservé
(``eer_champs_etat``) avec l'empreinte de la valeur confirmée.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.services.eer import conditions
from app.services.eer.constantes import EtatChamp

ORIGINES_A_CONFIRMER = frozenset({"ORION", "VERSION_PRECEDENTE", "IMPORT"})


@dataclass(frozen=True)
class ChampFiche:
    chemin: str
    libelle: str
    section: str
    obligatoire: bool
    valeur: Any
    etat: EtatChamp
    source: str | None = None

    @property
    def bloquant(self) -> bool:
        return self.obligatoire and self.etat in (EtatChamp.MANQUANT, EtatChamp.A_CONFIRMER)


@dataclass(frozen=True)
class EtatEnregistre:
    etat: EtatChamp
    empreinte: str | None = None


def lire(source: Mapping[str, Any], chemin: str) -> Any:
    courant: Any = source
    for segment in chemin.split("."):
        if not isinstance(courant, Mapping) or segment not in courant:
            return None
        courant = courant[segment]
    return courant


def empreinte(valeur: Any) -> str:
    brut = json.dumps(valeur, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(brut.encode("utf-8")).hexdigest()


def _vide(valeur: Any) -> bool:
    return valeur is None or (isinstance(valeur, str) and not valeur.strip()) or valeur == []


def pre_remplir(
    fiche: Mapping[str, Any],
    source: Mapping[str, Any],
    faits: Mapping[str, Any],
    *,
    origines: Mapping[str, str] | None = None,
    etats: Mapping[str, EtatEnregistre] | None = None,
) -> list[ChampFiche]:
    origines = origines or {}
    etats = etats or {}
    champs: list[ChampFiche] = []
    for d in fiche["champs"]:
        chemin = d["chemin"]
        valeur = lire(source, chemin)
        enregistre = etats.get(chemin)
        if not conditions.evaluer(d.get("condition"), faits):
            etat = EtatChamp.NON_APPLICABLE
        elif enregistre and enregistre.etat == EtatChamp.NON_APPLICABLE and not d["obligatoire"]:
            etat = EtatChamp.NON_APPLICABLE
        elif _vide(valeur):
            etat = EtatChamp.MANQUANT
        elif enregistre and enregistre.etat == EtatChamp.CONFIRME and enregistre.empreinte == empreinte(valeur):
            etat = EtatChamp.CONFIRME
        elif origines.get(chemin) in ORIGINES_A_CONFIRMER:
            etat = EtatChamp.A_CONFIRMER
        else:
            etat = EtatChamp.CONNU
        champs.append(ChampFiche(
            chemin, d["libelle"], d["section"], d["obligatoire"], valeur, etat,
            source=origines.get(chemin)))
    return champs


def confirmer(champ: ChampFiche) -> EtatEnregistre:
    if _vide(champ.valeur):
        raise ValueError(f"Champ « {champ.libelle} » vide : rien à confirmer")
    return EtatEnregistre(EtatChamp.CONFIRME, empreinte(champ.valeur))


ETATS_CONNUS = frozenset({EtatChamp.CONNU, EtatChamp.A_CONFIRMER, EtatChamp.CONFIRME})


def donnee_connue(chemins: tuple[str, ...], champs: list[ChampFiche]) -> bool | None:
    """Les données de fiche qui portent un élément de checklist sont-elles déjà connues ?

    ``("*",)`` = tous les champs obligatoires de la fiche. ``None`` = l'élément ne dépend
    d'aucune donnée applicable de cette fiche.
    """
    if chemins == ("*",):
        cibles = [c for c in champs if c.obligatoire]
    else:
        par_chemin = {c.chemin: c for c in champs}
        cibles = [par_chemin[x] for x in chemins if x in par_chemin]
    cibles = [c for c in cibles if c.etat != EtatChamp.NON_APPLICABLE]
    if not cibles:
        return None
    return all(c.etat in ETATS_CONNUS for c in cibles)


def champs_a_completer(champs: list[ChampFiche]) -> list[ChampFiche]:
    """Ce que l'agent doit compléter : le reste est déjà connu."""
    return [c for c in champs if c.bloquant]


def ecrire(source: dict[str, Any], chemin: str, valeur: Any) -> None:
    """Écrit dans la donnée source unique (jamais dans la fiche)."""
    *parents, feuille = chemin.split(".")
    courant = source
    for segment in parents:
        courant = courant.setdefault(segment, {})
        if not isinstance(courant, dict):
            raise ValueError(f"Chemin invalide : {chemin}")
    courant[feuille] = valeur
