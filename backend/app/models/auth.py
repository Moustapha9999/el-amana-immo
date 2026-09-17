from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.associations import (
    role_permissions_table,
    user_espace_acces_table,
    user_module_acces_table,
    user_roles_table,
)
from app.models.mixins import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

SESSION_KIND_PLATFORM = "platform"
SESSION_KIND_MODULE = "module"

if TYPE_CHECKING:
    from app.models.plateforme import PlateformeEspace, PlateformeModule


class Permission(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(255))
    module: Mapped[str] = mapped_column(String(80), index=True)


class Role(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "roles"

    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    permissions: Mapped[list["Permission"]] = relationship(secondary=role_permissions_table)


class Agence(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "agences"

    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    libelle: Mapped[str] = mapped_column(String(255))
    adresse: Mapped[str | None] = mapped_column(Text, nullable=True)
    ville: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Référentiel bancaire BEA (code banque / SWIFT)
    code_banque: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    banque_sigle: Mapped[str | None] = mapped_column(String(20), nullable=True)
    banque_raison_sociale: Mapped[str | None] = mapped_column(String(255), nullable=True)
    code_swift: Mapped[str | None] = mapped_column(String(20), nullable=True)


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    hashed_password: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    agence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agences.id"), nullable=True
    )

    roles: Mapped[list[Role]] = relationship(secondary=user_roles_table)
    sessions: Mapped[list["AuthSession"]] = relationship(back_populates="user")
    espaces: Mapped[list["PlateformeEspace"]] = relationship(
        secondary=user_espace_acces_table, back_populates="users"
    )
    modules: Mapped[list["PlateformeModule"]] = relationship(
        secondary=user_module_acces_table, back_populates="users"
    )

    @property
    def espace_codes(self) -> list[str]:
        return [e.code for e in self.espaces]

    @property
    def module_codes(self) -> list[str]:
        return [m.code for m in self.modules]


class AuthSession(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Session JWT révocable — Login 1 (platform) ou Login 2 (module)."""

    __tablename__ = "auth_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    refresh_jti: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), default=SESSION_KIND_PLATFORM, index=True)
    module_code: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    parent_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("auth_sessions.id"), nullable=True, index=True
    )

    user: Mapped[User] = relationship(back_populates="sessions")


class AuthLoginAttempt(Base, UUIDPrimaryKeyMixin):
    """Journal des tentatives Login 1 / Login 2 (succès, échec, lockout)."""

    __tablename__ = "auth_login_attempts"

    email: Mapped[str] = mapped_column(String(255), index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    login_kind: Mapped[str] = mapped_column(String(20), index=True)
    module_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
