"""Authentification machine-à-machine — règles préparatoires (Phase 3), NON ACTIVÉE.

Aucun jeton n'est émis ni validé : aucun mécanisme n'a été approuvé par la DSI
(docs/studio-integration-api.md § 12). Ce module ne fixe que les décisions que tout mécanisme retenu
devra appliquer avant d'accepter un appel d'application cliente. Il n'est appelé par aucune route.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.integrations import catalogue as cat
from app.services.integrations.clients import admissibilite

ENVIRONNEMENTS_OUVERTS = frozenset({"DEV", "TEST"})


@dataclass(frozen=True)
class Decision:
    autorise: bool
    code: str
    motif: str


@dataclass(frozen=True)
class DroitApprouve:
    """Instantané d'une opération approuvée (``integration_client_grants`` au statut ``approuvee``)."""

    operation_id: str
    methode: str
    chemin: str
    permissions: tuple[str, ...]


def _refus(code: str, motif: str) -> Decision:
    return Decision(False, code, motif)


def eligibilite_emission(
    statut_client: str | None,
    environnement_client: str | None,
    environnement_cible: str,
    nb_operations_approuvees: int,
) -> Decision:
    """Une application ne peut obtenir un jeton que si tout est établi ; tout le reste est refusé."""
    if environnement_cible not in ENVIRONNEMENTS_OUVERTS:
        return _refus("ENVIRONNEMENT_FERME", "Environnement non ouvert aux applications clientes.")
    if statut_client is None:
        return _refus("CLIENT_INCONNU", "Application inconnue.")
    if statut_client != "active":
        return _refus("CLIENT_NON_ACTIF", f"Application au statut « {statut_client} ».")
    if environnement_client != environnement_cible:
        return _refus("ENVIRONNEMENT_DIFFERENT", "Application enregistrée pour un autre environnement.")
    if nb_operations_approuvees < 1:
        return _refus("AUCUNE_OPERATION_APPROUVEE", "Aucune opération approuvée pour cette application.")
    return Decision(True, "ELIGIBLE", "Application active, environnement conforme, opérations approuvées.")


def decision_appel(
    op: cat.Operation | None,
    methode: str,
    chemin_gabarit: str,
    droits: dict[str, DroitApprouve],
    etats_modules: dict[str, str],
) -> Decision:
    """Un jeton valide ne suffit pas : l'opération appelée doit être approuvée et toujours fiable.

    ``chemin_gabarit`` est le gabarit de route résolu par le routeur (``/api/v1/x/{id}``), jamais
    l'URL brute. Les contrôles métier et de périmètre des données de la route restent à appliquer.
    """
    if op is None or op.methode != methode.upper() or op.chemin != chemin_gabarit:
        return _refus("OPERATION_INCONNUE", "Opération absente du catalogue actuel.")
    droit = droits.get(op.operation_id)
    if droit is None:
        return _refus("OPERATION_NON_APPROUVEE", "Opération non approuvée pour cette application.")
    if droit.methode != op.methode or droit.chemin != op.chemin:
        return _refus("OPERATION_MODIFIEE", "La route a changé depuis l'approbation : nouvelle revue requise.")
    if sorted(droit.permissions) != sorted(op.permissions):
        return _refus("PERMISSIONS_MODIFIEES", "Les permissions de la route ont changé : nouvelle revue requise.")
    ok, motif = admissibilite(op, etats_modules)
    if not ok:
        return _refus("OPERATION_NON_FIABLE", motif or "Contrôle d'accès de la route non établi.")
    return Decision(True, "APPROUVEE", "Opération approuvée ; contrôles métier de la route à appliquer.")
