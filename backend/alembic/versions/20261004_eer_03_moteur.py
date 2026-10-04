"""EER — moteur : règles versionnées, checklist, états des champs de fiche, contrôles, décisions.

Additif : aucune table existante modifiée. Données initiales chargées par
``scripts/eer_init_referentiel.py`` (insérées si absentes, jamais réécrites).
Voir docs/conformite/eer-architecture-metier.md §3 et §23.

Revision ID: 20261004_eer_03_moteur
Revises: 20261004_eer_02_parties_dossiers
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy import Text

revision: str = "20261004_eer_03_moteur"
down_revision: Union[str, None] = "20261004_eer_02_parties_dossiers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if not inspector.has_table('eer_checklist_regles'):
        op.create_table('eer_checklist_regles',
            sa.Column('code', sa.String(length=60), nullable=False),
            sa.Column('version', sa.Integer(), nullable=False),
            sa.Column('libelle', sa.String(length=255), nullable=False),
            sa.Column('categorie', sa.String(length=30), nullable=False),
            sa.Column('axe', sa.String(length=15), nullable=False),
            sa.Column('nature', sa.String(length=15), nullable=False),
            sa.Column('portee', sa.String(length=10), nullable=False),
            sa.Column('role_cible', sa.String(length=30), nullable=True),
            sa.Column('obligatoire', sa.Boolean(), nullable=False),
            sa.Column('condition', postgresql.JSONB(astext_type=Text()), nullable=True),
            sa.Column('ordre', sa.Integer(), nullable=False),
            sa.Column('type_controle', sa.String(length=20), nullable=False),
            sa.Column('document_type_code', sa.String(length=40), nullable=True),
            sa.Column('date_effet', sa.Date(), nullable=False),
            sa.Column('actif', sa.Boolean(), nullable=False),
            sa.Column('created_by_id', sa.UUID(), nullable=True),
            sa.Column('id', sa.UUID(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.CheckConstraint("portee = 'DOSSIER' OR role_cible IS NOT NULL", name='ck_eer_regles_role'),
            sa.CheckConstraint("portee IN ('DOSSIER','PARTIE')", name='ck_eer_regles_portee'),
            sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('code', 'version', name='uq_eer_checklist_regles_code_version')
        )
        op.create_index('ix_eer_checklist_regles_code', 'eer_checklist_regles', ['code'], unique=False)

    if not inspector.has_table('eer_checklist_items'):
        op.create_table('eer_checklist_items',
            sa.Column('dossier_id', sa.UUID(), nullable=False),
            sa.Column('regle_id', sa.UUID(), nullable=False),
            sa.Column('regle_code', sa.String(length=60), nullable=False),
            sa.Column('regle_version', sa.Integer(), nullable=False),
            sa.Column('dossier_partie_id', sa.UUID(), nullable=True),
            sa.Column('libelle', sa.String(length=255), nullable=False),
            sa.Column('categorie', sa.String(length=30), nullable=False),
            sa.Column('axe', sa.String(length=15), nullable=False),
            sa.Column('nature', sa.String(length=15), nullable=False),
            sa.Column('obligatoire', sa.Boolean(), nullable=False),
            sa.Column('ordre', sa.Integer(), nullable=False),
            sa.Column('statut', sa.String(length=20), nullable=False),
            sa.Column('presence', sa.String(length=12), nullable=True),
            sa.Column('motif', sa.Text(), nullable=True),
            sa.Column('motif_code', sa.String(length=40), nullable=True),
            sa.Column('neutralise_auto', sa.Boolean(), nullable=False),
            sa.Column('derogation_acceptee', sa.Boolean(), nullable=False),
            sa.Column('raison_applicabilite', postgresql.JSONB(astext_type=Text()), nullable=False),
            sa.Column('document_id', sa.UUID(), nullable=True),
            sa.Column('pointe_par_id', sa.UUID(), nullable=True),
            sa.Column('pointe_le', sa.DateTime(timezone=True), nullable=True),
            sa.Column('controle_par_id', sa.UUID(), nullable=True),
            sa.Column('controle_le', sa.DateTime(timezone=True), nullable=True),
            sa.Column('id', sa.UUID(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.CheckConstraint("presence IS NULL OR presence IN ('PRESENT','ABSENT','SANS_OBJET')", name='ck_eer_items_presence'),
            sa.CheckConstraint("statut IN ('NON_CONTROLE','EN_COURS','CONFORME','NON_CONFORME','MANQUANT','NON_APPLICABLE','A_VERIFIER')", name='ck_eer_items_statut'),
            sa.CheckConstraint("statut NOT IN ('NON_CONFORME','NON_APPLICABLE') OR motif IS NOT NULL", name='ck_eer_items_motif'),
            sa.ForeignKeyConstraint(['controle_par_id'], ['users.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['document_id'], ['ged_documents.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['dossier_id'], ['eer_dossiers.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['dossier_partie_id'], ['eer_dossier_parties.id'], ondelete='RESTRICT'),
            sa.ForeignKeyConstraint(['pointe_par_id'], ['users.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['regle_id'], ['eer_checklist_regles.id'], ondelete='RESTRICT'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('dossier_id', 'regle_code', 'dossier_partie_id', name='uq_eer_checklist_items', postgresql_nulls_not_distinct=True)
        )
        op.create_index('ix_eer_checklist_items_dossier_id', 'eer_checklist_items', ['dossier_id'], unique=False)
        op.create_index('ix_eer_checklist_items_dossier_partie_id', 'eer_checklist_items', ['dossier_partie_id'], unique=False)
        op.create_index('ix_eer_checklist_items_statut', 'eer_checklist_items', ['statut'], unique=False)

    if not inspector.has_table('eer_champs_etat'):
        op.create_table('eer_champs_etat',
            sa.Column('dossier_id', sa.UUID(), nullable=False),
            sa.Column('dossier_partie_id', sa.UUID(), nullable=True),
            sa.Column('chemin', sa.String(length=120), nullable=False),
            sa.Column('etat', sa.String(length=15), nullable=False),
            sa.Column('source', sa.String(length=30), nullable=True),
            sa.Column('empreinte', sa.String(length=64), nullable=True),
            sa.Column('confirme_par_id', sa.UUID(), nullable=True),
            sa.Column('confirme_le', sa.DateTime(timezone=True), nullable=True),
            sa.Column('id', sa.UUID(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.CheckConstraint("etat IN ('CONNU','MANQUANT','A_CONFIRMER','CONFIRME','NON_APPLICABLE')", name='ck_eer_champs_etat_etat'),
            sa.ForeignKeyConstraint(['confirme_par_id'], ['users.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['dossier_id'], ['eer_dossiers.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['dossier_partie_id'], ['eer_dossier_parties.id'], ondelete='RESTRICT'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('dossier_id', 'dossier_partie_id', 'chemin', name='uq_eer_champs_etat', postgresql_nulls_not_distinct=True)
        )
        op.create_index('ix_eer_champs_etat_dossier_id', 'eer_champs_etat', ['dossier_id'], unique=False)

    if not inspector.has_table('eer_controles'):
        op.create_table('eer_controles',
            sa.Column('dossier_id', sa.UUID(), nullable=False),
            sa.Column('item_id', sa.UUID(), nullable=True),
            sa.Column('code', sa.String(length=60), nullable=False),
            sa.Column('type_controle', sa.String(length=20), nullable=False),
            sa.Column('resultat', sa.String(length=20), nullable=False),
            sa.Column('detail', postgresql.JSONB(astext_type=Text()), nullable=False),
            sa.Column('version', sa.Integer(), nullable=False),
            sa.Column('execute_par_id', sa.UUID(), nullable=True),
            sa.Column('execute_le', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('id', sa.UUID(), nullable=False),
            sa.ForeignKeyConstraint(['dossier_id'], ['eer_dossiers.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['execute_par_id'], ['users.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['item_id'], ['eer_checklist_items.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_eer_controles_dossier_id', 'eer_controles', ['dossier_id'], unique=False)

    if not inspector.has_table('eer_decisions'):
        op.create_table('eer_decisions',
            sa.Column('dossier_id', sa.UUID(), nullable=False),
            sa.Column('version', sa.Integer(), nullable=False),
            sa.Column('resultat', sa.String(length=15), nullable=False),
            sa.Column('conformite_physique', sa.String(length=15), nullable=False),
            sa.Column('conformite_systeme', sa.String(length=15), nullable=False),
            sa.Column('conformite_coherence', sa.String(length=15), nullable=False),
            sa.Column('explication', postgresql.JSONB(astext_type=Text()), nullable=False),
            sa.Column('parametres', postgresql.JSONB(astext_type=Text()), nullable=False),
            sa.Column('decide_par_id', sa.UUID(), nullable=True),
            sa.Column('decide_le', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('id', sa.UUID(), nullable=False),
            sa.CheckConstraint("resultat IN ('CONFORME','NON_CONFORME','INCOMPLET')", name='ck_eer_decisions_resultat'),
            sa.ForeignKeyConstraint(['decide_par_id'], ['users.id'], ondelete='RESTRICT'),
            sa.ForeignKeyConstraint(['dossier_id'], ['eer_dossiers.id'], ondelete='RESTRICT'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_eer_decisions_dossier_id', 'eer_decisions', ['dossier_id'], unique=False)


def downgrade() -> None:
    op.drop_table('eer_decisions')
    op.drop_table('eer_controles')
    op.drop_table('eer_champs_etat')
    op.drop_table('eer_checklist_items')
    op.drop_table('eer_checklist_regles')
