"""Déclaration BCM : décisions sur les règles de calcul. Additif.

``clientele_bcm_regles`` : une ligne par décision (code de règle, valeur, statut CONFIRMEE / A_VALIDER,
motif, auteur). La dernière décision par code s'applique ; sans décision, la valeur par défaut documentée
dans ``app/data/clientele_bcm_regles.py``. Ni modifiable ni supprimable (déclencheurs).

Revision ID: 20261019_clientele_12
Revises: 20261016_reclamations_10
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261019_clientele_12"
down_revision: Union[str, None] = "20261016_reclamations_10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "clientele_bcm_regles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(60), nullable=False),
        sa.Column("valeur", postgresql.JSONB(), nullable=False),
        sa.Column("statut", sa.String(12), nullable=False),
        sa.Column("motif", sa.Text(), nullable=False),
        sa.Column("decide_par_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decide_par_nom", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("statut IN ('CONFIRMEE','A_VALIDER')", name="ck_clientele_bcm_regles_statut"),
    )
    op.create_index("ix_clientele_bcm_regles_code", "clientele_bcm_regles", ["code", "created_at"])
    op.execute("""
        CREATE OR REPLACE FUNCTION clientele_bcm_regles_immuable() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'UPDATE' AND NEW.decide_par_id IS NULL
               AND (to_jsonb(NEW) - 'decide_par_id') = (to_jsonb(OLD) - 'decide_par_id') THEN
                RETURN NEW;
            END IF;
            RAISE EXCEPTION 'Règles BCM : décision ni modifiable ni supprimable' USING ERRCODE = 'P0001';
        END $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_clientele_bcm_regles_immuable BEFORE UPDATE OR DELETE ON clientele_bcm_regles
        FOR EACH ROW EXECUTE FUNCTION clientele_bcm_regles_immuable()
    """)
    op.execute("""
        CREATE TRIGGER trg_clientele_bcm_regles_truncate BEFORE TRUNCATE ON clientele_bcm_regles
        FOR EACH STATEMENT EXECUTE FUNCTION clientele_bcm_regles_immuable()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_clientele_bcm_regles_truncate ON clientele_bcm_regles")
    op.execute("DROP TRIGGER IF EXISTS trg_clientele_bcm_regles_immuable ON clientele_bcm_regles")
    op.execute("DROP FUNCTION IF EXISTS clientele_bcm_regles_immuable()")
    op.drop_index("ix_clientele_bcm_regles_code", table_name="clientele_bcm_regles")
    op.drop_table("clientele_bcm_regles")
