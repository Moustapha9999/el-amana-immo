"""Pièces d'un dossier : fichiers GED (``ged_documents``, module ``reclamations``) + catégorie métier.

Module cloisonné (``MODULES_CLOISONNES``) : pièces servies uniquement par cette API, selon le
périmètre du dossier ; pas d'OCR (les données client n'alimentent pas l'index plein texte).
Chaque dépôt crée un nouveau document : un original n'est jamais écrasé. Le retrait est logique
(corbeille GED, motif obligatoire) ; le scan original ne se retire que par l'administrateur du
module. Dépôt, consultation, téléchargement et retrait sont audités et tracés dans la chronologie.
"""

from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GedDocument, ReclamationDocument
from app.models.reclamations import CATEGORIES_DOCUMENT
from app.services.ged_service import GedService
from app.services.reclamations import constantes as C
from app.services.reclamations.acces import ReclamationsScope
from app.services.reclamations.dossiers import _evenement, actions, charger
from app.services.reclamations.outils import (
    auditer,
    conflit,
    erreur,
    iso,
    maintenant,
    noms_utilisateurs,
    propre,
    texte_long,
)


def _nature(mime: str | None, nom: str) -> str:
    n = nom.lower()
    if (mime or "").startswith("image/"):
        return "image"
    if n.endswith(".pdf"):
        return "pdf"
    if n.endswith((".xls", ".xlsx", ".csv")):
        return "excel"
    if n.endswith((".doc", ".docx")):
        return "word"
    return "autre"


async def lister(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID) -> dict:
    s.exiger("reclamations.document.view")
    r = await charger(db, s, rid)
    rows = (await db.execute(
        select(GedDocument, ReclamationDocument)
        .outerjoin(ReclamationDocument, ReclamationDocument.document_id == GedDocument.id)
        .where(GedDocument.module_code == C.MODULE_CODE, GedDocument.entity == C.GED_ENTITE,
               GedDocument.entity_id == str(r.id), GedDocument.deleted_at.is_(None))
        .order_by(GedDocument.created_at,
                  case({c: i for i, c in enumerate(C.CATEGORIE_DOCUMENT_LIBELLES)}, value=ReclamationDocument.categorie,
                       else_=len(C.CATEGORIE_DOCUMENT_LIBELLES)),
                  GedDocument.filename))).all()
    noms = await noms_utilisateurs(db, {d.uploaded_by_id for d, _m in rows})
    items = []
    for d, m in rows:
        categorie = m.categorie if m else "AUTRE"
        items.append({
            "id": str(d.id), "titre": d.title, "date_document": iso(d.date_document),
            "filename": d.filename, "mime_type": d.mime_type, "size_bytes": d.size_bytes,
            "nature": _nature(d.mime_type, d.filename), "categorie": categorie,
            "categorie_libelle": C.CATEGORIE_DOCUMENT_LIBELLES.get(categorie, categorie),
            "commentaire": m.commentaire if m else None, "created_at": iso(d.created_at),
            "depose_par": noms.get(d.uploaded_by_id) if d.uploaded_by_id else None,
            "ocr_status": d.ocr_status,
        })
    a = actions(s, r)
    return {"items": items, "actions": {"deposer": a["documents_deposer"], "telecharger": a["documents_telecharger"],
                                        "retirer": a["documents_retirer"]}}


