import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin


class ApiErrorEvent(Base, UUIDPrimaryKeyMixin):
    """Erreur API renvoyée à un utilisateur (supervision CORE ADMIN, lecture seule)."""

    __tablename__ = "api_error_events"

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    method: Mapped[str] = mapped_column(String(10))
    route: Mapped[str] = mapped_column(String(255))
    status_code: Mapped[int] = mapped_column(Integer, index=True)
    code: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    exception_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    module_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
