"""Réclamations — notes jointes et suppression logique (corbeille).

Additif :
- catégories de pièces ``NOTE``, ``COURRIER``, ``JUSTIFICATIF`` (contrainte élargie, rien n'est reclassé) ;
- colonnes ``supprimee_le``, ``supprimee_par_id``, ``motif_suppression`` sur ``reclamations``.
Aucune suppression physique n'est introduite : la chronologie reste en ajout seul.

Revision ID: 20261014_reclamations_03
Revises: 20261014_reclamations_02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261014_reclamations_03"
down_revision: Union[str, None] = "20261014_reclamations_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CATEGORIES = ("NOTE", "COURRIER", "JUSTIFICATIF", "ORIGINAL", "PIECE_CLIENT", "TRANSMISSION", "FICHE_TRAITEMENT",
              "JUSTIFICATIF_SERVICE", "RETOUR_SERVICE", "REPONSE_CLIENT", "PREUVE_ENVOI", "AUTRE")
ANCIENNES = CATEGORIES[3:]


def _in(colonne: str, valeurs: tuple[str, ...]) -> str:
    return f"{colonne} IN ({','.join(repr(v) for v in valeurs)})"


def upgrade() -> None:
    op.execute("ALTER TABLE reclamation_documents DROP CONSTRAINT IF EXISTS ck_reclamation_documents_categorie")
    op.create_check_constraint("ck_reclamation_documents_categorie", "reclamation_documents",
                               _in("categorie", CATEGORIES))

    colonnes = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("reclamations")}
    if "supprimee_le" not in colonnes:
        op.add_column("reclamations", sa.Column("supprimee_le", sa.DateTime(timezone=True), nullable=True))
        op.create_index("ix_reclamations_supprimee_le", "reclamations", ["supprimee_le"])
    if "supprimee_par_id" not in colonnes:
        op.add_column("reclamations", sa.Column(
            "supprimee_par_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True))
    if "motif_suppression" not in colonnes:
        op.add_column("reclamations", sa.Column("motif_suppression", sa.Text(), nullable=True))


def downgrade() -> None:
    op.execute("UPDATE reclamation_documents SET categorie = 'AUTRE' WHERE categorie IN ('NOTE', 'COURRIER', 'JUSTIFICATIF')")
    op.execute("ALTER TABLE reclamation_documents DROP CONSTRAINT IF EXISTS ck_reclamation_documents_categorie")
    op.create_check_constraint("ck_reclamation_documents_categorie", "reclamation_documents",
                               _in("categorie", ANCIENNES))
    op.drop_index("ix_reclamations_supprimee_le", table_name="reclamations")
    for col in ("motif_suppression", "supprimee_par_id", "supprimee_le"):
        op.drop_column("reclamations", col)
