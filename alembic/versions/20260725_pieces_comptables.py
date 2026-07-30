"""Pièces comptables — type, journée, référence.

Revision ID: 20260725_pieces
Revises: 20260724_cession
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260725_pieces"
down_revision: Union[str, None] = "20260724_cession"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_type_piece = sa.Enum(
    "facture",
    "pv",
    "bon_commande",
    "bon_livraison",
    "contrat",
    "autre",
    name="typepiececomptable",
)


def upgrade() -> None:
    _type_piece.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "pieces_jointes",
        sa.Column("type_piece", _type_piece, nullable=False, server_default="facture"),
    )
    op.add_column(
        "pieces_jointes",
        sa.Column("date_journee", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")),
    )
    op.add_column("pieces_jointes", sa.Column("reference", sa.String(length=120), nullable=True))
    op.add_column("pieces_jointes", sa.Column("libelle", sa.String(length=255), nullable=True))
    op.add_column(
        "pieces_jointes",
        sa.Column("uploaded_by_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_pieces_jointes_uploaded_by",
        "pieces_jointes",
        "users",
        ["uploaded_by_id"],
        ["id"],
    )
    op.create_index("ix_pieces_jointes_type_piece", "pieces_jointes", ["type_piece"])
    op.create_index("ix_pieces_jointes_date_journee", "pieces_jointes", ["date_journee"])
    op.alter_column("pieces_jointes", "type_piece", server_default=None)
    op.alter_column("pieces_jointes", "date_journee", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_pieces_jointes_date_journee", table_name="pieces_jointes")
    op.drop_index("ix_pieces_jointes_type_piece", table_name="pieces_jointes")
    op.drop_constraint("fk_pieces_jointes_uploaded_by", "pieces_jointes", type_="foreignkey")
    op.drop_column("pieces_jointes", "uploaded_by_id")
    op.drop_column("pieces_jointes", "libelle")
    op.drop_column("pieces_jointes", "reference")
    op.drop_column("pieces_jointes", "date_journee")
    op.drop_column("pieces_jointes", "type_piece")
    _type_piece.drop(op.get_bind(), checkfirst=True)
