"""Échéances EER : compléments échus et pièces d'identité expirées / bientôt expirées.

Ne décide rien et ne modifie aucun dossier : envoie des notifications (référence du dossier
seulement), au plus une par dossier et par type d'alerte sur la fenêtre ``RAPPEL_JOURS``.
L'alerte « bientôt expirée » n'existe que si ``controle.expiration_proche_jours`` est renseigné.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EerComplement, EerDossier, EerDossierPartie, EerPieceIdentite, Notification
from app.services.eer.constantes import RoleDossier
from app.services.eer.workflow import Statut
from app.services.eer_controles_auto import jours_parametre
from app.services.eer_dossier_service import EerDossierService
from app.services.eer_notifications import ENTITE, envoyer

RAPPEL_JOURS = 7
VERROU_JOB = 74_210_001  # pg_try_advisory_xact_lock : un seul passage à la fois (plusieurs workers)
# Relation en cours ou établie : la validité des pièces reste à suivre.
STATUTS_SUIVIS = tuple(s for s in Statut if s not in (Statut.BROUILLON, Statut.ABANDONNE, Statut.ARCHIVE))
ROLES_PIECE = (RoleDossier.CLIENT, RoleDossier.MANDATAIRE, RoleDossier.BENEFICIAIRE_EFFECTIF)


async def _deja_notifie(db: AsyncSession, dossier_id: uuid.UUID, evenement: str) -> bool:
    depuis = datetime.now(UTC) - timedelta(days=RAPPEL_JOURS)
    return await db.scalar(select(Notification.id).where(
        Notification.entity == ENTITE, Notification.entity_id == str(dossier_id),
        Notification.event_type == evenement, Notification.created_at >= depuis).limit(1)) is not None


async def complements_echus(db: AsyncSession, aujourd_hui: date) -> int:
    lignes = (await db.execute(
        select(EerDossier, EerComplement)
        .join(EerComplement, EerComplement.dossier_id == EerDossier.id)
        .where(EerComplement.statut == "OUVERT", EerComplement.echeance < aujourd_hui,
               EerDossier.statut == Statut.A_COMPLETER, EerDossier.deleted_at.is_(None)))).all()
    envoyes = 0
    for d, c in lignes:
        evenement = "eer.complement.echu"
        if await _deja_notifie(db, d.id, evenement):
            continue
        retard = (aujourd_hui - c.echeance).days
        envoyes += await envoyer(db, d, [d.created_by_id, c.demande_par_id, d.analyste_id], auteur_id=None,
                                  evenement=evenement, titre="Complément EER échu", priorite="avertissement",
                                  message=f"Le complément n° {c.numero} du dossier {{ref}} est échu depuis "
                                          f"{retard} jour(s).")
    return envoyes


async def pieces_a_renouveler(db: AsyncSession, aujourd_hui: date, jours_proche: int | None) -> int:
    limite = aujourd_hui + timedelta(days=jours_proche or 0)
    lignes = (await db.execute(
        select(EerDossier.id, EerPieceIdentite.date_expiration)
        .join(EerDossierPartie, EerDossierPartie.dossier_id == EerDossier.id)
        .join(EerPieceIdentite, EerPieceIdentite.partie_id == EerDossierPartie.partie_id)
        .where(EerDossier.deleted_at.is_(None), EerDossier.statut.in_(STATUTS_SUIVIS),
               EerDossierPartie.role.in_(ROLES_PIECE), EerPieceIdentite.date_expiration.is_not(None),
               EerPieceIdentite.date_expiration < aujourd_hui if jours_proche is None
               else EerPieceIdentite.date_expiration <= limite))).all()
    premiere: dict[uuid.UUID, date] = {}
    for dossier_id, expiration in lignes:
        premiere[dossier_id] = min(expiration, premiere.get(dossier_id, expiration))
    envoyes = 0
    svc = EerDossierService(db)
    for dossier_id, expiration in premiere.items():
        expiree = expiration < aujourd_hui
        evenement = "eer.piece.expiree" if expiree else "eer.piece.expiration_proche"
        if await _deja_notifie(db, dossier_id, evenement):
            continue
        d = await svc.charger(dossier_id)
        message = ("Une pièce d'identité du dossier {ref} est expirée depuis le "
                   f"{expiration:%d/%m/%Y}." if expiree else
                   "Une pièce d'identité du dossier {ref} expire le " f"{expiration:%d/%m/%Y}.")
        envoyes += await envoyer(db, d, [d.analyste_id, d.created_by_id], auteur_id=None, evenement=evenement,
                                  titre="Pièce d'identité expirée" if expiree else "Pièce d'identité bientôt expirée",
                                  priorite="avertissement" if expiree else "attention", message=message)
    return envoyes


async def executer(db: AsyncSession, aujourd_hui: date | None = None) -> dict[str, int | bool]:
    """Un passage complet, dans la transaction de l'appelant (qui valide)."""
    if not await db.scalar(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": VERROU_JOB}):
        return {"execute": False, "complements_echus": 0, "pieces": 0}
    aujourd_hui = aujourd_hui or date.today()
    jours = jours_parametre((await EerDossierService(db).parametres()).get("controle.expiration_proche_jours"))
    return {
        "execute": True,
        "complements_echus": await complements_echus(db, aujourd_hui),
        "pieces": await pieces_a_renouveler(db, aujourd_hui, jours),
    }
