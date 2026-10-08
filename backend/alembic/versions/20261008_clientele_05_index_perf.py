"""Index de performance du moteur d'indicateurs (classification à une date, alertes, EER du mois).

Additif, idempotent. Ne pas appliquer sur la production avant validation sur
``bea_digital_clientele_test``.

Revision ID: 20261008_clientele_05
Revises: 20261008_clientele_04
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20261008_clientele_05"
down_revision: Union[str, None] = "20261008_clientele_04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX = (
    ("ix_clientele_classif_historique_racine_date", "clientele_classif_historique",
     "(racine_client, created_at DESC)", None),
    ("ix_clientele_alertes_created_statut", "clientele_alertes", "(created_at, statut)", None),
    ("ix_eer_dossiers_maj_bcm", "eer_dossiers", "(date_eer, statut, racine_client)",
     "deleted_at IS NULL"),
)


def upgrade() -> None:
    for nom, table, cols, where in _INDEX:
        clause = f" WHERE {where}" if where else ""
        op.execute(f"CREATE INDEX IF NOT EXISTS {nom} ON {table} {cols}{clause}")


def downgrade() -> None:
    for nom, _table, _cols, _where in _INDEX:
        op.execute(f"DROP INDEX IF EXISTS {nom}")
