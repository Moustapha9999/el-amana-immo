"""Suppression définitive d'une réclamation, quel que soit son statut (y compris clôturée ou archivée).

``DELETE FROM reclamations`` dans la transaction de la requête : les tables du dossier suivent par
``ON DELETE CASCADE`` (fiches de traitement, réponses, opérations, appels, métadonnées des pièces,
chronologie). Les pièces GED du dossier (``ged_documents`` du module, rattachées à ce seul dossier)
et ses notifications sont supprimées avec lui ; les fichiers ne sont effacés du disque qu'après le
commit (``effacer_fichiers``). Les autres dossiers qui le citaient (doublon, lien) perdent seulement
ce lien (``SET NULL``). Les opérations ne sont que des références : rien n'est écrit dans ORION.

La trace reste dans ``audit_logs`` (référence, statut, client, opérations, pièces, motif éventuel).
Les dossiers mis à la corbeille avant cette règle restent restaurables ou supprimables.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GedDocument, Notification, Reclamation
from app.services.ged_service import GedService
from app.services.reclamations import constantes as C
from app.services.reclamations import operations as ops
from app.services.reclamations.acces import PERMISSION_SUPPRESSION as PERMISSION
from app.services.reclamations.acces import ReclamationsScope
from app.services.reclamations.dossiers import _evenement, charger
from app.services.reclamations.outils import auditer, conflit, erreur, iso, maintenant, texte_long

__all__ = ["PERMISSION", "effacer_fichiers", "restaurer", "supprimer"]

logger = logging.getLogger(__name__)


def _revision(r: Reclamation, data: dict) -> None:
    if data.get("revision") is not None and data["revision"] != r.revision:
        raise conflit("Le dossier a été modifié entre-temps : rechargez-le", "CONFLIT_REVISION",
                      revision=r.revision)


async def supprimer(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID,
                    data: dict) -> tuple[dict, list[Path]]:
    """Supprime le dossier et retourne les fichiers GED à effacer une fois la transaction validée."""
    s.exiger(PERMISSION)
    r = await charger(db, s, rid, verrou=True, corbeille=True)
    _revision(r, data)
    motif = texte_long(data.get("motif"))
    operations = await ops.lister(db, r.id)
    docs = list((await db.scalars(select(GedDocument).where(
        GedDocument.module_code == C.MODULE_CODE, GedDocument.entity == C.GED_ENTITE,
        GedDocument.entity_id == str(r.id)))).all())
    ged = GedService(db)
    fichiers = [ged.absolute_path(d.stored_path) for d in docs if d.stored_path]
    reference = r.reference

    await auditer(db, s, "reclamations.suppression_definitive", C.GED_ENTITE, r.id, before={
        "reference": reference, "statut": r.statut, "etape": r.etape, "archivee_le": iso(r.archivee_le),
        "client": r.client_nom, "racine": r.client_racine, "objet": r.objet,
        "operations": [{"reference": o.reference, "montant": ops.montant_str(o.montant)} for o in operations],
        "documents": [d.filename for d in docs],
    }, after={"supprimee_le": iso(maintenant()), "motif": motif})

    ids_docs = [d.id for d in docs]
    if ids_docs:
        await db.execute(update(GedDocument).where(GedDocument.parent_document_id.in_(ids_docs),
                                                   GedDocument.id.not_in(ids_docs))
                         .values(parent_document_id=None))
        await db.execute(delete(GedDocument).where(GedDocument.id.in_(ids_docs)))
    await db.execute(delete(Notification).where(
        Notification.module_code == C.MODULE_CODE, Notification.entity == C.GED_ENTITE,
        Notification.entity_id == str(r.id)))
    await db.execute(delete(Reclamation).where(Reclamation.id == r.id))
    db.expunge(r)
    await db.flush()
    return {"id": str(rid), "reference": reference, "operations_supprimees": len(operations),
            "documents_supprimes": len(docs)}, fichiers


def effacer_fichiers(fichiers: list[Path]) -> None:
    for f in fichiers:
        try:
            f.unlink(missing_ok=True)
        except OSError:
            logger.warning("Fichier GED non effacé après suppression d'une réclamation : %s", f.name)


async def restaurer(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, data: dict) -> Reclamation:
    """Dossier mis à la corbeille avant la suppression définitive : remis dans les listes."""
    s.exiger(PERMISSION)
    r = await charger(db, s, rid, verrou=True, corbeille=True)
    if not r.supprimee_le:
        raise conflit("Ce dossier n'est pas supprimé", "NON_SUPPRIME")
    _revision(r, data)
    motif = texte_long(data.get("motif"))
    if not motif:
        raise erreur("Le motif est obligatoire", "MOTIF_OBLIGATOIRE")
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
