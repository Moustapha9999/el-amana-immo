"""Stock : la permission de réouverture de période couvre la suppression administrateur.

Revision ID: 20260929_perm_stock_suppr_admin
Revises: 20260929_api_error_events
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260929_perm_stock_suppr_admin"
down_revision: Union[str, None] = "20260929_api_error_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NOUVEAU = "Réouverture de période et suppression administrateur (périodes clôturées, workflows)"
_ANCIEN = "Réouverture d'une période clôturée"


def upgrade() -> None:
    op.execute(
        f"UPDATE permissions SET label = '{_NOUVEAU.replace(chr(39), chr(39) * 2)}' "
        f"WHERE code = 'mg.stock.period.reopen' AND label = '{_ANCIEN.replace(chr(39), chr(39) * 2)}'"
    )


def downgrade() -> None:
    op.execute(
        f"UPDATE permissions SET label = '{_ANCIEN.replace(chr(39), chr(39) * 2)}' "
        f"WHERE code = 'mg.stock.period.reopen' AND label = '{_NOUVEAU.replace(chr(39), chr(39) * 2)}'"
    )
