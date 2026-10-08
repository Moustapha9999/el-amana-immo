"""Sauvegardes & Recovery CORE ADMIN — orchestration, périmètres, audit.

Trois niveaux : GLOBAL (base entière + fichiers), DÉPARTEMENT (modules du
département lus dans ``plateforme_modules``), MODULE (tables exclusives + GED du
module). Le travail lourd (pg_dump / psql / fichiers) est dans
``platform_backup_engine`` et tourne hors de la boucle asyncio.

Les étapes (démarrage, échec, succès) sont committées au fil de l'eau : une
sauvegarde ou une restauration en échec reste tracée (``audit_logs`` +
``platform_backups`` / ``platform_restores``) même si la requête se termine en
erreur, et les outils PostgreSQL externes n'attendent jamais un verrou tenu par
la transaction de la requête.
"""

from __future__ import annotations

import asyncio
import shutil
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException, Request
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.request_client import get_client_ip
from app.data.module_backup_scopes import (
    GLOBAL_RESTORE_JOURNAL_TABLES,
    MODULE_BACKUP_SCOPES,
    SECURITY_PLANE_TABLES,
    SHARED_CORE_TABLES,
    ged_codes_for,
    missing_tables,
    modules_for_espace,
    resolve_tables,
    scope_for_module,
)
from app.models import User
from app.models.plateforme import PlateformeEspace
from app.models.platform_ops import PlatformBackup, PlatformRestore
from app.services import platform_backup_engine as engine
from app.services.audit_helpers import record_audit
from app.services.notification_service import NotificationService

# Ré-exports historiques (supervision, hub).
backup_root = engine.backup_root
upload_root = engine.upload_root

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
LEVEL_CODES = {"global": "GLOBAL", "departement": "DEPARTEMENT", "module": "MODULE"}
RESTORABLE_STATUSES = frozenset({"success"})
STALE_RUNNING = timedelta(hours=2)
MIN_REASON_LENGTH = 10


def _error(status_code: int, code: str, message: str, **extra) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message, **extra})


