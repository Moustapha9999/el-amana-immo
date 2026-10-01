"""Notes de frais : table des paiements (une note → 0..n paiements).

Reprise : chaque note déjà (partiellement) payée reçoit un paiement « Reprise »
égal à son `montant_paye`, pour que le cumul reste la somme des paiements.
Le paiement partiel devient le comportement par défaut.

Revision ID: 20260930_mg_notes_paiements
Revises: 20260929_perm_stock_suppr_admin
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260930_mg_notes_paiements"
down_revision: Union[str, None] = "20260929_perm_stock_suppr_admin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "mg_note_frais_paiements"


def upgrade() -> None:
    if TABLE not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            TABLE,
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("numero", sa.String(40), nullable=False),
            sa.Column(
                "note_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("mg_notes_frais.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column("date_paiement", sa.Date(), nullable=False),
            sa.Column("montant", sa.Numeric(18, 2), nullable=False),
            sa.Column("mode_paiement", sa.String(40), nullable=False),
            sa.Column("reference", sa.String(120), nullable=True),
            sa.Column("numero_cheque", sa.String(60), nullable=True),
            sa.Column("banque", sa.String(120), nullable=True),
            sa.Column("compte", sa.String(120), nullable=True),
            sa.Column("observation", sa.Text(), nullable=True),
            sa.Column("statut", sa.String(20), nullable=False, server_default="VALIDE"),
            sa.Column("motif_annulation", sa.Text(), nullable=True),
            sa.Column("annule_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("annule_par_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("annule_par_nom", sa.String(255), nullable=True),
            sa.Column("created_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_by_nom", sa.String(255), nullable=True),
            sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("updated_by_nom", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("numero", name="uq_mg_note_frais_paiements_numero"),
            sa.CheckConstraint("montant > 0", name="ck_mg_note_frais_paiements_montant_positif"),
            sa.CheckConstraint("statut IN ('VALIDE', 'ANNULE')", name="ck_mg_note_frais_paiements_statut"),
        )
        for col in ("numero", "note_id", "date_paiement", "mode_paiement", "statut"):
            op.create_index(f"ix_{TABLE}_{col}", TABLE, [col])

    op.execute(
        f"""
        INSERT INTO {TABLE} (id, numero, note_id, date_paiement, montant, mode_paiement, reference,
                             observation, statut, created_at, updated_at)
        SELECT gen_random_uuid(),
               'PAY-' || to_char(COALESCE(n.date_paiement, n.updated_at::date), 'YYYY') || '-R'
                 || lpad((row_number() OVER (ORDER BY n.date_demande, n.reference))::text, 4, '0'),
               n.id,
               COALESCE(n.date_paiement, n.updated_at::date),
               n.montant_paye,
               COALESCE(NULLIF(n.mode_paiement, ''), 'Virement'),
               n.ref_paiement,
               COALESCE(n.commentaire_paiement, 'Reprise des paiements antérieurs'),
               'VALIDE', now(), now()
        FROM mg_notes_frais n
        WHERE n.montant_paye > 0
          AND NOT EXISTS (SELECT 1 FROM {TABLE} p WHERE p.note_id = n.id)
        """
    )
    op.execute(
        "UPDATE mg_note_frais_parametres SET valeur = 'true' "
        "WHERE cle = 'notes.paiement_partiel' AND lower(valeur) IN ('false', '0', 'non', 'no')"
    )


def downgrade() -> None:
    op.execute(f"DROP TABLE IF EXISTS {TABLE}")