async def deposer(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, fichier: UploadFile, categorie: str,
                  commentaire: str | None, *, titre: str | None = None, date_document: date | None = None) -> dict:
    """Nouvelle pièce (jamais d'écrasement). Une note (``NOTE``) = scan PDF / image, titre obligatoire."""
    s.exiger("reclamations.document.upload")
    if categorie not in CATEGORIES_DOCUMENT:
        raise erreur("Catégorie de document inconnue", "CATEGORIE_INVALIDE")
    titre = propre(titre)
    if categorie == C.CATEGORIE_NOTE:
        if not titre:
            raise erreur("Le titre ou l'objet de la note est obligatoire", "TITRE_OBLIGATOIRE")
        if Path(fichier.filename or "").suffix.lower() not in C.FORMATS_SCAN:
            raise erreur("Une note scannée se joint en PDF ou en image (JPG, PNG, TIFF, WebP)", "FORMAT_NOTE")
    aujourdhui = maintenant().date()
    if date_document and date_document > aujourdhui:
        raise erreur("La date du document ne peut pas être dans le futur", "DATE_FUTURE")
    r = await charger(db, s, rid, verrou=True)
    if r.archivee_le:
        raise conflit("Dossier archivé : aucune pièce ne peut être ajoutée", "DOSSIER_ARCHIVE")
    doc = await GedService(db).upload(file=fichier, espace_code=C.ESPACE_CODE, module_code=C.MODULE_CODE,
                                      entity=C.GED_ENTITE, entity_id=str(r.id), uploaded_by_id=s.user_id)
    doc.doc_type = f"RECLAMATION_{categorie}"
    doc.title = (titre or f"{C.CATEGORIE_DOCUMENT_LIBELLES[categorie]} — {r.reference}")[:255]
    doc.reference = r.reference
    doc.date_document = date_document or aujourdhui
    doc.security_level = "restricted"
    doc.ocr_status = "skipped"
    commentaire = texte_long(commentaire)
    db.add(ReclamationDocument(document_id=doc.id, reclamation_id=r.id, categorie=categorie,
                               commentaire=commentaire, created_by_id=s.user_id))
    db.add(_evenement(r, s, "DOCUMENT_AJOUT", statut_avant=r.statut, etape_avant=r.etape, commentaire=commentaire,
                      donnees={"fichier": doc.filename, "categorie": C.CATEGORIE_DOCUMENT_LIBELLES[categorie],
                               **({"titre": titre} if titre else {})}))
    await db.flush()
    await auditer(db, s, "reclamations.document.upload", C.GED_ENTITE, r.id, after={
        "document_id": str(doc.id), "fichier": doc.filename, "categorie": categorie, "taille": doc.size_bytes,
        "titre": titre, "date_document": iso(doc.date_document)})
    await db.commit()
    return await lister(db, s, rid)


async def _document(db: AsyncSession, rid: uuid.UUID, did: uuid.UUID) -> GedDocument:
    doc = await db.get(GedDocument, did)
    if (doc is None or doc.deleted_at is not None or doc.module_code != C.MODULE_CODE
            or doc.entity != C.GED_ENTITE or doc.entity_id != str(rid)):
        raise erreur("Document introuvable", "NOT_FOUND", 404)
    return doc


async def retirer(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, did: uuid.UUID, motif: str) -> dict:
    s.exiger("reclamations.document.remove")
    motif = texte_long(motif) or ""
    if not motif:
        raise erreur("Motif obligatoire", "MOTIF_OBLIGATOIRE")
    r = await charger(db, s, rid, verrou=True)
    if r.archivee_le:
        raise conflit("Dossier archivé : les pièces sont figées", "DOSSIER_ARCHIVE")
    doc = await _document(db, r.id, did)
    meta = await db.get(ReclamationDocument, doc.id)
    categorie = meta.categorie if meta else "AUTRE"
    if categorie == "ORIGINAL" and not s.peut("reclamations.admin"):
        raise conflit("Le scan original ne peut être retiré que par l'administrateur du module", "ORIGINAL_PROTEGE")
    doc.deleted_at = maintenant()
    doc.is_active = False
    doc.deleted_by_id = s.user_id
    doc.delete_reason = motif[:500]
    db.add(_evenement(r, s, "DOCUMENT_RETRAIT", statut_avant=r.statut, etape_avant=r.etape, commentaire=motif,
                      donnees={"fichier": doc.filename, "categorie": C.CATEGORIE_DOCUMENT_LIBELLES.get(categorie)}))
    await db.flush()
    await auditer(db, s, "reclamations.document.remove", C.GED_ENTITE, r.id,
                  before={"document_id": str(doc.id), "fichier": doc.filename, "categorie": categorie},
                  after={"motif": motif})
    return await lister(db, s, rid)


async def fichier(db: AsyncSession, s: ReclamationsScope, rid: uuid.UUID, did: uuid.UUID, *,
                  apercu: bool = False) -> tuple[GedDocument, Path]:
    s.exiger("reclamations.document.download")
    r = await charger(db, s, rid)
    doc = await _document(db, r.id, did)
    chemin = GedService(db).absolute_path(doc.stored_path)
    if not chemin.exists():
        raise erreur("Fichier introuvable sur le serveur", "NOT_FOUND", 404)
    await auditer(db, s, "reclamations.document.preview" if apercu else "reclamations.document.download",
                  C.GED_ENTITE, r.id, after={"document_id": str(doc.id), "fichier": doc.filename})
    return doc, chemin
