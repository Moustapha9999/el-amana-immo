"""Déclaration BCM : statut DESACTIVEE (motif, auteur, date). Additif.

Revision ID: 20261012_clientele_09
Revises: 20261010_clientele_08
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261012_clientele_09"
down_revision: Union[str, None] = "20261010_clientele_08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_T = "clientele_declarations_bcm"
_CK = "ck_clientele_declarations_bcm_statut"
_AVANT = "statut IN ('BROUILLON','CALCULEE','A_CONTROLER','VALIDEE','CLOTUREE','ARCHIVEE')"
_APRES = "statut IN ('BROUILLON','CALCULEE','A_CONTROLER','VALIDEE','CLOTUREE','ARCHIVEE','DESACTIVEE')"


def upgrade() -> None:
    op.add_column(_T, sa.Column("desactivee_le", sa.DateTime(timezone=True), nullable=True))
    op.add_column(_T, sa.Column("desactivee_par_id", postgresql.UUID(as_uuid=True),
                                sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True))
    op.add_column(_T, sa.Column("motif_desactivation", sa.Text(), nullable=True))
    op.drop_constraint(_CK, _T, type_="check")
    op.create_check_constraint(_CK, _T, _APRES)


def downgrade() -> None:
    op.execute(f"UPDATE {_T} SET statut = CASE WHEN cellules IS NULL THEN 'BROUILLON' ELSE 'CALCULEE' END "
               "WHERE statut = 'DESACTIVEE'")
    op.drop_constraint(_CK, _T, type_="check")
    op.create_check_constraint(_CK, _T, _AVANT)
    op.drop_column(_T, "motif_desactivation")
    op.drop_column(_T, "desactivee_par_id")
    op.drop_column(_T, "desactivee_le")
