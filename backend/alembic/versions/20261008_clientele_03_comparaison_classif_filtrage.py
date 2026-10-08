"""Base clientèle — snapshots d'import, rapprochement, classification, filtrage.

Additif uniquement. L'absence d'une ligne d'extraction n'est jamais une suppression.
Les règles de classification sont du référentiel (aucune matrice métier hardcodée).
Ne pas appliquer sur la production avant validation sur ``bea_digital_clientele_test``.

Revision ID: 20261008_clientele_03
Revises: 20261008_clientele_02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261008_clientele_03"
down_revision: Union[str, None] = "20261008_clientele_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UUID = postgresql.UUID(as_uuid=True)


def _table(name: str, *cols: sa.Column, **kwargs) -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(name):
        op.create_table(name, *cols, **kwargs)


def upgrade() -> None:
    _table(
        "clientele_import_clients",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("import_id", _UUID, sa.ForeignKey("clientele_imports.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("racine_client", sa.String(6), nullable=False),
        sa.Column("raison_sociale", sa.String(255), nullable=True),
        sa.Column("prenoms", sa.Text(), nullable=True),
        sa.Column("nationalite", sa.String(80), nullable=True),
        sa.Column("statut_resident", sa.String(1), nullable=True),
        sa.Column("agent_economique", sa.String(80), nullable=True),
        sa.Column("situation_juridique", sa.String(120), nullable=True),
        sa.Column("categorie_juridique", sa.String(80), nullable=True),
        sa.Column("secteur_activite", sa.String(160), nullable=True),
        sa.Column("famille_secteur_activite", sa.String(120), nullable=True),
        sa.Column("type_identifiant", sa.String(3), nullable=True),
        sa.Column("nni", sa.String(40), nullable=True),
        sa.Column("nif", sa.String(40), nullable=True),
        sa.Column("rcs", sa.String(255), nullable=True),
        sa.UniqueConstraint("import_id", "racine_client", name="uq_clientele_import_clients"),
    )
    op.create_index("ix_clientele_import_clients_import", "clientele_import_clients", ["import_id"])

    _table(
        "clientele_import_comptes",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("import_id", _UUID, sa.ForeignKey("clientele_imports.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("rib", sa.String(23), nullable=False),
        sa.Column("compte", sa.String(11), nullable=True),
        sa.Column("racine_client", sa.String(6), nullable=False),
        sa.Column("code_agence", sa.String(20), nullable=True),
        sa.Column("etat_compte", sa.String(10), nullable=True),
        sa.Column("devise", sa.String(3), nullable=True),
        sa.Column("ncg", sa.String(6), nullable=True),
        sa.Column("conformite_compte", sa.String(15), nullable=True),
        sa.Column("liste_interdiction", sa.Text(), nullable=True),
        sa.Column("date_ouverture", sa.Date(), nullable=True),
        sa.UniqueConstraint("import_id", "rib", name="uq_clientele_import_comptes_rib"),
        sa.CheckConstraint("etat_compte IS NULL OR etat_compte IN ('OUVERT','FERME')",
                           name="ck_clientele_import_comptes_etat"),
    )
    op.create_index("ix_clientele_import_comptes_import", "clientele_import_comptes", ["import_id"])
    op.create_index("ix_clientele_import_comptes_racine", "clientele_import_comptes",
                    ["import_id", "racine_client"])

    _table(
        "clientele_rapprochements",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("import_a_id", _UUID, sa.ForeignKey("clientele_imports.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("import_b_id", _UUID, sa.ForeignKey("clientele_imports.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("synthese", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by_id", _UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("import_a_id", "import_b_id", name="uq_clientele_rapprochements_paire"),
        sa.CheckConstraint("import_a_id <> import_b_id", name="ck_clientele_rapprochements_distincts"),
    )
    op.create_index("ix_clientele_rapprochements_created", "clientele_rapprochements", ["created_at"])

    _table(
        "clientele_rapprochement_ecarts",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("rapprochement_id", _UUID,
                  sa.ForeignKey("clientele_rapprochements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("objet", sa.String(10), nullable=False),
        sa.Column("categorie", sa.String(24), nullable=False),
        sa.Column("racine_client", sa.String(6), nullable=True),
        sa.Column("rib", sa.String(23), nullable=True),
        sa.Column("champ", sa.String(40), nullable=True),
        sa.Column("libelle_champ", sa.String(80), nullable=True),
        sa.Column("valeur_a", sa.Text(), nullable=True),
        sa.Column("valeur_b", sa.Text(), nullable=True),
        sa.Column("code", sa.String(40), nullable=True),
        sa.CheckConstraint("objet IN ('CLIENT','COMPTE')", name="ck_clientele_rappr_ecarts_objet"),
        sa.CheckConstraint(
            "categorie IN ('NOUVEAU','MODIFIE','ABSENT_EXTRACTION','ANOMALIE')",
            name="ck_clientele_rappr_ecarts_cat"),
    )
    op.create_index("ix_clientele_rappr_ecarts_rappr", "clientele_rapprochement_ecarts",
                    ["rapprochement_id"])
    op.create_index("ix_clientele_rappr_ecarts_cat", "clientele_rapprochement_ecarts",
                    ["rapprochement_id", "objet", "categorie"])

    _table(
        "clientele_classif_niveaux",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("code", sa.String(12), nullable=False, unique=True),
        sa.Column("libelle", sa.String(40), nullable=False),
        sa.Column("rang", sa.Integer(), nullable=False),
        sa.Column("actif", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.CheckConstraint("code IN ('FAIBLE','MOYEN','ELEVE','INTERDIT')",
                           name="ck_clientele_classif_niveaux_code"),
    )

    _table(
        "clientele_classif_criteres",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("code", sa.String(40), nullable=False, unique=True),
        sa.Column("libelle", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("champ_defaut", sa.String(40), nullable=True),
        sa.Column("actif", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    _table(
        "clientele_classif_versions",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("numero", sa.Integer(), nullable=False, unique=True),
        sa.Column("libelle", sa.String(160), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False, server_default="MAX_NIVEAU"),
        sa.Column("seuils", postgresql.JSONB(), nullable=True),
        sa.Column("date_effet", sa.Date(), nullable=False),
        sa.Column("date_fin", sa.Date(), nullable=True),
        sa.Column("statut", sa.String(16), nullable=False, server_default="BROUILLON"),
        sa.Column("created_by_id", _UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("mode IN ('MAX_NIVEAU','SCORE')", name="ck_clientele_classif_versions_mode"),
        sa.CheckConstraint("statut IN ('BROUILLON','ACTIVE','ARCHIVEE')",
                           name="ck_clientele_classif_versions_statut"),
    )

    _table(
        "clientele_classif_regles",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("version_id", _UUID, sa.ForeignKey("clientele_classif_versions.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("critere_id", _UUID, sa.ForeignKey("clientele_classif_criteres.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("priorite", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("poids", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("niveau_cible", sa.String(12), nullable=False),
        sa.Column("operateur", sa.String(24), nullable=False),
        sa.Column("champ_source", sa.String(40), nullable=False),
        sa.Column("portee", sa.String(10), nullable=False, server_default="CLIENT"),
        sa.Column("valeur", postgresql.JSONB(), nullable=True),
        sa.Column("motif", sa.Text(), nullable=False),
        sa.Column("actif", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.CheckConstraint("niveau_cible IN ('FAIBLE','MOYEN','ELEVE','INTERDIT')",
                           name="ck_clientele_classif_regles_niveau"),
        sa.CheckConstraint(
            "operateur IN ('EGAL','DIFFERENT','IN','NOT_IN','CONTIENT','VIDE','NON_VIDE')",
            name="ck_clientele_classif_regles_op"),
        sa.CheckConstraint("portee IN ('CLIENT','COMPTE')", name="ck_clientele_classif_regles_portee"),
    )
    op.create_index("ix_clientele_classif_regles_version", "clientele_classif_regles", ["version_id"])

    _table(
        "clientele_classifications",
        sa.Column("racine_client", sa.String(6),
                  sa.ForeignKey("clientele_clients.racine_client", ondelete="RESTRICT",
                                onupdate="RESTRICT"),
                  primary_key=True),
        sa.Column("niveau", sa.String(12), nullable=False),
        sa.Column("version_id", _UUID, sa.ForeignKey("clientele_classif_versions.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("motifs", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("source", sa.String(12), nullable=False),
        sa.Column("motif_risque", sa.Text(), nullable=True),
        sa.Column("motif_classement", sa.Text(), nullable=True),
        sa.Column("classifie_le", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("classifie_par_id", _UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("niveau IN ('FAIBLE','MOYEN','ELEVE','INTERDIT')",
                           name="ck_clientele_classifications_niveau"),
        sa.CheckConstraint("source IN ('MOTEUR','MANUEL','EXCEL')",
                           name="ck_clientele_classifications_source"),
    )

    _table(
        "clientele_classif_historique",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("racine_client", sa.String(6),
                  sa.ForeignKey("clientele_clients.racine_client", ondelete="RESTRICT",
                                onupdate="RESTRICT"),
                  nullable=False),
        sa.Column("ancienne_classe", sa.String(12), nullable=True),
        sa.Column("nouvelle_classe", sa.String(12), nullable=False),
        sa.Column("motif_risque", sa.Text(), nullable=True),
        sa.Column("motif_classement", sa.Text(), nullable=True),
        sa.Column("source", sa.String(12), nullable=False),
        sa.Column("version_id", _UUID, sa.ForeignKey("clientele_classif_versions.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("detail", postgresql.JSONB(), nullable=True),
        sa.Column("created_by_id", _UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("nouvelle_classe IN ('FAIBLE','MOYEN','ELEVE','INTERDIT')",
                           name="ck_clientele_classif_hist_niveau"),
    )
    op.create_index("ix_clientele_classif_hist_racine", "clientele_classif_historique",
                    ["racine_client", "created_at"])

    _table(
        "clientele_filtrage_listes",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("code", sa.String(40), nullable=False, unique=True),
        sa.Column("libelle", sa.String(160), nullable=False),
        sa.Column("source", sa.String(40), nullable=False, server_default="INTERNE"),
        sa.Column("actif", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    _table(
        "clientele_filtrage_entrees",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("liste_id", _UUID, sa.ForeignKey("clientele_filtrage_listes.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("nom", sa.String(160), nullable=True),
        sa.Column("prenom", sa.String(160), nullable=True),
        sa.Column("raison_sociale", sa.String(255), nullable=True),
        sa.Column("date_naissance", sa.Date(), nullable=True),
        sa.Column("nationalite", sa.String(80), nullable=True),
        sa.Column("identifiant", sa.String(80), nullable=True),
        sa.Column("type_identifiant", sa.String(12), nullable=True),
        sa.Column("actif", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_clientele_filtrage_entrees_liste", "clientele_filtrage_entrees", ["liste_id"])

    _table(
        "clientele_alertes",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("racine_client", sa.String(6),
                  sa.ForeignKey("clientele_clients.racine_client", ondelete="RESTRICT",
                                onupdate="RESTRICT"),
                  nullable=False),
        sa.Column("statut", sa.String(24), nullable=False, server_default="NOUVELLE"),
        sa.Column("motif", sa.String(40), nullable=False),
        sa.Column("empreinte", sa.String(80), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("correspondance", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("precedent_faux_positif", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("assignee_id", _UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("cloturee_le", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "statut IN ('NOUVELLE','A_ANALYSER','EN_INVESTIGATION','CONFIRMEE',"
            "'FAUX_POSITIF','REJETEE','CLOTUREE')",
            name="ck_clientele_alertes_statut"),
    )
    op.create_index("ix_clientele_alertes_racine", "clientele_alertes", ["racine_client"])
    op.create_index("ix_clientele_alertes_statut", "clientele_alertes", ["statut"])
    op.create_index("ix_clientele_alertes_empreinte", "clientele_alertes", ["empreinte"])
    op.create_index("ix_clientele_alertes_ouverte", "clientele_alertes",
                    ["racine_client", "empreinte"],
                    unique=True,
                    postgresql_where=sa.text("statut <> 'CLOTUREE'"))

    _table(
        "clientele_alerte_evenements",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("alerte_id", _UUID, sa.ForeignKey("clientele_alertes.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("statut", sa.String(24), nullable=False),
        sa.Column("decision", sa.String(24), nullable=True),
        sa.Column("commentaire", sa.Text(), nullable=True),
        sa.Column("created_by_id", _UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_clientele_alerte_evt_alerte", "clientele_alerte_evenements", ["alerte_id"])

    _table(
        "clientele_alerte_justificatifs",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("alerte_id", _UUID, sa.ForeignKey("clientele_alertes.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("nom_fichier", sa.String(255), nullable=False),
        sa.Column("chemin", sa.String(400), nullable=False),
        sa.Column("created_by_id", _UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    _table(
        "clientele_filtrage_empreintes",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("racine_client", sa.String(6), nullable=False),
        sa.Column("empreinte", sa.String(80), nullable=False),
        sa.Column("decision", sa.String(24), nullable=False),
        sa.Column("alerte_id", _UUID, sa.ForeignKey("clientele_alertes.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("commentaire", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("racine_client", "empreinte", "decision",
                            name="uq_clientele_filtrage_empreintes"),
    )
    op.create_index("ix_clientele_filtrage_emp_cle", "clientele_filtrage_empreintes",
                    ["empreinte", "racine_client"])

    _seed()


def _seed() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("""
        INSERT INTO clientele_classif_niveaux (id, code, libelle, rang, actif) VALUES
          (gen_random_uuid(), 'FAIBLE', 'Faible', 1, true),
          (gen_random_uuid(), 'MOYEN', 'Moyen', 2, true),
          (gen_random_uuid(), 'ELEVE', 'Élevé', 3, true),
          (gen_random_uuid(), 'INTERDIT', 'Interdit', 4, true)
        ON CONFLICT (code) DO NOTHING
    """))
    bind.execute(sa.text("""
        INSERT INTO clientele_classif_criteres (id, code, libelle, description, champ_defaut, actif)
        VALUES
          (gen_random_uuid(), 'PPE', 'PPE',
           'Personne politiquement exposée. Source ORION absente — à brancher (EER / liste métier).',
           NULL, true),
          (gen_random_uuid(), 'RESIDENCE', 'Résidence',
           'Statut résident ORION (R / N). Les seuils restent à valider.',
           'statut_resident', true),
          (gen_random_uuid(), 'NATIONALITE', 'Nationalité',
           'Nationalité ORION. Aucune liste de pays n''est préchargée.',
           'nationalite', true),
          (gen_random_uuid(), 'FORME_JURIDIQUE', 'Forme juridique',
           'Catégorie / situation juridique ORION.',
           'categorie_juridique', true),
          (gen_random_uuid(), 'ASSOCIATION', 'Association',
           'À configurer (valeurs juridiques validées par le métier).',
           'categorie_juridique', true),
          (gen_random_uuid(), 'FONDATION', 'Fondation',
           'À configurer (valeurs juridiques validées par le métier).',
           'categorie_juridique', true),
          (gen_random_uuid(), 'SECTEUR', 'Secteur d''activité',
           'Secteur ORION. Aucun secteur à risque n''est préchargé.',
           'secteur_activite', true),
          (gen_random_uuid(), 'ENTREPRISE_RECENTE', 'Entreprise récente',
           'Date d''ouverture min. des comptes — seuil d''âge à valider.',
           'date_ouverture', true),
          (gen_random_uuid(), 'FILTRAGE', 'Filtrage',
           'Alerte de filtrage confirmée. Source : module filtrage, pas ORION.',
           NULL, true),
          (gen_random_uuid(), 'LISTE_INTERDICTION', 'Liste d''interdiction',
           'Champ ORION LISTE_INTERDICTION sur les comptes.',
           'liste_interdiction', true),
          (gen_random_uuid(), 'RISQUE_EXISTANT', 'Risque existant',
           'Classification déjà présente (ne pas boucler sans règle explicite).',
           'niveau', true)
        ON CONFLICT (code) DO NOTHING
    """))
    bind.execute(sa.text("""
        INSERT INTO clientele_classif_versions
            (id, numero, libelle, mode, date_effet, statut)
        SELECT gen_random_uuid(), 1,
               'Référentiel vide — règles à valider (aucune matrice hardcodée)',
               'MAX_NIVEAU', CURRENT_DATE, 'ACTIVE'
        WHERE NOT EXISTS (SELECT 1 FROM clientele_classif_versions)
    """))
    bind.execute(sa.text("""
        INSERT INTO clientele_filtrage_listes (id, code, libelle, source, actif)
        VALUES
          (gen_random_uuid(), 'LISTE_INTERNE', 'Liste interne de filtrage', 'INTERNE', true)
        ON CONFLICT (code) DO NOTHING
    """))


def downgrade() -> None:
    for table in (
        "clientele_filtrage_empreintes",
        "clientele_alerte_justificatifs",
        "clientele_alerte_evenements",
        "clientele_alertes",
        "clientele_filtrage_entrees",
        "clientele_filtrage_listes",
        "clientele_classif_historique",
        "clientele_classifications",
        "clientele_classif_regles",
        "clientele_classif_versions",
        "clientele_classif_criteres",
        "clientele_classif_niveaux",
        "clientele_rapprochement_ecarts",
        "clientele_rapprochements",
        "clientele_import_comptes",
        "clientele_import_clients",
    ):
        op.drop_table(table)
