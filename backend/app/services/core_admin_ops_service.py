"""CORE ADMIN — activité, alertes, notifications, GED, paramètres (Login 1)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.pagination import page_offset
from app.models import AuditLog, Notification, User
from app.models.auth import AuthLoginAttempt, AuthSession
from app.models.enums import TypeNotification
from app.models.ged import GedDocument
from app.models.plateforme import PlateformeModule
from app.services.core_admin_audit_service import CoreAdminAuditService
from app.services.core_admin_service import FUSEAU, day_bounds_nouakchott, platform_health


def _iso(value) -> str | None:
    return value.isoformat() if value else None


class CoreAdminOpsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _count(self, stmt) -> int:
        return int((await self.db.execute(stmt)).scalar() or 0)

    async def activity(
        self,
        page: int,
        size: int,
        *,
        search: str | None = None,
        module_code: str | None = None,
        hours: int = 48,
    ) -> tuple[list[dict], int, dict]:
        now = datetime.now(timezone.utc)
        since = now - timedelta(hours=max(1, min(hours, 168)))
        start, end = day_bounds_nouakchott(now)
        filters = [AuditLog.created_at >= since]
        if module_code:
            filters.append(AuditLog.module_code == module_code)
        join_user = bool(search and search.strip())
        if join_user:
            term = f"%{search.strip().lower()}%"
            filters.append(
                or_(
                    func.lower(AuditLog.action).like(term),
                    func.lower(AuditLog.entity).like(term),
                    func.lower(User.email).like(term),
                    func.lower(User.full_name).like(term),
                )
            )
        count_stmt = select(func.count()).select_from(AuditLog)
        if join_user:
            count_stmt = count_stmt.outerjoin(User, AuditLog.user_id == User.id)
        total = await self._count(count_stmt.where(*filters))
        stmt = (
            select(AuditLog)
            .options(selectinload(AuditLog.user))
            .where(*filters)
            .order_by(AuditLog.created_at.desc())
            .offset(page_offset(page, size))
            .limit(size)
        )
        if join_user:
            stmt = stmt.outerjoin(User, AuditLog.user_id == User.id)
        rows = list((await self.db.execute(stmt)).scalars().unique().all())
        audit = CoreAdminAuditService(self.db)
        items = [audit.serialize(row) for row in rows]
        derniere_heure = await self._count(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.created_at >= now - timedelta(hours=1))
        )
        aujourd_hui = await self._count(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.created_at >= start, AuditLog.created_at < end)
        )
        modules = await self._count(
            select(func.count(func.distinct(AuditLog.module_code))).where(
                AuditLog.created_at >= since, AuditLog.module_code.is_not(None)
            )
        )
        return items, total, {
            "total": total,
            "derniere_heure": derniere_heure,
            "aujourd_hui": aujourd_hui,
            "modules": modules,
        }

    async def alerts(
        self,
        page: int,
        size: int,
        *,
        search: str | None = None,
        kind: str = "echecs",
    ) -> tuple[list[dict], int, dict, dict]:
        settings = get_settings()
        now = datetime.now(timezone.utc)
        window = now - timedelta(minutes=settings.login_lockout_window_minutes)
        stmt = select(AuthLoginAttempt)
        if kind == "echecs":
            stmt = stmt.where(AuthLoginAttempt.success.is_(False))
        elif kind == "succes":
            stmt = stmt.where(AuthLoginAttempt.success.is_(True))
        elif kind == "fenetre":
            stmt = stmt.where(AuthLoginAttempt.created_at >= window)
        if search and search.strip():
            term = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    AuthLoginAttempt.email.ilike(term),
                    AuthLoginAttempt.ip_address.ilike(term),
                    AuthLoginAttempt.module_code.ilike(term),
                )
            )
        total = await self._count(select(func.count()).select_from(stmt.order_by(None).subquery()))
        result = await self.db.execute(
            stmt.order_by(AuthLoginAttempt.created_at.desc())
            .offset(page_offset(page, size))
            .limit(size)
        )
        rows = list(result.scalars().all())
        items = [
            {
                "id": str(row.id),
                "email": row.email,
                "ip_address": row.ip_address,
                "login_kind": row.login_kind,
                "module_code": row.module_code,
                "success": row.success,
                "created_at": _iso(row.created_at),
            }
            for row in rows
        ]
        echecs = await self._count(
            select(func.count())
            .select_from(AuthLoginAttempt)
            .where(AuthLoginAttempt.success.is_(False), AuthLoginAttempt.created_at >= window)
        )
        succes = await self._count(
            select(func.count())
            .select_from(AuthLoginAttempt)
            .where(AuthLoginAttempt.success.is_(True), AuthLoginAttempt.created_at >= window)
        )
        suspects = await self._count(
            select(func.count(func.distinct(AuthLoginAttempt.email))).where(
                AuthLoginAttempt.success.is_(False), AuthLoginAttempt.created_at >= window
            )
        )
        total_all = await self._count(select(func.count()).select_from(AuthLoginAttempt))
        return (
            items,
            total,
            {
                "total": total_all,
                "echecs_fenetre": echecs,
                "succes_fenetre": succes,
                "emails_suspects": suspects,
            },
            {
                "lockout_window_minutes": settings.login_lockout_window_minutes,
                "lockout_max_failures": settings.login_lockout_max_failures,
            },
        )

    async def notifications(
        self,
        page: int,
        size: int,
        *,
        search: str | None = None,
        statut: str = "tous",
        module_code: str | None = None,
    ) -> tuple[list[dict], int, dict]:
        stmt = select(Notification).outerjoin(User, User.id == Notification.user_id)
        if statut == "non_lues":
            stmt = stmt.where(Notification.lu.is_(False))
        elif statut == "lues":
            stmt = stmt.where(Notification.lu.is_(True))
        if module_code:
            stmt = stmt.where(Notification.module_code == module_code)
        if search and search.strip():
            term = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    Notification.titre.ilike(term),
                    Notification.message.ilike(term),
                    User.email.ilike(term),
                    User.full_name.ilike(term),
                )
            )
        total = await self._count(select(func.count()).select_from(stmt.order_by(None).subquery()))
        result = await self.db.execute(
            stmt.order_by(Notification.created_at.desc()).offset(page_offset(page, size)).limit(size)
        )
        notifs = list(result.scalars().unique().all())
        user_ids = {row.user_id for row in notifs if row.user_id}
        users: dict = {}
        if user_ids:
            loaded = await self.db.execute(select(User).where(User.id.in_(user_ids)))
            users = {row.id: row for row in loaded.scalars().all()}
        items = []
        for notif in notifs:
            user = users.get(notif.user_id)
            items.append(
                {
                    "id": str(notif.id),
                    "user_id": str(notif.user_id),
                    "user_email": user.email if user else None,
                    "user_full_name": user.full_name if user else None,
                    "type_notification": (
                        notif.type_notification.value
                        if hasattr(notif.type_notification, "value")
                        else str(notif.type_notification)
                    ),
                    "titre": notif.titre,
                    "message": notif.message,
                    "lu": bool(notif.lu),
                    "entity": notif.entity,
                    "entity_id": notif.entity_id,
                    "espace_code": notif.espace_code,
                    "module_code": notif.module_code,
                    "created_at": _iso(notif.created_at),
                }
            )
        total_n = await self._count(select(func.count()).select_from(Notification))
        non_lues = await self._count(
            select(func.count()).select_from(Notification).where(Notification.lu.is_(False))
        )
        systeme = await self._count(
            select(func.count())
            .select_from(Notification)
            .where(Notification.type_notification == TypeNotification.SYSTEME)
        )
        return items, total, {
            "total": total_n,
            "non_lues": non_lues,
            "lues": max(0, total_n - non_lues),
            "systeme": systeme,
        }

    async def ged(
        self,
        page: int,
        size: int,
        *,
        search: str | None = None,
        module_code: str | None = None,
    ) -> tuple[list[dict], int, dict]:
        empty_kpis = {"total": 0, "modules": 0, "taille_octets": 0, "reservee": True}
        try:
            stmt = select(GedDocument).where(GedDocument.deleted_at.is_(None))
            if module_code:
                stmt = stmt.where(GedDocument.module_code == module_code)
            if search and search.strip():
                term = f"%{search.strip()}%"
                stmt = stmt.where(
                    or_(
                        GedDocument.filename.ilike(term),
                        GedDocument.entity.ilike(term),
                        GedDocument.module_code.ilike(term),
                        GedDocument.espace_code.ilike(term),
                    )
                )
            total = await self._count(select(func.count()).select_from(stmt.order_by(None).subquery()))
            result = await self.db.execute(
                stmt.order_by(GedDocument.created_at.desc()).offset(page_offset(page, size)).limit(size)
            )
            rows = list(result.scalars().all())
            items = [
                {
                    "id": str(row.id),
                    "espace_code": row.espace_code,
                    "module_code": row.module_code,
                    "entity": row.entity,
                    "entity_id": row.entity_id,
                    "filename": row.filename,
                    "mime_type": row.mime_type,
                    "size_bytes": row.size_bytes or 0,
                    "uploaded_by_id": str(row.uploaded_by_id) if row.uploaded_by_id else None,
                    "created_at": _iso(row.created_at),
                }
                for row in rows
            ]
            total_all = await self._count(
                select(func.count()).select_from(GedDocument).where(GedDocument.deleted_at.is_(None))
            )
            modules = await self._count(
                select(func.count(func.distinct(GedDocument.module_code))).where(
                    GedDocument.deleted_at.is_(None)
                )
            )
            taille = int(
                (
                    await self.db.execute(
                        select(func.coalesce(func.sum(GedDocument.size_bytes), 0)).where(
                            GedDocument.deleted_at.is_(None)
                        )
                    )
                ).scalar()
                or 0
            )
            return items, total, {
                "total": total_all,
                "modules": modules,
                "taille_octets": taille,
                "reservee": True,
            }
        except Exception:
            # Table absente tant que le dump / migration GED n’est pas appliqué.
            await self.db.rollback()
            return [], 0, empty_kpis

    def general_settings(self) -> dict:
        settings = get_settings()
        return {
            "app_name": settings.app_name,
            "app_env": settings.app_env,
            "app_debug": settings.app_debug,
            "api_v1_prefix": settings.api_v1_prefix,
            "fuseau": FUSEAU,
            "cors_origins": settings.cors_origin_list,
            "upload_dir": settings.upload_dir,
            "ged_dir": settings.ged_dir,
            "access_token_expire_minutes": settings.access_token_expire_minutes,
            "refresh_token_expire_days": settings.refresh_token_expire_days,
            "module_refresh_token_expire_minutes": settings.module_refresh_token_expire_minutes,
        }

    async def security_settings(self) -> dict:
        settings = get_settings()
        now = datetime.now(timezone.utc)
        window = now - timedelta(minutes=settings.login_lockout_window_minutes)
        alertes = await self._count(
            select(func.count())
            .select_from(AuthLoginAttempt)
            .where(AuthLoginAttempt.success.is_(False), AuthLoginAttempt.created_at >= window)
        )
        sessions = await self._count(
            select(func.count())
            .select_from(AuthSession)
            .where(AuthSession.revoked_at.is_(None), AuthSession.expires_at > now)
        )
        return {
            "login_lockout_window_minutes": settings.login_lockout_window_minutes,
            "login_lockout_max_failures": settings.login_lockout_max_failures,
            "jwt_algorithm": settings.jwt_algorithm,
            "alertes_fenetre": alertes,
            "sessions_actives": sessions,
        }

    async def maintenance_settings(self) -> dict:
        settings = get_settings()
        now = datetime.now(timezone.utc)
        db_ok = True
        try:
            await self.db.execute(select(1))
        except Exception:
            db_ok = False
        modules_total = await self._count(select(func.count()).select_from(PlateformeModule))
        modules_actifs = await self._count(
            select(func.count())
            .select_from(PlateformeModule)
            .where(PlateformeModule.is_active.is_(True), PlateformeModule.statut == "actif")
        )
        sessions = await self._count(
            select(func.count())
            .select_from(AuthSession)
            .where(AuthSession.revoked_at.is_(None), AuthSession.expires_at > now)
        )
        return {
            "db_ok": db_ok,
            "skip_migrations": os.environ.get("SKIP_MIGRATIONS", "1") == "1",
            "modules_actifs": modules_actifs,
            "modules_total": modules_total,
            "sessions_actives": sessions,
            "upload_dir_exists": Path(settings.upload_dir).exists(),
            "ged_dir_exists": Path(settings.ged_dir).exists(),
            "app_env": settings.app_env,
            "etat": platform_health(db_ok=db_ok, modules_actifs=modules_actifs),
        }
