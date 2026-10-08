"""Orchestration CORE QUERY : analyse → validation → permissions → exécution → journal + audit."""

from __future__ import annotations

import csv
import io
import re
import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.request_client import get_client_ip
from app.db.session import engine
from app.models import CoreQueryFavorite, CoreQueryLog, PlateformeModule, User
from app.services.audit_helpers import record_audit
from app.services.core_query.builder import build_sql
from app.services.core_query.executor import (
    DEFAULT_LIMIT,
    EXPORT_LIMIT,
    MAX_LIMIT,
    QueryExecutionError,
    ensure_reader_role,
    execute_admin,
    execute_select,
    reader_role_status,
)
from app.services.core_query.nl_parser import EXAMPLES, TZ, interpret
from app.services.core_query.schema import Catalog, get_catalog, invalidate_catalog
from app.services.core_query.validator import QueryRefused, ValidatedQuery, check_admin_sql, validate_sql
from app.services.permission_service import load_user_permission_codes, user_has_permission_codes

PERM_VIEW = "core.admin.query.view"
PERM_EXECUTE = "core.admin.query.execute"
PERM_SQL = "core.admin.query.sql"
PERM_EXPORT = "core.admin.query.export"
PERM_ADMIN = "core.admin.query.admin"

SOURCES = {"assistant", "builder", "sql"}
PDF_EXPORT_LIMIT = 2000
STEP_LABELS = [
    ("analyse", "Analyse de la requête"),
    ("tables", "Vérification des tables"),
    ("columns", "Vérification des colonnes"),
    ("permissions", "Vérification des permissions"),
    ("read_only", "Contrôle lecture seule"),
    ("limit", "Limite de résultats"),
    ("execute", "Exécution"),
    ("audit", "Enregistrement dans l'audit"),
]
ADMIN_STEP_LABELS = [
    ("permissions", "Permission mode administrateur"),
    ("server", "Contrôle d'accès serveur"),
    ("reason", "Motif de la modification"),
    ("limit", "Limite de résultats"),
    ("execute", "Exécution"),
    ("commit", "Validation (COMMIT)"),
    ("audit", "Enregistrement dans l'audit"),
]
REASON_MIN_LENGTH = 5


def _squash(sql: str | None) -> str:
    return re.sub(r"\s+", " ", (sql or "").strip().rstrip(";")).strip()


class _Steps:
    def __init__(self, labels: list[tuple[str, str]] | None = None) -> None:
        self.labels = labels or STEP_LABELS
        self.state: dict[str, str] = {}

    def ok(self, key: str) -> None:
        self.state[key] = "ok"

    def fail(self, key: str) -> None:
        self.state[key] = "failed"

    def as_list(self) -> list[dict[str, str]]:
        return [{"key": k, "label": lbl, "status": self.state.get(k, "pending")} for k, lbl in self.labels]


