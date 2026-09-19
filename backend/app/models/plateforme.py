"""Catalogue BEA DIGITAL (espaces / modules) — distinct du référentiel org `departements`."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.associations import user_espace_acces_table, user_module_acces_table
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.auth import User


class PlateformeEspace(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "plateforme_espaces"

    code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    route: Mapped[str | None] = mapped_column(String(160), nullable=True)
    statut: Mapped[str] = mapped_column(String(20), default="bientot", index=True)
    status_message: Mapped[str] = mapped_column(Text, default="")
    maintenance_starts_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    maintenance_ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    modules: Mapped[list[PlateformeModule]] = relationship(back_populates="espace")
    users: Mapped[list[User]] = relationship(
        secondary=user_espace_acces_table,
        back_populates="espaces",
    )


class PlateformeModule(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "plateforme_modules"

    espace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plateforme_espaces.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    entry_path: Mapped[str | None] = mapped_column(String(160), nullable=True)
    statut: Mapped[str] = mapped_column(String(20), default="bientot", index=True)
    status_message: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[str] = mapped_column(String(40), default="1.0.0")
    maintenance_starts_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    maintenance_ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    admins_bypass_maintenance: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    espace: Mapped[PlateformeEspace] = relationship(back_populates="modules")
    users: Mapped[list[User]] = relationship(
        secondary=user_module_acces_table,
        back_populates="modules",
    )
