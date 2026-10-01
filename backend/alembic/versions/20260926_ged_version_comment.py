"""GED — version_comment pour versioning documentaire.

Revision ID: 20260926_ged_version_comment
Revises: 20260926_ged_ocr
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260926_ged_version_comment"
down_revision: Union[str, None] = "20260926_ged_ocr"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ged_documents",
        sa.Column("version_comment", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ged_documents", "version_comment")
