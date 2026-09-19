"""Incidents sécurité enrichis (type, module, user concerné).

Revision ID: 20260919_security_center
Revises: 20260919_security_hardening
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260919_security_center"
down_revision: Union[str, None] = "20260919_security_hardening"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "security_incidents",
        sa.Column("type_incident", sa.String(length=40), server_default="autre", nullable=False),
    )
    op.add_column(
        "security_incidents",
        sa.Column("module_code", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "security_incidents",
        sa.Column("espace_code", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "security_incidents",
        sa.Column("user_concerne_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_security_incidents_type_incident", "security_incidents", ["type_incident"])
    op.create_index("ix_security_incidents_module_code", "security_incidents", ["module_code"])
    op.create_index("ix_security_incidents_espace_code", "security_incidents", ["espace_code"])
    op.create_index(
        "ix_security_incidents_user_concerne_id", "security_incidents", ["user_concerne_id"]
    )
    op.create_foreign_key(
        "fk_security_incidents_user_concerne",
        "security_incidents",
        "users",
        ["user_concerne_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_security_incidents_user_concerne", "security_incidents", type_="foreignkey")
    op.drop_index("ix_security_incidents_user_concerne_id", table_name="security_incidents")
    op.drop_index("ix_security_incidents_espace_code", table_name="security_incidents")
    op.drop_index("ix_security_incidents_module_code", table_name="security_incidents")
    op.drop_index("ix_security_incidents_type_incident", table_name="security_incidents")
    op.drop_column("security_incidents", "user_concerne_id")
    op.drop_column("security_incidents", "espace_code")
    op.drop_column("security_incidents", "module_code")
    op.drop_column("security_incidents", "type_incident")
