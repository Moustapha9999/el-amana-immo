"""CORE ADMIN — CORE QUERY / Data Explorer (lecture seule, mode administrateur optionnel)."""

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_platform_permission
from app.db.session import get_db
from app.models import User
from app.services.core_query.service import CoreQueryService

router = APIRouter(prefix="/plateforme/admin/core-query", tags=["core-admin-query"])

_VIEW = require_platform_permission("core.admin.query.view")
_EXECUTE = require_platform_permission("core.admin.query.execute")
_EXPORT = require_platform_permission("core.admin.query.export")


class AnalyzeIn(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class SqlIn(BaseModel):
    sql: str = Field(min_length=1, max_length=20_000)


class BuilderIn(BaseModel):
    spec: dict[str, Any]


class ExecuteIn(BaseModel):
    mode: Literal["assistant", "builder", "sql"] = "assistant"
    question: str | None = Field(None, max_length=1000)
    expected_sql: str | None = Field(None, max_length=20_000)
    spec: dict[str, Any] | None = None
    sql: str | None = Field(None, max_length=200_000)
    favorite_id: UUID | None = None
    limit: int | None = Field(None, ge=1, le=5000)
    admin: bool = False
    dry_run: bool = False
    reason: str | None = Field(None, max_length=2000)


class ExportIn(ExecuteIn):
    format: Literal["xlsx", "pdf", "csv"] = "xlsx"


class FavoriteIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: str | None = Field(None, max_length=1000)
    source: Literal["assistant", "builder", "sql"]
    question: str | None = Field(None, max_length=1000)
    sql: str | None = Field(None, max_length=20_000)
    spec: dict[str, Any] | None = None


class FavoriteUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=160)
    description: str | None = Field(None, max_length=1000)


@router.get("/schema")
async def core_query_schema(
    request: Request,
    refresh: bool = False,
    user: User = Depends(_VIEW),
    db: AsyncSession = Depends(get_db),
):
    return await CoreQueryService(db, user, request).schema_payload(refresh=refresh)


@router.get("/dashboard")
async def core_query_dashboard(
    request: Request,
    user: User = Depends(_VIEW),
    db: AsyncSession = Depends(get_db),
):
    return await CoreQueryService(db, user, request).dashboard()


@router.post("/analyze")
async def core_query_analyze(
    body: AnalyzeIn,
    request: Request,
    user: User = Depends(_VIEW),
    db: AsyncSession = Depends(get_db),
):
    return await CoreQueryService(db, user, request).analyze(body.question)


@router.post("/build")
async def core_query_build(
    body: BuilderIn,
    request: Request,
    user: User = Depends(_VIEW),
    db: AsyncSession = Depends(get_db),
):
    return await CoreQueryService(db, user, request).build(body.spec)


@router.post("/validate")
async def core_query_validate(
    body: SqlIn,
    request: Request,
    user: User = Depends(_VIEW),
    db: AsyncSession = Depends(get_db),
):
    return await CoreQueryService(db, user, request).validate(body.sql)


@router.post("/execute")
async def core_query_execute(
    body: ExecuteIn,
    request: Request,
    user: User = Depends(_EXECUTE),
    db: AsyncSession = Depends(get_db),
):
    return await CoreQueryService(db, user, request).execute(body.model_dump(mode="json"))


@router.post("/export")
async def core_query_export(
    body: ExportIn,
    request: Request,
    user: User = Depends(_EXPORT),
    db: AsyncSession = Depends(get_db),
):
    svc = CoreQueryService(db, user, request)
    payload = body.model_dump(mode="json")
    content, filename, media = await svc.export(payload, body.format)
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/history")
async def core_query_history(
    request: Request,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: Literal["success", "refused", "error"] | None = None,
    scope: Literal["mine", "all"] = "mine",
    q: str | None = Query(None, max_length=200),
    user: User = Depends(_VIEW),
    db: AsyncSession = Depends(get_db),
):
    return await CoreQueryService(db, user, request).history(
        page=page, size=size, status=status, scope=scope, search=q
    )


@router.get("/favorites")
async def core_query_favorites(
    request: Request,
    user: User = Depends(_VIEW),
    db: AsyncSession = Depends(get_db),
):
    return await CoreQueryService(db, user, request).favorites()


@router.post("/favorites", status_code=201)
async def core_query_favorite_create(
    body: FavoriteIn,
    request: Request,
    user: User = Depends(_VIEW),
    db: AsyncSession = Depends(get_db),
):
    return await CoreQueryService(db, user, request).create_favorite(body.model_dump(mode="json"))


@router.patch("/favorites/{favorite_id}")
async def core_query_favorite_update(
    favorite_id: UUID,
    body: FavoriteUpdate,
    request: Request,
    user: User = Depends(_VIEW),
    db: AsyncSession = Depends(get_db),
):
    return await CoreQueryService(db, user, request).update_favorite(
        favorite_id, body.model_dump(exclude_unset=True)
    )


@router.delete("/favorites/{favorite_id}", status_code=204)
async def core_query_favorite_delete(
    favorite_id: UUID,
    request: Request,
    user: User = Depends(_VIEW),
    db: AsyncSession = Depends(get_db),
):
    await CoreQueryService(db, user, request).delete_favorite(favorite_id)
    return Response(status_code=204)
