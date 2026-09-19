"""CORE ADMIN ops: backups, recovery, module status/version, flags.

Revision ID: 20260918_core_admin_ops
Revises: 20260917_ged_documents
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260918_core_admin_ops"
down_revision: Union[str, None] = "20260917_ged_documents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_PERMS = [
    ("core.admin.backup.view", "Consultation des sauvegardes (CORE ADMIN)", "core"),
    ("core.admin.backup.create", "Création de sauvegardes (CORE ADMIN)", "core"),
    ("core.admin.backup.delete", "Suppression de sauvegardes (CORE ADMIN)", "core"),
    ("core.admin.recovery.view", "Consultation recovery (CORE ADMIN)", "core"),
    ("core.admin.recovery.execute", "Exécution recovery (CORE ADMIN)", "core"),
    ("core.admin.monitoring.view", "Supervision plateforme (CORE ADMIN)", "core"),
    ("core.admin.maintenance.view", "Consultation maintenance (CORE ADMIN)", "core"),
    ("core.admin.maintenance.manage", "Gestion maintenance (CORE ADMIN)", "core"),
    ("core.admin.module_status.view", "Consultation état des modules (CORE ADMIN)", "core"),
    ("core.admin.module_status.manage", "Gestion état des modules (CORE ADMIN)", "core"),
    ("core.admin.versions.view", "Consultation versions modules (CORE ADMIN)", "core"),
    ("core.admin.versions.manage", "Gestion versions modules (CORE ADMIN)", "core"),
]


def upgrade() -> None:
    op.add_column(
        "plateforme_modules",
        sa.Column("status_message", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "plateforme_modules",
        sa.Column("version", sa.String(40), nullable=False, server_default="1.0.0"),
    )
    op.add_column(
        "plateforme_modules",
        sa.Column("maintenance_starts_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "plateforme_modules",
        sa.Column("maintenance_ends_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "plateforme_modules",
        sa.Column(
            "admins_bypass_maintenance",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )

    op.add_column(
        "plateforme_espaces",
        sa.Column("status_message", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "plateforme_espaces",
        sa.Column("maintenance_starts_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "plateforme_espaces",
        sa.Column("maintenance_ends_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "platform_ops_flags",
        sa.Column("key", sa.String(80), primary_key=True),
        sa.Column(
            "value",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "platform_backups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("level", sa.String(20), nullable=False),
        sa.Column("backup_type", sa.String(40), nullable=False),
        sa.Column("espace_code", sa.String(80), nullable=True),
        sa.Column("module_code", sa.String(80), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("file_path", sa.String(512), nullable=True),
        sa.Column("uploads_path", sa.String(512), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("tables_included", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("shared_dependencies", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_platform_backups_level", "platform_backups", ["level"])
    op.create_index("ix_platform_backups_backup_type", "platform_backups", ["backup_type"])
    op.create_index("ix_platform_backups_status", "platform_backups", ["status"])
    op.create_index("ix_platform_backups_espace_code", "platform_backups", ["espace_code"])
    op.create_index("ix_platform_backups_module_code", "platform_backups", ["module_code"])

    op.create_table(
        "platform_restores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("backup_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("safety_backup_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("level", sa.String(20), nullable=False),
        sa.Column("espace_code", sa.String(80), nullable=True),
        sa.Column("module_code", sa.String(80), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("dependency_warning", sa.Text(), nullable=True),
        sa.Column(
            "acknowledged_dependencies",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["backup_id"], ["platform_backups.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["safety_backup_id"], ["platform_backups.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_platform_restores_backup_id", "platform_restores", ["backup_id"])
    op.create_index("ix_platform_restores_status", "platform_restores", ["status"])
    op.create_index("ix_platform_restores_level", "platform_restores", ["level"])

    op.create_table(
        "platform_module_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("module_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["module_id"], ["plateforme_modules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_platform_module_versions_module_id", "platform_module_versions", ["module_id"]
    )

    conn = op.get_bind()
    for code, label, module in _NEW_PERMS:
        conn.execute(
            sa.text(
                """
                INSERT INTO permissions (id, code, label, module, created_at, updated_at)
                SELECT gen_random_uuid(), :code, :label, :module, NOW(), NOW()
                WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = :code)
                """
            ),
            {"code": code, "label": label, "module": module},
        )


def downgrade() -> None:
    op.drop_table("platform_module_versions")
    op.drop_table("platform_restores")
    op.drop_table("platform_backups")
    op.drop_table("platform_ops_flags")
    op.drop_column("plateforme_espaces", "maintenance_ends_at")
    op.drop_column("plateforme_espaces", "maintenance_starts_at")
    op.drop_column("plateforme_espaces", "status_message")
    op.drop_column("plateforme_modules", "admins_bypass_maintenance")
    op.drop_column("plateforme_modules", "maintenance_ends_at")
    op.drop_column("plateforme_modules", "maintenance_starts_at")
    op.drop_column("plateforme_modules", "version")
    op.drop_column("plateforme_modules", "status_message")
    conn = op.get_bind()
    for code, _, _ in _NEW_PERMS:
        conn.execute(sa.text("DELETE FROM permissions WHERE code = :code"), {"code": code})
