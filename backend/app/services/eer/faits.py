"""Faits du moteur EER : données du dossier + faits dérivés (PPE, FATCA, risque, avis)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.data.eer_referentiel import TYPES_CLIENT
from app.services.eer.constantes import Risque, RoleDossier, TypeClient

_ORDRE_RISQUE = {Risque.FAIBLE: 0, Risque.MOYEN: 1, Risque.ELEVE: 2}


@dataclass(frozen=True)
class PartieDossier:
    """Une partie dans un rôle du dossier. ``faits`` = données de la partie et du rôle."""

    partie_id: str
    role: RoleDossier
    faits: Mapping[str, Any] = field(default_factory=dict)


def risque_effectif(type_client: str | None, risque_declare: str | None) -> str | None:
    """Le risque imposé par le type (association → ELEVE) prime sur un risque inférieur."""
    impose = TYPES_CLIENT.get(type_client, {}).get("risque_impose") if type_client else None
    if impose is None:
        return risque_declare
    if risque_declare is None or _ORDRE_RISQUE.get(risque_declare, -1) < _ORDRE_RISQUE[impose]:
        return impose
    return risque_declare


def avis_requis(faits: Mapping[str, Any]) -> list[str]:
    """Motifs rendant l'avis du Service Conformité KYC obligatoire (matrices §5.2). Vide = non requis."""
    motifs: list[str] = []
    type_client = faits.get("type_client")
    if type_client in (TypeClient.PM_PRIVEE, TypeClient.PM_PUBLIQUE):
        motifs.append("Toute ouverture de compte d'une personne morale est soumise à l'accord du Service Conformité KYC")
    if type_client == TypeClient.ASSOCIATION:
        motifs.append("Profil association : risque élevé automatique, avis obligatoire")
    if type_client == TypeClient.PP and faits.get("risque") in (Risque.MOYEN, Risque.ELEVE):
        motifs.append("Profil à risque moyen ou élevé : validation préalable du Service Conformité KYC")
    if faits.get("ppe") is True:
        motifs.append("Personne politiquement exposée (client ou mandataire)")
    if faits.get("fatca_indice") is True:
        motifs.append("Indice d'américanité (client ou mandataire)")
    return motifs


def construire_faits(dossier: Mapping[str, Any], parties: Sequence[PartieDossier]) -> dict[str, Any]:
    """Faits du dossier. PPE / FATCA ne sont portés que par le client et le mandataire (fiches)."""
    faits = dict(dossier)
    porteurs = [p for p in parties if p.role in (RoleDossier.CLIENT, RoleDossier.MANDATAIRE)]
    client = next((p for p in parties if p.role == RoleDossier.CLIENT), None)
    mandataires = [p for p in parties if p.role == RoleDossier.MANDATAIRE]

    faits["client_ppe"] = client.faits.get("ppe") if client else None
    faits["ppe"] = any(p.faits.get("ppe") is True for p in porteurs)
    faits["fatca_indice"] = any(p.faits.get("fatca_indice") is True for p in porteurs)
    faits["a_mandataire"] = bool(mandataires)
    faits["nb_mandataires"] = len(mandataires)
    faits["compte_ouvert"] = bool(dossier.get("etat_compte") or dossier.get("racine_client"))
    faits["risque_declare"] = dossier.get("risque")
    faits["risque"] = risque_effectif(dossier.get("type_client"), dossier.get("risque"))
    motifs = avis_requis(faits)
    faits["avis_kyc_requis"] = bool(motifs)
    faits["avis_kyc_motifs"] = motifs
    return faits


def faits_partie(faits_dossier: Mapping[str, Any], partie: PartieDossier) -> dict[str, Any]:
    """Faits d'une règle de portée PARTIE : faits du dossier + ``partie.*``."""
    return {**faits_dossier, **{f"partie.{k}": v for k, v in partie.faits.items()},
            "partie.role": partie.role}
