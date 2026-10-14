"""Réclamations — retrait de la fonctionnalité « Délais & alertes ».

Seules les permissions ``reclamations.delais.manage`` et ``reclamations.delais.validate`` sont
retirées (liens rôle supprimés en cascade). Les règles de délai, les jours fériés et les colonnes
d'échéance des dossiers sont conservés tels quels : plus lus ni alimentés par l'application.

Revision ID: 20261014_reclamations_07
Revises: 20261014_reclamations_06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261014_reclamations_07"
down_revision: Union[str, None] = "20261014_reclamations_06"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PERMISSIONS_RETIREES = (
    ("reclamations.delais.manage", "Paramétrage des délais et du calendrier"),
    ("reclamations.delais.validate", "Validation Conformité des règles de délai"),
)


def upgrade() -> None:
    op.execute(sa.text("DELETE FROM permissions WHERE code IN (:a, :b)").bindparams(
        a=PERMISSIONS_RETIREES[0][0], b=PERMISSIONS_RETIREES[1][0]))


def downgrade() -> None:
    for code, libelle in PERMISSIONS_RETIREES:
        op.execute(sa.text("INSERT INTO permissions (id, code, label, module) "
                           "SELECT gen_random_uuid(), :c, :l, 'reclamations' "
                           "WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = :c)").bindparams(c=code, l=libelle))
