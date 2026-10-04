"""EER — parties (saisie unique), pièces d'identité, dossiers, rôles, actionnariat, risque.

Additif : aucune table existante modifiée. Données initiales chargées par
``scripts/eer_init_referentiel.py`` (insérées si absentes, jamais réécrites).
Voir docs/conformite/eer-architecture-metier.md §3 et §23.

Revision ID: 20261004_eer_02_parties_dossiers
Revises: 20261004_eer_01_referentiels
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy import Text

revision: str = "20261004_eer_02_parties_dossiers"
down_revision: Union[str, None] = "20261004_eer_01_referentiels"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STATUT_CHECK = (
    "statut IN ('BROUILLON','SOUMIS','A_AFFECTER','AFFECTE','EN_CONTROLE','CONFORME','NON_CONFORME',"
    "'A_COMPLETER','RESOUMIS','AVIS_CONFORMITE','VALIDE','CLOTURE','ARCHIVE','ABANDONNE')"
)
ETAPE_CHECK = "etape IS NULL OR etape IN ('CHECKLIST','CHECKLIST_VALIDEE','FICHES','CONTROLES')"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if not inspector.has_table('eer_parties'):
        op.create_table('eer_parties',
            sa.Column('nature', sa.String(length=10), nullable=False),
            sa.Column('nom', sa.String(length=255), nullable=False),
            sa.Column('nationalite', sa.String(length=80), nullable=True),
            sa.Column('pays_residence', sa.String(length=80), nullable=True),
            sa.Column('adresse', sa.Text(), nullable=True),
            sa.Column('telephone_1', sa.String(length=40), nullable=True),
            sa.Column('telephone_2', sa.String(length=40), nullable=True),
            sa.Column('telephone_3', sa.String(length=40), nullable=True),
            sa.Column('email', sa.String(length=255), nullable=True),
            sa.Column('racine_client', sa.String(length=40), nullable=True),
            sa.Column('created_by_id', sa.UUID(), nullable=True),
            sa.Column('id', sa.UUID(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.CheckConstraint("nature IN ('PHYSIQUE','MORALE')", name='ck_eer_parties_nature'),
            sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_eer_parties_nom', 'eer_parties', ['nom'], unique=False)
        op.create_index('ix_eer_parties_racine_client', 'eer_parties', ['racine_client'], unique=False)

    if not inspector.has_table('eer_parties_physiques'):
        op.create_table('eer_parties_physiques',
            sa.Column('partie_id', sa.UUID(), nullable=False),
            sa.Column('sexe', sa.String(length=1), nullable=True),
            sa.Column('prenom', sa.String(length=120), nullable=True),
            sa.Column('prenom_pere', sa.String(length=120), nullable=True),
            sa.Column('date_naissance', sa.Date(), nullable=True),
            sa.Column('lieu_naissance', sa.String(length=120), nullable=True),
            sa.Column('situation_matrimoniale', sa.String(length=40), nullable=True),
            sa.Column('profession', sa.String(length=120), nullable=True),
            sa.Column('employeur', sa.String(length=200), nullable=True),
            sa.Column('salaire_net', sa.Numeric(precision=18, scale=2), nullable=True),
            sa.Column('date_embauche', sa.Date(), nullable=True),
            sa.Column('type_contrat', sa.String(length=60), nullable=True),
            sa.ForeignKeyConstraint(['partie_id'], ['eer_parties.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('partie_id')
        )

    if not inspector.has_table('eer_parties_morales'):
        op.create_table('eer_parties_morales',
            sa.Column('partie_id', sa.UUID(), nullable=False),
            sa.Column('forme', sa.String(length=60), nullable=True),
            sa.Column('date_creation', sa.Date(), nullable=True),
            sa.Column('activites', sa.Text(), nullable=True),
            sa.Column('effectif', sa.Integer(), nullable=True),
            sa.Column('rc_chronologique', sa.String(length=60), nullable=True),
            sa.Column('rc_analytique', sa.String(length=60), nullable=True),
            sa.Column('nif', sa.String(length=60), nullable=True),
            sa.Column('residence_fiscale', sa.String(length=80), nullable=True),
            sa.Column('site_web', sa.String(length=255), nullable=True),
            sa.Column('numero_agrement', sa.String(length=60), nullable=True),
            sa.Column('impact_rse', sa.Boolean(), nullable=True),
            sa.Column('domaines_rse', sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(['partie_id'], ['eer_parties.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('partie_id')
        )
        op.create_index('ix_eer_parties_morales_nif', 'eer_parties_morales', ['nif'], unique=False)

    if not inspector.has_table('eer_pieces_identite'):
        op.create_table('eer_pieces_identite',
            sa.Column('partie_id', sa.UUID(), nullable=False),
            sa.Column('type_piece', sa.String(length=30), nullable=False),
            sa.Column('numero', sa.String(length=60), nullable=False),
            sa.Column('date_delivrance', sa.Date(), nullable=True),
            sa.Column('date_expiration', sa.Date(), nullable=True),
            sa.Column('pays_emission', sa.String(length=80), nullable=True),
            sa.Column('id', sa.UUID(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['partie_id'], ['eer_parties.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('type_piece', 'numero', 'pays_emission', name='uq_eer_pieces_identite', postgresql_nulls_not_distinct=True)
        )
        op.create_index('ix_eer_pieces_identite_partie_id', 'eer_pieces_identite', ['partie_id'], unique=False)

    if not inspector.has_table('eer_dossiers'):
        op.create_table('eer_dossiers',
            sa.Column('reference', sa.String(length=20), nullable=False),
            sa.Column('operation_type', sa.String(length=20), nullable=False),
            sa.Column('agence_id', sa.UUID(), nullable=False),
            sa.Column('type_client_code', sa.String(length=20), nullable=False),
            sa.Column('profil_code', sa.String(length=60), nullable=False),
            sa.Column('sous_profil_code', sa.String(length=60), nullable=True),
            sa.Column('type_compte_code', sa.String(length=60), nullable=True),
            sa.Column('client_partie_id', sa.UUID(), nullable=False),
            sa.Column('racine_client', sa.String(length=40), nullable=True),
            sa.Column('numero_idp', sa.String(length=40), nullable=True),
            sa.Column('numero_idm', sa.String(length=40), nullable=True),
            sa.Column('date_eer', sa.Date(), nullable=False),
            sa.Column('numero_compte', sa.String(length=40), nullable=True),
            sa.Column('date_ouverture_compte', sa.Date(), nullable=True),
            sa.Column('nombre_signataires', sa.Integer(), nullable=True),
            sa.Column('type_signature', sa.String(length=12), nullable=True),
            sa.Column('tranche_mouvement_code', sa.String(length=30), nullable=True),
            sa.Column('origine_fonds', sa.Text(), nullable=True),
            sa.Column('destination_fonds', sa.Text(), nullable=True),
            sa.Column('commentaire_profil', sa.Text(), nullable=True),
            sa.Column('risque_lbcft', sa.String(length=10), nullable=True),
            sa.Column('ppe_dossier', sa.Boolean(), nullable=False),
            sa.Column('fatca_dossier', sa.Boolean(), nullable=False),
            sa.Column('avis_requis', sa.Boolean(), nullable=False),
            sa.Column('conformite_physique', sa.String(length=15), nullable=True),
            sa.Column('conformite_systeme', sa.String(length=15), nullable=True),
            sa.Column('conformite_coherence', sa.String(length=15), nullable=True),
            sa.Column('decision_globale', sa.String(length=15), nullable=True),
            sa.Column('moment_controle', sa.String(length=15), nullable=False),
            sa.Column('etat_compte', sa.String(length=20), nullable=True),
            sa.Column('statut', sa.String(length=20), nullable=False),
            sa.Column('etape', sa.String(length=20), nullable=True),
            sa.Column('version_courante', sa.Integer(), nullable=False),
            sa.Column('revision', sa.Integer(), server_default='0', nullable=False),
            sa.Column('nb_relances', sa.Integer(), nullable=False),
            sa.Column('derniere_relance_le', sa.DateTime(timezone=True), nullable=True),
            sa.Column('motif_abandon', sa.Text(), nullable=True),
            sa.Column('parametres_snapshot', postgresql.JSONB(astext_type=Text()), nullable=False),
            sa.Column('created_by_id', sa.UUID(), nullable=False),
            sa.Column('analyste_id', sa.UUID(), nullable=True),
            sa.Column('controleur_id', sa.UUID(), nullable=True),
            sa.Column('soumis_le', sa.DateTime(timezone=True), nullable=True),
            sa.Column('valide_le', sa.DateTime(timezone=True), nullable=True),
            sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('id', sa.UUID(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.CheckConstraint("moment_controle IN ('PREALABLE','A_POSTERIORI')", name='ck_eer_dossiers_moment'),
            sa.CheckConstraint("operation_type IN ('ENTREE_RELATION','MISE_A_JOUR')", name='ck_eer_dossiers_operation'),
            sa.CheckConstraint("statut <> 'ABANDONNE' OR motif_abandon IS NOT NULL", name='ck_eer_dossiers_abandon'),
            sa.CheckConstraint("type_signature IS NULL OR type_signature IN ('UNIQUE','CONJOINTES','SEPAREES')", name='ck_eer_dossiers_type_signature'),
            sa.CheckConstraint('nb_relances >= 0', name='ck_eer_dossiers_relances'),
            sa.CheckConstraint('revision >= 0', name='ck_eer_dossiers_revision'),
            sa.CheckConstraint('version_courante >= 1', name='ck_eer_dossiers_version'),
            sa.CheckConstraint(STATUT_CHECK, name='ck_eer_dossiers_statut'),
            sa.CheckConstraint(ETAPE_CHECK, name='ck_eer_dossiers_etape'),
            sa.ForeignKeyConstraint(['agence_id'], ['agences.id'], ondelete='RESTRICT'),
            sa.ForeignKeyConstraint(['analyste_id'], ['users.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['client_partie_id'], ['eer_parties.id'], ondelete='RESTRICT'),
            sa.ForeignKeyConstraint(['controleur_id'], ['users.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='RESTRICT'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('reference')
        )
        op.create_index('ix_eer_dossiers_agence_id', 'eer_dossiers', ['agence_id'], unique=False)
        op.create_index('ix_eer_dossiers_client_partie_id', 'eer_dossiers', ['client_partie_id'], unique=False)
        op.create_index('ix_eer_dossiers_decision_globale', 'eer_dossiers', ['decision_globale'], unique=False)
        op.create_index('ix_eer_dossiers_etat_compte', 'eer_dossiers', ['etat_compte'], unique=False)
        op.create_index('ix_eer_dossiers_profil_code', 'eer_dossiers', ['profil_code'], unique=False)
        op.create_index('ix_eer_dossiers_racine_client', 'eer_dossiers', ['racine_client'], unique=False)
        op.create_index('ix_eer_dossiers_statut', 'eer_dossiers', ['statut'], unique=False)
        op.create_index('ix_eer_dossiers_type_client_code', 'eer_dossiers', ['type_client_code'], unique=False)
        op.create_index('ix_eer_dossiers_agence_statut', 'eer_dossiers', ['agence_id', 'statut'], unique=False)
        op.create_index('ix_eer_dossiers_analyste_statut', 'eer_dossiers', ['analyste_id', 'statut'], unique=False)
        op.create_index('ix_eer_dossiers_created_at', 'eer_dossiers', ['created_at'], unique=False)

    if not inspector.has_table('eer_dossier_parties'):
        op.create_table('eer_dossier_parties',
            sa.Column('dossier_id', sa.UUID(), nullable=False),
            sa.Column('partie_id', sa.UUID(), nullable=False),
            sa.Column('role', sa.String(length=30), nullable=False),
            sa.Column('forme_mandat', sa.String(length=20), nullable=True),
            sa.Column('lien_client', sa.Text(), nullable=True),
            sa.Column('fonction', sa.String(length=120), nullable=True),
            sa.Column('comptes_mandat', sa.Text(), nullable=True),
            sa.Column('ppe', sa.Boolean(), nullable=True),
            sa.Column('ppe_motif', sa.Text(), nullable=True),
            sa.Column('fatca_indice', sa.Boolean(), nullable=True),
            sa.Column('fatca_detail', sa.Text(), nullable=True),
            sa.Column('risque_lbcft', sa.String(length=10), nullable=True),
            sa.Column('gestionnaire_id', sa.UUID(), nullable=True),
            sa.Column('responsable_agence_id', sa.UUID(), nullable=True),
            sa.Column('be_source', sa.String(length=10), nullable=True),
            sa.Column('be_pourcentage_calcule', sa.Numeric(precision=7, scale=4), nullable=True),
            sa.Column('ordre', sa.Integer(), nullable=False),
            sa.Column('id', sa.UUID(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.CheckConstraint("be_source IS NULL OR be_source IN ('CALCULE','DECLARE')", name='ck_eer_dossier_parties_be'),
            sa.CheckConstraint("forme_mandat IS NULL OR forme_mandat IN ('MANDATAIRE_SOCIAL','PROCURATION')", name='ck_eer_dossier_parties_mandat'),
            sa.CheckConstraint("role IN ('CLIENT','MANDATAIRE') OR (ppe IS NULL AND fatca_indice IS NULL AND risque_lbcft IS NULL)", name='ck_eer_dossier_parties_ppe_fatca'),
            sa.CheckConstraint("role IN ('CLIENT','MANDATAIRE','SIGNATAIRE_COMPTE','GERANT','CO_GERANT','SIGNATAIRE_ASSOCIATION','CO_SIGNATAIRE_ASSOCIATION','MEMBRE_DIRECTION','ACTIONNAIRE','BENEFICIAIRE_EFFECTIF','CONTACT_URGENCE')", name='ck_eer_dossier_parties_role'),
            sa.ForeignKeyConstraint(['dossier_id'], ['eer_dossiers.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['gestionnaire_id'], ['users.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['partie_id'], ['eer_parties.id'], ondelete='RESTRICT'),
            sa.ForeignKeyConstraint(['responsable_agence_id'], ['users.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('dossier_id', 'partie_id', 'role', name='uq_eer_dossier_parties')
        )
        op.create_index('ix_eer_dossier_parties_dossier_id', 'eer_dossier_parties', ['dossier_id'], unique=False)
        op.create_index('ix_eer_dossier_parties_partie_id', 'eer_dossier_parties', ['partie_id'], unique=False)
        op.create_index('ix_eer_dossier_parties_role', 'eer_dossier_parties', ['role'], unique=False)

    if not inspector.has_table('eer_detentions'):
        op.create_table('eer_detentions',
            sa.Column('dossier_id', sa.UUID(), nullable=False),
            sa.Column('detenteur_partie_id', sa.UUID(), nullable=False),
            sa.Column('detenue_partie_id', sa.UUID(), nullable=False),
            sa.Column('pourcentage', sa.Numeric(precision=7, scale=4), nullable=True),
            sa.Column('lien', sa.Text(), nullable=True),
            sa.Column('niveau', sa.Integer(), nullable=True),
            sa.Column('id', sa.UUID(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.CheckConstraint('detenteur_partie_id <> detenue_partie_id', name='ck_eer_detentions_distinct'),
            sa.CheckConstraint('pourcentage IS NOT NULL OR lien IS NOT NULL', name='ck_eer_detentions_lien'),
            sa.CheckConstraint('pourcentage IS NULL OR (pourcentage > 0 AND pourcentage <= 100)', name='ck_eer_detentions_pourcentage'),
            sa.ForeignKeyConstraint(['detenteur_partie_id'], ['eer_parties.id'], ondelete='RESTRICT'),
            sa.ForeignKeyConstraint(['detenue_partie_id'], ['eer_parties.id'], ondelete='RESTRICT'),
            sa.ForeignKeyConstraint(['dossier_id'], ['eer_dossiers.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('dossier_id', 'detenteur_partie_id', 'detenue_partie_id', name='uq_eer_detentions')
        )
        op.create_index('ix_eer_detentions_dossier_id', 'eer_detentions', ['dossier_id'], unique=False)

    if not inspector.has_table('eer_evaluations_risque'):
        op.create_table('eer_evaluations_risque',
            sa.Column('dossier_id', sa.UUID(), nullable=False),
            sa.Column('dossier_partie_id', sa.UUID(), nullable=True),
            sa.Column('niveau', sa.String(length=10), nullable=False),
            sa.Column('niveau_declare', sa.String(length=10), nullable=True),
            sa.Column('facteurs', postgresql.JSONB(astext_type=Text()), nullable=False),
            sa.Column('justification', sa.Text(), nullable=True),
            sa.Column('evalue_par_id', sa.UUID(), nullable=True),
            sa.Column('evalue_le', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('id', sa.UUID(), nullable=False),
            sa.CheckConstraint("niveau IN ('FAIBLE','MOYEN','ELEVE')", name='ck_eer_eval_risque_niveau'),
            sa.ForeignKeyConstraint(['dossier_id'], ['eer_dossiers.id'], ondelete='RESTRICT'),
            sa.ForeignKeyConstraint(['dossier_partie_id'], ['eer_dossier_parties.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['evalue_par_id'], ['users.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_eer_evaluations_risque_dossier_id', 'eer_evaluations_risque', ['dossier_id'], unique=False)


def downgrade() -> None:
    op.drop_table('eer_evaluations_risque')
    op.drop_table('eer_detentions')
    op.drop_table('eer_dossier_parties')
    op.drop_table('eer_dossiers')
    op.drop_table('eer_pieces_identite')
    op.drop_table('eer_parties_morales')
    op.drop_table('eer_parties_physiques')
    op.drop_table('eer_parties')
