"""Auth : changement de mot de passe obligatoire (``users.must_change_password``).

Positionné quand un administrateur définit le mot de passe (création, réinitialisation) ou
explicitement depuis CORE ADMIN ; levé quand l'utilisateur choisit son propre mot de passe.
Les comptes existants ne sont pas concernés (défaut ``false``).

Revision ID: 20261026_auth_01
Revises: 20261023_reclamations_12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261026_auth_01"
down_revision: Union[str, None] = "20261023_reclamations_12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
retour_arriere = "compatible"


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("users", "must_change_password")
