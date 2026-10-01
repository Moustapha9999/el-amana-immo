"""Contrats MG — reconduction, préavis, version, avenants ; TVA par défaut 16 %.

Revision ID: 20261001_contrats_avenants
Revises: 20260930_achats_invariants
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "20261001_contrats_avenants"
down_revision: Union[str, None] = "20260930_achats_invariants"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("mg_contrats")}
    if "reconduction" not in cols:
        op.add_column(
            "mg_contrats",
            sa.Column("reconduction", sa.String(20), nullable=False, server_default="AUCUNE"),
        )
    if "preavis_jours" not in cols:
        op.add_column("mg_contrats", sa.Column("preavis_jours", sa.Integer(), nullable=True))
    if "version" not in cols:
        op.add_column("mg_contrats", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))

    if not insp.has_table("mg_contrat_avenants"):
        op.create_table(
            "mg_contrat_avenants",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "contrat_id",
                UUID(as_uuid=True),
                sa.ForeignKey("mg_contrats.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("numero", sa.Integer(), nullable=False),
            sa.Column("type_avenant", sa.String(30), nullable=False),
            sa.Column("objet", sa.String(255), nullable=False),
            sa.Column("date_effet", sa.Date(), nullable=False),
            sa.Column("montant_ht_avant", sa.Numeric(18, 2), nullable=True),
            sa.Column("montant_ht_apres", sa.Numeric(18, 2), nullable=True),
            sa.Column("montant_ttc_avant", sa.Numeric(18, 2), nullable=True),
            sa.Column("montant_ttc_apres", sa.Numeric(18, 2), nullable=True),
            sa.Column("date_fin_avant", sa.Date(), nullable=True),
            sa.Column("date_fin_apres", sa.Date(), nullable=True),
            sa.Column("clauses", sa.Text(), nullable=True),
            sa.Column("version_contrat", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("user_nom", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("contrat_id", "numero", name="uq_mg_contrat_avenants_numero"),
        )
        op.create_index("ix_mg_contrat_avenants_contrat_id", "mg_contrat_avenants", ["contrat_id"])

    op.execute(
        "UPDATE mg_contrat_parametres SET valeur = '16' WHERE cle = 'contrats.taux_tva' AND valeur IN ('', '0')"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS mg_contrat_avenants")
    op.execute("ALTER TABLE mg_contrats DROP COLUMN IF EXISTS version")
    op.execute("ALTER TABLE mg_contrats DROP COLUMN IF EXISTS preavis_jours")
    op.execute("ALTER TABLE mg_contrats DROP COLUMN IF EXISTS reconduction")
