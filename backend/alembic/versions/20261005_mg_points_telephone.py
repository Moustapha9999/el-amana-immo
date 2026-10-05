"""Points de facturation — téléphone de contact du site.

Revision ID: 20261005_mg_points_telephone
Revises: 20261005_mg_facturation
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261005_mg_points_telephone"
down_revision: Union[str, None] = "20261005_mg_facturation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("mg_points_facturation")}
    if "telephone" not in cols:
        op.add_column("mg_points_facturation", sa.Column("telephone", sa.String(40), nullable=True))


def downgrade() -> None:
    op.drop_column("mg_points_facturation", "telephone")
