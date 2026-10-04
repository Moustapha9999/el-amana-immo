"""EER — suppression logique des dossiers (décision du 04/10/2026).

Additif : trois colonnes nullables sur ``eer_dossiers``. Le dossier supprimé disparaît des
listes et de l'API ; versions, historique, décisions et visas restent intacts (immuables).

Revision ID: 20261004_eer_05_suppression
Revises: 20261004_eer_04_suivi
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261004_eer_05_suppression"
down_revision: Union[str, None] = "20261004_eer_04_suivi"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    colonnes = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("eer_dossiers")}
    if "deleted_at" not in colonnes:
        op.add_column("eer_dossiers", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
        op.add_column("eer_dossiers", sa.Column("deleted_by_id", sa.UUID(), nullable=True))
        op.add_column("eer_dossiers", sa.Column("motif_suppression", sa.Text(), nullable=True))
        op.create_foreign_key("fk_eer_dossiers_deleted_by", "eer_dossiers", "users", ["deleted_by_id"], ["id"],
                              ondelete="SET NULL")
        op.create_check_constraint("ck_eer_dossiers_suppression", "eer_dossiers",
                                   "deleted_at IS NULL OR motif_suppression IS NOT NULL")
        op.create_index("ix_eer_dossiers_actifs", "eer_dossiers", ["created_at"],
                        postgresql_where=sa.text("deleted_at IS NULL"))


def downgrade() -> None:
    op.drop_index("ix_eer_dossiers_actifs", table_name="eer_dossiers")
    op.drop_constraint("ck_eer_dossiers_suppression", "eer_dossiers", type_="check")
    op.drop_constraint("fk_eer_dossiers_deleted_by", "eer_dossiers", type_="foreignkey")
    op.drop_column("eer_dossiers", "motif_suppression")
    op.drop_column("eer_dossiers", "deleted_by_id")
    op.drop_column("eer_dossiers", "deleted_at")
