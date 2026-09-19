"""Sauvegardes et recovery CORE ADMIN — dumps PostgreSQL + métadonnées."""

from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.data.module_backup_scopes import (
    merge_scopes,
    modules_for_espace,
    scope_for_module,
)
from app.models import User
from app.models.platform_ops import PlatformBackup, PlatformRestore
from app.services.audit_helpers import record_audit

BACKUP_LEVELS = frozenset({"global", "departement", "module"})
BACKUP_TYPES = frozenset(
    {
        "automatique",
        "manuelle",
        "avant_maintenance",
        "avant_mise_a_jour",
        "avant_migration",
        "securite_recovery",
    }
)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def backup_root() -> Path:
    settings = get_settings()
    raw = Path(settings.backup_dir)
    if raw.is_absolute():
        path = raw
    else:
        # Conteneur Docker : /backups monté ; sinon racine dépôt.
        docker = Path("/backups")
        path = docker if docker.is_dir() else (_project_root() / raw)
    path.mkdir(parents=True, exist_ok=True)
    return path


def upload_root() -> Path:
    settings = get_settings()
    raw = Path(settings.upload_dir)
    if raw.is_absolute():
        return raw
    candidate = Path("/app") / raw
    if candidate.exists() or str(raw).startswith("storage"):
        base = Path("/app") if Path("/app").is_dir() else _project_root()
        return base / raw
    return _project_root() / raw


def _pg_dsn() -> dict[str, str]:
    settings = get_settings()
    url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    parsed = urlparse(url)
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "user": unquote(parsed.username or "immo_user"),
        "password": unquote(parsed.password or ""),
        "dbname": (parsed.path or "/bea_digital").lstrip("/") or "bea_digital",
    }


def _run_pg(cmd: list[str], *, password: str) -> None:
    env = os.environ.copy()
    env["PGPASSWORD"] = password
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "échec pg_dump/pg_restore").strip()
        raise RuntimeError(detail[:2000])


def _copy_uploads(subdir: str | None, dest: Path) -> str | None:
    src_root = upload_root()
    src = src_root / subdir if subdir else src_root
    if not src.exists():
        return None
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    return str(dest)


