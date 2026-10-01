"""Audit — identifiant de corrélation request_id.

Revision ID: 20260929_audit_request_id
Revises: 20260929_contrats_ref_paiement
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260929_audit_request_id"
down_revision: Union[str, None] = "20260929_contrats_ref_paiement"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("audit_logs")}
    if "request_id" not in cols:
        op.add_column("audit_logs", sa.Column("request_id", sa.String(64), nullable=True))
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_request_id ON audit_logs (request_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_audit_logs_request_id")
    op.execute("ALTER TABLE audit_logs DROP COLUMN IF EXISTS request_id")
