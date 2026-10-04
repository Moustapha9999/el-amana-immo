"""Périmètre d'accès EER : qui voit / modifie / soumet / affecte / émet l'avis / valide quels dossiers.

Point unique de décision, appliqué par le service (``EerDossierService``) et l'API — jamais
par le frontend. Réutilise le RBAC CORE (users / roles / permissions) et ``users.agence_id`` :
aucune table d'organisation propre à l'EER.

Règle agence :
- ``eer.scope.all`` (rôles conformité, superviseur, lecteur, admin ; ``*`` superuser) →
  toutes les agences ;
- sinon (chargé de clientèle) → uniquement les dossiers de ``users.agence_id`` ;
  sans agence rattachée → aucun dossier, aucune création.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection
from dataclasses import dataclass

from app.data.plateforme_catalogue import FUNCTIONAL_PERMISSIONS
from app.models import User
from app.services.permission_service import user_has_permission_codes

PERIMETRE_GLOBAL = "eer.scope.all"
PERMISSIONS_EER: tuple[str, ...] = tuple(code for code, _l, module in FUNCTIONAL_PERMISSIONS if module == "eer")

# Action métier → code permission (noms du cahier des charges → codes du catalogue CORE).
ACTIONS: dict[str, str] = {
    "lecture": "eer.view",
    "creation": "eer.create",
    "modification": "eer.update",
    "soumission": "eer.submit",
    "affectation": "eer.assign",
    "controle": "eer.control",
    "demande_complement": "eer.complement.request",
    "complement": "eer.complement.receive",
    "avis": "eer.avis",
    "validation": "eer.validate",
    "cloture": "eer.archive",
    "archivage": "eer.archive",
    "derogation": "eer.validate",
    "export": "eer.export",
    "reporting": "eer.report.view",
    "documents": "eer.document.view",
    "audit": "eer.audit.view",
    "administration": "eer.admin",
}


@dataclass(frozen=True)
class EerScope:
    user_id: uuid.UUID
    agence_id: uuid.UUID | None
    toutes_agences: bool
    permissions: frozenset[str]
    roles: tuple[str, ...] = ()

    def peut(self, code: str) -> bool:
        return code in self.permissions

    def couvre(self, agence_id: uuid.UUID | None) -> bool:
        if self.toutes_agences:
            return True
        return self.agence_id is not None and agence_id == self.agence_id

    @property
    def agences(self) -> list[uuid.UUID] | None:
        """``None`` = toutes ; liste vide = aucune."""
        if self.toutes_agences:
            return None
        return [self.agence_id] if self.agence_id else []

    def capacites(self) -> dict[str, bool]:
        return {action: self.peut(code) for action, code in ACTIONS.items()}

    def to_dict(self) -> dict:
        return {
            "user_id": str(self.user_id),
            "agence_id": str(self.agence_id) if self.agence_id else None,
            "perimetre": "TOUTES_AGENCES" if self.toutes_agences else ("AGENCE" if self.agence_id else "AUCUN"),
            "roles": list(self.roles),
            "permissions": sorted(self.permissions),
            "capacites": self.capacites(),
        }


def permissions_effectives(permissions: Collection[str]) -> frozenset[str]:
    """Codes EER réellement accordés (``*`` et ``eer.admin`` couvrent tout le module)."""
    have = set(permissions)
    return frozenset(code for code in PERMISSIONS_EER if user_has_permission_codes(have, code))


def resolve_eer_access_scope(user: User, permissions: Collection[str]) -> EerScope:
    effectives = permissions_effectives(permissions)
    roles = tuple(sorted(r.code for r in (user.__dict__.get("roles") or []) if r.code.startswith("eer.")))
    return EerScope(
        user_id=user.id,
        agence_id=user.agence_id,
        toutes_agences=PERIMETRE_GLOBAL in effectives,
        permissions=effectives,
        roles=roles,
    )
