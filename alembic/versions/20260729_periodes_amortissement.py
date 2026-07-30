"""Périodes trimestrielles chronologiques d'amortissement.

Revision ID: 20260729_periodes
Revises: 20260729_exercices
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260729_periodes"
down_revision: Union[str, None] = "20260729_exercices"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "periodes_amortissement",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("exercice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("annee", sa.Integer(), nullable=False),
        sa.Column("trimestre", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("date_arrete", sa.Date(), nullable=False),
        sa.Column("statut", sa.String(length=20), nullable=False, server_default="en_attente"),
        sa.Column("calcule_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valide_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valide_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("total_dotation", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("nb_dotations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["exercice_id"], ["exercices_comptables.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["valide_by_id"], ["users.id"]),
        sa.UniqueConstraint(
            "exercice_id", "trimestre", name="uq_periode_amort_exercice_trimestre"
        ),
        sa.CheckConstraint("trimestre BETWEEN 1 AND 4", name="ck_periode_amort_trimestre"),
    )
    op.create_index("ix_periodes_amortissement_exercice_id", "periodes_amortissement", ["exercice_id"])
    op.create_index("ix_periodes_amortissement_annee", "periodes_amortissement", ["annee"])
    op.create_index("ix_periodes_amortissement_code", "periodes_amortissement", ["code"])
    op.create_index("ix_periodes_amortissement_statut", "periodes_amortissement", ["statut"])

    # Les exercices déjà ouverts démarrent à T1. Les validations individuelles
    # antérieures restent intactes, mais ne valent pas validation globale de période.
    op.execute(
        """
        INSERT INTO periodes_amortissement (
            id, exercice_id, annee, trimestre, code, date_arrete, statut,
            total_dotation, nb_dotations, created_at, updated_at
        )
        SELECT
            gen_random_uuid(), e.id, e.annee, q.trimestre,
            e.annee::text || '-Q' || q.trimestre::text,
            make_date(e.annee, q.trimestre * 3, 1)
                + interval '1 month' - interval '1 day',
            CASE
                WHEN e.statut = 'cloture' THEN 'cloturee'
                WHEN q.trimestre = 1 THEN 'ouverte'
                ELSE 'en_attente'
            END,
            0, 0, now(), now()
        FROM exercices_comptables e
        CROSS JOIN (VALUES (1), (2), (3), (4)) AS q(trimestre)
        """
    )


def downgrade() -> None:
    op.drop_index("ix_periodes_amortissement_statut", table_name="periodes_amortissement")
    op.drop_index("ix_periodes_amortissement_code", table_name="periodes_amortissement")
    op.drop_index("ix_periodes_amortissement_annee", table_name="periodes_amortissement")
    op.drop_index("ix_periodes_amortissement_exercice_id", table_name="periodes_amortissement")
    op.drop_table("periodes_amortissement")
