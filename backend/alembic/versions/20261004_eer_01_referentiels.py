"""EER — référentiels paramétrables, paramètres KYC datés, compteur de références.

Additif : aucune table existante modifiée. Données initiales chargées par
``scripts/eer_init_referentiel.py`` (insérées si absentes, jamais réécrites).
Voir docs/conformite/eer-architecture-metier.md §3 et §23.

Revision ID: 20261004_eer_01_referentiels
Revises: 20261003_acc_departement
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy import Text

revision: str = "20261004_eer_01_referentiels"
down_revision: Union[str, None] = "20261003_acc_departement"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if not inspector.has_table('eer_referentiels'):
        op.create_table('eer_referentiels',
            sa.Column('domaine', sa.String(length=40), nullable=False),
            sa.Column('code', sa.String(length=60), nullable=False),
            sa.Column('libelle', sa.String(length=200), nullable=False),
            sa.Column('parent_id', sa.UUID(), nullable=True),
            sa.Column('ordre', sa.Integer(), nullable=False),
            sa.Column('actif', sa.Boolean(), nullable=False),
            sa.Column('meta', postgresql.JSONB(astext_type=Text()), nullable=False),
            sa.Column('id', sa.UUID(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['parent_id'], ['eer_referentiels.id'], ondelete='RESTRICT'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('domaine', 'code', name='uq_eer_referentiels_domaine_code')
        )
        op.create_index('ix_eer_referentiels_domaine', 'eer_referentiels', ['domaine'], unique=False)
        op.create_index('ix_eer_referentiels_parent_id', 'eer_referentiels', ['parent_id'], unique=False)

    if not inspector.has_table('eer_parametres'):
        op.create_table('eer_parametres',
            sa.Column('code', sa.String(length=80), nullable=False),
            sa.Column('valeur', postgresql.JSONB(astext_type=Text()), nullable=True),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('date_effet', sa.Date(), nullable=False),
            sa.Column('valide_par_id', sa.UUID(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('id', sa.UUID(), nullable=False),
            sa.ForeignKeyConstraint(['valide_par_id'], ['users.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('code', 'date_effet', name='uq_eer_parametres_code_effet')
        )
        op.create_index('ix_eer_parametres_code', 'eer_parametres', ['code'], unique=False)

    if not inspector.has_table('eer_reference_compteurs'):
        op.create_table('eer_reference_compteurs',
            sa.Column('annee', sa.Integer(), nullable=False),
            sa.Column('dernier', sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint('annee')
        )


def downgrade() -> None:
    op.drop_table('eer_reference_compteurs')
    op.drop_table('eer_parametres')
    op.drop_table('eer_referentiels')
