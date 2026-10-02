"""Stock MG — rapprochement d'inventaire sur une référence externe (inventaire bancaire).

``stock_cible`` : stock à retenir dans BEA DIGITAL après ajustement (ex. « stock actuel agence »
de la banque) ; l'ajustement vaut alors stock_cible − stock système figé, et l'écart restant
(physique − cible) reste à régulariser sans mouvement.
``donnees_source`` : colonnes historiques du document de référence (stock initial, entrées,
sorties, statut agence…), conservées pour traçabilité, jamais rejouées en mouvements.

Revision ID: 20261003_mg_inv_rapprochement
Revises: 20261002_mg_inventaire_mensuel
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20261003_mg_inv_rapprochement"
down_revision: Union[str, None] = "20261002_mg_inventaire_mensuel"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("mg_inventaire_lignes")}
    if "stock_cible" not in existing:
        op.add_column("mg_inventaire_lignes", sa.Column("stock_cible", sa.Numeric(18, 3), nullable=True))
    if "donnees_source" not in existing:
        op.add_column("mg_inventaire_lignes", sa.Column("donnees_source", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("mg_inventaire_lignes", "donnees_source")
    op.drop_column("mg_inventaire_lignes", "stock_cible")
