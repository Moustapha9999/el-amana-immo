"""Périmètre d'accès Réclamations : qui voit quels dossiers, qui peut agir.

Point unique de décision, appliqué par les services et l'API — jamais par le frontend.
Réutilise le RBAC CORE (``reclamations.*``) et le rattachement aux unités
(``reclamation_unite_membres``) :

- ``reclamations.scope.all`` (Service Réclamations, consultation / audit, admin) → tous les dossiers ;
- sinon → dossiers créés par l'agent, reçus par l'une de ses unités, ou affectés (même par le
  passé) à l'une de ses unités. Sans unité rattachée : seulement ses propres saisies ;
- en plus, dossiers des unités rattachées à son périmètre organisationnel (affectation CORE ADMIN
  élargie à ENTITE / ENTITE_ET_SOUS_ENTITES, ex. directeur). Le périmètre élargit les dossiers
  visibles, pas les actions : elles restent soumises aux permissions du rôle, et le retour d'un
  service reste réservé aux membres de l'unité de traitement.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection
from dataclasses import dataclass, field

from fastapi import HTTPException, status
from sqlalchemy import ColumnElement, and_, exists, false, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.plateforme_catalogue import FUNCTIONAL_PERMISSIONS
from app.models import Reclamation, ReclamationAffectation, ReclamationUnite, ReclamationUniteMembre, User
from app.services.org_referentiel import charger_perimetre
from app.services.permission_service import load_user_permission_codes, user_has_permission_codes
from app.services.reclamations.constantes import MODULE_CODE

PERIMETRE_GLOBAL = "reclamations.scope.all"
PERMISSION_SUPPRESSION = "reclamations.delete"
PERMISSIONS: tuple[str, ...] = tuple(code for code, _l, module in FUNCTIONAL_PERMISSIONS if module == MODULE_CODE)

# Capacité exposée au frontend → permission (le backend revérifie toujours).
CAPACITES: dict[str, str] = {
    "voir": "reclamations.view",
    "tout_voir": PERIMETRE_GLOBAL,
    "creer": "reclamations.create",
    "modifier": "reclamations.update",
    "qualifier": "reclamations.qualify",
    "affecter": "reclamations.assign",
    "traiter": "reclamations.treat",
    "gerer_service": "reclamations.service.manage",
    "examiner_retour": "reclamations.review",
    "envoyer_reponse": "reclamations.response.send",
    "refuser": "reclamations.reject",
    "annuler": "reclamations.cancel",
    "cloturer": "reclamations.close",
    "rouvrir": "reclamations.reopen",
    "archiver": "reclamations.archive",
    "supprimer": "reclamations.delete",
    "documents_voir": "reclamations.document.view",
    "documents_deposer": "reclamations.document.upload",
    "documents_telecharger": "reclamations.document.download",
    "documents_retirer": "reclamations.document.remove",
    "reporting_voir": "reclamations.reporting.view",
    "reporting_exporter": "reclamations.reporting.export",
    "referentiels_voir": "reclamations.references.view",
    "referentiels_gerer": "reclamations.references.manage",
    "referentiels_valider": "reclamations.references.validate",
    "unites_gerer": "reclamations.services.manage",
    "admin": "reclamations.admin",
}


@dataclass(frozen=True)
class ReclamationsScope:
    user: User
    permissions: frozenset[str]
    unites: frozenset[uuid.UUID] = field(default_factory=frozenset)
    unites_responsable: frozenset[uuid.UUID] = field(default_factory=frozenset)
    membre_service_central: bool = False
    # Unités dont les dossiers sont visibles via le périmètre organisationnel (pas une appartenance).
    unites_perimetre_org: frozenset[uuid.UUID] = field(default_factory=frozenset)
    ip_address: str | None = None
    session_id: uuid.UUID | None = None

    @property
    def user_id(self) -> uuid.UUID:
        return self.user.id

    @property
    def toutes(self) -> bool:
        return PERIMETRE_GLOBAL in self.permissions

    def peut(self, *codes: str) -> bool:
        return any(code in self.permissions for code in codes)

    def exiger(self, *codes: str) -> None:
        if not self.peut(*codes):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail={"code": "PERMISSION_DENIED", "message": "Permission refusée", "required": list(codes)},
            )

    def membre_de(self, unite_id: uuid.UUID | None) -> bool:
        return unite_id is not None and unite_id in self.unites

    def responsable_de(self, unite_id: uuid.UUID | None) -> bool:
        return unite_id is not None and unite_id in self.unites_responsable

    def filtre_dossiers(self) -> ColumnElement[bool]:
        """Condition SQL des dossiers visibles (à appliquer à toute liste, KPI ou export) : hors corbeille."""
        return and_(Reclamation.supprimee_le.is_(None), self._perimetre())

    def filtre_corbeille(self) -> ColumnElement[bool]:
        """Dossiers supprimés (logiquement) du périmètre, visibles des seuls profils habilités à supprimer."""
        if not self.peut(PERMISSION_SUPPRESSION):
            return false()
        return and_(Reclamation.supprimee_le.is_not(None), self._perimetre())

    def _perimetre(self) -> ColumnElement[bool]:
        if not self.peut("reclamations.view"):
            return false()
        if self.toutes:
            return Reclamation.id.is_not(None)
        conditions: list[ColumnElement[bool]] = [Reclamation.created_by_id == self.user_id]
        if self.unites:
            unites = list(self.unites)
            conditions.append(Reclamation.unite_reception_id.in_(unites))
            conditions.append(exists().where(
                ReclamationAffectation.reclamation_id == Reclamation.id,
                ReclamationAffectation.unite_destinataire_id.in_(unites),
            ))
        if self.unites_perimetre_org:
            org = list(self.unites_perimetre_org)
            conditions.append(Reclamation.unite_reception_id.in_(org))
            conditions.append(Reclamation.unite_concernee_id.in_(org))
            conditions.append(exists().where(
                ReclamationAffectation.reclamation_id == Reclamation.id,
                ReclamationAffectation.unite_destinataire_id.in_(org),
            ))
        return or_(*conditions)

    async def couvre(self, db: AsyncSession, r: Reclamation) -> bool:
        if not self.peut("reclamations.view"):
            return False
        if r.supprimee_le is not None and not self.peut(PERMISSION_SUPPRESSION):
            return False
        if self.toutes or r.created_by_id == self.user_id or self.membre_de(r.unite_reception_id):
            return True
        org = self.unites_perimetre_org
        if r.unite_reception_id in org or r.unite_concernee_id in org:
            return True
        visibles = self.unites | org
        if not visibles:
            return False
        return await db.scalar(select(exists().where(
            ReclamationAffectation.reclamation_id == r.id,
            ReclamationAffectation.unite_destinataire_id.in_(list(visibles)),
        ))) or False

    async def exiger_dossier(self, db: AsyncSession, r: Reclamation | None) -> Reclamation:
        """404 plutôt que 403 hors périmètre : l'existence d'un dossier n'est pas divulguée."""
        if r is None or not await self.couvre(db, r):
            raise HTTPException(status.HTTP_404_NOT_FOUND,
                                detail={"code": "NOT_FOUND", "message": "Réclamation introuvable"})
        return r

    def capacites(self) -> dict[str, bool]:
        return {nom: code in self.permissions for nom, code in CAPACITES.items()}

    def to_dict(self) -> dict:
        return {
            "user_id": str(self.user_id),
            "perimetre": "TOUS" if self.toutes else (
                "UNITES" if self.unites or self.unites_perimetre_org else "PERSONNEL"),
            "unites": sorted(str(u) for u in self.unites),
            "unites_perimetre_org": sorted(str(u) for u in self.unites_perimetre_org),
            "unites_responsable": sorted(str(u) for u in self.unites_responsable),
            "membre_service_central": self.membre_service_central,
            "capacites": self.capacites(),
        }


