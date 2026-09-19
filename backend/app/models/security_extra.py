"""Historique mots de passe + incidents sécurité."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class PasswordHistory(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "password_history"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SecurityIncident(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "security_incidents"

    titre: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    type_incident: Mapped[str] = mapped_column(String(40), default="autre", index=True)
    niveau: Mapped[str] = mapped_column(String(20), default="info", index=True)
    statut: Mapped[str] = mapped_column(String(30), default="ouvert", index=True)
    actions: Mapped[str | None] = mapped_column(Text, nullable=True)
    responsable: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    module_code: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    espace_code: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    user_concerne_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PasswordResetJti(Base):
    """Anti-rejeu tokens reset MDP (préparé pour SMTP futur)."""

    __tablename__ = "password_reset_jtis"

    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