class PlatformBackupService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def dashboard(self) -> dict:
        total = await self.db.scalar(select(func.count()).select_from(PlatformBackup))
        success = await self.db.scalar(
            select(func.count())
            .select_from(PlatformBackup)
            .where(PlatformBackup.status == "success")
        )
        failed = await self.db.scalar(
            select(func.count())
            .select_from(PlatformBackup)
            .where(PlatformBackup.status == "failed")
        )
        last_global = (
            await self.db.execute(
                select(PlatformBackup)
                .where(
                    PlatformBackup.level == "global",
                    PlatformBackup.status == "success",
                )
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
        last_error = (
            await self.db.execute(
                select(PlatformBackup)
                .where(PlatformBackup.status == "failed")
                .order_by(PlatformBackup.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return {
            "total": int(total or 0),
            "success": int(success or 0),
            "failed": int(failed or 0),
            "derniere_globale": self._serialize(last_global) if last_global else None,
            "derniere_manuelle": self._serialize(last_manual) if last_manual else None,
            "derniere_erreur": self._serialize(last_error) if last_error else None,
        }

    async def list_backups(
        self,
        *,
        page: int,
        size: int,
        level: str | None = None,
        module_code: str | None = None,
        espace_code: str | None = None,
    ) -> tuple[list[dict], int]:
        stmt = select(PlatformBackup).order_by(PlatformBackup.created_at.desc())
        count_stmt = select(func.count()).select_from(PlatformBackup)
        if level:
            stmt = stmt.where(PlatformBackup.level == level)
            count_stmt = count_stmt.where(PlatformBackup.level == level)
        if module_code:
            stmt = stmt.where(PlatformBackup.module_code == module_code)
            count_stmt = count_stmt.where(PlatformBackup.module_code == module_code)
        if espace_code:
            stmt = stmt.where(PlatformBackup.espace_code == espace_code)
            count_stmt = count_stmt.where(PlatformBackup.espace_code == espace_code)
        total = int(await self.db.scalar(count_stmt) or 0)
        rows = (
            await self.db.execute(stmt.offset((page - 1) * size).limit(size))
        ).scalars().all()
        return [self._serialize(r) for r in rows], total

    async def get(self, backup_id: uuid.UUID) -> PlatformBackup | None:
        return await self.db.get(PlatformBackup, backup_id)

    def analyze_dependencies(self, *, level: str, module_code: str | None, espace_code: str | None) -> dict:
        if level == "global":
            return {
                "partial_restore_safe": False,
                "exclusive_tables": [],
                "shared_dependencies": [],
                "warning": (
                    "Une restauration globale remplace l'ensemble de la base BEA-DIGITAL "
                    "(CORE + métiers). Préférer un recovery module si possible."
                ),
            }
        if level == "module":
            scope = scope_for_module(module_code or "")
            if scope is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "code": "BACKUP_SCOPE_UNKNOWN",
                        "message": f"Périmètre backup inconnu pour le module « {module_code} ».",
                    },
                )
            return {
                "partial_restore_safe": True,
                "exclusive_tables": scope["exclusive_tables"],
                "shared_dependencies": scope["shared_dependencies"],
                "warning": (
                    "Les tables CORE et référentiels partagés (users, agences, plan comptable, …) "
                    "ne seront pas écrasées. Elles doivent déjà être cohérentes avec les données restaurées."
                ),
            }
        codes = modules_for_espace(espace_code or "")
        scope = merge_scopes(codes)
        if scope is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "BACKUP_SCOPE_UNKNOWN",
                    "message": f"Aucun module sauvegardable pour le département « {espace_code} ».",
                },
            )
        return {
            "partial_restore_safe": True,
            "exclusive_tables": scope["exclusive_tables"],
            "shared_dependencies": scope["shared_dependencies"],
            "modules": codes,
            "warning": (
                "Recovery département : seuls les modules connus de ce département sont restaurés. "
                "CORE reste intact."
            ),
        }

    async def create_backup(
        self,
        *,
        user: User,
        level: str,
        backup_type: str = "manuelle",
        espace_code: str | None = None,
        module_code: str | None = None,
        request: Request | None = None,
        label: str | None = None,
    ) -> dict:
        if level not in BACKUP_LEVELS:
            raise HTTPException(status_code=400, detail="Niveau de sauvegarde invalide")
        if backup_type not in BACKUP_TYPES:
            raise HTTPException(status_code=400, detail="Type de sauvegarde invalide")

        tables: list[str] | None = None
        shared: list[str] | None = None
        uploads_subdir: str | None = None
        if level == "module":
            scope = scope_for_module(module_code or "")
            if not scope:
                raise HTTPException(status_code=400, detail="Module non supporté pour backup partiel")
            tables = scope["exclusive_tables"]
            shared = scope["shared_dependencies"]
            uploads_subdir = scope["uploads_subdir"]
            if not espace_code and module_code:
                from app.models.plateforme import PlateformeModule
                from sqlalchemy.orm import selectinload

                mod = (
                    await self.db.execute(
                        select(PlateformeModule)
                        .options(selectinload(PlateformeModule.espace))
                        .where(PlateformeModule.code == module_code)
                    )
                ).scalar_one_or_none()
                if mod and mod.espace:
                    espace_code = mod.espace.code
        elif level == "departement":
            codes = modules_for_espace(espace_code or "")
            scope = merge_scopes(codes)
            if not scope:
                raise HTTPException(status_code=400, detail="Département sans module sauvegardable")
            tables = scope["exclusive_tables"]
            shared = scope["shared_dependencies"]
            uploads_subdir = scope["uploads_subdir"]
            module_code = None

        row = PlatformBackup(
            id=uuid.uuid4(),
            level=level,
            backup_type=backup_type,
            espace_code=espace_code,
            module_code=module_code,
            status="running",
            tables_included=tables,
            shared_dependencies=shared,
            created_by_id=user.id,
            label=label
            or self._default_label(level, espace_code=espace_code, module_code=module_code),
        )
        self.db.add(row)
        await self.db.flush()

        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        root = backup_root()
        dump_name = f"bea-{level}-{stamp}-{str(row.id)[:8]}.dump"
        dump_path = root / dump_name
        uploads_dest = root / f"uploads-{level}-{stamp}-{str(row.id)[:8]}"

        try:
            dsn = _pg_dsn()
            cmd = [
                "pg_dump",
                "-h",
                dsn["host"],
                "-p",
                dsn["port"],
                "-U",
                dsn["user"],
                "-d",
                dsn["dbname"],
                "--format=custom",
                "--no-owner",
                "--no-acl",
                "-f",
                str(dump_path),
            ]
            if tables:
                for table in tables:
                    cmd.extend(["-t", table])
            _run_pg(cmd, password=dsn["password"])
            size = dump_path.stat().st_size if dump_path.exists() else 0
            if size < 64:
                raise RuntimeError("Dump vide ou trop petit")
            uploads_path = _copy_uploads(uploads_subdir if level != "global" else None, uploads_dest)
            row.file_path = str(dump_path)
            row.uploads_path = uploads_path
            row.size_bytes = size
            row.status = "success"
            row.finished_at = datetime.now(timezone.utc)
            row.error_message = None
        except Exception as exc:  # noqa: BLE001 — journaliser l'échec backup
            row.status = "failed"
            row.error_message = str(exc)[:2000]
            row.finished_at = datetime.now(timezone.utc)
            if dump_path.exists():
                dump_path.unlink(missing_ok=True)

        await record_audit(
            self.db,
            user=user,
            action="backup_create" if row.status == "success" else "backup_failed",
            entity="platform_backup",
            entity_id=str(row.id),
            request=request,
            espace_code=espace_code,
            module_code=module_code or "core",
            after=self._serialize(row),
        )
        await self.db.flush()
        if row.status != "success":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "code": "BACKUP_FAILED",
                    "message": row.error_message or "Échec de la sauvegarde",
                    "backup_id": str(row.id),
                },
            )
        return self._serialize(row)

    async def delete_backup(
        self,
        backup_id: uuid.UUID,
        *,
        user: User,
        request: Request | None = None,
    ) -> None:
        row = await self.get(backup_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Sauvegarde introuvable")
        before = self._serialize(row)
        if row.file_path:
            Path(row.file_path).unlink(missing_ok=True)
        if row.uploads_path:
            p = Path(row.uploads_path)
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
        await self.db.delete(row)
        await record_audit(
            self.db,
            user=user,
            action="backup_delete",
            entity="platform_backup",
            entity_id=str(backup_id),
            request=request,
            module_code="core",
            before=before,
        )

    async def restore(
        self,
        backup_id: uuid.UUID,
        *,
        user: User,
        acknowledge_dependencies: bool = False,
        request: Request | None = None,
    ) -> dict:
        backup = await self.get(backup_id)
        if backup is None or backup.status != "success" or not backup.file_path:
            raise HTTPException(status_code=404, detail="Sauvegarde restaurable introuvable")
        if not Path(backup.file_path).exists():
            raise HTTPException(status_code=404, detail="Fichier de sauvegarde manquant sur disque")

        analysis = self.analyze_dependencies(
            level=backup.level,
            module_code=backup.module_code,
            espace_code=backup.espace_code,
        )
        if backup.level != "global" and analysis.get("shared_dependencies") and not acknowledge_dependencies:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "DEPENDENCIES_NOT_ACKNOWLEDGED",
                    "message": analysis["warning"],
                    "shared_dependencies": analysis["shared_dependencies"],
                    "exclusive_tables": analysis["exclusive_tables"],
                },
            )

        restore = PlatformRestore(
            id=uuid.uuid4(),
            backup_id=backup.id,
            level=backup.level,
            espace_code=backup.espace_code,
            module_code=backup.module_code,
            status="running",
            dependency_warning=analysis.get("warning"),
            acknowledged_dependencies=acknowledge_dependencies,
            created_by_id=user.id,
        )
        self.db.add(restore)
        await self.db.flush()

        await record_audit(
            self.db,
            user=user,
            action="recovery_start",
            entity="platform_restore",
            entity_id=str(restore.id),
            request=request,
            espace_code=backup.espace_code,
            module_code=backup.module_code or "core",
            after={"backup_id": str(backup.id)},
        )

        try:
            safety = await self.create_backup(
                user=user,
                level=backup.level,
                backup_type="securite_recovery",
                espace_code=backup.espace_code,
                module_code=backup.module_code,
                request=request,
                label=f"Sécurité avant recovery {backup.id}",
            )
            restore.safety_backup_id = uuid.UUID(safety["id"])
            await self.db.flush()

            if backup.level == "global":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "code": "GLOBAL_RESTORE_MANUAL",
                        "message": (
                            "La restauration globale depuis l'UI est bloquée pour protéger CORE. "
                            "Utilisez scripts/restore-local.ps1 hors production après validation DSI. "
                            "Un backup de sécurité vient d'être créé."
                        ),
                        "safety_backup_id": safety["id"],
                    },
                )

            tables = backup.tables_included or []
            if not tables:
                raise RuntimeError("Aucune table exclusive dans cette sauvegarde")

            dsn = _pg_dsn()
            # TRUNCATE des tables exclusives puis restore data-only
            truncate_sql = "TRUNCATE " + ", ".join(f'"{t}"' for t in tables) + " CASCADE;"
            _run_pg(
                [
                    "psql",
                    "-h",
                    dsn["host"],
                    "-p",
                    dsn["port"],
                    "-U",
                    dsn["user"],
                    "-d",
                    dsn["dbname"],
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-c",
                    truncate_sql,
                ],
                password=dsn["password"],
            )
            restore_cmd = [
                "pg_restore",
                "-h",
                dsn["host"],
                "-p",
                dsn["port"],
                "-U",
                dsn["user"],
                "-d",
                dsn["dbname"],
                "--data-only",
                "--no-owner",
                "--no-acl",
                "--disable-triggers",
            ]
            for table in tables:
                restore_cmd.extend(["-t", table])
            restore_cmd.append(backup.file_path)
            _run_pg(restore_cmd, password=dsn["password"])

            if backup.uploads_path and Path(backup.uploads_path).exists():
                scope = scope_for_module(backup.module_code or "")
                sub = scope["uploads_subdir"] if scope else None
                dest = upload_root() / sub if sub else upload_root()
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(backup.uploads_path, dest)

            restore.status = "success"
            restore.finished_at = datetime.now(timezone.utc)
            action = "recovery_success"
        except HTTPException:
            restore.status = "failed"
            restore.error_message = "GLOBAL_RESTORE_MANUAL"
            restore.finished_at = datetime.now(timezone.utc)
            await record_audit(
                self.db,
                user=user,
                action="recovery_failed",
                entity="platform_restore",
                entity_id=str(restore.id),
                request=request,
                module_code=backup.module_code or "core",
                after=self._serialize_restore(restore),
            )
            raise
        except Exception as exc:  # noqa: BLE001
            restore.status = "failed"
            restore.error_message = str(exc)[:2000]
            restore.finished_at = datetime.now(timezone.utc)
            action = "recovery_failed"
            await record_audit(
                self.db,
                user=user,
                action=action,
                entity="platform_restore",
                entity_id=str(restore.id),
                request=request,
                module_code=backup.module_code or "core",
                after=self._serialize_restore(restore),
            )
            await self.db.flush()
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "RECOVERY_FAILED",
                    "message": restore.error_message,
                    "restore_id": str(restore.id),
                    "safety_backup_id": str(restore.safety_backup_id)
                    if restore.safety_backup_id
                    else None,
                },
            ) from exc

        await record_audit(
            self.db,
            user=user,
            action=action,
            entity="platform_restore",
            entity_id=str(restore.id),
            request=request,
            espace_code=backup.espace_code,
            module_code=backup.module_code or "core",
            after=self._serialize_restore(restore),
        )
        await self.db.flush()
        return self._serialize_restore(restore)

    async def list_restores(self, *, page: int, size: int) -> tuple[list[dict], int]:
        total = int(await self.db.scalar(select(func.count()).select_from(PlatformRestore)) or 0)
        rows = (
            await self.db.execute(
                select(PlatformRestore)
                .order_by(PlatformRestore.created_at.desc())
                .offset((page - 1) * size)
                .limit(size)
            )
        ).scalars().all()
        return [self._serialize_restore(r) for r in rows], total

    @staticmethod
    def _default_label(level: str, *, espace_code: str | None, module_code: str | None) -> str:
        if level == "global":
            return "BEA-DIGITAL (global)"
        if level == "departement":
            return f"Département {espace_code or '?'}"
        return f"Module {module_code or '?'}"

    @staticmethod
    def _serialize(row: PlatformBackup | None) -> dict:
        if row is None:
            return {}
        return {
            "id": str(row.id),
            "level": row.level,
            "backup_type": row.backup_type,
            "espace_code": row.espace_code,
            "module_code": row.module_code,
            "status": row.status,
            "file_path": row.file_path,
            "uploads_path": row.uploads_path,
            "size_bytes": row.size_bytes,
            "tables_included": row.tables_included,
            "shared_dependencies": row.shared_dependencies,
            "error_message": row.error_message,
            "created_by_id": str(row.created_by_id) if row.created_by_id else None,
            "label": row.label,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        }

    @staticmethod
    def _serialize_restore(row: PlatformRestore) -> dict:
        return {
            "id": str(row.id),
            "backup_id": str(row.backup_id),
            "safety_backup_id": str(row.safety_backup_id) if row.safety_backup_id else None,
            "level": row.level,
            "espace_code": row.espace_code,
            "module_code": row.module_code,
            "status": row.status,
            "dependency_warning": row.dependency_warning,
            "acknowledged_dependencies": row.acknowledged_dependencies,
            "error_message": row.error_message,
            "created_by_id": str(row.created_by_id) if row.created_by_id else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        }
