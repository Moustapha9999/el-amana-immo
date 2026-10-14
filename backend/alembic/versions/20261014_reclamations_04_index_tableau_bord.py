"""Réclamations — index du tableau de bord 360°.

Additif, sans réécriture de données :
- ``ix_reclamations_actives_echeance`` : index partiel des dossiers actifs (non supprimés, non
  archivés, non terminés) sur l'échéance — retards, échéances à 7 jours, job d'alertes ;
- ``ix_reclamations_racine_reception`` : récurrence par client (racine) sur la période.

Revision ID: 20261014_reclamations_04
Revises: 20261014_reclamations_03
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20261014_reclamations_04"
down_revision: Union[str, None] = "20261014_reclamations_03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_reclamations_actives_echeance ON reclamations (echeance) "
        "WHERE supprimee_le IS NULL AND archivee_le IS NULL "
        "AND statut NOT IN ('CLOTUREE', 'REJETEE', 'ANNULEE')"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_reclamations_racine_reception "
        "ON reclamations (client_racine, date_premiere_reception) WHERE client_racine IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_reclamations_racine_reception")
    op.execute("DROP INDEX IF EXISTS ix_reclamations_actives_echeance")
