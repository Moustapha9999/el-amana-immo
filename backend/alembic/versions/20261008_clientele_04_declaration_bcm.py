"""Déclaration mensuelle BCM — une ligne par mois, snapshot à la validation.

Additif. Ne pas appliquer sur la production avant validation sur
``bea_digital_clientele_test``. Pas de FK vers le référentiel clients.

Revision ID: 20261008_clientele_04
Revises: 20261008_clientele_03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261008_clientele_04"
down_revision: Union[str, None] = "20261008_clientele_03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("clientele_declarations_bcm"):
        return
    op.create_table(
        "clientele_declarations_bcm",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("annee", sa.Integer(), nullable=False),
        sa.Column("mois", sa.Integer(), nullable=False),
        sa.Column("date_debut", sa.Date(), nullable=False),
        sa.Column("date_fin", sa.Date(), nullable=False),
        sa.Column("fin_mois_precedent", sa.Date(), nullable=False),
        sa.Column("statut", sa.String(20), nullable=False, server_default="BROUILLON"),
        sa.Column("moteur_version", sa.String(40), nullable=True),
        sa.Column("grille_version", sa.String(40), nullable=True),
        sa.Column("cellules", postgresql.JSONB(), nullable=True),
        sa.Column("controles", postgresql.JSONB(), nullable=True),
        sa.Column("populations", postgresql.JSONB(), nullable=True),
        sa.Column("commentaire", sa.Text(), nullable=True),
        sa.Column("created_by_id", _UUID, sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("calculee_le", sa.DateTime(timezone=True), nullable=True),
        sa.Column("calculee_par_id", _UUID, sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("controlee_le", sa.DateTime(timezone=True), nullable=True),
        sa.Column("controlee_par_id", _UUID, sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("validee_le", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validee_par_id", _UUID, sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("cloturee_le", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cloturee_par_id", _UUID, sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("archivee_le", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("annee", "mois", name="uq_clientele_declarations_bcm_periode"),
        sa.CheckConstraint("mois BETWEEN 1 AND 12", name="ck_clientele_declarations_bcm_mois"),
        sa.CheckConstraint(
            "statut IN ('BROUILLON','CALCULEE','A_CONTROLER','VALIDEE','CLOTUREE','ARCHIVEE')",
            name="ck_clientele_declarations_bcm_statut",
        ),
    )
    op.create_index("ix_clientele_declarations_bcm_statut", "clientele_declarations_bcm",
                    ["statut"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("clientele_declarations_bcm"):
        op.drop_table("clientele_declarations_bcm")
