"""Contexte espace/module sur audit, notifications et grants.

Revision ID: 20260917_audit_context
Revises: 20260917_dual_auth

Colonnes additives nullable (ou défaut serveur) : aucune donnée métier
n'est réécrite. Compatible avec le module Immobilisations existant.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260917_audit_context"
down_revision: Union[str, None] = "20260917_dual_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("audit_logs", sa.Column("espace_code", sa.String(length=80), nullable=True))
    op.add_column("audit_logs", sa.Column("module_code", sa.String(length=80), nullable=True))
    op.add_column("audit_logs", sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index("ix_audit_logs_espace_code", "audit_logs", ["espace_code"])
    op.create_index("ix_audit_logs_module_code", "audit_logs", ["module_code"])

    op.add_column("notifications", sa.Column("espace_code", sa.String(length=80), nullable=True))
    op.add_column("notifications", sa.Column("module_code", sa.String(length=80), nullable=True))
    op.create_index("ix_notifications_espace_code", "notifications", ["espace_code"])
    op.create_index("ix_notifications_module_code", "notifications", ["module_code"])

    op.add_column(
        "user_espace_acces",
        sa.Column("status", sa.String(length=20), nullable=False, server_default="actif"),
    )
    op.add_column(
        "user_espace_acces",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.add_column(
        "user_espace_acces",
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_user_espace_acces_created_by",
        "user_espace_acces",
        "users",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "user_module_acces",
        sa.Column("status", sa.String(length=20), nullable=False, server_default="actif"),
    )
    op.add_column(
        "user_module_acces",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.add_column(
        "user_module_acces",
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_user_module_acces_created_by",
        "user_module_acces",
        "users",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_user_module_acces_created_by", "user_module_acces", type_="foreignkey")
    op.drop_column("user_module_acces", "created_by")
    op.drop_column("user_module_acces", "created_at")
    op.drop_column("user_module_acces", "status")

    op.drop_constraint("fk_user_espace_acces_created_by", "user_espace_acces", type_="foreignkey")
    op.drop_column("user_espace_acces", "created_by")
    op.drop_column("user_espace_acces", "created_at")
    op.drop_column("user_espace_acces", "status")

    op.drop_index("ix_notifications_module_code", table_name="notifications")
    op.drop_index("ix_notifications_espace_code", table_name="notifications")
    op.drop_column("notifications", "module_code")
    op.drop_column("notifications", "espace_code")

    op.drop_index("ix_audit_logs_module_code", table_name="audit_logs")
    op.drop_index("ix_audit_logs_espace_code", table_name="audit_logs")
    op.drop_column("audit_logs", "session_id")
    op.drop_column("audit_logs", "module_code")
    op.drop_column("audit_logs", "espace_code")
