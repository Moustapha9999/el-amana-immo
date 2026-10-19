"""Base Clientèle : référentiel des analystes KYC, libellé du module, désactivation réversible d'EER. Additif.

- ``clientele_analystes_kyc`` : analystes reconnus pour l'import hebdomadaire et les décisions de
  classification (nom unique, lien facultatif vers un compte utilisateur, désactivable, jamais supprimé
  par l'application).
- Module ``clientele`` : libellé « Base Clientèle » (seulement s'il porte encore l'ancien libellé).
- Module ``eer`` : statut ``inactif`` (même effet qu'une désactivation CORE ADMIN : menu masqué, API refusée
  par ``require_module_access``, rappels d'échéances suspendus). Tables, données et permissions EER
  conservées ; réactivation par CORE ADMIN ou ``downgrade``.

Revision ID: 20261020_clientele_14
Revises: 20261019_clientele_13
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261020_clientele_14"
down_revision: Union[str, None] = "20261019_clientele_13"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "clientele_analystes_kyc",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("nom", sa.String(120), nullable=False),
        sa.Column("nom_normalise", sa.String(120), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("actif", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("nom_normalise", name="uq_clientele_analystes_kyc_nom"),
    )
    op.create_index("ix_clientele_analystes_kyc_user", "clientele_analystes_kyc", ["user_id"])
    op.execute("UPDATE plateforme_modules SET label = 'Base Clientèle' "
               "WHERE code = 'clientele' AND label = 'Référentiel clients'")
    op.execute("UPDATE plateforme_modules SET statut = 'inactif', is_active = false WHERE code = 'eer'")


def downgrade() -> None:
    op.execute("UPDATE plateforme_modules SET statut = 'actif', is_active = true "
               "WHERE code = 'eer' AND statut = 'inactif'")
    op.execute("UPDATE plateforme_modules SET label = 'Référentiel clients' "
               "WHERE code = 'clientele' AND label = 'Base Clientèle'")
    op.drop_index("ix_clientele_analystes_kyc_user", table_name="clientele_analystes_kyc")
    op.drop_table("clientele_analystes_kyc")