def confirmation_phrase(level: str, espace_code: str | None, module_code: str | None) -> str:
    if level == "global":
        return "RESTAURER GLOBAL"
    if level == "departement":
        return f"RESTAURER {(espace_code or '').upper()}"
    return f"RESTAURER {(module_code or '').upper()}"


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class PlatformBackupService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ——— Référentiels (départements / modules / tables) ———

    async def _existing_tables(self) -> set[str]:
        rows = await self.db.execute(
            text("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public'")
        )
        return {r[0] for r in rows}

    async def _espaces(self) -> list[PlateformeEspace]:
        rows = await self.db.execute(
            select(PlateformeEspace)
            .options(selectinload(PlateformeEspace.modules))
            .order_by(PlateformeEspace.sort_order, PlateformeEspace.label)
        )
        return list(rows.scalars().all())

    async def _labels(self) -> tuple[dict[str, str], dict[str, str]]:
        espaces = await self._espaces()
        esp = {e.code: e.label for e in espaces}
        mods = {m.code: m.label for e in espaces for m in e.modules}
        for code, scope in MODULE_BACKUP_SCOPES.items():
            mods.setdefault(code, scope["label"])
        return esp, mods

    def _module_info(self, code: str, label: str | None, statut: str | None, existing: set[str]) -> dict:
        scope = scope_for_module(code)
        tables = resolve_tables(code, existing)
        ged = ged_codes_for(code)
        uploads = list(scope.get("uploads_subdirs") or []) if scope else []
        return {
            "code": code,
            "label": label or (scope["label"] if scope else code),
            "statut": statut,
            "known": scope is not None,
            "tables": tables,
            "tables_count": len(tables),
            "missing_tables": missing_tables(code, existing),
            "ged_codes": ged,
            "uploads_subdirs": uploads,
            "backupable": bool(tables or ged or uploads),
        }

    async def catalogue(self) -> dict:
        existing = await self._existing_tables()
        espaces = await self._espaces()
        ged_counts = dict(
            (
                await self.db.execute(
                    text(
                        "SELECT module_code, count(*) FROM ged_documents "
                        "WHERE deleted_at IS NULL GROUP BY module_code"
                    )
                )
            ).all()
        )
        items = []
        for esp in espaces:
            modules = []
            for mod in sorted(esp.modules, key=lambda m: (m.sort_order, m.label)):
                info = self._module_info(mod.code, mod.label, mod.statut, existing)
                info["ged_documents"] = sum(int(ged_counts.get(g, 0)) for g in info["ged_codes"])
                modules.append(info)
            items.append(
                {
                    "code": esp.code,
                    "label": esp.label,
                    "statut": esp.statut,
                    "modules": modules,
                    "modules_count": len(modules),
                    "backupable_modules": sum(1 for m in modules if m["backupable"]),
                    "backupable": any(m["backupable"] for m in modules),
                }
            )
        return {
            "departements": items,
            "departements_count": len(items),
            "modules_count": sum(i["modules_count"] for i in items),
        }

    async def resolve_scope(
        self, *, level: str, espace_code: str | None, module_code: str | None
    ) -> dict:
        if level not in BACKUP_LEVELS:
            raise _error(400, "BACKUP_LEVEL_INVALID", "Niveau de sauvegarde invalide.")
        existing = await self._existing_tables()
        espaces = await self._espaces()
        if level == "global":
            return {
                "level": level,
                "espace_code": None,
                "module_code": None,
                "perimetre": "BEA DIGITAL — toutes les données",
                "departements": [e.code for e in espaces],
                "modules": [m.code for e in espaces for m in e.modules],
                "modules_detail": [],
                "tables": None,
                "ged_codes": [],
                "uploads_subdirs": [],
                "backupable": True,
                "warnings": [],
            }

        if level == "module":
            if not module_code:
                raise _error(400, "BACKUP_MODULE_REQUIRED", "Sélectionnez un module.")
            owner, mod = next(
                ((e, m) for e in espaces for m in e.modules if m.code == module_code), (None, None)
            )
            if mod is None and scope_for_module(module_code) is None:
                raise _error(404, "BACKUP_MODULE_UNKNOWN", f"Module « {module_code} » introuvable.")
            if owner is not None:
                if espace_code and owner.code != espace_code:
                    raise _error(
                        400,
                        "BACKUP_MODULE_ESPACE_MISMATCH",
                        f"Le module « {mod.label} » n'appartient pas à ce département.",
                    )
                espace_code = owner.code
            infos = [self._module_info(module_code, mod.label if mod else None, mod.statut if mod else None, existing)]
            perimetre = infos[0]["label"]
        else:
            if not espace_code:
                raise _error(400, "BACKUP_ESPACE_REQUIRED", "Sélectionnez un département.")
            esp = next((e for e in espaces if e.code == espace_code), None)
            if esp is None:
                raise _error(404, "BACKUP_ESPACE_UNKNOWN", f"Département « {espace_code} » introuvable.")
            mods = sorted(esp.modules, key=lambda m: (m.sort_order, m.label))
            pairs = [(m.code, m.label, m.statut) for m in mods] or [
                (c, None, None) for c in modules_for_espace(espace_code)
            ]
            infos = [self._module_info(c, lbl, st, existing) for c, lbl, st in pairs]
            perimetre = esp.label
            module_code = None

        tables: list[str] = []
        ged: list[str] = []
        uploads: list[str] = []
        warnings: list[str] = []
        for info in infos:
            for t in info["tables"]:
                if t not in tables:
                    tables.append(t)
            for g in info["ged_codes"]:
                if g not in ged:
                    ged.append(g)
            for u in info["uploads_subdirs"]:
                if u not in uploads:
                    uploads.append(u)
            if not info["known"]:
                warnings.append(f"Module « {info['label']} » : aucun périmètre de sauvegarde déclaré.")
            elif not info["backupable"]:
                warnings.append(f"Module « {info['label']} » : aucune donnée propre (rien à sauvegarder).")
            if info["missing_tables"]:
                warnings.append(
                    f"Module « {info['label']} » : tables déclarées absentes de la base "
                    f"({', '.join(info['missing_tables'])})."
                )
        return {
            "level": level,
            "espace_code": espace_code,
            "module_code": module_code,
            "perimetre": perimetre,
            "departements": [espace_code] if espace_code else [],
            "modules": [i["code"] for i in infos if i["backupable"]],
            "modules_detail": infos,
            "tables": tables,
            "ged_codes": ged,
            "uploads_subdirs": uploads,
            "backupable": bool(tables or ged or uploads),
            "warnings": warnings,
        }

    def _file_targets(self, scope: dict) -> list[tuple[str, Path]]:
        if scope["level"] == "global":
            return [("uploads", engine.upload_root()), ("ged", engine.ged_root())]
        targets = [(f"uploads/{sub}", engine.upload_root() / sub) for sub in scope["uploads_subdirs"]]
        targets += [(f"ged/{code}", engine.ged_root() / code) for code in scope["ged_codes"]]
        return targets

    async def _ged_columns(self) -> list[str]:
        rows = await self.db.execute(
            text(
                "SELECT a.attname FROM pg_catalog.pg_attribute a "
                "WHERE a.attrelid = 'public.ged_documents'::regclass AND a.attnum > 0 "
                "AND NOT a.attisdropped AND a.attgenerated = '' ORDER BY a.attnum"
            )
        )
        return [r[0] for r in rows]

    async def _row_counts(self, tables: list[str] | None) -> tuple[dict[str, int], bool]:
        if tables is None:
            rows = await self.db.execute(
                text(
                    "SELECT relname, n_live_tup FROM pg_catalog.pg_stat_user_tables "
                    "WHERE schemaname = 'public' ORDER BY relname"
                )
            )
            return {r[0]: int(r[1] or 0) for r in rows}, False
        counts: dict[str, int] = {}
        for table in tables:
            name = engine.safe_ident(table)
            counts[table] = int(await self.db.scalar(text(f'SELECT count(*) FROM public."{name}"')) or 0)
        return counts, True

    async def _ged_rows_count(self, codes: list[str]) -> int:
        if not codes:
            return 0
        return int(
            await self.db.scalar(
                text("SELECT count(*) FROM ged_documents WHERE module_code = ANY(:codes)"),
                {"codes": codes},
            )
            or 0
        )

    async def _estimate_bytes(self, scope: dict) -> int:
        if scope["level"] == "global":
            db_size = int(await self.db.scalar(text("SELECT pg_database_size(current_database())")) or 0)
        elif scope["tables"]:
            db_size = int(
                await self.db.scalar(
                    text(
                        "SELECT COALESCE(SUM(pg_total_relation_size(c.oid)), 0) FROM pg_catalog.pg_class c "
                        "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
                        "WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relname = ANY(:t)"
                    ),
                    {"t": scope["tables"]},
                )
                or 0
            )
        else:
            db_size = 0
        targets = self._file_targets(scope)
        files = await asyncio.to_thread(lambda: sum(engine.dir_stats(p)[1] for _, p in targets))
        return db_size + files

    async def _alembic_revision(self) -> str | None:
        try:
            return await self.db.scalar(text("SELECT version_num FROM alembic_version LIMIT 1"))
        except Exception:  # noqa: BLE001 — base sans Alembic (seed de test)
            return None

    # ——— Sauvegarde ———

    async def preview_backup(
        self, *, user: User, level: str, espace_code: str | None, module_code: str | None
    ) -> dict:
        scope = await self.resolve_scope(level=level, espace_code=espace_code, module_code=module_code)
        counts, exact = await self._row_counts(scope["tables"])
        return {
            "level": level,
            "type": LEVEL_CODES[level],
            "perimetre": scope["perimetre"],
            "espace_code": scope["espace_code"],
            "module_code": scope["module_code"],
            "departements_count": len(scope["departements"]),
            "modules_count": len(scope["modules"]),
            "modules": scope["modules_detail"],
            "tables_count": len(counts),
            "rows_total": sum(counts.values()),
            "rows_exact": exact,
            "ged_documents": await self._ged_rows_count(scope["ged_codes"]),
            "file_targets": [arc for arc, _ in self._file_targets(scope)],
            "estimated_bytes": await self._estimate_bytes(scope),
            "backupable": scope["backupable"],
            "warnings": scope["warnings"],
            "administrateur": {"id": str(user.id), "full_name": user.full_name, "email": user.email},
            "generated_at": datetime.now(timezone.utc).isoformat(),
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
        if backup_type not in BACKUP_TYPES:
            raise _error(400, "BACKUP_TYPE_INVALID", "Type de sauvegarde invalide.")
        scope = await self.resolve_scope(level=level, espace_code=espace_code, module_code=module_code)
        if not scope["backupable"]:
            raise _error(
                400,
                "BACKUP_SCOPE_EMPTY",
                f"Aucune donnée propre à sauvegarder pour « {scope['perimetre']} ».",
                warnings=scope["warnings"],
            )
        espace_code = scope["espace_code"]
        module_code = scope["module_code"]
        counts, exact = await self._row_counts(scope["tables"])
        ged_columns = await self._ged_columns() if scope["ged_codes"] else []
        ged_rows = await self._ged_rows_count(scope["ged_codes"])
        alembic_rev = await self._alembic_revision()
        ip = get_client_ip(request)

        row = PlatformBackup(
            id=uuid.uuid4(),
            level=level,
            backup_type=backup_type,
            espace_code=espace_code,
            module_code=module_code,
            status="running",
            tables_included=scope["tables"] if level != "global" else None,
            shared_dependencies=list(SHARED_CORE_TABLES) if level != "global" else None,
            created_by_id=user.id,
            ip_address=ip,
            label=label or self._default_label(level, scope["perimetre"]),
        )
        self.db.add(row)
        await self.db.commit()

        started = time.monotonic()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        root = engine.backup_root()
        base = root / f"bea-{level}-{stamp}-{str(row.id)[:8]}"
        plan = engine.BackupPlan(
            base=base,
            level=level,
            tables=None if level == "global" else list(scope["tables"]),
            ged_codes=list(scope["ged_codes"]),
            ged_columns=ged_columns,
            file_targets=self._file_targets(scope),
        )
        try:
            artifacts = await asyncio.to_thread(engine.execute_backup, plan, engine.pg_dsn())
            manifest = {
                "format": engine.MANIFEST_FORMAT,
                "backup_id": str(row.id),
                "level": level,
                "type": LEVEL_CODES[level],
                "backup_type": backup_type,
                "label": row.label,
                "perimetre": scope["perimetre"],
                "espace_code": espace_code,
                "module_code": module_code,
                "departements": scope["departements"],
                "modules": scope["modules"],
                "created_at": datetime.now(timezone.utc).isoformat(),
                "created_by": {"id": str(user.id), "email": user.email, "full_name": user.full_name},
                "ip_address": ip,
                "alembic_revision": alembic_rev,
                "app_env": get_settings().app_env,
                "tables": counts,
                "row_counts_exact": exact,
                "ged": {"module_codes": scope["ged_codes"], "columns": ged_columns, "rows": ged_rows},
                "files": {
                    "targets": [arc for arc, _ in plan.file_targets],
                    "files": artifacts.get("files", {}).get("files", 0),
                    "raw_bytes": artifacts.get("files", {}).get("raw_bytes", 0),
                },
                "artifacts": artifacts,
            }
            artifacts["manifest"] = await asyncio.to_thread(engine.write_manifest, base, manifest)
            primary = artifacts.get("dump") or artifacts.get("ged_rows") or artifacts["manifest"]
            row.artifacts = artifacts
            row.manifest = manifest
            row.file_path = str(root / artifacts["dump"]["file"]) if "dump" in artifacts else None
            row.uploads_path = str(root / artifacts["files"]["file"]) if "files" in artifacts else None
            row.size_bytes = sum(int(a.get("bytes", 0)) for a in artifacts.values())
            row.checksum_sha256 = primary["sha256"]
            row.integrity_status = "ok"
            row.integrity_checked_at = datetime.now(timezone.utc)
            row.integrity_detail = "Empreintes calculées à la création"
            row.status = "success"
            row.error_message = None
        except Exception as exc:  # noqa: BLE001 — échec tracé puis renvoyé
            row.status = "failed"
            row.error_message = str(exc)[:2000]
        row.finished_at = datetime.now(timezone.utc)
        row.duration_ms = int((time.monotonic() - started) * 1000)

        await record_audit(
            self.db,
            user=user,
            action="backup_create" if row.status == "success" else "backup_failed",
            entity="platform_backup",
            entity_id=str(row.id),
            request=request,
            espace_code=espace_code,
            module_code=module_code or "core",
            after=self._audit_payload(row),
        )
        await self.db.commit()
        if row.status != "success":
            raise _error(
                500,
                "BACKUP_FAILED",
                f"Échec de la sauvegarde : {row.error_message}",
                backup_id=str(row.id),
            )
        return await self.serialize(row)

    async def delete_backup(self, backup_id: uuid.UUID, *, user: User, request: Request | None = None) -> None:
        row = await self.get(backup_id)
        if row is None:
            raise _error(404, "BACKUP_NOT_FOUND", "Sauvegarde introuvable.")
        if row.status == "running":
            raise _error(409, "BACKUP_RUNNING", "Sauvegarde en cours : attendez la fin avant de la supprimer.")
        running_restore = await self.db.scalar(
            select(func.count()).select_from(PlatformRestore).where(
                PlatformRestore.backup_id == backup_id, PlatformRestore.status == "running"
            )
        )
        if running_restore:
            raise _error(409, "BACKUP_IN_USE", "Une restauration utilise cette sauvegarde en ce moment.")
        before = self._audit_payload(row)
        restores = (
            await self.db.execute(select(PlatformRestore).where(PlatformRestore.backup_id == backup_id))
        ).scalars().all()
        trace = {
            "id": str(row.id),
            "label": row.label,
            "level": row.level,
            "created_at": _iso(row.created_at),
            "deleted_at": _iso(datetime.now(timezone.utc)),
            "deleted_by": str(user.id),
        }
        for restore in restores:
            restore.details = {**(restore.details or {}), "deleted_backup": trace}
            restore.backup_id = None
        await self.db.flush()
        await asyncio.to_thread(
            engine.remove_artifacts, engine.backup_root(), row.artifacts, [row.file_path, row.uploads_path]
        )
        before["restores_linked"] = len(restores)
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

    # ——— Intégrité / téléchargement ———

    async def verify(self, backup_id: uuid.UUID, *, user: User, request: Request | None = None) -> dict:
        row = await self.get(backup_id)
        if row is None:
            raise _error(404, "BACKUP_NOT_FOUND", "Sauvegarde introuvable.")
        if row.status != "success":
            raise _error(400, "BACKUP_NOT_VERIFIABLE", "Seule une sauvegarde réussie peut être vérifiée.")
        checks = await asyncio.to_thread(
            engine.verify_artifacts, engine.backup_root(), row.artifacts, row.file_path
        )
        ok = all(c["ok"] for c in checks)
        row.integrity_status = "ok" if ok else "ko"
        row.integrity_checked_at = datetime.now(timezone.utc)
        row.integrity_detail = "; ".join(f"{c['artifact']}: {c['detail']}" for c in checks)[:4000]
        await record_audit(
            self.db,
            user=user,
            action="backup_verify" if ok else "backup_verify_failed",
            entity="platform_backup",
            entity_id=str(row.id),
            request=request,
            espace_code=row.espace_code,
            module_code=row.module_code or "core",
            after={"integrity_status": row.integrity_status, "checks": checks},
        )
        await self.db.commit()
        return {
            "backup_id": str(row.id),
            "integrity_status": row.integrity_status,
            "checked_at": _iso(row.integrity_checked_at),
            "checks": checks,
        }

    async def prepare_download(
        self, backup_id: uuid.UUID, *, user: User, request: Request | None = None
    ) -> tuple[Path, str, bool]:
        """(chemin, nom de fichier, temporaire ?) — l'appelant supprime le temporaire."""
        row = await self.get(backup_id)
        if row is None or row.status != "success":
            raise _error(404, "BACKUP_NOT_FOUND", "Sauvegarde téléchargeable introuvable.")
        root = engine.backup_root()
        name = f"bea-{row.level}-{row.created_at:%Y%m%d-%H%M%S}-{str(row.id)[:8]}"
        if row.artifacts:
            missing = [a["file"] for a in row.artifacts.values() if not (root / a["file"]).exists()]
            if missing:
                raise _error(404, "BACKUP_FILES_MISSING", f"Fichiers absents du disque : {', '.join(missing)}")
            path = await asyncio.to_thread(engine.build_download_bundle, root, row.artifacts, name)
            filename, temporary = f"{name}.tar", True
        elif row.file_path and Path(row.file_path).exists():
            path, filename, temporary = Path(row.file_path), Path(row.file_path).name, False
        else:
            raise _error(404, "BACKUP_FILES_MISSING", "Fichier de sauvegarde absent du disque.")
        await record_audit(
            self.db,
            user=user,
            action="backup_download",
            entity="platform_backup",
            entity_id=str(row.id),
            request=request,
            espace_code=row.espace_code,
            module_code=row.module_code or "core",
            after={"filename": filename, "checksum_sha256": row.checksum_sha256},
        )
        await self.db.commit()
        return path, filename, temporary

    # ——— Recovery ———

    @staticmethod
    def _restorable(backup: PlatformBackup | None) -> PlatformBackup:
        if backup is None or backup.status not in RESTORABLE_STATUSES or backup.level not in BACKUP_LEVELS:
            raise _error(404, "BACKUP_NOT_RESTORABLE", "Sauvegarde restaurable introuvable.")
        return backup

    async def _restore_plan(self, backup: PlatformBackup, *, include_security: bool) -> tuple[engine.RestorePlan, dict]:
        root = engine.backup_root()
        artifacts = backup.artifacts or {}
        dump: Path | None = None
        if "dump" in artifacts:
            dump = root / artifacts["dump"]["file"]
        elif not artifacts and backup.file_path:
            dump = Path(backup.file_path)
        missing = [a["file"] for a in artifacts.values() if not (root / a["file"]).exists()]
        if dump is not None and not dump.exists():
            missing.append(dump.name)
        if missing:
            raise _error(404, "BACKUP_FILES_MISSING", f"Fichiers absents du disque : {', '.join(sorted(set(missing)))}")

        existing = await self._existing_tables()
        toc = await asyncio.to_thread(engine.read_toc, dump) if dump is not None else []
        dump_tables = {name for _line, kind, name in toc if kind == "TABLE DATA"}
        preserved: set[str] = set()
        if backup.level == "global":
            preserved = set(GLOBAL_RESTORE_JOURNAL_TABLES)
            if not include_security:
                preserved |= set(SECURITY_PLANE_TABLES)
            tables = sorted(t for t in dump_tables if t in existing and t not in preserved)
        else:
            declared = backup.tables_included or []
            tables = [t for t in declared if t in dump_tables and t in existing and t not in SHARED_CORE_TABLES]

        owned = dict(
            (
                await self.db.execute(
                    text(
                        "SELECT s.relname, t.relname FROM pg_catalog.pg_class s "
                        "JOIN pg_catalog.pg_depend d ON d.objid = s.oid "
                        "AND d.classid = 'pg_catalog.pg_class'::regclass "
                        "AND d.refclassid = 'pg_catalog.pg_class'::regclass AND d.deptype IN ('a', 'i') "
                        "JOIN pg_catalog.pg_class t ON t.oid = d.refobjid "
                        "JOIN pg_catalog.pg_namespace n ON n.oid = s.relnamespace "
                        "WHERE s.relkind = 'S' AND n.nspname = 'public'"
                    )
                )
            ).all()
        )
        table_set = set(tables)
        toc_lines: list[str] = []
        for line, kind, name in toc:
            if kind == "TABLE DATA" and name in table_set:
                toc_lines.append(line)
            elif kind == "SEQUENCE SET":
                owner = owned.get(name)
                if backup.level == "global":
                    if owner is None or owner in table_set:
                        toc_lines.append(line)
                elif owner in table_set:
                    toc_lines.append(line)

        manifest = backup.manifest or {}
        ged_meta = manifest.get("ged") or {}
        ged_codes = list(ged_meta.get("module_codes") or []) if "ged_rows" in artifacts else []
        files_archive = root / artifacts["files"]["file"] if "files" in artifacts else None
        targets: list[tuple[str, Path]] = []
        for arc in (manifest.get("files") or {}).get("targets") or []:
            if arc == "uploads":
                targets.append((arc, engine.upload_root()))
            elif arc == "ged":
                targets.append((arc, engine.ged_root()))
            elif arc.startswith("uploads/"):
                targets.append((arc, engine.upload_root() / arc.split("/", 1)[1]))
            elif arc.startswith("ged/"):
                targets.append((arc, engine.ged_root() / arc.split("/", 1)[1]))
        legacy_uploads = None
        if not artifacts and backup.level == "global" and backup.uploads_path and Path(backup.uploads_path).is_dir():
            legacy_uploads = Path(backup.uploads_path)

        plan = engine.RestorePlan(
            dump=dump,
            toc_lines=toc_lines,
            tables=tables,
            ged_codes=ged_codes,
            ged_rows=root / artifacts["ged_rows"]["file"] if ged_codes else None,
            ged_columns=list(ged_meta.get("columns") or []),
            files_archive=files_archive if targets else None,
            file_targets=targets,
            legacy_uploads=legacy_uploads,
        )
        info = {
            "preserved": sorted(preserved & (dump_tables | existing)) if backup.level == "global" else [],
            "skipped": sorted(
                t for t in (backup.tables_included or []) if t not in table_set
            ) if backup.level != "global" else [],
            "alembic_backup": manifest.get("alembic_revision"),
        }
        return plan, info

    async def _cross_dependencies(self, tables: list[str]) -> list[dict]:
        if not tables:
            return []
        rows = await self.db.execute(
            text(
                "SELECT DISTINCT c.conrelid::regclass::text, c.confrelid::regclass::text "
                "FROM pg_catalog.pg_constraint c WHERE c.contype = 'f' "
                "AND (c.conrelid::regclass::text = ANY(:t) OR c.confrelid::regclass::text = ANY(:t)) "
                "AND c.conrelid <> c.confrelid"
            ),
            {"t": tables},
        )
        _esp_labels, mod_labels = await self._labels()
        existing = await self._existing_tables()
        owner: dict[str, str] = {}
        for code in MODULE_BACKUP_SCOPES:
            for t in resolve_tables(code, existing):
                owner.setdefault(t, code)
        table_set = set(tables)
        deps = []
        for child, parent in rows.all():
            child, parent = child.removeprefix("public."), parent.removeprefix("public.")
            outside = parent if child in table_set else child
            if outside in table_set or outside in SHARED_CORE_TABLES:
                continue
            code = owner.get(outside)
            deps.append(
                {
                    "table": child,
                    "references": parent,
                    "direction": "sortante" if child in table_set else "entrante",
                    "module_code": code,
                    "module_label": mod_labels.get(code or "", code),
                }
            )
        return sorted(deps, key=lambda d: (d["module_label"] or "", d["table"]))

    async def preview_restore(self, backup_id: uuid.UUID, *, include_security: bool = False) -> dict:
        backup = self._restorable(await self.get(backup_id))
        plan, info = await self._restore_plan(backup, include_security=include_security)
        manifest = backup.manifest or {}
        backup_counts: dict = manifest.get("tables") or {}
        current_counts, _ = await self._row_counts(None if backup.level == "global" else plan.tables)
        tables = [
            {
                "name": t,
                "rows_backup": backup_counts.get(t),
                "rows_current": current_counts.get(t),
            }
            for t in plan.tables
        ]
        current_rev = await self._alembic_revision()
        warnings: list[str] = []
        if backup.level == "global":
            warnings.append(
                "La restauration globale remplace les données de tous les départements et modules "
                "par l'état de la sauvegarde."
            )
            if include_security:
                warnings.append(
                    "Comptes, rôles et droits seront aussi restaurés : des comptes désactivés depuis "
                    "pourraient être réactivés et d'anciens mots de passe redevenir valides."
                )
        if info["alembic_backup"] and current_rev and info["alembic_backup"] != current_rev:
            warnings.append(
                f"Schéma différent (sauvegarde {info['alembic_backup']}, base {current_rev}) : "
                "la restauration sera refusée si les structures sont incompatibles."
            )
        if info["skipped"]:
            warnings.append(f"Tables ignorées (absentes de la base actuelle) : {', '.join(info['skipped'])}.")
        deps = await self._cross_dependencies(plan.tables) if backup.level != "global" else []
        if deps:
            mods = sorted({d["module_label"] or d["table"] for d in deps})
            warnings.append(
                "Données liées à d'autres modules (" + ", ".join(mods) + ") : la restauration sera "
                "refusée si elle laisse des références orphelines."
            )
        return {
            "backup": await self.serialize(backup),
            "level": backup.level,
            "type": LEVEL_CODES.get(backup.level, backup.level.upper()),
            "include_security": include_security if backup.level == "global" else False,
            "tables": tables,
            "tables_count": len(tables),
            "preserved_tables": info["preserved"],
            "ged": {
                "module_codes": plan.ged_codes,
                "rows_backup": (manifest.get("ged") or {}).get("rows") if plan.ged_codes else None,
                "rows_current": await self._ged_rows_count(plan.ged_codes),
            },
            "file_targets": [arc for arc, _ in plan.file_targets] or (["uploads"] if plan.legacy_uploads else []),
            "dependencies": deps,
            "warnings": warnings,
            "confirmation_phrase": confirmation_phrase(backup.level, backup.espace_code, backup.module_code),
            "safety_backup": True,
            "alembic": {"backup": info["alembic_backup"], "current": current_rev},
        }

    async def _notify_admins(self, *, titre: str, message: str, restore: PlatformRestore, actor: User, priorite: str | None = None) -> None:
        rows = await self.db.execute(
            text(
                "SELECT DISTINCT u.id FROM users u "
                "LEFT JOIN user_roles ur ON ur.user_id = u.id "
                "LEFT JOIN role_permissions rp ON rp.role_id = ur.role_id "
                "LEFT JOIN permissions p ON p.id = rp.permission_id "
                "WHERE u.is_active AND u.deleted_at IS NULL AND (u.is_superuser "
                "OR p.code IN ('core.admin.recovery.view', 'core.admin.recovery.execute'))"
            )
        )
        svc = NotificationService(self.db)
        for (user_id,) in rows.all():
            await svc.create(
                user_id=user_id,
                type_notification="core.recovery",
                titre=titre,
                message=message,
                entity="platform_restore",
                entity_id=str(restore.id),
                espace_code=restore.espace_code,
                module_code=restore.module_code or "core",
                priorite=priorite,
                emetteur_type="utilisateur",
                emetteur_label=actor.full_name or actor.email,
                destinataire_type="administrateurs",
                destinataire_label="Administrateurs CORE (recovery)",
                actor_user_id=actor.id,
            )

    async def restore(
        self,
        backup_id: uuid.UUID,
        *,
        user: User,
        acknowledge_dependencies: bool = False,
        confirmation: str | None = None,
        reason: str | None = None,
        include_security: bool = False,
        request: Request | None = None,
    ) -> dict:
        backup = self._restorable(await self.get(backup_id))
        include_security = bool(include_security) and backup.level == "global"
        expected = confirmation_phrase(backup.level, backup.espace_code, backup.module_code)
        if (confirmation or "").strip().upper() != expected:
            raise _error(
                400,
                "RECOVERY_CONFIRMATION_REQUIRED",
                f"Confirmation explicite requise : saisissez « {expected} ».",
                expected=expected,
            )
        motif = (reason or "").strip()
        if len(motif) < MIN_REASON_LENGTH:
            raise _error(
                400,
                "RECOVERY_REASON_REQUIRED",
                f"Indiquez le motif de la restauration ({MIN_REASON_LENGTH} caractères minimum).",
            )
        if not acknowledge_dependencies:
            raise _error(
                400,
                "DEPENDENCIES_NOT_ACKNOWLEDGED",
                "Confirmez avoir pris connaissance des données remplacées et des dépendances.",
            )
        running = await self.db.scalar(
            select(func.count())
            .select_from(PlatformRestore)
            .where(
                PlatformRestore.status == "running",
                PlatformRestore.created_at > datetime.now(timezone.utc) - STALE_RUNNING,
            )
        )
        if running:
            raise _error(409, "RECOVERY_IN_PROGRESS", "Une restauration est déjà en cours. Patientez.")

        preview = await self.preview_restore(backup_id, include_security=include_security)
        perimetre = backup.label or LEVEL_CODES.get(backup.level, backup.level)
        restore = PlatformRestore(
            id=uuid.uuid4(),
            backup_id=backup.id,
            level=backup.level,
            espace_code=backup.espace_code,
            module_code=backup.module_code,
            status="running",
            dependency_warning=" ".join(preview["warnings"])[:4000] or None,
            acknowledged_dependencies=True,
            created_by_id=user.id,
            reason=motif[:2000],
            ip_address=get_client_ip(request),
            options={"include_security": include_security, "confirmation": expected},
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
            after={
                "backup_id": str(backup.id),
                "level": backup.level,
                "perimetre": perimetre,
                "motif": motif,
                "include_security": include_security,
                "tables": preview["tables_count"],
            },
        )
        await self._notify_admins(
            titre=f"Restauration {LEVEL_CODES.get(backup.level)} lancée",
            message=f"{user.full_name or user.email} restaure « {perimetre} ». Motif : {motif}",
            restore=restore,
            actor=user,
            priorite="critique" if backup.level == "global" else None,
        )
        await self.db.commit()
        started = time.monotonic()

        try:
            safety = await self.create_backup(
                user=user,
                level=backup.level,
                backup_type="securite_recovery",
                espace_code=backup.espace_code,
                module_code=backup.module_code,
                request=request,
                label=f"Sécurité avant recovery {str(backup.id)[:8]}",
            )
        except HTTPException as exc:
            detail = exc.detail.get("message") if isinstance(exc.detail, dict) else str(exc.detail)
            await self._finish_failed(
                restore,
                user=user,
                request=request,
                started=started,
                message=f"Sauvegarde de sécurité impossible — restauration annulée, aucune donnée modifiée. {detail}",
                perimetre=perimetre,
            )
            raise _error(
                500,
                "RECOVERY_SAFETY_BACKUP_FAILED",
                restore.error_message or "Sauvegarde de sécurité impossible.",
                restore_id=str(restore.id),
            ) from exc
        restore.safety_backup_id = uuid.UUID(safety["id"])
        await self.db.commit()

        try:
            plan, _info = await self._restore_plan(backup, include_security=include_security)
            sql_result = await asyncio.to_thread(engine.execute_restore_sql, plan, engine.pg_dsn())
        except HTTPException as exc:
            detail = exc.detail.get("message") if isinstance(exc.detail, dict) else str(exc.detail)
            await self._finish_failed(
                restore, user=user, request=request, started=started, message=detail, perimetre=perimetre
            )
            raise
        except Exception as exc:  # noqa: BLE001 — transaction psql annulée, rien n'a changé
            await self._finish_failed(
                restore,
                user=user,
                request=request,
                started=started,
                message=engine.friendly_restore_error(str(exc)),
                raw=str(exc),
                perimetre=perimetre,
            )
            raise _error(
                500,
                "RECOVERY_FAILED",
                restore.error_message or "Échec de la restauration.",
                restore_id=str(restore.id),
                safety_backup_id=str(restore.safety_backup_id),
            ) from exc

        files_error: str | None = None
        files_result: dict = {}
        try:
            files_result = await asyncio.to_thread(engine.restore_files, plan)
        except Exception as exc:  # noqa: BLE001 — base restaurée, fichiers en échec = partielle
            files_error = str(exc)[:1000]

        restore.status = "success" if files_error is None else "partial"
        restore.error_message = (
            None
            if files_error is None
            else f"Base restaurée, mais les fichiers n'ont pas pu être remplacés : {files_error}"
        )
        restore.finished_at = datetime.now(timezone.utc)
        restore.duration_ms = int((time.monotonic() - started) * 1000)
        restore.details = {
            "tables": plan.tables,
            "tables_count": len(plan.tables),
            "ged_codes": plan.ged_codes,
            "file_targets": [arc for arc, _ in plan.file_targets],
            "sql": sql_result,
            "files": files_result,
            "preserved_tables": preview["preserved_tables"],
        }
        await record_audit(
            self.db,
            user=user,
            action="recovery_success" if files_error is None else "recovery_partial",
            entity="platform_restore",
            entity_id=str(restore.id),
            request=request,
            espace_code=backup.espace_code,
            module_code=backup.module_code or "core",
            after=self._restore_audit_payload(restore),
        )
        await self._notify_admins(
            titre=(
                f"Restauration {LEVEL_CODES.get(backup.level)} terminée"
                if files_error is None
                else f"Restauration {LEVEL_CODES.get(backup.level)} partielle"
            ),
            message=(
                f"« {perimetre} » restauré par {user.full_name or user.email} "
                f"({len(plan.tables)} tables)."
                + (f" Fichiers : {files_error}" if files_error else "")
            ),
            restore=restore,
            actor=user,
        )
        await self.db.commit()
        return await self.serialize_restore(restore)

    async def _finish_failed(
        self,
        restore: PlatformRestore,
        *,
        user: User,
        request: Request | None,
        started: float,
        message: str,
        perimetre: str,
        raw: str | None = None,
    ) -> None:
        restore.status = "failed"
        restore.error_message = message[:2000]
        restore.finished_at = datetime.now(timezone.utc)
        restore.duration_ms = int((time.monotonic() - started) * 1000)
        if raw:
            restore.details = {**(restore.details or {}), "raw_error": raw[:4000]}
        await record_audit(
            self.db,
            user=user,
            action="recovery_failed",
            entity="platform_restore",
            entity_id=str(restore.id),
            request=request,
            espace_code=restore.espace_code,
            module_code=restore.module_code or "core",
            after=self._restore_audit_payload(restore),
        )
        await self._notify_admins(
            titre=f"Restauration {LEVEL_CODES.get(restore.level)} échouée",
            message=f"« {perimetre} » : {message[:400]}",
            restore=restore,
            actor=user,
        )
        await self.db.commit()

    # ——— Lecture / historique / KPI ———

    async def get(self, backup_id: uuid.UUID) -> PlatformBackup | None:
        return await self.db.get(PlatformBackup, backup_id)

    async def get_restore(self, restore_id: uuid.UUID) -> PlatformRestore | None:
        return await self.db.get(PlatformRestore, restore_id)

    async def restores_of(self, backup_id: uuid.UUID) -> list[PlatformRestore]:
        rows = await self.db.execute(
            select(PlatformRestore)
            .where(PlatformRestore.backup_id == backup_id)
            .order_by(PlatformRestore.created_at.desc())
        )
        return list(rows.scalars().all())

    async def list_backups(
        self,
        *,
        page: int,
        size: int,
        level: str | None = None,
        module_code: str | None = None,
        espace_code: str | None = None,
        status_filter: str | None = None,
    ) -> tuple[list[dict], int]:
        filters = []
        if level:
            filters.append(PlatformBackup.level == level)
        if module_code:
            filters.append(PlatformBackup.module_code == module_code)
        if espace_code:
            filters.append(PlatformBackup.espace_code == espace_code)
        if status_filter:
            filters.append(PlatformBackup.status == status_filter)
        total = int(
            await self.db.scalar(select(func.count()).select_from(PlatformBackup).where(*filters)) or 0
        )
        rows = (
            await self.db.execute(
                select(PlatformBackup)
                .where(*filters)
                .order_by(PlatformBackup.created_at.desc())
                .offset((page - 1) * size)
                .limit(size)
            )
        ).scalars().all()
        return await self.serialize_many(list(rows)), total

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
        return [await self.serialize_restore(r) for r in rows], total

    async def history(
        self,
        *,
        page: int,
        size: int,
        kind: str | None = None,
        level: str | None = None,
        status_filter: str | None = None,
        espace_code: str | None = None,
        module_code: str | None = None,
    ) -> dict:
        where: list[str] = []
        params: dict = {}
        for column, value in (
            ("kind", kind),
            ("level", level),
            ("status", status_filter),
            ("espace_code", espace_code),
            ("module_code", module_code),
        ):
            if value:
                where.append(f"h.{column} = :{column}")
                params[column] = value
        clause = ("WHERE " + " AND ".join(where)) if where else ""
        union = """
            SELECT 'backup' AS kind, b.id, b.created_at, b.level, b.espace_code, b.module_code,
                   b.status, b.size_bytes, b.created_by_id, b.backup_type AS subtype, b.label,
                   b.id AS backup_id, b.duration_ms, b.integrity_status, b.error_message
              FROM platform_backups b
            UNION ALL
            SELECT 'restore', r.id, r.created_at, r.level, r.espace_code, r.module_code,
                   r.status, COALESCE(b.size_bytes, 0), r.created_by_id, 'recovery',
                   COALESCE(b.label, r.details -> 'deleted_backup' ->> 'label'),
                   r.backup_id, r.duration_ms, NULL, r.error_message
              FROM platform_restores r LEFT JOIN platform_backups b ON b.id = r.backup_id
        """
        total = int(
            await self.db.scalar(text(f"SELECT count(*) FROM ({union}) h {clause}"), params) or 0
        )
        rows = (
            await self.db.execute(
                text(
                    f"SELECT h.* FROM ({union}) h {clause} "
                    "ORDER BY h.created_at DESC LIMIT :limit OFFSET :offset"
                ),
                {**params, "limit": size, "offset": (page - 1) * size},
            )
        ).mappings().all()
        users = await self._users_map([r["created_by_id"] for r in rows])
        esp_labels, mod_labels = await self._labels()
        items = []
        for r in rows:
            items.append(
                {
                    "kind": r["kind"],
                    "id": str(r["id"]),
                    "backup_id": str(r["backup_id"]) if r["backup_id"] else None,
                    "created_at": _iso(r["created_at"]),
                    "level": r["level"],
                    "type": LEVEL_CODES.get(r["level"], r["level"].upper()),
                    "subtype": r["subtype"],
                    "perimetre": self._perimetre(r["level"], r["espace_code"], r["module_code"], esp_labels, mod_labels),
                    "espace_code": r["espace_code"],
                    "module_code": r["module_code"],
                    "status": r["status"],
                    "size_bytes": int(r["size_bytes"] or 0),
                    "duration_ms": r["duration_ms"],
                    "integrity_status": r["integrity_status"],
                    "error_message": r["error_message"],
                    "label": r["label"],
                    "administrateur": users.get(r["created_by_id"]),
                }
            )
        return {"items": items, "total": total, "page": page, "size": size}

    async def dashboard(self) -> dict:
        async def count(model, *where) -> int:
            return int(await self.db.scalar(select(func.count()).select_from(model).where(*where)) or 0)

        async def latest(model, *where, limit: int = 1):
            return list(
                (
                    await self.db.execute(
                        select(model).where(*where).order_by(model.created_at.desc()).limit(limit)
                    )
                ).scalars().all()
            )

        last_global = await latest(PlatformBackup, PlatformBackup.level == "global", PlatformBackup.status == "success")
        last_manual = await latest(PlatformBackup, PlatformBackup.backup_type == "manuelle", PlatformBackup.status == "success")
        last_error = await latest(PlatformBackup, PlatformBackup.status == "failed")
        recent_backups = await latest(PlatformBackup, limit=6)
        recent_restores = await latest(PlatformRestore, limit=6)
        failed_backups = await latest(PlatformBackup, PlatformBackup.status == "failed", limit=5)
        failed_restores = await latest(PlatformRestore, PlatformRestore.status.in_(("failed", "partial")), limit=5)
        total_size = int(
            await self.db.scalar(
                select(func.coalesce(func.sum(PlatformBackup.size_bytes), 0)).where(PlatformBackup.status == "success")
            )
            or 0
        )
        try:
            usage = await asyncio.to_thread(shutil.disk_usage, engine.backup_root())
            disk = {"total": usage.total, "free": usage.free}
        except OSError:
            disk = None
        errors = [
            {"kind": "backup", **(await self.serialize(b))} for b in failed_backups
        ] + [{"kind": "restore", **(await self.serialize_restore(r))} for r in failed_restores]
        errors.sort(key=lambda e: e.get("created_at") or "", reverse=True)
        return {
            "total": await count(PlatformBackup),
            "success": await count(PlatformBackup, PlatformBackup.status == "success"),
            "failed": await count(PlatformBackup, PlatformBackup.status == "failed"),
            "restores_total": await count(PlatformRestore),
            "restores_success": await count(PlatformRestore, PlatformRestore.status == "success"),
            "restores_failed": await count(PlatformRestore, PlatformRestore.status.in_(("failed", "partial"))),
            "integrity_ko": await count(PlatformBackup, PlatformBackup.integrity_status == "ko"),
            "total_size_bytes": total_size,
            "disk": disk,
            "derniere_globale": await self.serialize(last_global[0]) if last_global else None,
            "derniere_manuelle": await self.serialize(last_manual[0]) if last_manual else None,
            "derniere_erreur": await self.serialize(last_error[0]) if last_error else None,
            "dernieres_sauvegardes": await self.serialize_many(recent_backups),
            "dernieres_restaurations": [await self.serialize_restore(r) for r in recent_restores],
            "erreurs": errors[:6],
        }

    # ——— Sérialisation ———

    async def _users_map(self, ids) -> dict:
        wanted = {i for i in ids if i}
        if not wanted:
            return {}
        rows = await self.db.execute(select(User.id, User.full_name, User.email).where(User.id.in_(wanted)))
        return {r.id: {"id": str(r.id), "full_name": r.full_name, "email": r.email} for r in rows}

    @staticmethod
    def _perimetre(level, espace_code, module_code, esp_labels, mod_labels) -> str:
        if level == "global":
            return "BEA DIGITAL (global)"
        if level == "departement":
            return esp_labels.get(espace_code or "", espace_code or "—")
        mod = mod_labels.get(module_code or "", module_code or "—")
        esp = esp_labels.get(espace_code or "")
        return f"{esp} › {mod}" if esp else mod

    @staticmethod
    def _default_label(level: str, perimetre: str) -> str:
        if level == "global":
            return "BEA DIGITAL (global)"
        if level == "departement":
            return f"Département {perimetre}"
        return f"Module {perimetre}"

    @staticmethod
    def _audit_payload(row: PlatformBackup) -> dict:
        return {
            "backup_id": str(row.id),
            "level": row.level,
            "backup_type": row.backup_type,
            "espace_code": row.espace_code,
            "module_code": row.module_code,
            "status": row.status,
            "size_bytes": row.size_bytes,
            "duration_ms": row.duration_ms,
            "checksum_sha256": row.checksum_sha256,
            "tables": len(row.tables_included or []) if row.tables_included is not None else "all",
            "error": row.error_message,
        }

    @staticmethod
    def _restore_audit_payload(row: PlatformRestore) -> dict:
        return {
            "restore_id": str(row.id),
            "backup_id": str(row.backup_id) if row.backup_id else None,
            "safety_backup_id": str(row.safety_backup_id) if row.safety_backup_id else None,
            "level": row.level,
            "espace_code": row.espace_code,
            "module_code": row.module_code,
            "status": row.status,
            "motif": row.reason,
            "duration_ms": row.duration_ms,
            "options": row.options,
            "tables": (row.details or {}).get("tables_count"),
            "error": row.error_message,
        }

    async def serialize_many(self, rows: list[PlatformBackup]) -> list[dict]:
        users = await self._users_map([r.created_by_id for r in rows])
        labels = await self._labels()
        return [self._serialize(r, users, labels) for r in rows]

    async def serialize(self, row: PlatformBackup | None) -> dict:
        if row is None:
            return {}
        return (await self.serialize_many([row]))[0]

    def _serialize(self, row: PlatformBackup, users: dict, labels: tuple[dict, dict]) -> dict:
        esp_labels, mod_labels = labels
        artifacts = row.artifacts or {}
        manifest = row.manifest or {}
        return {
            "id": str(row.id),
            "level": row.level,
            "type": LEVEL_CODES.get(row.level, row.level.upper()),
            "backup_type": row.backup_type,
            "espace_code": row.espace_code,
            "module_code": row.module_code,
            "perimetre": self._perimetre(row.level, row.espace_code, row.module_code, esp_labels, mod_labels),
            "status": row.status,
            "file_path": row.file_path,
            "uploads_path": row.uploads_path,
            "emplacement": row.file_path or (str(engine.backup_root()) if artifacts else None),
            "artifacts": artifacts,
            "size_bytes": row.size_bytes,
            "tables_included": row.tables_included,
            "tables_count": len(manifest.get("tables") or {}) or len(row.tables_included or []),
            "rows_total": sum((manifest.get("tables") or {}).values()) if manifest.get("tables") else None,
            "ged_documents": (manifest.get("ged") or {}).get("rows"),
            "files_count": (manifest.get("files") or {}).get("files"),
            "modules": manifest.get("modules"),
            "departements": manifest.get("departements"),
            "alembic_revision": manifest.get("alembic_revision"),
            "shared_dependencies": row.shared_dependencies,
            "error_message": row.error_message,
            "created_by_id": str(row.created_by_id) if row.created_by_id else None,
            "administrateur": users.get(row.created_by_id),
            "ip_address": row.ip_address,
            "label": row.label,
            "checksum_sha256": row.checksum_sha256,
            "integrity_status": row.integrity_status,
            "integrity_checked_at": _iso(row.integrity_checked_at),
            "integrity_detail": row.integrity_detail,
            "duration_ms": row.duration_ms,
            "format": manifest.get("format") or "bea-backup/1",
            "restorable": row.status in RESTORABLE_STATUSES,
            "confirmation_phrase": confirmation_phrase(row.level, row.espace_code, row.module_code),
            "created_at": _iso(row.created_at),
            "finished_at": _iso(row.finished_at),
        }

    async def serialize_restore(self, row: PlatformRestore) -> dict:
        users = await self._users_map([row.created_by_id])
        esp_labels, mod_labels = await self._labels()
        return {
            "id": str(row.id),
            "backup_id": str(row.backup_id) if row.backup_id else None,
            "deleted_backup": (row.details or {}).get("deleted_backup"),
            "safety_backup_id": str(row.safety_backup_id) if row.safety_backup_id else None,
            "level": row.level,
            "type": LEVEL_CODES.get(row.level, row.level.upper()),
            "espace_code": row.espace_code,
            "module_code": row.module_code,
            "perimetre": self._perimetre(row.level, row.espace_code, row.module_code, esp_labels, mod_labels),
            "status": row.status,
            "reason": row.reason,
            "dependency_warning": row.dependency_warning,
            "acknowledged_dependencies": row.acknowledged_dependencies,
            "options": row.options,
            "details": {k: v for k, v in (row.details or {}).items() if k != "raw_error"},
            "error_message": row.error_message,
            "ip_address": row.ip_address,
            "duration_ms": row.duration_ms,
            "created_by_id": str(row.created_by_id) if row.created_by_id else None,
            "administrateur": users.get(row.created_by_id),
            "created_at": _iso(row.created_at),
            "finished_at": _iso(row.finished_at),
        }
