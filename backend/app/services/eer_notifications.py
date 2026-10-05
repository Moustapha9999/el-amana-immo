"""Notifications EER : qui doit agir après une étape du workflow.

Le message ne porte que la référence du dossier (jamais le nom du client, NNI, etc.) : la
notification peut être lue hors du module. Destinataires = agents actifs qui détiennent la
permission de l'action suivante sur l'agence du dossier ; l'auteur de l'action est exclu.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import EerDossier, User
from app.services.eer.workflow import Statut
from app.services.eer_access import charger_permissions_eer, resolve_eer_access_scope
from app.services.notification_service import NotificationService

ENTITE = "eer_dossier"
ESPACE = "audit-controle-conformite"
MODULE = "eer"

# Statut atteint → (permission de l'action attendue, titre, message, priorité).
_PAR_PERMISSION: dict[str, tuple[str, str, str, str]] = {
    Statut.A_AFFECTER: ("eer.assign", "Dossier EER à affecter", "Le dossier {ref} a été soumis et attend une affectation.", "info"),
    Statut.AVIS_CONFORMITE: ("eer.avis", "Avis Conformité KYC demandé", "Le dossier {ref} attend l'avis Conformité KYC.", "attention"),
    Statut.CONFORME: ("eer.validate", "Dossier EER à valider", "Le dossier {ref} a été déclaré conforme et attend la validation.", "info"),
}


async def _agents(db: AsyncSession, permission: str, agence_id: uuid.UUID | None) -> list[uuid.UUID]:
    users = (await db.scalars(select(User).options(selectinload(User.roles))
                              .where(User.is_active.is_(True), User.deleted_at.is_(None)))).all()
    ids = []
    for u in users:
        portee = resolve_eer_access_scope(u, await charger_permissions_eer(db, u))
        if portee.peut(permission) and portee.couvre(agence_id):
            ids.append(u.id)
    return ids


async def envoyer(db: AsyncSession, d: EerDossier, destinataires: Iterable[uuid.UUID | None], *,
                   auteur_id: uuid.UUID | None, evenement: str, titre: str, message: str,
                   priorite: str = "info") -> int:
    svc = NotificationService(db)
    envoyes = 0
    for uid in dict.fromkeys(u for u in destinataires if u and u != auteur_id):
        await svc.create(user_id=uid, type_notification="eer", titre=titre, message=message.format(ref=d.reference),
                         entity=ENTITE, entity_id=str(d.id), espace_code=ESPACE, module_code=MODULE, categorie="workflow",
                         priorite=priorite, event_type=evenement, emetteur_type="module",
                         emetteur_label="Entrées en relation", actor_user_id=auteur_id)
        envoyes += 1
    return envoyes


async def apres_transition(db: AsyncSession, d: EerDossier, auteur_id: uuid.UUID | None) -> int:
    statut = Statut(d.statut)
    evenement = f"eer.dossier.{statut.lower()}"
    if statut in _PAR_PERMISSION:
        permission, titre, message, priorite = _PAR_PERMISSION[statut]
        return await envoyer(db, d, await _agents(db, permission, d.agence_id), auteur_id=auteur_id,
                              evenement=evenement, titre=titre, message=message, priorite=priorite)
    if statut == Statut.AFFECTE:
        return await envoyer(db, d, [d.analyste_id], auteur_id=auteur_id, evenement=evenement,
                              titre="Dossier EER affecté", message="Le dossier {ref} vous a été affecté pour contrôle.")
    if statut == Statut.A_COMPLETER:
        return await envoyer(db, d, [d.created_by_id], auteur_id=auteur_id, evenement=evenement,
                              titre="Complément demandé", priorite="attention",
                              message="Un complément est demandé sur le dossier {ref}.")
    if statut == Statut.RESOUMIS:
        return await envoyer(db, d, [d.analyste_id], auteur_id=auteur_id, evenement=evenement,
                              titre="Complément reçu", message="Le complément du dossier {ref} a été fourni : reprise du contrôle.")
    if statut == Statut.VALIDE:
        return await envoyer(db, d, [d.created_by_id, d.analyste_id], auteur_id=auteur_id, evenement=evenement,
                              titre="Dossier EER validé", message="Le dossier {ref} a été validé.")
    if statut == Statut.ABANDONNE:
        return await envoyer(db, d, [d.created_by_id, d.analyste_id], auteur_id=auteur_id, evenement=evenement,
                              titre="Dossier EER abandonné", message="Le dossier {ref} a été abandonné.")
    return 0


async def relance(db: AsyncSession, d: EerDossier, auteur_id: uuid.UUID | None) -> int:
    return await envoyer(db, d, [d.created_by_id], auteur_id=auteur_id, evenement="eer.dossier.relance",
                          titre="Relance complément", priorite="attention",
                          message=f"Relance n° {d.nb_relances} : le complément du dossier {{ref}} est attendu.")
