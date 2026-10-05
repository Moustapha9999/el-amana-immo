"""Pièces KYC des dossiers EER, stockées dans la GED CORE et cloisonnées au module.

Dépôt, téléchargement et retrait passent uniquement par l'API EER (permissions
``eer.document.*`` + périmètre agence du dossier). Les routes génériques ``/ged/*`` et la
recherche documentaire refusent le module ``eer`` (voir ``MODULES_CLOISONNES``).
Pas d'OCR : le texte des pièces d'identité ne doit pas alimenter l'index plein texte.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select

from app.models import EerChecklistItem, EerChecklistRegle, EerDossier, GedDocument
from app.services.eer.workflow import Statut
from app.services.eer_dossier_service import (
    ESPACE_CODE,
    GED_ENTITE,
    MODULE_CODE,
    Acteur,
    EerDossierService,
    EerErreur,
    EerIntrouvable,
    _maintenant,
)
from app.services.ged_service import GedService

TYPES_DOCUMENT: dict[str, str] = {
    "FICHE_CLIENT": "Fiche client",
    "PIECE_IDENTITE": "Pièce d'identité",
    "SPECIMEN_SIGNATURE": "Spécimen de signature",
    "FICHE_MANDATAIRE": "Fiche client mandataire",
    "MANDAT": "Mandat / procuration",
    "JUSTIFICATIF": "Justificatif",
    "STATUTS": "Statuts / documents société",
    "AUTRE": "Autre pièce",
}

# Dossier décidé ou sorti du circuit : les pièces sont des preuves, on ne les modifie plus.
STATUTS_FIGES = frozenset({Statut.VALIDE, Statut.CLOTURE, Statut.ARCHIVE, Statut.ABANDONNE})


def _exiger_modifiable(d: EerDossier) -> None:
    if d.statut in STATUTS_FIGES:
        raise EerErreur(f"Dossier {d.statut} : les pièces ne sont plus modifiables")


async def documents_du_dossier(svc: EerDossierService, dossier_id: uuid.UUID) -> list[GedDocument]:
    return list((await svc.db.scalars(select(GedDocument).where(
        GedDocument.module_code == MODULE_CODE, GedDocument.entity == GED_ENTITE,
        GedDocument.entity_id == str(dossier_id), GedDocument.deleted_at.is_(None))
        .order_by(GedDocument.created_at))).all())


async def document_du_dossier(svc: EerDossierService, d: EerDossier, document_id: uuid.UUID) -> GedDocument:
    doc = await svc.db.get(GedDocument, document_id)
    if (doc is None or doc.deleted_at is not None or doc.module_code != MODULE_CODE
            or doc.entity != GED_ENTITE or doc.entity_id != str(d.id)):
        raise EerIntrouvable("Document introuvable")
    return doc


async def deposer(svc: EerDossierService, acteur: Acteur, dossier_id: uuid.UUID, fichier: UploadFile, *,
                  doc_type: str | None, item_id: uuid.UUID | None) -> GedDocument:
    """Dépose une pièce ; rattachée à un élément de checklist si ``item_id`` (sans le pointer :
    la présence et la conformité restent du ressort de l'analyste)."""
    acteur.exiger("eer.document.upload")
    d = await svc.charger(dossier_id, verrou=True, acteur=acteur)
    _exiger_modifiable(d)
    item: EerChecklistItem | None = None
    if item_id is not None:
        item = next((i for i in d.items if i.id == item_id), None)
        if item is None:
            raise EerIntrouvable("Élément de checklist introuvable")
        if item.nature != "DOCUMENT":
            raise EerErreur("Seuls les éléments de type document reçoivent une pièce")
        if doc_type is None:
            regle = await svc.db.get(EerChecklistRegle, item.regle_id)
            doc_type = regle.document_type_code if regle else None
    doc_type = doc_type or "AUTRE"
    if doc_type not in TYPES_DOCUMENT:
        raise EerErreur("Type de pièce inconnu")

    doc = await GedService(svc.db).upload(file=fichier, espace_code=ESPACE_CODE, module_code=MODULE_CODE,
                                          entity=GED_ENTITE, entity_id=str(d.id), uploaded_by_id=acteur.user.id)
    doc.doc_type = doc_type
    doc.title = TYPES_DOCUMENT[doc_type]
    doc.reference = d.reference
    doc.agence_id = d.agence_id
    doc.security_level = "restricted"
    doc.ocr_status = "skipped"
    if item is not None:
        item.document_id = doc.id
    await svc.db.flush()
    details = {"document": str(doc.id), "type": doc_type, "item": item.regle_code if item else None}
    await svc._historique(d, acteur, "DOCUMENT_DEPOSE", details=details)
    await svc._audit(acteur, "eer.document.upload", d, after=details)
    return doc


async def retirer(svc: EerDossierService, acteur: Acteur, dossier_id: uuid.UUID, document_id: uuid.UUID,
                  motif: str | None) -> GedDocument:
    """Retrait logique (corbeille GED) ; les éléments de checklist qui la référençaient sont détachés."""
    acteur.exiger("eer.document.upload")
    if not (motif or "").strip():
        raise EerErreur("Motif du retrait obligatoire")
    d = await svc.charger(dossier_id, verrou=True, acteur=acteur)
    _exiger_modifiable(d)
    doc = await document_du_dossier(svc, d, document_id)
    detaches = [i.regle_code for i in d.items if i.document_id == doc.id]
    for i in d.items:
        if i.document_id == doc.id:
            i.document_id = None
    doc.deleted_at = _maintenant()
    doc.is_active = False
    doc.deleted_by_id = acteur.user.id
    doc.delete_reason = motif.strip()[:500]
    await svc.db.flush()
    details = {"document": str(doc.id), "type": doc.doc_type, "items_detaches": detaches}
    await svc._historique(d, acteur, "DOCUMENT_RETIRE", motif=motif, details=details)
    await svc._audit(acteur, "eer.document.delete", d, after=details)
    return doc


async def fichier_a_telecharger(svc: EerDossierService, acteur: Acteur, dossier_id: uuid.UUID,
                                document_id: uuid.UUID) -> tuple[GedDocument, Path]:
    """Chaque consultation d'une pièce KYC est tracée dans l'audit CORE."""
    acteur.exiger("eer.document.download")
    d = await svc.charger(dossier_id, acteur=acteur)
    doc = await document_du_dossier(svc, d, document_id)
    chemin = GedService(svc.db).absolute_path(doc.stored_path)
    if not chemin.exists():
        raise EerIntrouvable("Fichier introuvable sur le serveur")
    await svc._audit(acteur, "eer.document.download", d, after={"document": str(doc.id), "type": doc.doc_type})
    return doc, chemin
