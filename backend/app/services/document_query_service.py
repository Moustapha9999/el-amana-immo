"""Recherche Document Service — métadonnées + FTS OCR, ACL espaces."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.auth import User
from app.models.ged import GedDocument
from app.services.plateforme_access_service import PlateformeAccessService


class DocumentQueryService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.access = PlateformeAccessService(db)

    async def user_espace_codes(self, user: User) -> set[str]:
        if user.is_superuser:
            espaces = await self.access.list_espaces()
            return {e.code for e in espaces}
        # Relation users.espaces
        codes = {e.code for e in (user.espaces or [])}
        if codes:
            return codes
        from app.models.plateforme import PlateformeEspace

        result = await self.db.execute(
            select(PlateformeEspace.code).where(
                PlateformeEspace.users.any(User.id == user.id)
            )
        )
        return set(result.scalars().all())

    def _security_filters(self, user: User, allowed_espaces: set[str]):
        """Confidential / restricted : uniquement dans les espaces de l'utilisateur."""
        if user.is_superuser:
            return []
        # public/internal visibles dans les espaces autorisés ;
        # confidential/restricted aussi mais uniquement si espace dans allowed
        return [
            GedDocument.espace_code.in_(sorted(allowed_espaces)),
        ]

    async def get_accessible(
        self, document_id: UUID, user: User, *, require_espaces: set[str] | None = None
    ) -> GedDocument:
        row = await self.db.scalar(
            select(GedDocument).where(
                GedDocument.id == document_id,
                GedDocument.deleted_at.is_(None),
            )
        )
        if row is None:
            raise NotFoundError("Document GED", str(document_id))
        allowed = require_espaces if require_espaces is not None else await self.user_espace_codes(user)
        if not user.is_superuser and row.espace_code not in allowed:
            raise ForbiddenError("Document hors périmètre d'accès")
        if (
            not user.is_superuser
            and row.security_level in ("confidential", "restricted")
            and row.espace_code not in allowed
        ):
            raise ForbiddenError("Niveau de confidentialité insuffisant")
        return row

    async def search(
        self,
        *,
        user: User,
        espace_code: str | None = None,
        espace_codes: list[str] | None = None,
        module_code: str | None = None,
        doc_type: str | None = None,
        agence_id: UUID | None = None,
        fournisseur_id: UUID | None = None,
        department_id: UUID | None = None,
        ocr_status: str | None = None,
        security_level: str | None = None,
        date_debut: date | None = None,
        date_fin: date | None = None,
        q: str | None = None,
        search_ocr: bool = False,
        page: int = 1,
        size: int = 50,
        general: bool = False,
    ) -> tuple[list[GedDocument], int, dict]:
        """Retourne (rows, total, meta). meta.ocr_pending_hint si FTS vide à cause OCR en cours."""
        allowed = await self.user_espace_codes(user)
        if not allowed and not user.is_superuser:
            return [], 0, {"ocr_pending_hint": False}

        filters = [GedDocument.deleted_at.is_(None)]
        filters.extend(self._security_filters(user, allowed))

        if general:
            # Intersection demande utilisateur ∩ espaces autorisés
            if espace_codes:
                wanted = {c.strip().lower() for c in espace_codes if c.strip()}
                scope = wanted & allowed if not user.is_superuser else wanted
                if not scope:
                    return [], 0, {"ocr_pending_hint": False}
                filters.append(GedDocument.espace_code.in_(sorted(scope)))
            elif espace_code:
                code = espace_code.strip().lower()
                if not user.is_superuser and code not in allowed:
                    raise ForbiddenError(f"Espace non autorisé: {code}")
                filters.append(GedDocument.espace_code == code)
            # sinon : tous les espaces autorisés (déjà dans _security_filters)
        else:
            if not espace_code:
                raise ForbiddenError("espace_code requis pour la vue département")
            code = espace_code.strip().lower()
            if not user.is_superuser and code not in allowed:
                raise ForbiddenError(f"Espace non autorisé: {code}")
            filters.append(GedDocument.espace_code == code)

        if module_code:
            filters.append(GedDocument.module_code == module_code.strip().lower())
        if doc_type:
            filters.append(GedDocument.doc_type == doc_type.strip().upper())
        if agence_id:
            filters.append(GedDocument.agence_id == agence_id)
        if fournisseur_id:
            filters.append(GedDocument.fournisseur_id == fournisseur_id)
        if department_id:
            filters.append(GedDocument.department_id == department_id)
        if ocr_status:
            filters.append(GedDocument.ocr_status == ocr_status.strip().lower())
        if security_level:
            filters.append(GedDocument.security_level == security_level.strip().lower())
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

        ocr_pending_hint = False
        if q and q.strip():
            term = q.strip()
            like = f"%{term}%"
            meta_clause = or_(
                GedDocument.filename.ilike(like),
                GedDocument.title.ilike(like),
                GedDocument.reference.ilike(like),
                GedDocument.description.ilike(like),
                GedDocument.doc_type.ilike(like),
                GedDocument.module_code.ilike(like),
                GedDocument.entity.ilike(like),
            )
            if search_ocr:
                # FTS + métadonnées
                ts_query = func.plainto_tsquery("french", term)
                fts_clause = and_(
                    GedDocument.ocr_status == "done",
                    GedDocument.ocr_text_search.op("@@")(ts_query),
                )
                filters.append(or_(meta_clause, fts_clause))
            else:
                filters.append(meta_clause)

        total = int(
            await self.db.scalar(
                select(func.count()).select_from(GedDocument).where(*filters)
            )
            or 0
        )

        if search_ocr and q and q.strip() and total == 0:
            pending_filters = [
                GedDocument.deleted_at.is_(None),
                GedDocument.ocr_status.in_(("pending", "processing")),
            ]
            if not user.is_superuser:
                pending_filters.append(GedDocument.espace_code.in_(sorted(allowed)))
            pending_count = int(
                await self.db.scalar(
                    select(func.count()).select_from(GedDocument).where(*pending_filters)
                )
                or 0
            )
            ocr_pending_hint = pending_count > 0

        page = max(1, page)
        size = min(max(1, size), 200)
        rows = list(
            (
                await self.db.scalars(
                    select(GedDocument)
                    .where(*filters)
                    .order_by(GedDocument.created_at.desc())
                    .offset((page - 1) * size)
                    .limit(size)
                )
            ).all()
        )
        return rows, total, {"ocr_pending_hint": ocr_pending_hint}
