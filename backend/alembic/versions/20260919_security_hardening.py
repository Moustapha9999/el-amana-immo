"""Sécurité renforcée : historique MDP, incidents, TOTP at-rest, anti-rejeu reset.

Revision ID: 20260919_security_hardening
Revises: 20260918_notif_center
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260919_security_hardening"
down_revision: Union[str, None] = "20260918_notif_center"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "totp_secret",
        existing_type=sa.String(length=64),
        type_=sa.String(length=255),
        existing_nullable=True,
    )
    op.create_table(
        "password_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_password_history_user_id", "password_history", ["user_id"])

    op.create_table(
        "security_incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("titre", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("niveau", sa.String(20), nullable=False, server_default="info"),
        sa.Column("statut", sa.String(30), nullable=False, server_default="ouvert"),
        sa.Column("actions", sa.Text(), nullable=True),
        sa.Column("responsable", sa.String(255), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_security_incidents_niveau", "security_incidents", ["niveau"])
    op.create_index("ix_security_incidents_statut", "security_incidents", ["statut"])

    op.create_table(
        "password_reset_jtis",
        sa.Column("jti", sa.String(64), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_password_reset_jtis_user_id", "password_reset_jtis", ["user_id"])


def downgrade() -> None:
    op.drop_table("password_reset_jtis")
    op.drop_table("security_incidents")
    op.drop_table("password_history")
    op.alter_column(
        "users",
        "totp_secret",
        existing_type=sa.String(length=255),
        type_=sa.String(length=64),
        existing_nullable=True,
    )
