"""Ops CORE ADMIN — backups, recovery, versions, flags (hors tables métier immo)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class PlatformBackup(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "platform_backups"

    level: Mapped[str] = mapped_column(String(20), index=True)  # global|departement|module
    backup_type: Mapped[str] = mapped_column(String(40), index=True)
    espace_code: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    module_code: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    uploads_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    tables_included: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    shared_dependencies: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)

    restores: Mapped[list[PlatformRestore]] = relationship(
        back_populates="backup",
        foreign_keys="PlatformRestore.backup_id",
    )


class PlatformRestore(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "platform_restores"

    backup_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform_backups.id", ondelete="RESTRICT"), index=True
    )
    safety_backup_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform_backups.id", ondelete="SET NULL"), nullable=True
    )
    level: Mapped[str] = mapped_column(String(20), index=True)
    espace_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    module_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    dependency_warning: Mapped[str | None] = mapped_column(Text, nullable=True)
    acknowledged_dependencies: Mapped[bool] = mapped_column(Boolean, default=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    backup: Mapped[PlatformBackup] = relationship(
        back_populates="restores",
        foreign_keys=[backup_id],
    )


class PlatformModuleVersion(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "platform_module_versions"

    module_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plateforme_modules.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[str] = mapped_column(String(40))
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PlatformOpsFlag(Base):
    __tablename__ = "platform_ops_flags"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
