import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import TypeNotification
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.auth import User


class Notification(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    type_notification: Mapped[TypeNotification] = mapped_column(Enum(TypeNotification))
    titre: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    lu: Mapped[bool] = mapped_column(Boolean, default=False)
    entity: Mapped[str | None] = mapped_column(String(80), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    espace_code: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    module_code: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    # Centre global (enrichissement ops) — distinct du journal d'audit.
    categorie: Mapped[str] = mapped_column(String(40), default="systeme", index=True)
    priorite: Mapped[str] = mapped_column(String(20), default="info", index=True)
    event_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    event_code: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    emetteur_type: Mapped[str] = mapped_column(String(40), default="systeme")
    emetteur_label: Mapped[str] = mapped_column(String(255), default="Système")
    destinataire_type: Mapped[str] = mapped_column(String(40), default="utilisateur")
    destinataire_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class AuditLog(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "audit_logs"

    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    before_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    espace_code: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    module_code: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User | None"] = relationship(foreign_keys=[user_id])
