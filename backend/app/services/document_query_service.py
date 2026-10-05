"""Recherche Document Service — métadonnées + FTS OCR, ACL, versions, audit."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.audit import AuditLog
from app.models.auth import User
from app.models.ged import GedDocument
from app.services.ged_service import MODULES_CLOISONNES, est_cloisonne
from app.services.permission_service import load_user_permission_codes, user_has_permission_codes
from app.services.plateforme_access_service import PlateformeAccessService


class DocumentQueryService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.access = PlateformeAccessService(db)

    async def user_espace_codes(self, user: User) -> set[str]:
        if user.is_superuser:
            espaces = await self.access.list_espaces()
            return {e.code for e in espaces}
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
        cloison = GedDocument.module_code.notin_(sorted(MODULES_CLOISONNES))
        if user.is_superuser:
            return [cloison]
        return [
            cloison,
            GedDocument.espace_code.in_(sorted(allowed_espaces)),
        ]

    async def _assert_security_level(self, row: GedDocument, user: User) -> None:
        if user.is_superuser:
            return
        level = (row.security_level or "internal").lower()
        if level == "restricted":
            have = await load_user_permission_codes(self.db, user)
            if not user_has_permission_codes(
                have, "ged.write", "mg.archives.manage", "archives.general.ocr.retry"
            ):
                raise ForbiddenError("Niveau de confidentialité insuffisant (restricted)")

    async def get_accessible(
        self,
        document_id: UUID,
        user: User,
        *,
        require_espaces: set[str] | None = None,
        include_deleted: bool = False,
    ) -> GedDocument:
        filters = [GedDocument.id == document_id]
        if not include_deleted:
            filters.append(GedDocument.deleted_at.is_(None))
        row = await self.db.scalar(select(GedDocument).where(*filters))
        if row is None or est_cloisonne(row.module_code, row.entity):
            raise NotFoundError("Document GED", str(document_id))
        allowed = require_espaces if require_espaces is not None else await self.user_espace_codes(user)
        if not user.is_superuser and row.espace_code not in allowed:
            raise ForbiddenError("Document hors périmètre d'accès")
        await self._assert_security_level(row, user)
        return row

    async def resolve_root(self, row: GedDocument) -> GedDocument:
        current = row
        seen: set[UUID] = set()
        while current.parent_document_id is not None:
            if current.id in seen:
                break
            seen.add(current.id)
            parent = await self.db.get(GedDocument, current.parent_document_id)
            if parent is None:
                break
            current = parent
        return current

    async def list_versions(self, document_id: UUID, user: User) -> list[GedDocument]:
        row = await self.get_accessible(document_id, user)
        root = await self.resolve_root(row)
        rows = list(
            (
                await self.db.scalars(
                    select(GedDocument)
                    .where(
                        GedDocument.deleted_at.is_(None),
                        or_(
                            GedDocument.id == root.id,
                            GedDocument.parent_document_id == root.id,
                        ),
                    )
                    .order_by(GedDocument.version.asc(), GedDocument.created_at.asc())
                )
            ).all()
        )
        return rows

    async def list_relations(self, document_id: UUID, user: User) -> list[GedDocument]:
        """Documents liés = même opération métier (entity/entity_id)."""
        row = await self.get_accessible(document_id, user)
        rows = list(
            (
                await self.db.scalars(
                    select(GedDocument)
                    .where(
                        GedDocument.deleted_at.is_(None),
                        GedDocument.espace_code == row.espace_code,
                        GedDocument.module_code == row.module_code,
                        GedDocument.entity == row.entity,
                        GedDocument.entity_id == row.entity_id,
                        GedDocument.id != row.id,
                    )
                    .order_by(GedDocument.created_at.desc())
                    .limit(100)
                )
            ).all()
        )
        return rows

    async def list_audit(self, document_id: UUID, user: User, *, limit: int = 100) -> list[AuditLog]:
        await self.get_accessible(document_id, user, include_deleted=True)
        rows = list(
            (
                await self.db.scalars(
                    select(AuditLog)
                    .where(
                        AuditLog.entity == "ged_document",
                        AuditLog.entity_id == str(document_id),
                    )
                    .order_by(AuditLog.created_at.desc())
                    .limit(min(max(1, limit), 500))
                )
            ).all()
        )
        return rows

    async def dashboard_stats(
        self,
        user: User,
        *,
        espace_code: str | None = None,
        general: bool = False,
    ) -> dict:
        """KPI + séries pour dashboards archives (données réelles, source unique)."""
        from datetime import datetime, timezone

        allowed = await self.user_espace_codes(user)
        if not allowed and not user.is_superuser:
            return self._empty_dashboard()

        filters = [GedDocument.deleted_at.is_(None)]
        if general:
            if not user.is_superuser:
                filters.append(GedDocument.espace_code.in_(sorted(allowed)))
            if espace_code:
                code = espace_code.strip().lower()
                if not user.is_superuser and code not in allowed:
                    raise ForbiddenError(f"Espace non autorisé: {code}")
                filters.append(GedDocument.espace_code == code)
        else:
            if not espace_code:
                raise ForbiddenError("espace_code requis")
            code = espace_code.strip().lower()
            if not user.is_superuser and code not in allowed:
                raise ForbiddenError(f"Espace non autorisé: {code}")
            filters.append(GedDocument.espace_code == code)

        async def _count(*extra):
            return int(
                await self.db.scalar(
                    select(func.count()).select_from(GedDocument).where(*filters, *extra)
                )
                or 0
            )

        now = datetime.now(timezone.utc)
        total = await _count()
        ce_mois = await _count(
            func.extract("year", GedDocument.created_at) == now.year,
            func.extract("month", GedDocument.created_at) == now.month,
        )
        cette_annee = await _count(func.extract("year", GedDocument.created_at) == now.year)
        ocr_done = await _count(GedDocument.ocr_status == "done")
        ocr_pending = await _count(GedDocument.ocr_status == "pending")
        ocr_processing = await _count(GedDocument.ocr_status == "processing")
        ocr_failed = await _count(GedDocument.ocr_status == "failed")
        ocr_en_cours = ocr_pending + ocr_processing
        a_verifier = ocr_failed

        trash_filters = [GedDocument.deleted_at.is_not(None)]
        if espace_code:
            trash_filters.append(GedDocument.espace_code == espace_code.strip().lower())
        elif not user.is_superuser:
            trash_filters.append(GedDocument.espace_code.in_(sorted(allowed)))
        corbeille = int(
            await self.db.scalar(
                select(func.count()).select_from(GedDocument).where(*trash_filters)
            )
            or 0
        )

        mois_rows = await self.db.execute(
            select(
                func.extract("year", GedDocument.created_at).label("y"),
                func.extract("month", GedDocument.created_at).label("m"),
                func.count().label("n"),
            )
            .where(*filters)
            .group_by("y", "m")
            .order_by("y", "m")
        )
        mois_map = {(int(r.y), int(r.m)): int(r.n) for r in mois_rows}
        # 12 derniers mois (zéros inclus) — évite le "pic" trompeur à 1 point
        par_mois: list[dict] = []
        y, m = now.year, now.month
        for _ in range(12):
            par_mois.append(
                {
                    "year": y,
                    "month": m,
                    "count": mois_map.get((y, m), 0),
                    "label": f"{m:02d}/{y}",
                }
            )
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        par_mois.reverse()

        espace_rows = await self.db.execute(
            select(
                GedDocument.espace_code,
                func.count().label("n"),
                func.count().filter(GedDocument.ocr_status == "done").label("ocr_ok"),
                func.count()
                .filter(GedDocument.ocr_status.in_(("pending", "processing")))
                .label("ocr_run"),
                func.count().filter(GedDocument.ocr_status == "failed").label("ocr_err"),
            )
            .where(*filters)
            .group_by(GedDocument.espace_code)
        )
        espace_labels = {
            "moyens-generaux": "Moyens Généraux",
            "comptabilite": "Comptabilité",
            "rh": "RH",
            "credit": "Crédit",
            "informatique": "Informatique",
            "archives": "Archives",
        }
        par_espace = [
            {
                "espace_code": e or "—",
                "label": espace_labels.get(e or "", e or "—"),
                "count": int(n),
                "ocr_done": int(ok or 0),
                "ocr_en_cours": int(run or 0),
                "a_verifier": int(err or 0),
            }
            for e, n, ok, run, err in espace_rows
        ]
        departements_actifs = len([r for r in par_espace if r["count"] > 0])

        mod_rows = await self.db.execute(
            select(GedDocument.module_code, func.count())
            .where(*filters)
            .group_by(GedDocument.module_code)
            .order_by(func.count().desc())
        )
        module_labels = {
            "achats-appro": "Achats",
            "stock-fournitures": "Stock",
            "notes-frais": "Notes de frais",
            "contrats-echeances": "Contrats",
            "archives-mg": "Archives MG",
            "immobilisations": "Immobilisations",
        }
        par_module = [
            {
                "module_code": mod or "—",
                "label": module_labels.get(mod or "", mod or "—"),
                "count": int(n),
            }
            for mod, n in mod_rows
        ]

        type_expr = func.coalesce(GedDocument.doc_type, GedDocument.entity, "AUTRE")
        type_rows = await self.db.execute(
            select(type_expr, func.count())
            .where(*filters)
            .group_by(type_expr)
            .order_by(func.count().desc())
        )
        par_type = [{"type": t or "—", "count": int(n)} for t, n in type_rows][:20]

        ag_rows = await self.db.execute(
            select(GedDocument.agence_id, func.count())
            .where(*filters, GedDocument.agence_id.is_not(None))
            .group_by(GedDocument.agence_id)
            .order_by(func.count().desc())
            .limit(15)
        )
        par_agence = [
            {"agence_id": str(a), "label": str(a)[:8] + "…", "count": int(n)}
            for a, n in ag_rows
            if a is not None
        ]
        # Enrichir labels agences si table accessible
        if par_agence:
            try:
                from app.models.auth import Agence

                ids = [r["agence_id"] for r in par_agence]
                from uuid import UUID as _UUID

                uuid_ids = [_UUID(i) for i in ids]
                rows = list(
                    (
                        await self.db.scalars(
                            select(Agence).where(Agence.id.in_(uuid_ids))
                        )
                    ).all()
                )
                names = {
                    str(a.id): (a.libelle or a.code or str(a.id)) for a in rows
                }
                for r in par_agence:
                    r["label"] = names.get(r["agence_id"], r["label"])
            except Exception:
                pass

        dossiers_actifs = int(
            await self.db.scalar(
                select(func.count()).select_from(
                    select(
                        GedDocument.module_code,
                        GedDocument.entity,
                        GedDocument.entity_id,
                    )
                    .where(*filters)
                    .distinct()
                    .subquery()
                )
            )
            or 0
        )

        manquants = 0
        if general or (espace_code or "") == "moyens-generaux":
            try:
                from app.services.mg_archives_service import MgArchivesService

                manquants = len(await MgArchivesService(self.db).list_missing(limit=500))
            except Exception:
                manquants = 0

        recent_rows = list(
            (
                await self.db.scalars(
                    select(GedDocument)
                    .where(*filters)
                    .order_by(GedDocument.created_at.desc())
                    .limit(8)
                )
            ).all()
        )

        activity_actions = (
            "document_ingest",
            "document_archive_operation",
            "document_view",
            "document_download",
            "archive_manual",
            "archive_download",
            "archive_view",
            "ocr_done",
            "ocr_failed",
            "ocr_processing",
            "document_version_create",
        )
        act_filters = [
            AuditLog.entity == "ged_document",
            AuditLog.action.in_(activity_actions),
        ]
        if not general and espace_code:
            act_filters.append(AuditLog.espace_code == espace_code.strip().lower())
        elif not user.is_superuser and allowed:
            act_filters.append(AuditLog.espace_code.in_(sorted(allowed)))

        act_rows = await self.db.execute(
            select(
                func.date(AuditLog.created_at).label("d"),
                AuditLog.action,
                func.count().label("n"),
            )
            .where(*act_filters)
            .group_by("d", AuditLog.action)
            .order_by("d")
            .limit(400)
        )
        activity: dict[str, dict[str, int]] = {}
        for r in act_rows:
            day = str(r.d)
            bucket = activity.setdefault(
                day, {"uploads": 0, "views": 0, "downloads": 0, "archives": 0}
            )
            action = r.action or ""
            n = int(r.n)
            if action in (
                "document_ingest",
                "document_archive_operation",
                "archive_manual",
                "document_version_create",
            ):
                bucket["uploads"] += n
                bucket["archives"] += n
            elif action in ("document_view", "archive_view"):
                bucket["views"] += n
            elif action in ("document_download", "archive_download"):
                bucket["downloads"] += n
        activite = [{"date": d, **vals} for d, vals in sorted(activity.items())[-30:]]

        recent_ev = list(
            (
                await self.db.scalars(
                    select(AuditLog)
                    .where(*act_filters)
                    .order_by(AuditLog.created_at.desc())
                    .limit(12)
                )
            ).all()
        )
        action_labels = {
            "document_ingest": "Document ajouté",
            "document_archive_operation": "Document archivé",
            "archive_manual": "Archivage manuel",
            "document_view": "Document consulté",
            "archive_view": "Document consulté",
            "document_download": "Document téléchargé",
            "archive_download": "Document téléchargé",
            "ocr_processing": "OCR lancé",
            "ocr_done": "OCR terminé",
            "ocr_failed": "OCR échoué",
            "document_version_create": "Nouvelle version",
            "document_soft_delete": "Document mis à la corbeille",
            "document_update": "Métadonnées modifiées",
        }
        doc_ids: list[UUID] = []
        for ev in recent_ev:
            if not ev.entity_id:
                continue
            try:
                doc_ids.append(UUID(str(ev.entity_id)))
            except (TypeError, ValueError):
                continue
        name_by_id: dict[str, str] = {}
        if doc_ids:
            named = (
                await self.db.scalars(select(GedDocument).where(GedDocument.id.in_(doc_ids)))
            ).all()
            name_by_id = {
                str(row.id): row.title or row.filename or row.reference or ""
                for row in named
            }
        activite_recente = []
        for ev in recent_ev:
            after = ev.after_data if isinstance(ev.after_data, dict) else {}
            filename = name_by_id.get(str(ev.entity_id or "")) or after.get("filename") or after.get("title")
            activite_recente.append(
                {
                    "id": str(ev.id),
                    "action": ev.action,
                    "label": action_labels.get(ev.action, ev.action),
                    "created_at": ev.created_at.isoformat() if ev.created_at else None,
                    "entity_id": ev.entity_id,
                    "espace_code": ev.espace_code,
                    "module_code": ev.module_code,
                    "filename": filename or None,
                    "after": ev.after_data,
                }
            )

        return {
            "total": total,
            "ce_mois": ce_mois,
            "cette_annee": cette_annee,
            "ocr_done": ocr_done,
            "ocr_pending": ocr_pending,
            "ocr_processing": ocr_processing,
            "ocr_failed": ocr_failed,
            "ocr_en_cours": ocr_en_cours,
            "corbeille": corbeille,
            "manquants": manquants,
            "a_verifier": a_verifier,
            "dossiers_actifs": dossiers_actifs,
            "departements_actifs": departements_actifs,
            "par_mois": par_mois,
            "par_espace": par_espace,
            "par_module": par_module,
            "par_type": par_type,
            "par_agence": par_agence,
            "activite": activite,
            "activite_recente": activite_recente,
            "recents": recent_rows,
            "ocr": {
                "pending": ocr_pending,
                "processing": ocr_processing,
                "done": ocr_done,
                "failed": ocr_failed,
                "en_cours": ocr_en_cours,
            },
        }

    @staticmethod
    def _empty_dashboard() -> dict:
        return {
            "total": 0,
            "ce_mois": 0,
            "cette_annee": 0,
            "ocr_done": 0,
            "ocr_pending": 0,
            "ocr_processing": 0,
            "ocr_failed": 0,
            "ocr_en_cours": 0,
            "corbeille": 0,
            "manquants": 0,
            "a_verifier": 0,
            "dossiers_actifs": 0,
            "departements_actifs": 0,
            "par_mois": [],
            "par_espace": [],
            "par_module": [],
            "par_type": [],
            "par_agence": [],
            "activite": [],
            "activite_recente": [],
            "recents": [],
            "ocr": {
                "pending": 0,
                "processing": 0,
                "done": 0,
                "failed": 0,
                "en_cours": 0,
            },
        }

    async def search(
        self,
        *,
        user: User,
        espace_code: str | None = None,
        espace_codes: list[str] | None = None,
        module_code: str | None = None,
        doc_type: str | None = None,
        entity: str | None = None,
        entity_id: str | None = None,
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
        else:
            if not espace_code:
                raise ForbiddenError("espace_code requis pour la vue département")
            code = espace_code.strip().lower()
            if not user.is_superuser and code not in allowed:
                raise ForbiddenError(f"Espace non autorisé: {code}")
            filters.append(GedDocument.espace_code == code)

        if module_code:
            filters.append(GedDocument.module_code == module_code.strip().lower())
        if entity:
            filters.append(GedDocument.entity == entity.strip())
        if entity_id:
            filters.append(GedDocument.entity_id == entity_id.strip())
        if doc_type:
            val = doc_type.strip().lower()
            filters.append(
                or_(
                    func.lower(GedDocument.doc_type) == val,
                    func.lower(GedDocument.entity) == val,
                )
            )
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

        # Masquer restricted sans droit élevé
        if not user.is_superuser:
            have = await load_user_permission_codes(self.db, user)
            if not user_has_permission_codes(
                have, "ged.write", "mg.archives.manage", "archives.general.ocr.retry"
            ):
                filters.append(
                    or_(
                        GedDocument.security_level.is_(None),
                        GedDocument.security_level != "restricted",
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

    async def _scope_filters(self, user: User, *, general: bool = True) -> list:
        allowed = await self.user_espace_codes(user)
        if not allowed and not user.is_superuser:
            return []
        filters = [GedDocument.deleted_at.is_(None), GedDocument.module_code.notin_(sorted(MODULES_CLOISONNES))]
        if general and not user.is_superuser:
            filters.append(GedDocument.espace_code.in_(sorted(allowed)))
        return filters

    async def list_dossiers(self, user: User, *, limit: int = 200) -> list[dict]:
        filters = await self._scope_filters(user)
        if not filters and not user.is_superuser:
            return []
        rows = await self.db.execute(
            select(
                GedDocument.espace_code,
                GedDocument.module_code,
                GedDocument.entity,
                GedDocument.entity_id,
                func.count().label("n"),
                func.min(GedDocument.reference).label("reference"),
                func.max(GedDocument.created_at).label("updated"),
            )
            .where(*filters)
            .group_by(
                GedDocument.espace_code,
                GedDocument.module_code,
                GedDocument.entity,
                GedDocument.entity_id,
            )
            .order_by(func.max(GedDocument.created_at).desc())
            .limit(limit)
        )
        return [
            {
                "espace_code": e,
                "module_code": m,
                "entity": ent,
                "entity_id": eid,
                "count": int(n),
                "reference": ref,
                "updated_at": upd.isoformat() if upd else None,
            }
            for e, m, ent, eid, n, ref, upd in rows
        ]

    async def list_duplicates(self, user: User, *, limit: int = 50) -> list[dict]:
        """Doublons potentiels : même nom de fichier et même taille. Pas de suppression."""
        filters = await self._scope_filters(user)
        if not filters and not user.is_superuser:
            return []
        grouped = (
            select(
                GedDocument.filename,
                GedDocument.size_bytes,
                func.count().label("n"),
            )
            .where(*filters)
            .group_by(GedDocument.filename, GedDocument.size_bytes)
            .having(func.count() > 1)
            .limit(limit)
            .subquery()
        )
        rows = list(
            (
                await self.db.scalars(
                    select(GedDocument)
                    .join(
                        grouped,
                        and_(
                            GedDocument.filename == grouped.c.filename,
                            GedDocument.size_bytes == grouped.c.size_bytes,
                        ),
                    )
                    .where(*filters)
                    .order_by(GedDocument.filename, GedDocument.created_at.desc())
                )
            ).all()
        )
        buckets: dict[tuple, list] = {}
        for row in rows:
            buckets.setdefault((row.filename, row.size_bytes), []).append(row)
        out = []
        for (name, size), docs in buckets.items():
            out.append(
                {
                    "filename": name,
                    "size_bytes": int(size or 0),
                    "criterion": "nom et taille identiques",
                    "documents": docs,
                }
            )
        return out

    async def list_a_verifier(self, user: User, *, limit: int = 200) -> list[dict]:
        filters = await self._scope_filters(user)
        if not filters and not user.is_superuser:
            return []
        rows = list(
            (
                await self.db.scalars(
                    select(GedDocument)
                    .where(
                        *filters,
                        or_(
                            GedDocument.ocr_status == "failed",
                            GedDocument.reference.is_(None),
                            GedDocument.doc_type.is_(None),
                            GedDocument.title.is_(None),
                        ),
                    )
                    .order_by(GedDocument.created_at.desc())
                    .limit(limit)
                )
            ).all()
        )
        items = []
        for row in rows:
            motifs = []
            if row.ocr_status == "failed":
                motifs.append("OCR incomplet" if not row.ocr_error else "Document illisible")
            if not row.reference:
                motifs.append("Référence inconnue")
            if not row.doc_type:
                motifs.append("Document non classé")
            if not row.title:
                motifs.append("Métadonnées incomplètes")
            items.append({"motifs": motifs, "document": row})
        return items

    async def filter_catalogue(self, user: User) -> dict:
        """Départements et modules du catalogue, types réellement présents en GED."""
        from sqlalchemy.orm import selectinload

        from app.models.plateforme import PlateformeEspace

        allowed = await self.user_espace_codes(user)
        rows = list(
            (
                await self.db.scalars(
                    select(PlateformeEspace)
                    .options(selectinload(PlateformeEspace.modules))
                    .where(PlateformeEspace.is_active.is_(True))
                    .order_by(PlateformeEspace.sort_order, PlateformeEspace.label)
                )
            ).all()
        )
        espaces = []
        for espace in rows:
            if not user.is_superuser and espace.code not in allowed:
                continue
            espaces.append(
                {
                    "code": espace.code,
                    "label": espace.label,
                    "modules": [
                        {"code": mod.code, "label": mod.label}
                        for mod in sorted(espace.modules, key=lambda m: (m.sort_order, m.label))
                        if mod.is_active
                    ],
                }
            )

        filters = await self._scope_filters(user)
        types: list[dict] = []
        if filters or user.is_superuser:
            type_expr = func.coalesce(GedDocument.doc_type, GedDocument.entity)
            res = await self.db.execute(
                select(GedDocument.module_code, GedDocument.espace_code, type_expr)
                .where(*filters, type_expr.is_not(None))
                .group_by(GedDocument.module_code, GedDocument.espace_code, type_expr)
                .order_by(type_expr)
            )
            types = [
                {"module_code": mod or "", "espace_code": esp or "", "type": typ}
                for mod, esp, typ in res
                if typ
            ]
        return {"espaces": espaces, "types": types}
