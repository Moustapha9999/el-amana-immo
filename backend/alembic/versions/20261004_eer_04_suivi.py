"""EER — anomalies, compléments, versions, historique, visas internes.

Additif : aucune table existante modifiée. Données initiales chargées par
``scripts/eer_init_referentiel.py`` (insérées si absentes, jamais réécrites).
Voir docs/conformite/eer-architecture-metier.md §3 et §23.

Revision ID: 20261004_eer_04_suivi
Revises: 20261004_eer_03_moteur
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy import Text

revision: str = "20261004_eer_04_suivi"
down_revision: Union[str, None] = "20261004_eer_03_moteur"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Instantanés, décisions, timeline et visas : jamais modifiés ni supprimés.
IMMUABLES = ("eer_versions", "eer_decisions", "eer_historique", "eer_visas")


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if not inspector.has_table('eer_anomalies'):
        op.create_table('eer_anomalies',
            sa.Column('dossier_id', sa.UUID(), nullable=False),
            sa.Column('item_id', sa.UUID(), nullable=True),
            sa.Column('controle_id', sa.UUID(), nullable=True),
            sa.Column('document_id', sa.UUID(), nullable=True),
            sa.Column('dossier_partie_id', sa.UUID(), nullable=True),
            sa.Column('champ', sa.String(length=120), nullable=True),
            sa.Column('type_code', sa.String(length=60), nullable=False),
            sa.Column('gravite', sa.String(length=10), nullable=False),
            sa.Column('description', sa.Text(), nullable=False),
            sa.Column('observation', sa.Text(), nullable=True),
            sa.Column('action_attendue', sa.Text(), nullable=True),
            sa.Column('statut', sa.String(length=15), nullable=False),
            sa.Column('justification', sa.Text(), nullable=True),
            sa.Column('echeance_regularisation', sa.Date(), nullable=True),
            sa.Column('version_detection', sa.Integer(), nullable=False),
            sa.Column('version_resolution', sa.Integer(), nullable=True),
            sa.Column('created_by_id', sa.UUID(), nullable=True),
            sa.Column('resolved_by_id', sa.UUID(), nullable=True),
            sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('id', sa.UUID(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.CheckConstraint("gravite IN ('BLOQUANTE','MAJEURE','MINEURE')", name='ck_eer_anomalies_gravite'),
            sa.CheckConstraint("statut <> 'ACCEPTEE' OR justification IS NOT NULL", name='ck_eer_anomalies_derogation'),
            sa.CheckConstraint("statut IN ('OUVERTE','EN_COMPLEMENT','CORRIGEE','ACCEPTEE','CLOSE','ANNULEE')", name='ck_eer_anomalies_statut'),
            sa.ForeignKeyConstraint(['controle_id'], ['eer_controles.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['document_id'], ['ged_documents.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['dossier_id'], ['eer_dossiers.id'], ondelete='RESTRICT'),
            sa.ForeignKeyConstraint(['dossier_partie_id'], ['eer_dossier_parties.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['item_id'], ['eer_checklist_items.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['resolved_by_id'], ['users.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_eer_anomalies_dossier_id', 'eer_anomalies', ['dossier_id'], unique=False)
        op.create_index('ix_eer_anomalies_item_id', 'eer_anomalies', ['item_id'], unique=False)
        op.create_index('ix_eer_anomalies_statut', 'eer_anomalies', ['statut'], unique=False)

    if not inspector.has_table('eer_complements'):
        op.create_table('eer_complements',
            sa.Column('dossier_id', sa.UUID(), nullable=False),
            sa.Column('numero', sa.Integer(), nullable=False),
            sa.Column('origine', sa.String(length=20), nullable=False),
            sa.Column('consigne', sa.Text(), nullable=True),
            sa.Column('echeance', sa.Date(), nullable=True),
            sa.Column('statut', sa.String(length=10), nullable=False),
            sa.Column('version_demande', sa.Integer(), nullable=False),
            sa.Column('demande_par_id', sa.UUID(), nullable=True),
            sa.Column('recu_par_id', sa.UUID(), nullable=True),
            sa.Column('recu_le', sa.DateTime(timezone=True), nullable=True),
            sa.Column('id', sa.UUID(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.CheckConstraint("statut IN ('OUVERT','RECU','ANNULE')", name='ck_eer_complements_statut'),
            sa.ForeignKeyConstraint(['demande_par_id'], ['users.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['dossier_id'], ['eer_dossiers.id'], ondelete='RESTRICT'),
            sa.ForeignKeyConstraint(['recu_par_id'], ['users.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('dossier_id', 'numero', name='uq_eer_complements_numero')
        )
        op.create_index('ix_eer_complements_dossier_id', 'eer_complements', ['dossier_id'], unique=False)

    if not inspector.has_table('eer_complement_elements'):
        op.create_table('eer_complement_elements',
            sa.Column('complement_id', sa.UUID(), nullable=False),
            sa.Column('item_id', sa.UUID(), nullable=True),
            sa.Column('anomalie_id', sa.UUID(), nullable=True),
            sa.Column('champ', sa.String(length=120), nullable=True),
            sa.Column('fourni', sa.Boolean(), nullable=False),
            sa.Column('id', sa.UUID(), nullable=False),
            sa.CheckConstraint('item_id IS NOT NULL OR anomalie_id IS NOT NULL OR champ IS NOT NULL', name='ck_eer_complement_elements_cible'),
            sa.ForeignKeyConstraint(['anomalie_id'], ['eer_anomalies.id'], ondelete='RESTRICT'),
            sa.ForeignKeyConstraint(['complement_id'], ['eer_complements.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['item_id'], ['eer_checklist_items.id'], ondelete='RESTRICT'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_eer_complement_elements_complement_id', 'eer_complement_elements', ['complement_id'], unique=False)

    if not inspector.has_table('eer_versions'):
        op.create_table('eer_versions',
            sa.Column('dossier_id', sa.UUID(), nullable=False),
            sa.Column('numero', sa.Integer(), nullable=False),
            sa.Column('evenement', sa.String(length=30), nullable=False),
            sa.Column('contenu', postgresql.JSONB(astext_type=Text()), nullable=False),
            sa.Column('empreinte', sa.String(length=64), nullable=False),
            sa.Column('cree_par_id', sa.UUID(), nullable=True),
            sa.Column('cree_le', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('id', sa.UUID(), nullable=False),
            sa.ForeignKeyConstraint(['cree_par_id'], ['users.id'], ondelete='RESTRICT'),
            sa.ForeignKeyConstraint(['dossier_id'], ['eer_dossiers.id'], ondelete='RESTRICT'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('dossier_id', 'numero', 'evenement', name='uq_eer_versions')
        )
        op.create_index('ix_eer_versions_dossier_id', 'eer_versions', ['dossier_id'], unique=False)

    if not inspector.has_table('eer_historique'):
        op.create_table('eer_historique',
            sa.Column('dossier_id', sa.UUID(), nullable=False),
            sa.Column('action', sa.String(length=40), nullable=False),
            sa.Column('de_statut', sa.String(length=20), nullable=True),
            sa.Column('vers_statut', sa.String(length=20), nullable=True),
            sa.Column('etape', sa.String(length=20), nullable=True),
            sa.Column('version', sa.Integer(), nullable=False),
            sa.Column('motif', sa.Text(), nullable=True),
            sa.Column('details', postgresql.JSONB(astext_type=Text()), nullable=False),
            sa.Column('acteur_id', sa.UUID(), nullable=True),
            sa.Column('cree_le', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('id', sa.UUID(), nullable=False),
            sa.ForeignKeyConstraint(['acteur_id'], ['users.id'], ondelete='RESTRICT'),
            sa.ForeignKeyConstraint(['dossier_id'], ['eer_dossiers.id'], ondelete='RESTRICT'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_eer_historique_cree_le', 'eer_historique', ['cree_le'], unique=False)
        op.create_index('ix_eer_historique_dossier_id', 'eer_historique', ['dossier_id'], unique=False)

    if not inspector.has_table('eer_visas'):
        op.create_table('eer_visas',
            sa.Column('dossier_id', sa.UUID(), nullable=False),
            sa.Column('dossier_partie_id', sa.UUID(), nullable=True),
            sa.Column('user_id', sa.UUID(), nullable=False),
            sa.Column('fonction', sa.String(length=120), nullable=False),
            sa.Column('avis', sa.String(length=40), nullable=False),
            sa.Column('commentaire', sa.Text(), nullable=True),
            sa.Column('version', sa.Integer(), nullable=False),
            sa.Column('vise_le', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('id', sa.UUID(), nullable=False),
            sa.ForeignKeyConstraint(['dossier_id'], ['eer_dossiers.id'], ondelete='RESTRICT'),
            sa.ForeignKeyConstraint(['dossier_partie_id'], ['eer_dossier_parties.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='RESTRICT'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_eer_visas_dossier_id', 'eer_visas', ['dossier_id'], unique=False)

    op.execute(
        """
        CREATE OR REPLACE FUNCTION eer_refuser_modification() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Table % immuable : % refusé', TG_TABLE_NAME, TG_OP
                USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table in IMMUABLES:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_immuable ON {table}")
        op.execute(
            f"CREATE TRIGGER trg_{table}_immuable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION eer_refuser_modification()"
        )


def downgrade() -> None:
    for table in IMMUABLES:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_immuable ON {table}")
    op.execute("DROP FUNCTION IF EXISTS eer_refuser_modification()")
    op.drop_table('eer_visas')
    op.drop_table('eer_historique')
    op.drop_table('eer_versions')
    op.drop_table('eer_complement_elements')
    op.drop_table('eer_complements')
    op.drop_table('eer_anomalies')