class CoreQueryService:
    def __init__(self, db: AsyncSession, user: User, request: Request | None = None) -> None:
        self.db = db
        self.user = user
        self.request = request
        self._perms: set[str] | None = None

    # ------------------------------------------------------------------ contexte

    async def perms(self) -> set[str]:
        if self._perms is None:
            self._perms = await load_user_permission_codes(self.db, self.user)
        return self._perms

    async def can(self, code: str) -> bool:
        return user_has_permission_codes(await self.perms(), code)

    async def catalog(self, refresh: bool = False) -> Catalog:
        return await get_catalog(engine, refresh=refresh)

    async def modules(self) -> dict[str, str]:
        rows = (await self.db.execute(select(PlateformeModule.code, PlateformeModule.label))).all()
        return {code: label for code, label in rows}

    async def schema_payload(self, refresh: bool = False) -> dict:
        cat = await self.catalog(refresh)
        await ensure_reader_role(engine, cat)
        payload = cat.to_public()
        payload["reader_role"] = reader_role_status()
        payload["examples"] = EXAMPLES
        payload["permissions"] = {
            "execute": await self.can(PERM_EXECUTE),
            "sql": await self.can(PERM_SQL),
            "export": await self.can(PERM_EXPORT),
            "admin": await self.can(PERM_ADMIN),
            "all_history": await self._can_see_all_history(),
        }
        payload["limits"] = {"default": DEFAULT_LIMIT, "max": MAX_LIMIT, "export": EXPORT_LIMIT}
        return payload

    async def _can_see_all_history(self) -> bool:
        return self.user.is_superuser or await self.can("core.admin.audit")

    # ------------------------------------------------------------------ génération

    async def analyze(self, question: str) -> dict:
        cat = await self.catalog()
        interp = interpret(question, cat, modules=await self.modules())
        data = interp.to_dict()
        data["validation"] = None
        if interp.ok and interp.sql:
            try:
                v = validate_sql(interp.sql, cat)
                data["validation"] = {"ok": True, "tables": v.tables}
            except QueryRefused as exc:
                data["validation"] = {"ok": False, "code": exc.code, "message": exc.message}
        return data

    async def build(self, spec: dict) -> dict:
        cat = await self.catalog()
        try:
            built = build_sql(spec, cat)
            validate_sql(built["sql"], cat)
        except QueryRefused as exc:
            raise HTTPException(400, detail={"code": "QUERY_REFUSED", "message": exc.message, "reason": exc.code})
        return built

    async def validate(self, sql: str) -> dict:
        cat = await self.catalog()
        try:
            v = validate_sql(sql, cat)
        except QueryRefused as exc:
            return {"ok": False, "code": exc.code, "message": exc.message}
        return {"ok": True, "tables": v.tables}

    async def _resolve(self, payload: dict, steps: _Steps, cat: Catalog) -> tuple[str, str | None, str, uuid.UUID | None]:
        """Retourne (source, question, sql, favorite_id) — SQL toujours produit côté serveur hors mode SQL."""
        source = payload.get("mode") or "assistant"
        question = (payload.get("question") or "").strip() or None
        favorite_id: uuid.UUID | None = None
        spec = payload.get("spec")
        sql_text = payload.get("sql")

        if payload.get("favorite_id"):
            fav = await self._favorite_visible(uuid.UUID(str(payload["favorite_id"])))
            favorite_id = fav.id
            source, question, spec, sql_text = fav.source, fav.question, fav.builder_spec, fav.sql_text
            fav.run_count = (fav.run_count or 0) + 1
            fav.last_run_at = datetime.now(TZ)

        if source not in SOURCES:
            raise QueryRefused("BAD_MODE", "Mode d'exécution inconnu.")

        if source == "assistant":
            if not question:
                raise QueryRefused("EMPTY", "Saisissez une question.")
            interp = interpret(question, cat, modules=await self.modules())
            if not interp.ok or not interp.sql:
                steps.fail("analyse")
                raise QueryRefused("CLARIFICATION", interp.clarification or "Question non comprise.")
            expected = payload.get("expected_sql")
            if expected and _squash(expected) != _squash(interp.sql):
                steps.fail("analyse")
                raise QueryRefused(
                    "STALE",
                    "La requête générée a changé depuis l'analyse (date relative). Relancez « Analyser ».",
                )
            sql = interp.sql
        elif source == "builder":
            if not isinstance(spec, dict):
                raise QueryRefused("EMPTY", "Configuration du Query Builder manquante.")
            sql = build_sql(spec, cat)["sql"]
        else:
            if not await self.can(PERM_SQL):
                steps.fail("permissions")
                raise QueryRefused("PERMISSION", "Permission core.admin.query.sql requise pour exécuter du SQL libre.")
            sql = (sql_text or "").strip()
        steps.ok("analyse")
        return source, question, sql, favorite_id

    # ------------------------------------------------------------------ exécution

    async def execute(self, payload: dict, *, export_format: str | None = None) -> dict:
        if payload.get("admin"):
            return await self._execute_admin(payload, export_format=export_format)
        steps = _Steps()
        cat = await self.catalog()
        source, question, sql, favorite_id = payload.get("mode") or "assistant", payload.get("question"), None, None
        validated: ValidatedQuery | None = None
        try:
            source, question, sql, favorite_id = await self._resolve(payload, steps, cat)
            try:
                validated = validate_sql(sql, cat)
            except QueryRefused as exc:
                if exc.code in {"UNKNOWN_TABLE", "FORBIDDEN_TABLE"}:
                    steps.fail("tables")
                elif exc.code in {"UNKNOWN_COLUMN", "SENSITIVE_COLUMN"}:
                    steps.ok("tables")
                    steps.fail("columns")
                else:
                    steps.fail("read_only")
                raise
            steps.ok("tables")
            steps.ok("columns")
            steps.ok("permissions")
            steps.ok("read_only")
            if export_format:
                limit = PDF_EXPORT_LIMIT if export_format == "pdf" else EXPORT_LIMIT
            else:
                limit = max(1, min(int(payload.get("limit") or DEFAULT_LIMIT), MAX_LIMIT))
            steps.ok("limit")
            use_role = await ensure_reader_role(engine, cat)
            result = await execute_select(engine, validated.sql, limit=limit, use_reader_role=use_role)
            steps.ok("execute")
        except QueryRefused as exc:
            log = await self._log(source, question, sql, "refused", favorite_id=favorite_id,
                                  error_code=exc.code, error_message=exc.message, export_format=export_format)
            await record_audit(self.db, user=self.user, action="core_query_refused", entity="core_query",
                               entity_id=str(log.id), request=self.request, module_code="core",
                               after={"source": source, "reason": exc.code, "sql": (sql or "")[:2000]})
            steps.ok("audit")
            await self.db.commit()
            raise HTTPException(400, detail={
                "code": "QUERY_REFUSED", "message": exc.message, "reason": exc.code,
                "log_id": str(log.id), "steps": steps.as_list(), "sql": sql,
            }) from None
        except QueryExecutionError as exc:
            steps.fail("execute")
            log = await self._log(source, question, sql, "error", favorite_id=favorite_id,
                                  tables=validated.tables if validated else None,
                                  error_code=exc.code, error_message=exc.message, export_format=export_format)
            await record_audit(self.db, user=self.user, action="core_query_error", entity="core_query",
                               entity_id=str(log.id), request=self.request, module_code="core",
                               after={"source": source, "reason": exc.code, "sql": (sql or "")[:2000]})
            steps.ok("audit")
            await self.db.commit()
            raise HTTPException(422, detail={
                "code": "QUERY_FAILED", "message": exc.message, "reason": exc.code,
                "log_id": str(log.id), "steps": steps.as_list(), "sql": sql,
            }) from None

        log = await self._log(
            source, question, validated.sql, "success", favorite_id=favorite_id, tables=validated.tables,
            result_count=result.total, truncated=result.truncated, duration_ms=result.duration_ms,
            export_format=export_format,
        )
        await record_audit(
            self.db, user=self.user,
            action="core_query_export" if export_format else "core_query_execute",
            entity="core_query", entity_id=str(log.id), request=self.request, module_code="core",
            after={
                "source": source, "tables": validated.tables, "rows": result.total,
                "duration_ms": result.duration_ms, "format": export_format, "sql": validated.sql[:2000],
            },
        )
        steps.ok("audit")
        return {
            "log_id": str(log.id),
            "source": source,
            "question": question,
            "sql": validated.sql,
            "tables": validated.tables,
            "columns": result.columns,
            "rows": result.rows,
            "total": result.total,
            "returned": len(result.rows),
            "truncated": result.truncated,
            "limit": limit,
            "duration_ms": result.duration_ms,
            "read_only_role": use_role,
            "steps": steps.as_list(),
            "executed_at": datetime.now(TZ).isoformat(),
        }

    async def _execute_admin(self, payload: dict, *, export_format: str | None = None) -> dict:
        """Mode administrateur : SQL libre (écriture, DDL) — COMMIT, ou ROLLBACK si simulation / export."""
        steps = _Steps(ADMIN_STEP_LABELS)
        sql = (payload.get("sql") or "").strip()
        reason = (payload.get("reason") or "").strip() or None
        dry_run = bool(payload.get("dry_run")) or bool(export_format)
        if dry_run:
            steps.labels = [(k, "Simulation (ROLLBACK)" if k == "commit" else lbl) for k, lbl in ADMIN_STEP_LABELS]
        is_write = False
        try:
            if (payload.get("mode") or "sql") != "sql":
                raise QueryRefused("BAD_MODE", "Le mode administrateur s'applique à l'éditeur SQL.")
            if not await self.can(PERM_ADMIN):
                steps.fail("permissions")
                raise QueryRefused("PERMISSION", "Permission core.admin.query.admin requise (mode administrateur).")
            steps.ok("permissions")
            try:
                check = check_admin_sql(sql)
            except QueryRefused:
                steps.fail("server")
                raise
            steps.ok("server")
            is_write = check.is_write
            if is_write and not dry_run and len(reason or "") < REASON_MIN_LENGTH:
                steps.fail("reason")
                raise QueryRefused(
                    "REASON_REQUIRED",
                    f"Indiquez le motif de cette modification ({REASON_MIN_LENGTH} caractères minimum).",
                )
            steps.ok("reason")
            if export_format:
                limit = PDF_EXPORT_LIMIT if export_format == "pdf" else EXPORT_LIMIT
            else:
                limit = max(1, min(int(payload.get("limit") or DEFAULT_LIMIT), MAX_LIMIT))
            steps.ok("limit")
            result = await execute_admin(engine, check.sql, limit=limit, dry_run=dry_run)
            steps.ok("execute")
            steps.ok("commit")
            if result.committed and is_write:
                invalidate_catalog()
        except QueryRefused as exc:
            log = await self._log("sql", None, sql, "refused", error_code=exc.code, error_message=exc.message,
                                  export_format=export_format, admin_mode=True, dry_run=dry_run, reason=reason)
            await record_audit(self.db, user=self.user, action="core_query_admin_refused", entity="core_query",
                               entity_id=str(log.id), request=self.request, module_code="core",
                               after={"reason": exc.code, "motif": reason, "sql": sql[:4000]})
            steps.ok("audit")
            await self.db.commit()
            raise HTTPException(400, detail={
                "code": "QUERY_REFUSED", "message": exc.message, "reason": exc.code,
                "log_id": str(log.id), "steps": steps.as_list(), "sql": sql,
            }) from None
        except QueryExecutionError as exc:
            steps.fail("execute")
            log = await self._log("sql", None, sql, "error", error_code=exc.code, error_message=exc.message,
                                  export_format=export_format, admin_mode=True, dry_run=dry_run, reason=reason)
            await record_audit(self.db, user=self.user, action="core_query_admin_error", entity="core_query",
                               entity_id=str(log.id), request=self.request, module_code="core",
                               after={"reason": exc.code, "motif": reason, "sql": sql[:4000],
                                      "note": "Transaction annulée (ROLLBACK) : aucune donnée modifiée."})
            steps.ok("audit")
            await self.db.commit()
            raise HTTPException(422, detail={
                "code": "QUERY_FAILED",
                "message": exc.message + " — transaction annulée, aucune donnée modifiée.",
                "reason": exc.code, "log_id": str(log.id), "steps": steps.as_list(), "sql": sql,
            }) from None

        log = await self._log(
            "sql", None, check.sql, "success", result_count=result.total, truncated=result.truncated,
            duration_ms=result.duration_ms, export_format=export_format, admin_mode=True, dry_run=dry_run,
            command_tag=result.command_tag, reason=reason,
        )
        if export_format:
            action = "core_query_admin_export"
        elif dry_run:
            action = "core_query_admin_simulate"
        else:
            action = "core_query_admin_execute"
        await record_audit(
            self.db, user=self.user, action=action, entity="core_query", entity_id=str(log.id),
            request=self.request, module_code="core",
            after={
                "motif": reason, "command": result.command_tag, "affected_rows": result.affected_rows,
                "write": is_write, "committed": result.committed, "duration_ms": result.duration_ms,
                "format": export_format, "sql": check.sql[:4000],
            },
        )
        steps.ok("audit")
        return {
            "log_id": str(log.id),
            "source": "sql",
            "question": None,
            "sql": check.sql,
            "tables": [],
            "columns": result.columns,
            "rows": result.rows,
            "total": result.total,
            "returned": len(result.rows),
            "truncated": result.truncated,
            "limit": limit,
            "duration_ms": result.duration_ms,
            "read_only_role": False,
            "admin_mode": True,
            "dry_run": dry_run,
            "is_write": is_write,
            "committed": result.committed,
            "command_tag": result.command_tag,
            "affected_rows": result.affected_rows,
            "steps": steps.as_list(),
            "executed_at": datetime.now(TZ).isoformat(),
        }

    async def export(self, payload: dict, fmt: str) -> tuple[bytes, str, str]:
        from app.services.reporting_export import build_styled_pdf, build_styled_workbook

        data = await self.execute(payload, export_format=fmt)
        headers = [c["name"] for c in data["columns"]]
        rows = [[self._export_cell(v) for v in row] for row in data["rows"]]
        title = (data.get("question") or "Requête CORE QUERY")[:120]
        mode = "mode administrateur" if data.get("admin_mode") else "lecture seule"
        subtitle = f"{data['total']} ligne(s) — CORE QUERY ({mode})"
        if data["truncated"]:
            subtitle += f" — export limité à {len(rows)} lignes"
        stamp = datetime.now(TZ).strftime("%Y%m%d-%H%M")
        if fmt == "xlsx":
            content = build_styled_workbook(
                sheet_title="CORE QUERY", report_title=title, headers=headers, rows=rows, subtitle=subtitle
            )
            return content, f"core-query-{stamp}.xlsx", (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        if fmt == "pdf":
            content = build_styled_pdf(report_title=title, headers=headers, rows=rows, subtitle=subtitle)
            return content, f"core-query-{stamp}.pdf", "application/pdf"
        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=";")
        writer.writerow(headers)
        writer.writerows(rows)
        return ("\ufeff" + buf.getvalue()).encode("utf-8"), f"core-query-{stamp}.csv", "text/csv; charset=utf-8"

    @staticmethod
    def _export_cell(value: Any) -> Any:
        if isinstance(value, bool):
            return "Oui" if value else "Non"
        if isinstance(value, str) and re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", value):
            try:
                return datetime.fromisoformat(value).astimezone(TZ).strftime("%d/%m/%Y %H:%M")
            except ValueError:
                return value
        if isinstance(value, (list, dict)):
            return str(value)
        return value

    async def _log(
        self, source: str, question: str | None, sql: str | None, status: str, *,
        favorite_id: uuid.UUID | None = None, tables: list[str] | None = None,
        result_count: int | None = None, truncated: bool = False, duration_ms: int | None = None,
        error_code: str | None = None, error_message: str | None = None, export_format: str | None = None,
        admin_mode: bool = False, dry_run: bool = False, command_tag: str | None = None, reason: str | None = None,
    ) -> CoreQueryLog:
        log = CoreQueryLog(
            user_id=self.user.id,
            source=source if source in SOURCES else "assistant",
            question=(question or None) and question[:4000],
            generated_sql=(sql or None) and sql[:20000],
            tables_used=tables,
            status=status,
            error_code=error_code,
            error_message=(error_message or None) and error_message[:2000],
            result_count=result_count,
            truncated=truncated,
            execution_time_ms=duration_ms,
            export_format=export_format,
            favorite_id=favorite_id,
            ip_address=get_client_ip(self.request),
            admin_mode=admin_mode,
            dry_run=dry_run,
            command_tag=(command_tag or None) and command_tag[:120],
            reason=(reason or None) and reason[:2000],
        )
        self.db.add(log)
        await self.db.flush()
        return log

    # ------------------------------------------------------------------ historique / tableau de bord

    async def history(self, *, page: int, size: int, status: str | None, scope: str, search: str | None) -> dict:
        all_allowed = await self._can_see_all_history()
        stmt = select(CoreQueryLog, User.full_name, User.email).outerjoin(User, User.id == CoreQueryLog.user_id)
        if scope != "all" or not all_allowed:
            stmt = stmt.where(CoreQueryLog.user_id == self.user.id)
        if status:
            stmt = stmt.where(CoreQueryLog.status == status)
        if search:
            like = f"%{search.strip()}%"
            stmt = stmt.where(or_(CoreQueryLog.question.ilike(like), CoreQueryLog.generated_sql.ilike(like)))
        total = (await self.db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
        rows = (
            await self.db.execute(stmt.order_by(CoreQueryLog.created_at.desc()).offset((page - 1) * size).limit(size))
        ).all()
        return {
            "items": [self._log_out(log, name, email) for log, name, email in rows],
            "total": total,
            "page": page,
            "size": size,
            "all_allowed": all_allowed,
        }

    @staticmethod
    def _log_out(log: CoreQueryLog, name: str | None, email: str | None) -> dict:
        return {
            "id": str(log.id),
            "user_name": name,
            "user_email": email,
            "source": log.source,
            "question": log.question,
            "sql": log.generated_sql,
            "tables": log.tables_used or [],
            "status": log.status,
            "error_code": log.error_code,
            "error_message": log.error_message,
            "result_count": log.result_count,
            "truncated": log.truncated,
            "duration_ms": log.execution_time_ms,
            "export_format": log.export_format,
            "admin_mode": bool(log.admin_mode),
            "dry_run": bool(log.dry_run),
            "command_tag": log.command_tag,
            "reason": log.reason,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }

    async def dashboard(self) -> dict:
        now = datetime.now(TZ)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        base = select(CoreQueryLog).where(CoreQueryLog.created_at >= start, CoreQueryLog.created_at < start + timedelta(days=1))
        if not await self._can_see_all_history():
            base = base.where(CoreQueryLog.user_id == self.user.id)
        sub = base.subquery()
        row = (
            await self.db.execute(
                select(
                    func.count(),
                    func.count().filter(sub.c.status == "success"),
                    func.count().filter(sub.c.status == "refused"),
                    func.count().filter(sub.c.status == "error"),
                    func.avg(sub.c.execution_time_ms).filter(sub.c.status == "success"),
                ).select_from(sub)
            )
        ).one()
        recent = await self.history(page=1, size=8, status=None, scope="all", search=None)
        favorites = await self.favorites()
        return {
            "today": {
                "total": row[0],
                "success": row[1],
                "refused": row[2],
                "errors": row[3],
                "avg_ms": int(row[4]) if row[4] is not None else None,
            },
            "recent": recent["items"],
            "favorites": favorites[:6],
            "favorites_count": len(favorites),
            "reader_role": reader_role_status(),
        }

    # ------------------------------------------------------------------ favoris

    def _fav_visible_clause(self):
        return or_(CoreQueryFavorite.user_id == self.user.id, CoreQueryFavorite.is_system.is_(True))

    async def _favorite_visible(self, fav_id: uuid.UUID) -> CoreQueryFavorite:
        fav = (
            await self.db.execute(
                select(CoreQueryFavorite).where(CoreQueryFavorite.id == fav_id, self._fav_visible_clause())
            )
        ).scalar_one_or_none()
        if fav is None:
            raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Favori introuvable."})
        return fav

    @staticmethod
    def _fav_out(f: CoreQueryFavorite) -> dict:
        return {
            "id": str(f.id),
            "name": f.name,
            "description": f.description,
            "source": f.source,
            "question": f.question,
            "sql": f.sql_text,
            "spec": f.builder_spec,
            "is_system": f.is_system,
            "run_count": f.run_count,
            "last_run_at": f.last_run_at.isoformat() if f.last_run_at else None,
            "created_at": f.created_at.isoformat() if f.created_at else None,
        }

    async def favorites(self) -> list[dict]:
        rows = (
            await self.db.execute(
                select(CoreQueryFavorite)
                .where(self._fav_visible_clause())
                .order_by(CoreQueryFavorite.is_system.desc(), CoreQueryFavorite.name)
            )
        ).scalars().all()
        return [self._fav_out(f) for f in rows]

    async def create_favorite(self, data: dict) -> dict:
        source = data.get("source")
        if source not in SOURCES:
            raise HTTPException(400, detail={"code": "VALIDATION_ERROR", "message": "Source de favori inconnue."})
        cat = await self.catalog()
        if source == "assistant" and not (data.get("question") or "").strip():
            raise HTTPException(400, detail={"code": "VALIDATION_ERROR", "message": "Question manquante."})
        try:
            if source == "builder":
                validate_sql(build_sql(data.get("spec") or {}, cat)["sql"], cat)
            if source == "sql":
                if not await self.can(PERM_SQL):
                    raise HTTPException(403, detail={
                        "code": "PERMISSION_DENIED", "message": "Permission core.admin.query.sql requise.",
                    })
                validate_sql(data.get("sql") or "", cat)
        except QueryRefused as exc:
            raise HTTPException(400, detail={"code": "QUERY_REFUSED", "message": exc.message, "reason": exc.code})
        fav = CoreQueryFavorite(
            user_id=self.user.id,
            name=data["name"].strip()[:160],
            description=(data.get("description") or "").strip() or None,
            source=source,
            question=(data.get("question") or "").strip() or None,
            sql_text=(data.get("sql") or "").strip() or None if source == "sql" else None,
            builder_spec=data.get("spec") if source == "builder" else None,
            is_system=False,
        )
        self.db.add(fav)
        await self.db.flush()
        await record_audit(self.db, user=self.user, action="core_query_favorite_create", entity="core_query_favorite",
                           entity_id=str(fav.id), request=self.request, module_code="core",
                           after={"name": fav.name, "source": source})
        return self._fav_out(fav)

    async def update_favorite(self, fav_id: uuid.UUID, data: dict) -> dict:
        fav = await self._favorite_visible(fav_id)
        if fav.is_system or fav.user_id != self.user.id:
            raise HTTPException(403, detail={"code": "PERMISSION_DENIED", "message": "Favori système non modifiable."})
        before = {"name": fav.name, "description": fav.description}
        if data.get("name"):
            fav.name = data["name"].strip()[:160]
        if "description" in data:
            fav.description = (data.get("description") or "").strip() or None
        await self.db.flush()
        await record_audit(self.db, user=self.user, action="core_query_favorite_update", entity="core_query_favorite",
                           entity_id=str(fav.id), request=self.request, module_code="core",
                           before=before, after={"name": fav.name, "description": fav.description})
        return self._fav_out(fav)

    async def delete_favorite(self, fav_id: uuid.UUID) -> None:
        fav = await self._favorite_visible(fav_id)
        if fav.is_system or fav.user_id != self.user.id:
            raise HTTPException(403, detail={"code": "PERMISSION_DENIED", "message": "Favori système non supprimable."})
        await record_audit(self.db, user=self.user, action="core_query_favorite_delete", entity="core_query_favorite",
                           entity_id=str(fav.id), request=self.request, module_code="core",
                           before={"name": fav.name})
        await self.db.delete(fav)
        await self.db.flush()
