"""Facturation Fournisseurs — taux de TVA par profil, datés.

* ``mg_facturation_tva`` : taux applicable à un profil sur une période (début / fin facultatifs).
  Le taux d'une facture = celui en vigueur à sa date de facture ; aucun taux = aucun calcul.
* Reprise des taux déjà portés par ``mg_facturation_profils.taux_tva`` (sans date de début).
  La colonne reste en place comme valeur courante, recalculée à chaque modification.

Revision ID: 20261006_mg_facturation_tva
Revises: 20261006_mg_facturation_profils
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261006_mg_facturation_tva"
down_revision: Union[str, None] = "20261006_mg_facturation_profils"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mg_facturation_tva",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profil_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mg_facturation_profils.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("taux", sa.Numeric(5, 2), nullable=False),
        sa.Column("date_debut", sa.Date(), nullable=True),
        sa.Column("date_fin", sa.Date(), nullable=True),
        sa.Column("observation", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("taux >= 0 AND taux <= 100", name="ck_mg_facturation_tva_taux"),
        sa.CheckConstraint(
            "date_debut IS NULL OR date_fin IS NULL OR date_fin >= date_debut", name="ck_mg_facturation_tva_periode"
        ),
    )
    op.execute(
        "INSERT INTO mg_facturation_tva (id, profil_id, taux, observation) "
        "SELECT gen_random_uuid(), id, taux_tva, 'Repris du profil' FROM mg_facturation_profils WHERE taux_tva IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_table("mg_facturation_tva")
