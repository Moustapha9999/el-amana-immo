"""Périmètre d'accès EER : qui voit / modifie / soumet / affecte / émet l'avis / valide quels dossiers.

Point unique de décision, appliqué par le service (``EerDossierService``) et l'API — jamais
par le frontend. Réutilise le RBAC CORE (users / roles / permissions) et ``users.agence_id`` :
aucune table d'organisation propre à l'EER.

Règle agence :
- ``eer.scope.all`` (rôles conformité, superviseur, lecteur, admin ; ``*`` superuser) →
  toutes les agences ;
- sinon (chargé de clientèle) → uniquement les dossiers de ``users.agence_id`` ;
  sans agence rattachée → aucun dossier, aucune création.

Décision du 04/10/2026 : l'accès au département + module EER donne tous les droits EER
(``charger_permissions_eer``) ; sans cet accès, aucun droit EER, même avec un rôle ``eer.*``.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection
from dataclasses import dataclass

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.plateforme_catalogue import FUNCTIONAL_PERMISSIONS
from app.models import PlateformeModule, User, user_espace_acces_table, user_module_acces_table
from app.services.permission_service import load_user_permission_codes, user_has_permission_codes

MODULE_EER = "eer"
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
    "document_depot": "eer.document.upload",
    "document_telechargement": "eer.document.download",
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


async def acces_module_eer(db: AsyncSession, user: User) -> bool:
    """Grants CORE ADMIN module EER + son département, sur un module actif (requêtes explicites :
    ``user`` peut être un autre agent dont les relations ne sont pas chargées)."""
    if user.is_superuser:
        return True
    trouve = await db.scalar(
        select(PlateformeModule.id)
        .join(user_module_acces_table, user_module_acces_table.c.module_id == PlateformeModule.id)
        .join(user_espace_acces_table, and_(user_espace_acces_table.c.espace_id == PlateformeModule.espace_id,
                                            user_espace_acces_table.c.user_id == user.id))
        .where(PlateformeModule.code == MODULE_EER, PlateformeModule.is_active.is_(True),
               user_module_acces_table.c.user_id == user.id)
        .limit(1)
    )
    return trouve is not None


async def charger_permissions_eer(db: AsyncSession, user: User) -> set[str]:
    """Permissions CORE + décision du 04/10/2026 : tout agent ayant accès au département et au
    module EER (grants CORE ADMIN) dispose de l'ensemble des droits EER."""
    have = await load_user_permission_codes(db, user)
    if user.is_superuser:
        return have
    if await acces_module_eer(db, user):
        return have | {"eer.admin"}
    return {code for code in have if not code.startswith("eer.")}


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
