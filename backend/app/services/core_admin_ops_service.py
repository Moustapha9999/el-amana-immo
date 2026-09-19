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
        categorie: str | None = None,
        priorite: str | None = None,
        espace_code: str | None = None,
        periode: str | None = None,
        user_id: str | None = None,
    ) -> tuple[list[dict], int, dict]:
        from datetime import datetime, timedelta, timezone

        from app.data.notification_taxonomy import (
            NOTIFICATION_CATEGORIES,
            NOTIFICATION_PRIORITIES,
            categorie_from_type,
            infer_priorite,
        )

        stmt = select(Notification).outerjoin(User, User.id == Notification.user_id)
        # Hors archives par défaut (sauf filtre dédié)
        if statut == "archivees":
            stmt = stmt.where(Notification.archived.is_(True))
        else:
            stmt = stmt.where(Notification.archived.is_(False))
            if statut == "non_lues":
                stmt = stmt.where(Notification.lu.is_(False))
            elif statut == "lues":
                stmt = stmt.where(Notification.lu.is_(True))
        if module_code:
            stmt = stmt.where(Notification.module_code == module_code)
        if espace_code:
            stmt = stmt.where(Notification.espace_code == espace_code)
        if categorie:
            stmt = stmt.where(Notification.categorie == categorie)
        if priorite:
            stmt = stmt.where(Notification.priorite == priorite)
        if user_id:
            try:
                from uuid import UUID as _UUID

                stmt = stmt.where(Notification.user_id == _UUID(user_id))
            except ValueError:
                pass
        if periode and periode != "tous":
            now = datetime.now(timezone.utc)
            if periode == "aujourd_hui":
                start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            elif periode == "7j":
                start = now - timedelta(days=7)
            elif periode == "30j":
                start = now - timedelta(days=30)
            elif periode == "mois":
                start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            else:
                start = None
            if start is not None:
                stmt = stmt.where(Notification.created_at >= start)
        if search and search.strip():
            term = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    Notification.titre.ilike(term),
                    Notification.message.ilike(term),
                    Notification.event_code.ilike(term),
                    Notification.entity.ilike(term),
                    Notification.entity_id.ilike(term),
                    Notification.module_code.ilike(term),
                    Notification.espace_code.ilike(term),
                    Notification.categorie.ilike(term),
                    Notification.destinataire_label.ilike(term),
                    Notification.emetteur_label.ilike(term),
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
            type_code = (
                notif.type_notification.value
                if hasattr(notif.type_notification, "value")
                else str(notif.type_notification)
            )
            cat = getattr(notif, "categorie", None) or categorie_from_type(
                type_code, module_code=notif.module_code
            )
            prio = getattr(notif, "priorite", None) or infer_priorite(notif.titre, notif.message or "")
            dest_label = getattr(notif, "destinataire_label", None) or (
                user.full_name if user and user.full_name else (user.email if user else None)
            )
            items.append(
                {
                    "id": str(notif.id),
                    "user_id": str(notif.user_id),
                    "user_email": user.email if user else None,
                    "user_full_name": user.full_name if user else None,
                    "type_notification": type_code,
                    "titre": notif.titre,
                    "message": notif.message,
                    "lu": bool(notif.lu),
                    "archived": bool(getattr(notif, "archived", False)),
                    "entity": notif.entity,
                    "entity_id": notif.entity_id,
                    "espace_code": notif.espace_code,
                    "module_code": notif.module_code,
                    "categorie": cat,
                    "categorie_label": NOTIFICATION_CATEGORIES.get(cat, cat),
                    "priorite": prio,
                    "priorite_label": NOTIFICATION_PRIORITIES.get(prio, prio),
                    "event_type": getattr(notif, "event_type", None) or type_code,
                    "event_code": getattr(notif, "event_code", None),
                    "emetteur_type": getattr(notif, "emetteur_type", None) or "systeme",
                    "emetteur_label": (
                        (getattr(notif, "emetteur_label", None) or "Système").replace("Syst?me", "Système")
                    ),
                    "destinataire_type": getattr(notif, "destinataire_type", None) or "utilisateur",
                    "destinataire_label": dest_label,
                    "created_at": _iso(notif.created_at),
                }
            )

        base_active = select(Notification).where(Notification.archived.is_(False))
        total_n = await self._count(select(func.count()).select_from(base_active.subquery()))
        non_lues = await self._count(
            select(func.count())
            .select_from(Notification)
            .where(Notification.archived.is_(False), Notification.lu.is_(False))
        )
        alertes = await self._count(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.archived.is_(False),
                Notification.priorite.in_(("attention", "avertissement", "critique")),
            )
        )
        critiques = await self._count(
            select(func.count())
            .select_from(Notification)
            .where(Notification.archived.is_(False), Notification.priorite == "critique")
        )
        return items, total, {
            "total": total_n,
            "non_lues": non_lues,
            "lues": max(0, total_n - non_lues),
            "alertes": alertes,
            "critiques": critiques,
            "systeme": await self._count(
                select(func.count())
                .select_from(Notification)
                .where(Notification.archived.is_(False), Notification.categorie == "systeme")
            ),
            "categories": NOTIFICATION_CATEGORIES,
            "priorites": NOTIFICATION_PRIORITIES,
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
        from app.models.auth import SESSION_KIND_MODULE, SESSION_KIND_PLATFORM
        from app.services.security_policy_service import SecurityPolicyService

        settings = get_settings()
        now = datetime.now(timezone.utc)
        policy = await SecurityPolicyService(self.db).get_policy()
        window = now - timedelta(minutes=int(policy["login_lockout_window_minutes"]))

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
        sessions_platform = await self._count(
            select(func.count())
            .select_from(AuthSession)
            .where(
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
                AuthSession.kind == SESSION_KIND_PLATFORM,
            )
        )
        sessions_module = await self._count(
            select(func.count())
            .select_from(AuthSession)
            .where(
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
                AuthSession.kind == SESSION_KIND_MODULE,
            )
        )

        db_ok = True
        try:
            await self.db.execute(select(1))
        except Exception:
            db_ok = False

        mfa_users = await self._count(
            select(func.count())
            .select_from(User)
            .where(
                User.deleted_at.is_(None),
                User.is_active.is_(True),
                User.totp_enabled.is_(True),
            )
        )

        admins_without = await self._count(
            select(func.count())
            .select_from(User)
            .where(
                User.deleted_at.is_(None),
                User.is_active.is_(True),
                User.is_superuser.is_(True),
                User.totp_enabled.is_(False),
            )
        )

        fail_rows = (
            await self.db.execute(
                select(AuthLoginAttempt.email, func.count().label("n"))
                .where(
                    AuthLoginAttempt.success.is_(False),
                    AuthLoginAttempt.created_at >= window,
                )
                .group_by(AuthLoginAttempt.email)
                .having(func.count() >= int(policy["login_lockout_max_failures"]))
                .order_by(func.count().desc())
                .limit(20)
            )
        ).all()
        comptes_verrouilles = [
            {
                "email": email,
                "echecs": int(n),
                "fenetre_minutes": int(policy["login_lockout_window_minutes"]),
            }
            for email, n in fail_rows
        ]

        upload_ok = Path(settings.upload_dir).exists()
        ged_ok = Path(settings.ged_dir).exists()
        ssl_status = (
            "configure_verifie"
            if settings.database_ssl_enabled and settings.database_ssl_verify
            else "configure"
            if settings.database_ssl_enabled
            else "non_configure"
        )
        secret_status = (
            "a_changer"
            if settings.secret_key in {"change-me", "changeme", "secret"}
            else "configure"
        )

        docs_on = settings.api_docs_enabled
        if docs_on is None:
            docs_on = settings.app_env.lower() in {"development", "dev", "local"} or settings.app_debug

        etat = {
            "auth": {"ok": True, "label": "Authentification"},
            "sessions": {"ok": True, "label": "Sessions"},
            "api": {"ok": True, "label": "API"},
            "audit": {"ok": True, "label": "Audit"},
            "db": {"ok": db_ok, "label": "Base de données"},
            "stockage": {"ok": upload_ok and ged_ok, "label": "Stockage"},
        }

        return {
            "login_lockout_window_minutes": int(policy["login_lockout_window_minutes"]),
            "login_lockout_max_failures": int(policy["login_lockout_max_failures"]),
            "jwt_algorithm": settings.jwt_algorithm,
            "alertes_fenetre": alertes,
            "sessions_actives": sessions,
            "sessions_platform": sessions_platform,
            "sessions_module": sessions_module,
            "access_token_expire_minutes": settings.access_token_expire_minutes,
            "refresh_token_expire_days": settings.refresh_token_expire_days,
            "module_refresh_token_expire_minutes": settings.module_refresh_token_expire_minutes,
            "password_policy": {
                "min_length": int(policy["password_min_length"]),
                "require_uppercase": bool(policy["password_require_uppercase"]),
                "require_lowercase": bool(policy["password_require_lowercase"]),
                "require_digit": bool(policy["password_require_digit"]),
                "require_special": bool(policy["password_require_special"]),
                "hash_algorithm": "bcrypt",
                "history_reuse_current_forbidden": True,
            },
            "mfa_required_for_core_admin": bool(policy["mfa_required_for_core_admin"]),
            "mfa_users_enabled": mfa_users,
            "mfa_admins_without": admins_without,
            "rate_limit_enabled": bool(policy["rate_limit_enabled"]),
            "rate_limit": {
                "login_per_minute": int(policy["rate_limit_login_per_minute"]),
                "api_per_minute": int(policy["rate_limit_api_per_minute"]),
                "sensitive_per_minute": int(policy["rate_limit_sensitive_per_minute"]),
                "password_reset_per_minute": int(policy["rate_limit_password_reset_per_minute"]),
            },
            "security_headers_enabled": bool(settings.security_headers_enabled),
            "api_docs_enabled": bool(docs_on),
            "cors_origins": settings.cors_origin_list,
            "database_ssl": ssl_status,
            "secret_key_status": secret_status,
            "upload_dir_exists": upload_ok,
            "ged_dir_exists": ged_ok,
            "app_env": settings.app_env,
            "app_debug": bool(settings.app_debug),
            "comptes_verrouilles": comptes_verrouilles,
            "etat": etat,
            "fuseau": FUSEAU,
            "verifie_at": now.isoformat(),
            "policy_source": policy.get("source"),
            "policy_updated_at": policy.get("updated_at"),
            "policy_editable": True,
        }

    async def update_security_policy(self, patch: dict) -> dict:
        from app.services.security_policy_service import SecurityPolicyService

        await SecurityPolicyService(self.db).update_policy(patch)
        return await self.security_settings()

    async def security_check(self) -> dict:
        """Contrôle défensif de configuration — pas de scan offensif."""
        from app.services.security_policy_service import get_cached_security_policy

        settings = get_settings()
        pol = get_cached_security_policy()
        now = datetime.now(timezone.utc)
        items: list[dict] = []

        def add(key: str, label: str, status: str, detail: str) -> None:
            items.append({"key": key, "label": label, "status": status, "detail": detail})

        if settings.secret_key in {"change-me", "changeme", "secret"}:
            add("secret", "Clé JWT", "ko", "SECRET_KEY par défaut — à changer avant TEST/PROD.")
        else:
            add("secret", "Clé JWT", "ok", "SECRET_KEY configurée (valeur non affichée).")

        add(
            "lockout",
            "Lockout Login",
            "ok",
            f"{pol['login_lockout_max_failures']} échecs / {pol['login_lockout_window_minutes']} min.",
        )

        if pol.get("mfa_required_for_core_admin"):
            without = await self._count(
                select(func.count())
                .select_from(User)
                .where(
                    User.deleted_at.is_(None),
                    User.is_active.is_(True),
                    User.is_superuser.is_(True),
                    User.totp_enabled.is_(False),
                )
            )
            if without > 0:
                add(
                    "mfa",
                    "MFA administrateurs",
                    "warn",
                    f"Obligatoire — {without} superuser(s) sans MFA.",
                )
            else:
                add("mfa", "MFA administrateurs", "ok", "Obligatoire et respecté (superusers).")
        else:
            add("mfa", "MFA administrateurs", "warn", "Non obligatoire (politique actuelle).")

        if pol.get("rate_limit_enabled"):
            add("rate", "Rate limiting", "ok", "Activé côté API (Login, reset, API, sensible).")
        else:
            add("rate", "Rate limiting", "ko", "Désactivé dans la politique sécurité.")

        if settings.security_headers_enabled:
            add("headers", "En-têtes HTTP", "ok", "Middleware sécurité actif.")
        else:
            add("headers", "En-têtes HTTP", "warn", "SECURITY_HEADERS_ENABLED=false.")

        docs_on = settings.api_docs_enabled
        if docs_on is None:
            docs_on = settings.app_env.lower() in {"development", "dev", "local"} or settings.app_debug
        if docs_on and settings.app_env.lower() not in {"development", "dev", "local"}:
            add("docs", "Documentation API", "warn", "/docs exposé hors développement.")
        else:
            add("docs", "Documentation API", "ok", "Exposée" if docs_on else "Désactivée")

        if settings.app_debug and settings.app_env.lower() not in {"development", "dev", "local"}:
            add("debug", "Mode debug", "ko", "APP_DEBUG=true hors développement.")
        else:
            add("debug", "Mode debug", "ok", f"APP_DEBUG={settings.app_debug}.")

        db_ok = True
        try:
            await self.db.execute(select(1))
        except Exception:
            db_ok = False
        if not db_ok:
            add("db", "Base de données", "ko", "SELECT 1 a échoué.")
        elif settings.database_ssl_enabled:
            add("db", "Base de données", "ok", "Connectée — SSL configuré.")
        else:
            add("db", "Base de données", "warn", "Connectée — SSL non activé (OK en local).")

        upload_ok = Path(settings.upload_dir).exists()
        ged_ok = Path(settings.ged_dir).exists()
        if upload_ok and ged_ok:
            add("storage", "Stockage / GED", "ok", "Dossiers upload et GED présents.")
        else:
            add("storage", "Stockage / GED", "warn", f"upload={upload_ok}, ged={ged_ok}.")

        audit_n = await self._count(select(func.count()).select_from(AuditLog))
        add("audit", "Journal d’audit", "ok", f"{audit_n} événement(s) enregistré(s).")

        sessions = await self._count(
            select(func.count())
            .select_from(AuthSession)
            .where(AuthSession.revoked_at.is_(None), AuthSession.expires_at > now)
        )
        add("sessions", "Sessions actives", "ok", f"{sessions} session(s) valide(s).")

        if int(pol["password_min_length"]) >= 10 and pol.get("password_require_digit"):
            add(
                "password",
                "Politique mots de passe",
                "ok",
                f"Longueur min {pol['password_min_length']} + complexité.",
            )
        else:
            add(
                "password",
                "Politique mots de passe",
                "warn",
                f"Longueur min {pol['password_min_length']} — renforcer la complexité recommandé.",
            )

        ok_c = sum(1 for i in items if i["status"] == "ok")
        warn_c = sum(1 for i in items if i["status"] == "warn")
        ko_c = sum(1 for i in items if i["status"] == "ko")
        return {
            "items": items,
            "ok_count": ok_c,
            "warn_count": warn_c,
            "ko_count": ko_c,
            "verifie_at": now.isoformat(),
            "fuseau": FUSEAU,
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
