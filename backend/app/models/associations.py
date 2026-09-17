from sqlalchemy import Column, DateTime, ForeignKey, String, Table, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base

user_roles_table = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)

role_permissions_table = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "permission_id",
        UUID(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

user_espace_acces_table = Table(
    "user_espace_acces",
    Base.metadata,
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "espace_id",
        UUID(as_uuid=True),
        ForeignKey("plateforme_espaces.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("status", String(20), nullable=False, server_default="actif"),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column("created_by", UUID(as_uuid=True), nullable=True),
)

user_module_acces_table = Table(
    "user_module_acces",
    Base.metadata,
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "module_id",
        UUID(as_uuid=True),
        ForeignKey("plateforme_modules.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("status", String(20), nullable=False, server_default="actif"),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column("created_by", UUID(as_uuid=True), nullable=True),
)
