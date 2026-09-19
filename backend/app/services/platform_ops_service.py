"""État des modules, maintenance, versions, supervision légère."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.models import User
from app.models.enums import TypeNotification
from app.models.plateforme import PlateformeEspace, PlateformeModule
from app.models.platform_ops import PlatformBackup, PlatformModuleVersion, PlatformOpsFlag
from app.services.audit_helpers import record_audit
from app.services.notification_service import NotificationService
from app.services.platform_backup_service import backup_root, upload_root

MODULE_STATUTS = frozenset(
    {
        "actif",
        "developpement",
        "mise_a_jour",
        "maintenance",
        "suspendu",
        "bloque",
        "bientot",
        "archive",
        "inactif",
    }
)

# Accès métier Login 2 autorisé uniquement si actif (sauf bypass admin).
LOGIN_ALLOWED_STATUTS = frozenset({"actif"})

# Messages par défaut si status_message vide.
DEFAULT_STATUS_MESSAGES = {
    "developpement": "Ce module est actuellement en cours de développement.",
    "mise_a_jour": "Une mise à jour technique est en cours. Réessayez ultérieurement.",
    "maintenance": "Une intervention technique est en cours sur ce module.",
    "suspendu": "Ce module est temporairement suspendu.",
    "bloque": "L'accès à ce module est bloqué.",
    "bientot": "Ce module sera bientôt disponible.",
    "archive": "Ce module est archivé.",
    "inactif": "Ce module est inactif.",
}

PROTECTED_MODULE_STATUTS = frozenset({"actif", "maintenance", "mise_a_jour"})
GLOBAL_MAINT_KEY = "global_maintenance"


class PlatformOpsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def supervision(self) -> dict:
        settings = get_settings()
        db_ok = True
        try:
            await self.db.execute(text("SELECT 1"))
        except Exception:  # noqa: BLE001
            db_ok = False

        modules = (
            await self.db.execute(
                select(PlateformeModule)
                .options(selectinload(PlateformeModule.espace))
                .order_by(PlateformeModule.sort_order, PlateformeModule.label)
            )
        ).scalars().all()
        espaces = (
            await self.db.execute(
                select(PlateformeEspace).order_by(PlateformeEspace.sort_order, PlateformeEspace.label)
            )
        ).scalars().all()

        last_backup = (
            await self.db.execute(
                select(PlatformBackup)
                .where(PlatformBackup.status == "success")
                .order_by(PlatformBackup.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        last_failed = (
            await self.db.execute(
                select(PlatformBackup)
                .where(PlatformBackup.status == "failed")
                .order_by(PlatformBackup.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        upload_ok = upload_root().exists()
        backup_ok = backup_root().exists() and (last_failed is None or (
            last_backup is not None
            and last_backup.created_at
            and last_failed.created_at
            and last_backup.created_at >= last_failed.created_at
        ))

        global_flag = await self.get_global_maintenance()
        modules_ok = all(m.statut in {"actif", "bientot", "developpement"} or not m.is_active for m in modules if m.is_active)
        # modules ops: KO if any active module in maintenance/bloque without planned end overdue ignored
        blocked = [m for m in modules if m.is_active and m.statut in {"maintenance", "mise_a_jour", "bloque", "suspendu"}]

        by_espace: list[dict] = []
        for espace in espaces:
            emods = [m for m in modules if m.espace_id == espace.id]
            attention = espace.statut == "maintenance" or any(
                m.statut in {"maintenance", "mise_a_jour", "bloque", "suspendu"} for m in emods
            )
            by_espace.append(
                {
                    "code": espace.code,
                    "label": espace.label,
                    "statut": espace.statut,
                    "ok": not attention and espace.is_active,
                    "attention": attention,
                    "modules": [
                        {
                            "code": m.code,
                            "label": m.label,
                            "statut": m.statut,
                            "version": m.version,
                            "status_message": m.status_message,
                            "ok": m.statut in {"actif", "bientot", "developpement"},
                        }
                        for m in emods
                    ],
                }
            )

        statut_counts: dict[str, int] = {}
        for m in modules:
            statut_counts[m.statut] = statut_counts.get(m.statut, 0) + 1

        return {
            "application": {"ok": True, "label": "Application"},
            "api": {"ok": True, "label": "API"},
            "database": {"ok": db_ok, "label": "Base de données"},
            "authentication": {"ok": True, "label": "Authentification"},
            "storage": {"ok": upload_ok, "label": "Storage"},
            "modules": {
                "ok": len(blocked) == 0 and modules_ok,
                "label": "Modules",
                "en_alerte": len(blocked),
            },
            "backup": {
                "ok": backup_ok,
                "label": "Backup",
                "dernier": {
                    "id": str(last_backup.id),
                    "created_at": last_backup.created_at.isoformat() if last_backup.created_at else None,
                    "status": last_backup.status,
                    "level": last_backup.level,
                }
                if last_backup
                else None,
            },
            "global_maintenance": global_flag,
            "departements": by_espace,
            "modules_par_statut": statut_counts,
            "app_env": settings.app_env,
        }

    async def list_module_states(self) -> list[dict]:
        rows = (
            await self.db.execute(
                select(PlateformeModule)
                .options(selectinload(PlateformeModule.espace))
                .order_by(PlateformeModule.sort_order, PlateformeModule.label)
            )
        ).scalars().all()
        return [self._serialize_module(m) for m in rows]

    async def update_module_status(
        self,
        module_id: uuid.UUID,
        *,
        user: User,
        statut: str,
        status_message: str | None = None,
        maintenance_starts_at: datetime | None = None,
        maintenance_ends_at: datetime | None = None,
        admins_bypass_maintenance: bool | None = None,
        notify: bool = True,
        request: Request | None = None,
    ) -> dict:
        if statut not in MODULE_STATUTS:
            raise HTTPException(status_code=400, detail="Statut module invalide")
        row = await self.db.get(PlateformeModule, module_id, options=[selectinload(PlateformeModule.espace)])
        if row is None:
            raise HTTPException(status_code=404, detail="Module introuvable")
        from app.data.plateforme_catalogue import DEFAULT_MODULE_CODE

        if row.code == DEFAULT_MODULE_CODE and statut not in PROTECTED_MODULE_STATUTS | {"actif"}:
            # Immobilisations : autoriser maintenance / mise à jour, pas archive/inactif définitif via cet écran
            if statut in {"archive", "inactif", "bloque"}:
                raise HTTPException(
                    status_code=400,
                    detail="Le module Immobilisations ne peut pas être archivé/bloqué depuis cet écran.",
                )

        before = self._serialize_module(row)
        old = row.statut
        row.statut = statut
        if status_message is not None:
            row.status_message = status_message
        elif not row.status_message and statut in DEFAULT_STATUS_MESSAGES:
            row.status_message = DEFAULT_STATUS_MESSAGES[statut]
        if maintenance_starts_at is not None:
            row.maintenance_starts_at = maintenance_starts_at
        if maintenance_ends_at is not None:
            row.maintenance_ends_at = maintenance_ends_at
        if admins_bypass_maintenance is not None:
            row.admins_bypass_maintenance = admins_bypass_maintenance
        if statut == "inactif":
            row.is_active = False
        elif statut in {"actif", "maintenance", "mise_a_jour", "developpement", "bientot"}:
            row.is_active = True

        await record_audit(
            self.db,
            user=user,
            action="module_status_change",
            entity="plateforme_module",
            entity_id=str(row.id),
            request=request,
            espace_code=row.espace.code if row.espace else None,
            module_code=row.code,
            before=before,
            after=self._serialize_module(row),
        )

        if notify and old != statut and statut in {"maintenance", "mise_a_jour", "actif"}:
            titre = row.label
            if statut in {"maintenance", "mise_a_jour"}:
                msg = row.status_message or DEFAULT_STATUS_MESSAGES.get(statut, "Module indisponible.")
                ntype = TypeNotification.MAINTENANCE
            else:
                msg = "Le module est de nouveau disponible."
                ntype = TypeNotification.SYSTEME
            await NotificationService(self.db).notify_staff(
                role_codes={"administrateur"},
                type_notification=ntype,
                titre=titre,
                message=msg,
                entity="plateforme_module",
                entity_id=str(row.id),
                espace_code=row.espace.code if row.espace else None,
                module_code=row.code,
            )

        await self.db.flush()
        return self._serialize_module(row)

    async def get_global_maintenance(self) -> dict:
        flag = await self.db.get(PlatformOpsFlag, GLOBAL_MAINT_KEY)
        if flag is None:
            return {"enabled": False, "title": "", "message": "", "ends_at": None}
        return {
            "enabled": bool(flag.value.get("enabled")),
            "title": flag.value.get("title") or "",
            "message": flag.value.get("message") or "",
            "ends_at": flag.value.get("ends_at"),
            "admins_bypass": bool(flag.value.get("admins_bypass", True)),
        }

    async def set_global_maintenance(
        self,
        *,
        user: User,
        enabled: bool,
        title: str = "",
        message: str = "",
        ends_at: str | None = None,
        admins_bypass: bool = True,
        request: Request | None = None,
    ) -> dict:
        flag = await self.db.get(PlatformOpsFlag, GLOBAL_MAINT_KEY)
        value = {
            "enabled": enabled,
            "title": title,
            "message": message,
            "ends_at": ends_at,
            "admins_bypass": admins_bypass,
        }
        if flag is None:
            flag = PlatformOpsFlag(key=GLOBAL_MAINT_KEY, value=value)
            self.db.add(flag)
        else:
            flag.value = value
            flag.updated_at = datetime.now(timezone.utc)
        await record_audit(
            self.db,
            user=user,
            action="module_maintenance_enable" if enabled else "module_maintenance_disable",
            entity="platform_ops_flags",
            entity_id=GLOBAL_MAINT_KEY,
            request=request,
            module_code="core",
            after=value,
        )
        await self.db.flush()
        return await self.get_global_maintenance()

    async def list_versions(self, module_id: uuid.UUID) -> list[dict]:
        rows = (
            await self.db.execute(
                select(PlatformModuleVersion)
                .where(PlatformModuleVersion.module_id == module_id)
                .order_by(PlatformModuleVersion.created_at.desc())
            )
        ).scalars().all()
        return [
            {
                "id": str(r.id),
                "module_id": str(r.module_id),
                "version": r.version,
                "notes": r.notes,
                "created_by_id": str(r.created_by_id) if r.created_by_id else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    async def add_version(
        self,
        module_id: uuid.UUID,
        *,
        user: User,
        version: str,
        notes: str = "",
        set_current: bool = True,
        request: Request | None = None,
    ) -> dict:
        module = await self.db.get(PlateformeModule, module_id)
        if module is None:
            raise HTTPException(status_code=404, detail="Module introuvable")
        version = version.strip()
        if not version:
            raise HTTPException(status_code=400, detail="Version requise")
        row = PlatformModuleVersion(
            id=uuid.uuid4(),
            module_id=module_id,
            version=version,
            notes=notes or "",
            created_by_id=user.id,
        )
        self.db.add(row)
        if set_current:
            module.version = version
        await record_audit(
            self.db,
            user=user,
            action="module_version_update",
            entity="plateforme_module",
            entity_id=str(module_id),
            request=request,
            module_code=module.code,
            after={"version": version, "notes": notes},
        )
        await self.db.flush()
        return {
            "id": str(row.id),
            "module_id": str(module_id),
            "version": version,
            "notes": notes,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "current": module.version,
        }

    async def dashboard_ops_kpis(self) -> dict:
        last = (
            await self.db.execute(
                select(PlatformBackup)
                .where(PlatformBackup.status == "success")
                .order_by(PlatformBackup.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        last_manual = (
            await self.db.execute(
                select(PlatformBackup)
                .where(
                    PlatformBackup.backup_type == "manuelle",
                    PlatformBackup.status == "success",
                )
                .order_by(PlatformBackup.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        modules = (await self.db.execute(select(PlateformeModule.statut))).scalars().all()
        counts: dict[str, int] = {}
        for s in modules:
            counts[s] = counts.get(s, 0) + 1
        return {
            "derniere_sauvegarde": last.created_at.isoformat() if last and last.created_at else None,
            "derniere_sauvegarde_ok": last.status == "success" if last else None,
            "derniere_manuelle": last_manual.created_at.isoformat()
            if last_manual and last_manual.created_at
            else None,
            "modules_par_statut": counts,
        }

    @staticmethod
    def module_access_payload(module: PlateformeModule, *, can_bypass: bool) -> dict:
        """Payload pour écran Login 2 / porte d'entrée module."""
        statut = module.statut
        message = module.status_message or DEFAULT_STATUS_MESSAGES.get(statut, "")
        allowed = statut in LOGIN_ALLOWED_STATUTS or (
            can_bypass and module.admins_bypass_maintenance and statut in {"maintenance", "mise_a_jour"}
        )
        return {
            "statut": statut,
            "status_message": message,
            "version": module.version,
            "maintenance_starts_at": module.maintenance_starts_at.isoformat()
            if module.maintenance_starts_at
            else None,
            "maintenance_ends_at": module.maintenance_ends_at.isoformat()
            if module.maintenance_ends_at
            else None,
            "access_allowed": allowed,
            "block_reason": None if allowed else statut,
        }

    @staticmethod
    def _serialize_module(m: PlateformeModule) -> dict:
        return {
            "id": str(m.id),
            "code": m.code,
            "label": m.label,
            "espace_code": m.espace.code if m.espace else None,
            "espace_label": m.espace.label if m.espace else None,
            "statut": m.statut,
            "status_message": m.status_message,
            "version": m.version,
            "is_active": m.is_active,
            "maintenance_starts_at": m.maintenance_starts_at.isoformat()
            if m.maintenance_starts_at
            else None,
            "maintenance_ends_at": m.maintenance_ends_at.isoformat()
            if m.maintenance_ends_at
            else None,
            "admins_bypass_maintenance": m.admins_bypass_maintenance,
        }
