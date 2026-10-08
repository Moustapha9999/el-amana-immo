"""CORE ADMIN — mode administrateur CORE QUERY + suppression de toute sauvegarde.

- ``core_query_logs`` : ``admin_mode``, ``dry_run``, ``command_tag``, ``reason``
  (traçabilité des requêtes d'écriture exécutées par un administrateur).
- Permission ``core.admin.query.admin`` (SQL sans restriction, écriture incluse).
- ``platform_restores.backup_id`` devient nullable, FK ``ON DELETE SET NULL`` :
  une sauvegarde déjà utilisée pour une restauration peut être supprimée,
  l'historique de restauration est conservé.

Revision ID: 20261008_admin_powers
Revises: 20261008_core_query
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261008_admin_powers"
down_revision: Union[str, None] = "20261008_core_query"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PERM = ("core.admin.query.admin", "CORE QUERY — mode administrateur : SQL sans restriction, écriture (CORE ADMIN)", "core")


def upgrade() -> None:
    op.add_column("core_query_logs", sa.Column("admin_mode", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("core_query_logs", sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("core_query_logs", sa.Column("command_tag", sa.String(120), nullable=True))
    op.add_column("core_query_logs", sa.Column("reason", sa.Text(), nullable=True))

    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO permissions (id, code, label, module, created_at, updated_at)
            SELECT gen_random_uuid(), :code, :label, :module, NOW(), NOW()
            WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = :code)
            """
        ),
        {"code": _PERM[0], "label": _PERM[1], "module": _PERM[2]},
    )

    op.drop_constraint("platform_restores_backup_id_fkey", "platform_restores", type_="foreignkey")
    op.alter_column("platform_restores", "backup_id", nullable=True)
    op.create_foreign_key(
        "platform_restores_backup_id_fkey", "platform_restores", "platform_backups",
        ["backup_id"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("platform_restores_backup_id_fkey", "platform_restores", type_="foreignkey")
    op.execute("DELETE FROM platform_restores WHERE backup_id IS NULL")
    op.alter_column("platform_restores", "backup_id", nullable=False)
    op.create_foreign_key(
        "platform_restores_backup_id_fkey", "platform_restores", "platform_backups",
        ["backup_id"], ["id"], ondelete="RESTRICT",
    )
    op.get_bind().execute(sa.text("DELETE FROM permissions WHERE code = :code"), {"code": _PERM[0]})
    for col in ("reason", "command_tag", "dry_run", "admin_mode"):
        op.drop_column("core_query_logs", col)
