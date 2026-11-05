"""Stock — unicité des références de mouvement.

Dernière ligne de défense : le verrou applicatif (``prochain_numero``) sérialise
l'attribution, cette contrainte refuse un doublon si deux transactions échappent
au verrou. Les demandes ont déjà ``ix_mg_employee_requests_number`` (UNIQUE).

Prérequis : aucune référence en double. Vérifier avant d'appliquer :

    SELECT reference, count(*) FROM mg_stock_mouvements GROUP BY 1 HAVING count(*) > 1;

Revision ID: 20261105_mg_stock_mvt_ref_uq
Revises: 20261102_mg_stock_periodes_02
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20261105_mg_stock_mvt_ref_uq"
down_revision: Union[str, None] = "20261102_mg_stock_periodes_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
retour_arriere = "compatible"


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_mg_stock_mouvements_reference")
    op.execute(
        "CREATE UNIQUE INDEX uq_mg_stock_mouvements_reference "
        "ON mg_stock_mouvements (reference)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_mg_stock_mouvements_reference")
    op.execute("CREATE INDEX ix_mg_stock_mouvements_reference ON mg_stock_mouvements (reference)")
