"""Validations trimestrielles d'amortissement par catégorie.

Revision ID: 20260730_periodes_categories
Revises: 20260729_periodes
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260730_periodes_categories"
down_revision: Union[str, None] = "20260729_periodes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "periodes_amortissement_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("periode_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("categorie_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("statut", sa.String(length=20), nullable=False, server_default="en_attente"),
        sa.Column("valide_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valide_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("total_dotation", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("nb_dotations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["periode_id"], ["periodes_amortissement.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["categorie_id"], ["categories_immobilisation.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["valide_by_id"], ["users.id"]),
        sa.UniqueConstraint(
            "periode_id", "categorie_id", name="uq_periode_amort_categorie"
        ),
    )
    op.create_index(
        "ix_periodes_amort_cat_periode_id",
        "periodes_amortissement_categories",
        ["periode_id"],
    )
    op.create_index(
        "ix_periodes_amort_cat_categorie_id",
        "periodes_amortissement_categories",
        ["categorie_id"],
    )
    op.create_index(
        "ix_periodes_amort_cat_statut",
        "periodes_amortissement_categories",
        ["statut"],
    )

    # Les périodes globalement validées couvrent toutes les catégories.
    op.execute(
        """
        INSERT INTO periodes_amortissement_categories (
            id, periode_id, categorie_id, statut, valide_at, valide_by_id,
            total_dotation, nb_dotations, created_at, updated_at
        )
        SELECT
            gen_random_uuid(), p.id, c.id, p.statut, p.valide_at, p.valide_by_id,
            0, 0, now(), now()
        FROM periodes_amortissement p
        CROSS JOIN categories_immobilisation c
        WHERE p.statut IN ('validee', 'cloturee')
          AND c.amortissable IS TRUE
          AND c.deleted_at IS NULL
        """
    )

    # Reconstitue les catégories déjà comptabilisées dans une période partielle.
    op.execute(
        """
        INSERT INTO periodes_amortissement_categories (
            id, periode_id, categorie_id, statut, valide_at,
            total_dotation, nb_dotations, created_at, updated_at
        )
        SELECT
            gen_random_uuid(), p.id, i.categorie_id, 'validee', max(a.updated_at),
            sum(a.montant), count(a.id), now(), now()
        FROM periodes_amortissement p
        JOIN amortissements a ON a.periode = p.code
        JOIN immobilisations i ON i.id = a.immobilisation_id
        WHERE p.statut = 'calculee'
          AND a.valide IS TRUE
          AND a.annule IS FALSE
          AND a.simule IS FALSE
          AND i.categorie_id IS NOT NULL
        GROUP BY p.id, i.categorie_id
        ON CONFLICT (periode_id, categorie_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_periodes_amort_cat_statut",
        table_name="periodes_amortissement_categories",
    )
    op.drop_index(
        "ix_periodes_amort_cat_categorie_id",
        table_name="periodes_amortissement_categories",
    )
    op.drop_index(
        "ix_periodes_amort_cat_periode_id",
        table_name="periodes_amortissement_categories",
    )
    op.drop_table("periodes_amortissement_categories")
