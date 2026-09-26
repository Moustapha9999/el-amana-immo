"""Archives MG — registre documentaire sur ged_documents (espace moyens-generaux)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import and_, extract, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import User
from app.models.ged import GedDocument
from app.models.mg_ops import MgBonCommande, MgContrat, MgNoteFrais
from app.models.mg_stock import MgInventaire
from app.schemas.mg_archives import (
    ArchiveDashboardOut,
    ArchiveDocOut,
    ArchiveDocUpdate,
    ArchiveMissingItem,
)
from app.services.ged_service import GedService

ESPACE = "moyens-generaux"
MODULE_LABELS = {
    "achats-appro": "Achats",
    "stock-fournitures": "Stock",
    "notes-frais": "Notes de frais",
    "contrats-echeances": "Contrats",
}


def _doc_out(row: GedDocument) -> ArchiveDocOut:
    return ArchiveDocOut(
        id=row.id,
        filename=row.filename,
        original_name=row.filename,
        title=row.title,
        description=row.description,
        doc_type=row.doc_type,
        reference=row.reference,
        module_code=row.module_code,
        espace_code=row.espace_code,
        entity=row.entity,
        entity_id=row.entity_id,
        date_document=row.date_document,
        archived_at=row.archived_at,
        created_at=row.created_at,
        mime_type=row.mime_type,
        size_bytes=row.size_bytes or 0,
        version=row.version or 1,
        parent_document_id=row.parent_document_id,
        agence_id=row.agence_id,
        department_id=row.department_id,
        fournisseur_id=row.fournisseur_id,
        uploaded_by_id=row.uploaded_by_id,
        deleted_at=row.deleted_at,
        delete_reason=row.delete_reason,
    )


class MgArchivesService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.ged = GedService(db)

    def _base_filters(self, *, trash: bool = False):
        filters = [GedDocument.espace_code == ESPACE]
        if trash:
            filters.append(GedDocument.deleted_at.is_not(None))
        else:
            filters.append(GedDocument.deleted_at.is_(None))
        return filters

    async def list_documents(
        self,
        *,
        module_code: str | None = None,
        q: str | None = None,
        doc_type: str | None = None,
        entity: str | None = None,
        agence_id: UUID | None = None,
        fournisseur_id: UUID | None = None,
        department_id: UUID | None = None,
        year: int | None = None,
        date_debut: date | None = None,
        date_fin: date | None = None,
        uploaded_by_id: UUID | None = None,
        mine_only: bool = False,
        recent_days: int | None = None,
        trash: bool = False,
        page: int = 1,
        size: int = 50,
        user: User | None = None,
    ) -> tuple[list[ArchiveDocOut], int]:
        filters = self._base_filters(trash=trash)
        if module_code:
            filters.append(GedDocument.module_code == module_code.strip().lower())
        if doc_type:
            filters.append(GedDocument.doc_type == doc_type.strip().upper())
        if entity:
            filters.append(GedDocument.entity == entity.strip())
        if agence_id:
            filters.append(GedDocument.agence_id == agence_id)
        if fournisseur_id:
            filters.append(GedDocument.fournisseur_id == fournisseur_id)
        if department_id:
            filters.append(GedDocument.department_id == department_id)
        if year:
            filters.append(
                or_(
                    extract("year", GedDocument.date_document) == year,
                    and_(
                        GedDocument.date_document.is_(None),
                        extract("year", GedDocument.created_at) == year,
                    ),
                )
            )
        if date_debut:
            filters.append(
                or_(
                    GedDocument.date_document >= date_debut,
                    and_(
                        GedDocument.date_document.is_(None),
                        func.date(GedDocument.created_at) >= date_debut,
                    ),
                )
            )
        if date_fin:
            filters.append(
                or_(
                    GedDocument.date_document <= date_fin,
                    and_(
                        GedDocument.date_document.is_(None),
                        func.date(GedDocument.created_at) <= date_fin,
                    ),
                )
            )
        if uploaded_by_id:
            filters.append(GedDocument.uploaded_by_id == uploaded_by_id)
        if mine_only and user is not None:
            filters.append(GedDocument.uploaded_by_id == user.id)
        if recent_days:
            horizon = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            # created within N days
            from datetime import timedelta

            filters.append(GedDocument.created_at >= horizon - timedelta(days=recent_days))
        if q and q.strip():
            like = f"%{q.strip()}%"
            filters.append(
                or_(
                    GedDocument.filename.ilike(like),
                    GedDocument.title.ilike(like),
                    GedDocument.reference.ilike(like),
                    GedDocument.description.ilike(like),
                    GedDocument.module_code.ilike(like),
                    GedDocument.entity.ilike(like),
                    GedDocument.doc_type.ilike(like),
                )
            )
        total = int(
            await self.db.scalar(select(func.count()).select_from(GedDocument).where(*filters))
            or 0
        )
        page, size = max(1, page), max(1, min(size, 500))
        stmt = (
            select(GedDocument)
            .where(*filters)
            .order_by(GedDocument.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        rows = list((await self.db.execute(stmt)).scalars().all())
        return [_doc_out(r) for r in rows], total

    async def get_document(self, document_id: UUID, *, include_deleted: bool = False) -> GedDocument:
        filters = [
            GedDocument.id == document_id,
            GedDocument.espace_code == ESPACE,
        ]
        if not include_deleted:
            filters.append(GedDocument.deleted_at.is_(None))
        row = await self.db.scalar(select(GedDocument).where(*filters))
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document introuvable")
        return row

    async def get_document_out(self, document_id: UUID) -> ArchiveDocOut:
        return _doc_out(await self.get_document(document_id, include_deleted=True))

    async def update_document(
        self, document_id: UUID, data: ArchiveDocUpdate, user: User
    ) -> ArchiveDocOut:
        row = await self.get_document(document_id)
        for field in (
            "title",
            "description",
            "doc_type",
            "reference",
            "date_document",
            "agence_id",
            "department_id",
            "fournisseur_id",
        ):
            val = getattr(data, field)
            if val is not None:
                if field == "doc_type" and isinstance(val, str):
                    val = val.strip().upper() or None
                setattr(row, field, val)
        row.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(row)
        return _doc_out(row)

    async def soft_delete(
        self, document_id: UUID, user: User, reason: str | None = None
    ) -> ArchiveDocOut:
        row = await self.get_document(document_id)
        row.deleted_at = datetime.now(timezone.utc)
        row.is_active = False
        row.deleted_by_id = user.id
        row.delete_reason = (reason or "").strip() or None
        await self.db.commit()
        await self.db.refresh(row)
        return _doc_out(row)

    async def restore(self, document_id: UUID, user: User) -> ArchiveDocOut:
        row = await self.get_document(document_id, include_deleted=True)
        if row.deleted_at is None:
            return _doc_out(row)
        row.deleted_at = None
        row.is_active = True
        row.deleted_by_id = None
        row.delete_reason = None
        row.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(row)
        return _doc_out(row)

    async def purge(self, document_id: UUID, user: User) -> None:
        row = await self.get_document(document_id, include_deleted=True)
        path = self.ged.absolute_path(row.stored_path)
        await self.db.delete(row)
        await self.db.commit()
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            pass

    async def upload_manual(
        self,
        *,
        file: UploadFile,
        user: User,
        module_code: str,
        entity: str,
        entity_id: str,
        title: str | None = None,
        description: str | None = None,
        doc_type: str | None = None,
        reference: str | None = None,
        date_document: date | None = None,
        agence_id: UUID | None = None,
        department_id: UUID | None = None,
        fournisseur_id: UUID | None = None,
    ) -> ArchiveDocOut:
        mod = module_code.strip().lower()
        if mod not in MODULE_LABELS:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Module source invalide")
        row = await self.ged.upload(
            file=file,
            espace_code=ESPACE,
            module_code=mod,
            entity=entity.strip(),
            entity_id=entity_id.strip(),
            uploaded_by_id=user.id,
        )
        row.title = (title or row.filename)[:255]
        row.description = description
        row.doc_type = (doc_type or "JUSTIFICATIF").strip().upper()[:80]
        row.reference = (reference or None) and reference.strip()[:120]
        row.date_document = date_document or date.today()
        row.archived_at = datetime.now(timezone.utc)
        row.agence_id = agence_id
        row.department_id = department_id
        row.fournisseur_id = fournisseur_id
        row.version = 1
        await self.db.commit()
        await self.db.refresh(row)
        return _doc_out(row)

    async def dashboard(self) -> ArchiveDashboardOut:
        now = datetime.now(timezone.utc)
        active = self._base_filters(trash=False)

        async def _count(*extra):
            return int(
                await self.db.scalar(
                    select(func.count()).select_from(GedDocument).where(*active, *extra)
                )
                or 0
            )

        total = await _count()
        ce_mois = await _count(
            extract("year", GedDocument.created_at) == now.year,
            extract("month", GedDocument.created_at) == now.month,
        )
        cette_annee = await _count(extract("year", GedDocument.created_at) == now.year)
        achats = await _count(GedDocument.module_code == "achats-appro")
        stock = await _count(GedDocument.module_code == "stock-fournitures")
        notes = await _count(GedDocument.module_code == "notes-frais")
        contrats = await _count(GedDocument.module_code == "contrats-echeances")
        corbeille = int(
            await self.db.scalar(
                select(func.count())
                .select_from(GedDocument)
                .where(*self._base_filters(trash=True))
            )
            or 0
        )
        missing = await self.list_missing(limit=500)
        manquants = len(missing)

        mois_rows = await self.db.execute(
            select(
                extract("year", GedDocument.created_at).label("y"),
                extract("month", GedDocument.created_at).label("m"),
                func.count().label("n"),
            )
            .where(*active)
            .group_by("y", "m")
            .order_by("y", "m")
        )
        par_mois = [
            {"year": int(r.y), "month": int(r.m), "count": int(r.n)} for r in mois_rows
        ]

        mod_rows = await self.db.execute(
            select(GedDocument.module_code, func.count())
            .where(*active)
            .group_by(GedDocument.module_code)
        )
        par_module = [
            {
                "module_code": m,
                "label": MODULE_LABELS.get(m or "", m or "—"),
                "count": int(n),
            }
            for m, n in mod_rows
        ]

        type_rows = await self.db.execute(
            select(func.coalesce(GedDocument.doc_type, GedDocument.entity), func.count())
            .where(*active)
            .group_by(func.coalesce(GedDocument.doc_type, GedDocument.entity))
        )
        par_type = [{"type": t or "—", "count": int(n)} for t, n in type_rows]

        ag_rows = await self.db.execute(
            select(GedDocument.agence_id, func.count())
            .where(*active, GedDocument.agence_id.is_not(None))
            .group_by(GedDocument.agence_id)
        )
        par_agence = [
            {"agence_id": str(a), "count": int(n)} for a, n in ag_rows if a is not None
        ]

        recent_rows = list(
            (
                await self.db.execute(
                    select(GedDocument)
                    .where(*active)
                    .order_by(GedDocument.created_at.desc())
                    .limit(8)
                )
            ).scalars().all()
        )

        return ArchiveDashboardOut(
            total=total,
            ce_mois=ce_mois,
            cette_annee=cette_annee,
            achats=achats,
            stock=stock,
            notes=notes,
            contrats=contrats,
            manquants=manquants,
            corbeille=corbeille,
            par_mois=par_mois[-12:],
            par_module=par_module,
            par_type=par_type[:20],
            par_agence=par_agence[:20],
            recents=[_doc_out(r) for r in recent_rows],
        )

    async def list_missing(self, *, limit: int = 100) -> list[ArchiveMissingItem]:
        items: list[ArchiveMissingItem] = []

        # BC clotures / valides sans piece GED
        bons = list(
            (
                await self.db.execute(
                    select(MgBonCommande)
                    .where(
                        MgBonCommande.deleted_at.is_(None),
                        MgBonCommande.statut.in_(
                            ["VALIDE", "ENVOYE", "PARTIEL", "RECU", "CLOTURE"]
                        ),
                    )
                    .limit(200)
                )
            ).scalars().all()
        )
        for b in bons:
            has = await self.db.scalar(
                select(func.count())
                .select_from(GedDocument)
                .where(
                    GedDocument.espace_code == ESPACE,
                    GedDocument.module_code == "achats-appro",
                    GedDocument.entity == "bon_commande",
                    GedDocument.entity_id == str(b.id),
                    GedDocument.deleted_at.is_(None),
                )
            )
            if not has:
                items.append(
                    ArchiveMissingItem(
                        code="BC_SANS_DOC",
                        label="BC sans document GED",
                        module_code="achats-appro",
                        source_type="bon_commande",
                        source_id=str(b.id),
                        reference=b.reference,
                        detail=f"Statut {b.statut}",
                    )
                )

        notes = list(
            (
                await self.db.execute(
                    select(MgNoteFrais)
                    .where(
                        MgNoteFrais.deleted_at.is_(None),
                        MgNoteFrais.statut.in_(
                            ["VALIDEE", "PAYEE", "CLOTUREE", "ARCHIVEE"]
                        ),
                    )
                    .limit(200)
                )
            ).scalars().all()
        )
        for n in notes:
            has = await self.db.scalar(
                select(func.count())
                .select_from(GedDocument)
                .where(
                    GedDocument.espace_code == ESPACE,
                    GedDocument.module_code == "notes-frais",
                    GedDocument.entity == "note_frais",
                    GedDocument.entity_id == str(n.id),
                    GedDocument.deleted_at.is_(None),
                )
            )
            if not has:
                items.append(
                    ArchiveMissingItem(
                        code="NOTE_SANS_JUSTIFICATIF",
                        label="Note de frais sans justificatif GED",
                        module_code="notes-frais",
                        source_type="note_frais",
                        source_id=str(n.id),
                        reference=getattr(n, "reference", None),
                        detail=f"Statut {n.statut}",
                    )
                )

        contrats = list(
            (
                await self.db.execute(
                    select(MgContrat)
                    .where(
                        MgContrat.deleted_at.is_(None),
                        MgContrat.statut.in_(["ACTIF", "ARCHIVE", "EXPIRE"]),
                    )
                    .limit(200)
                )
            ).scalars().all()
        )
        for c in contrats:
            has = await self.db.scalar(
                select(func.count())
                .select_from(GedDocument)
                .where(
                    GedDocument.espace_code == ESPACE,
                    GedDocument.module_code == "contrats-echeances",
                    GedDocument.entity == "contrat",
                    GedDocument.entity_id == str(c.id),
                    GedDocument.deleted_at.is_(None),
                )
            )
            if not has:
                items.append(
                    ArchiveMissingItem(
                        code="CONTRAT_SANS_DOC",
                        label="Contrat sans document principal",
                        module_code="contrats-echeances",
                        source_type="contrat",
                        source_id=str(c.id),
                        reference=getattr(c, "numero_contrat", None)
                        or getattr(c, "reference", None),
                        detail=f"Statut {c.statut}",
                    )
                )

        inventaires = list(
            (
                await self.db.execute(
                    select(MgInventaire)
                    .where(
                        MgInventaire.deleted_at.is_(None),
                        MgInventaire.statut.in_(["CLOTURE", "VALIDE"]),
                    )
                    .limit(100)
                )
            ).scalars().all()
        )
        for inv in inventaires:
            has = await self.db.scalar(
                select(func.count())
                .select_from(GedDocument)
                .where(
                    GedDocument.espace_code == ESPACE,
                    GedDocument.module_code == "stock-fournitures",
                    GedDocument.entity == "inventaire",
                    GedDocument.entity_id == str(inv.id),
                    GedDocument.deleted_at.is_(None),
                )
            )
            if not has:
                items.append(
                    ArchiveMissingItem(
                        code="INVENTAIRE_SANS_ETAT",
                        label="Inventaire sans état / pièce GED",
                        module_code="stock-fournitures",
                        source_type="inventaire",
                        source_id=str(inv.id),
                        reference=getattr(inv, "reference", None),
                        detail=f"Statut {inv.statut}",
                    )
                )

        return items[:limit]

    async def dossier(
        self, source_module: str, source_type: str, source_id: str
    ) -> dict:
        """Dossier documentaire calcule depuis les relations metier."""
        mod = source_module.strip().lower()
        kind = source_type.strip()
        sid = source_id.strip()
        nodes: list[dict] = [{"module_code": mod, "entity": kind, "entity_id": sid}]

        if mod == "achats-appro" and kind == "bon_commande":
            bon = await self.db.get(MgBonCommande, uuid.UUID(sid))
            if bon:
                if bon.demande_id:
                    nodes.append(
                        {
                            "module_code": "achats-appro",
                            "entity": "achat_demande",
                            "entity_id": str(bon.demande_id),
                        }
                    )
                if getattr(bon, "comparaison_id", None):
                    nodes.append(
                        {
                            "module_code": "achats-appro",
                            "entity": "achat_comparaison",
                            "entity_id": str(bon.comparaison_id),
                        }
                    )
                from app.models.mg_achats import MgAchatFacture, MgAchatPaiement, MgAchatReception

                recs = list(
                    (
                        await self.db.execute(
                            select(MgAchatReception).where(
                                MgAchatReception.bon_id == bon.id,
                                MgAchatReception.deleted_at.is_(None),
                            )
                        )
                    ).scalars().all()
                )
                for r in recs:
                    nodes.append(
                        {
                            "module_code": "achats-appro",
                            "entity": "achat_reception",
                            "entity_id": str(r.id),
                        }
                    )
                facts = list(
                    (
                        await self.db.execute(
                            select(MgAchatFacture).where(
                                MgAchatFacture.bon_id == bon.id,
                                MgAchatFacture.deleted_at.is_(None),
                            )
                        )
                    ).scalars().all()
                )
                for f in facts:
                    nodes.append(
                        {
                            "module_code": "achats-appro",
                            "entity": "achat_facture",
                            "entity_id": str(f.id),
                        }
                    )
                    pays = list(
                        (
                            await self.db.execute(
                                select(MgAchatPaiement).where(
                                    MgAchatPaiement.facture_id == f.id,
                                    MgAchatPaiement.deleted_at.is_(None),
                                )
                            )
                        ).scalars().all()
                    )
                    for p in pays:
                        nodes.append(
                            {
                                "module_code": "achats-appro",
                                "entity": "achat_paiement",
                                "entity_id": str(p.id),
                            }
                        )

        # Collect GED docs for all nodes
        docs: list[ArchiveDocOut] = []
        seen: set[UUID] = set()
        for n in nodes:
            rows = await self.ged.list_for_entity(
                module_code=n["module_code"],
                entity=n["entity"],
                entity_id=n["entity_id"],
            )
            for r in rows:
                if r.espace_code != ESPACE:
                    continue
                if r.id in seen:
                    continue
                seen.add(r.id)
                docs.append(_doc_out(r))

        return {
            "source_module": mod,
            "source_type": kind,
            "source_id": sid,
            "nodes": nodes,
            "documents": docs,
            "count": len(docs),
        }