def permissions_effectives(permissions: Collection[str]) -> frozenset[str]:
    """Codes Réclamations réellement accordés (``*`` et ``reclamations.admin`` couvrent tout)."""
    have = set(permissions)
    return frozenset(code for code in PERMISSIONS if user_has_permission_codes(have, code))


async def charger_scope(db: AsyncSession, user: User, *, ip_address: str | None = None,
                        session_id: uuid.UUID | None = None) -> ReclamationsScope:
    have = await load_user_permission_codes(db, user)
    effectives = permissions_effectives(have)
    # Le périmètre global reste `reclamations.scope.all` : `org.scope.all` n'ouvre pas les dossiers clients.
    perimetre = await charger_perimetre(db, user, permissions=have)
    unites_org: frozenset[uuid.UUID] = frozenset()
    if perimetre.entites:
        unites_org = frozenset((await db.scalars(select(ReclamationUnite.id).where(
            ReclamationUnite.org_entite_id.in_(list(perimetre.entites)),
            ReclamationUnite.actif.is_(True)))).all())
    lignes = (await db.execute(
        select(ReclamationUniteMembre.unite_id, ReclamationUniteMembre.role_membre,
               ReclamationUnite.est_service_reclamations)
        .join(ReclamationUnite, ReclamationUnite.id == ReclamationUniteMembre.unite_id)
        .where(ReclamationUniteMembre.user_id == user.id, ReclamationUniteMembre.actif.is_(True),
               ReclamationUnite.actif.is_(True))
    )).all()
    return ReclamationsScope(
        user=user,
        permissions=effectives,
        unites=frozenset(u for u, _r, _c in lignes),
        unites_responsable=frozenset(u for u, r, _c in lignes if r == "RESPONSABLE"),
        membre_service_central=any(c for _u, _r, c in lignes),
        unites_perimetre_org=unites_org,
        ip_address=ip_address,
        session_id=session_id,
    )
