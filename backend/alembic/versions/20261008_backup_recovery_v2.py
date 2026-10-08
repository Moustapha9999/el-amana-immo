"""CORE ADMIN — Sauvegardes & Recovery v2 : intégrité, manifeste, motif, téléchargement.

Additif : colonnes nullables sur ``platform_backups`` / ``platform_restores`` et
permission ``core.admin.backup.download``. Aucune table métier modifiée.

Revision ID: 20261008_backup_recovery_v2
Revises: 20261007_formation_module
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261008_backup_recovery_v2"
down_revision: Union[str, None] = "20261007_formation_module"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_PERMS = [
    ("core.admin.backup.download", "Téléchargement des sauvegardes (CORE ADMIN)", "core"),
]

_JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.add_column("platform_backups", sa.Column("checksum_sha256", sa.String(64), nullable=True))
    op.add_column("platform_backups", sa.Column("artifacts", _JSONB, nullable=True))
    op.add_column("platform_backups", sa.Column("manifest", _JSONB, nullable=True))
    op.add_column("platform_backups", sa.Column("duration_ms", sa.Integer(), nullable=True))
    op.add_column("platform_backups", sa.Column("integrity_status", sa.String(20), nullable=True))
    op.add_column(
        "platform_backups",
        sa.Column("integrity_checked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("platform_backups", sa.Column("integrity_detail", sa.Text(), nullable=True))
    op.add_column("platform_backups", sa.Column("ip_address", sa.String(45), nullable=True))
    op.create_index("ix_platform_backups_created_at", "platform_backups", ["created_at"])

    op.add_column("platform_restores", sa.Column("duration_ms", sa.Integer(), nullable=True))
    op.add_column("platform_restores", sa.Column("reason", sa.Text(), nullable=True))
    op.add_column("platform_restores", sa.Column("ip_address", sa.String(45), nullable=True))
    op.add_column("platform_restores", sa.Column("options", _JSONB, nullable=True))
    op.add_column("platform_restores", sa.Column("details", _JSONB, nullable=True))
    op.create_index("ix_platform_restores_created_at", "platform_restores", ["created_at"])

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
    conn = op.get_bind()
    for code, _, _ in _NEW_PERMS:
        conn.execute(sa.text("DELETE FROM permissions WHERE code = :code"), {"code": code})
    op.drop_index("ix_platform_restores_created_at", table_name="platform_restores")
    for col in ("details", "options", "ip_address", "reason", "duration_ms"):
        op.drop_column("platform_restores", col)
    op.drop_index("ix_platform_backups_created_at", table_name="platform_backups")
    for col in (
        "ip_address",
        "integrity_detail",
        "integrity_checked_at",
        "integrity_status",
        "duration_ms",
        "manifest",
        "artifacts",
        "checksum_sha256",
    ):
        op.drop_column("platform_backups", col)
