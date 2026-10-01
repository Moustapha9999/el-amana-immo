"""Stock v3 — réception BC + quantités reçues (additif).

Revision ID: 20260921_mg_stock_v3
Revises: 20260921_mg_stock_v2
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260921_mg_stock_v3"
down_revision: Union[str, None] = "20260921_mg_stock_v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "mg_bc_lignes",
        sa.Column("article_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mg_articles.id"), nullable=True),
    )
    op.add_column(
        "mg_bc_lignes",
        sa.Column("quantite_recue", sa.Numeric(18, 3), nullable=False, server_default="0"),
    )
    op.create_index("ix_mg_bc_lignes_article_id", "mg_bc_lignes", ["article_id"])


def downgrade() -> None:
    op.drop_index("ix_mg_bc_lignes_article_id", table_name="mg_bc_lignes")
    op.drop_column("mg_bc_lignes", "quantite_recue")
    op.drop_column("mg_bc_lignes", "article_id")
