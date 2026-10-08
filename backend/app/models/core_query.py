"""CORE QUERY — journal des requêtes et favoris (CORE ADMIN)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class CoreQueryLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "core_query_logs"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source: Mapped[str] = mapped_column(String(20))  # assistant|builder|sql|favorite
    question: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    tables_used: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20), index=True)  # success|refused|error
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    truncated: Mapped[bool] = mapped_column(Boolean, default=False)
    execution_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    export_format: Mapped[str | None] = mapped_column(String(10), nullable=True)
    favorite_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    admin_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False)
    command_tag: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class CoreQueryFavorite(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "core_query_favorites"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(20))  # assistant|builder|sql
    question: Mapped[str | None] = mapped_column(Text, nullable=True)
    sql_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    builder_spec: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    run_count: Mapped[int] = mapped_column(Integer, default=0)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
