"""Suppression d'une réclamation : mise à la corbeille (suppression logique) et restauration.

Pas de suppression physique : la chronologie est en ajout seul (trigger
``trg_reclamation_evenements_immuable``) et relève de la conservation documentaire ; la contourner
n'est pas permis. Un dossier supprimé sort des listes, KPI, exports et alertes ; il reste
consultable et restaurable par les profils ``reclamations.delete`` (et l'administrateur du module).

Rien n'est retiré : opérations concernées (simples références — aucune écriture dans ORION ni en
comptabilité), pièces GED, fiches de traitement et historique restent rattachés au dossier.

Suppression refusée (règles de conservation) : dossier archivé, clôturé ou rejeté, réponse
envoyée au client, pièce officielle (réponse, preuve d'envoi), dossier référencé par un autre.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GedDocument, Reclamation, ReclamationDocument, ReclamationReponse
from app.services.reclamations import constantes as C
from app.services.reclamations import operations as ops
from app.services.reclamations.acces import PERMISSION_SUPPRESSION as PERMISSION
from app.services.reclamations.acces import ReclamationsScope
from app.services.reclamations.dossiers import _evenement, charger
from app.services.reclamations.outils import auditer, conflit, erreur, iso, maintenant, texte_long

__all__ = ["PERMISSION", "blocages", "restaurer", "supprimer"]


def _raison(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


async def blocages(db: AsyncSession, dossiers: list[Reclamation]) -> dict[uuid.UUID, list[dict[str, str]]]:
    """Motifs interdisant la suppression, par dossier (vide = suppression possible)."""
    res: dict[uuid.UUID, list[dict[str, str]]] = {r.id: [] for r in dossiers}
    ids = [r.id for r in dossiers if not r.supprimee_le]
    if not ids:
        return res
    reponses = set((await db.scalars(select(ReclamationReponse.reclamation_id).where(
        ReclamationReponse.reclamation_id.in_(ids), ReclamationReponse.statut == "ENVOYEE"))).all())
    officiels = set((await db.scalars(
        select(ReclamationDocument.reclamation_id)
        .join(GedDocument, GedDocument.id == ReclamationDocument.document_id)
        .where(ReclamationDocument.reclamation_id.in_(ids), GedDocument.deleted_at.is_(None),
               ReclamationDocument.categorie.in_(C.CATEGORIES_OFFICIELLES)))).all())
    references: dict[uuid.UUID, list[str]] = {}
    for ref, doublon, liee in (await db.execute(
            select(Reclamation.reference, Reclamation.doublon_de_id, Reclamation.reclamation_liee_id).where(
                Reclamation.supprimee_le.is_(None),
                or_(Reclamation.doublon_de_id.in_(ids), Reclamation.reclamation_liee_id.in_(ids))))).all():
        for cible in {doublon, liee} & set(ids):
            references.setdefault(cible, []).append(ref)
    for r in dossiers:
        if r.supprimee_le:
            continue
        lst = res[r.id]
        if r.archivee_le:
            lst.append(_raison("DOSSIER_ARCHIVE", "Dossier archivé : il relève de la conservation documentaire "
                                                  "et ne peut pas être supprimé."))
        if r.statut in C.STATUTS_NON_SUPPRIMABLES:
            lst.append(_raison("DOSSIER_CLOTURE", f"Dossier {C.STATUT_LIBELLES[r.statut].lower()} : une décision "
                                                  "a été rendue, il se conserve (réouverture ou archivage)."))
        if r.id in reponses or r.date_reponse_client:
            lst.append(_raison("REPONSE_ENVOYEE", "Une réponse a été envoyée au client : le dossier se conserve."))
        if r.id in officiels:
            lst.append(_raison("DOCUMENTS_OFFICIELS", "Le dossier contient des documents officiels (réponse au "
                                                      "client, preuve d'envoi) : il se conserve."))
        if r.id in references:
            lst.append(_raison("DOSSIER_REFERENCE", "Dossier référencé par "
                                                    f"{', '.join(sorted(references[r.id]))} (doublon ou lien)."))
    return res


def _revision(r: Reclamation, data: dict) -> None:
    if data.get("revision") is not None and data["revision"] != r.revision:
        raise conflit("Le dossier a été modifié entre-temps : rechargez-le", "CONFLIT_REVISION",
                      revision=r.revision)


def _motif(data: dict) -> str:
    motif = texte_long(data.get("motif"))
    if not motif:
        raise erreur("Le motif est obligatoire", "MOTIF_OBLIGATOIRE")
    return motif


async def _nb_documents(db: AsyncSession, r: Reclamation) -> int:
    return await db.scalar(select(func.count()).select_from(GedDocument).where(
        GedDocument.module_code == C.MODULE_CODE, GedDocument.entity == C.GED_ENTITE,
        GedDocument.entity_id == str(r.id), GedDocument.deleted_at.is_(None))) or 0


async def supprimer(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, data: dict) -> dict:
    s.exiger(PERMISSION)
    r = await charger(db, s, rid, verrou=True, corbeille=True)
    if r.supprimee_le:
        raise conflit("Ce dossier est déjà supprimé", "DEJA_SUPPRIME")
    _revision(r, data)
    motif = _motif(data)
    if (data.get("confirmation") or "").strip().upper() != r.reference:
        raise erreur("Pour confirmer, saisissez exactement la référence du dossier", "CONFIRMATION_INVALIDE")
    raisons = (await blocages(db, [r]))[r.id]
    if raisons:
        raise conflit(raisons[0]["message"], raisons[0]["code"], blocages=raisons)
    operations = await ops.lister(db, r.id)
    nb_documents = await _nb_documents(db, r)
    r.supprimee_le = maintenant()
    r.supprimee_par_id = s.user_id
    r.motif_suppression = motif
    r.revision += 1
    r.updated_by_id = s.user_id
    db.add(_evenement(r, s, "SUPPRESSION", statut_avant=r.statut, etape_avant=r.etape, commentaire=motif,
                      donnees={"operations": len(operations), "documents": nb_documents}))
    await db.flush()
    await auditer(db, s, "reclamations.suppression", C.GED_ENTITE, r.id,
                  before={"reference": r.reference, "statut": r.statut, "etape": r.etape,
                          "operations": [o.reference for o in operations], "documents": nb_documents},
                  after={"supprimee_le": iso(r.supprimee_le), "motif": motif})
    return {"id": str(r.id), "reference": r.reference, "supprimee_le": iso(r.supprimee_le),
            "operations_conservees": len(operations), "documents_conserves": nb_documents}


async def restaurer(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, data: dict) -> Reclamation:
    s.exiger(PERMISSION)
    r = await charger(db, s, rid, verrou=True, corbeille=True)
    if not r.supprimee_le:
        raise conflit("Ce dossier n'est pas supprimé", "NON_SUPPRIME")
    _revision(r, data)
    motif = _motif(data)
    avant = {"supprimee_le": iso(r.supprimee_le), "motif_suppression": r.motif_suppression}
    r.supprimee_le = None
    r.supprimee_par_id = None
    r.motif_suppression = None
    r.revision += 1
    r.updated_by_id = s.user_id
    db.add(_evenement(r, s, "RESTAURATION", statut_avant=r.statut, etape_avant=r.etape, commentaire=motif,
                      donnees={"supprimee_le": avant["supprimee_le"]}))
    await db.flush()
    await auditer(db, s, "reclamations.restauration", C.GED_ENTITE, r.id, before=avant, after={"motif": motif})
    return r
