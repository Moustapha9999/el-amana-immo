"""Base clientèle — imports ORION, staging, anomalies, vue Situation.

Additif : tables ``clientele_imports`` / ``clientele_import_lignes`` /
``clientele_import_anomalies``, vue ``clientele_situation`` (pas de copie de la
clientèle), module ``clientele``. Aucune table existante métier n'est altérée
hors INSERT catalogue. Ne pas appliquer sur la production avant validation
sur la copie de test.

Revision ID: 20261008_clientele_02
Revises: 20261008_clientele_01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261008_clientele_02"
down_revision: Union[str, None] = "20261008_clientele_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UUID = postgresql.UUID(as_uuid=True)

ESPACE_CODE = "audit-controle-conformite"
DOMAINE_CODE = "conformite-securite-financiere"
MODULE_CODE = "clientele"

# Heuristique documentée (agent puis catégorie) — ce n'est PAS le « Profil ORION
# retraité » du classeur Situation (accord ~94 %). Voir docs/conformite/clientele-phase2.md.
_PROFIL = """
CASE
  WHEN cl.agent_economique IN ('PARTICULIERS', 'PERSONNEL BANQUE') THEN 'PP'
  WHEN cl.agent_economique IN (
        'AUTRES SOCIETES', 'COOPERATIVES ET GROUPEMENTS',
        'INSTITUTIONS FINANCIERES INT.', 'ADMINISTRATIONS LOCALES ET REG.',
        'ETABLISSEMENT PUBLIC CAR INDUS', 'BANQUES ET CORRESPONDANTS',
        'ADMINISTRATIONS PUBL. ET CENT.', 'ENTREPRISES INDIVIDUELLES'
      ) THEN 'PM'
  WHEN cl.categorie_juridique = 'PERSONNE PHYSIQUE' THEN 'PP'
  WHEN cl.categorie_juridique IS NOT NULL THEN 'PM'
  ELSE 'NON_IDENTIFIE'
END
"""


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if not inspector.has_table("clientele_imports"):
        op.create_table(
            "clientele_imports",
            sa.Column("id", _UUID, primary_key=True),
            sa.Column("fichier_nom", sa.String(255), nullable=False),
            sa.Column("fichier_sha256", sa.String(64), nullable=False),
            sa.Column("statut", sa.String(20), nullable=False, server_default="ANALYSE"),
            sa.Column("date_extraction", sa.Date(), nullable=True),
            sa.Column("nb_lignes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("nb_clients", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("nb_comptes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("nb_rejets", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("nb_anomalies", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("clients_crees", sa.Integer(), nullable=True),
            sa.Column("clients_maj", sa.Integer(), nullable=True),
            sa.Column("comptes_crees", sa.Integer(), nullable=True),
            sa.Column("comptes_maj", sa.Integer(), nullable=True),
            sa.Column("analyse", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("resultat", postgresql.JSONB(), nullable=True),
            sa.Column("created_by_id", _UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("importe_par_id", _UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("importe_le", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint("statut IN ('ANALYSE','IMPORTE','ABANDONNE')", name="ck_clientele_imports_statut"),
        )
        op.create_index("ix_clientele_imports_sha256", "clientele_imports", ["fichier_sha256"])
        op.create_index("ix_clientele_imports_created_at", "clientele_imports", ["created_at"])

    if not inspector.has_table("clientele_import_lignes"):
        op.create_table(
            "clientele_import_lignes",
            sa.Column("id", _UUID, primary_key=True),
            sa.Column("import_id", _UUID, sa.ForeignKey("clientele_imports.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("numero_ligne", sa.Integer(), nullable=False),
            sa.Column("statut_ligne", sa.String(10), nullable=False),
            sa.Column("motifs", sa.Text(), nullable=True),
            sa.Column("racine_client", sa.String(6), nullable=True),
            sa.Column("raison_sociale", sa.String(255), nullable=True),
            sa.Column("prenoms", sa.Text(), nullable=True),
            sa.Column("date_naissance", sa.Date(), nullable=True),
            sa.Column("date_naissance_orion", sa.String(120), nullable=True),
            sa.Column("nationalite", sa.String(80), nullable=True),
            sa.Column("statut_resident", sa.String(1), nullable=True),
            sa.Column("agent_economique", sa.String(80), nullable=True),
            sa.Column("situation_juridique", sa.String(120), nullable=True),
            sa.Column("categorie_juridique", sa.String(80), nullable=True),
            sa.Column("secteur_activite", sa.String(160), nullable=True),
            sa.Column("famille_secteur_activite", sa.String(120), nullable=True),
            sa.Column("type_identifiant", sa.String(3), nullable=True),
            sa.Column("identifiant_orion", sa.String(255), nullable=True),
            sa.Column("nni", sa.String(40), nullable=True),
            sa.Column("nif", sa.String(40), nullable=True),
            sa.Column("rcs", sa.String(255), nullable=True),
            sa.Column("compte", sa.String(11), nullable=True),
            sa.Column("rib", sa.String(23), nullable=True),
            sa.Column("code_agence", sa.String(20), nullable=True),
            sa.Column("etat_compte", sa.String(10), nullable=True),
            sa.Column("devise", sa.String(3), nullable=True),
            sa.Column("ncg", sa.String(6), nullable=True),
            sa.Column("rubrique_comptable", sa.String(80), nullable=True),
            sa.Column("date_ouverture", sa.Date(), nullable=True),
            sa.Column("ddc", sa.Date(), nullable=True),
            sa.Column("ddd", sa.Date(), nullable=True),
            sa.Column("conformite_compte", sa.String(15), nullable=True),
            sa.Column("liste_interdiction", sa.Text(), nullable=True),
            sa.CheckConstraint("statut_ligne IN ('VALIDE','REJETEE')",
                               name="ck_clientele_import_lignes_statut"),
            sa.UniqueConstraint("import_id", "numero_ligne", name="uq_clientele_import_lignes_num"),
        )
        op.create_index("ix_clientele_import_lignes_import", "clientele_import_lignes", ["import_id"])
        op.create_index("ix_clientele_import_lignes_racine", "clientele_import_lignes",
                        ["import_id", "racine_client"])
        op.create_index("ix_clientele_import_lignes_compte", "clientele_import_lignes",
                        ["import_id", "compte"])

    if not inspector.has_table("clientele_import_anomalies"):
        op.create_table(
            "clientele_import_anomalies",
            sa.Column("id", _UUID, primary_key=True),
            sa.Column("import_id", _UUID, sa.ForeignKey("clientele_imports.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("numero", sa.Integer(), nullable=False),
            sa.Column("racine_client", sa.String(6), nullable=True),
            sa.Column("code", sa.String(40), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("bloquante", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.create_index("ix_clientele_import_anomalies_import", "clientele_import_anomalies",
                        ["import_id"])
        op.create_index("ix_clientele_import_anomalies_code", "clientele_import_anomalies",
                        ["import_id", "code"])

    op.execute(sa.text(f"""
        CREATE OR REPLACE VIEW clientele_situation AS
        SELECT
            cl.id,
            cl.racine_client,
            cl.raison_sociale AS nom_client,
            cl.prenoms,
            cl.nationalite,
            cl.statut_resident,
            cl.nni,
            cl.nif,
            cl.rcs,
            cl.type_identifiant,
            cl.identifiant_orion,
            cl.categorie_juridique,
            cl.situation_juridique,
            cl.agent_economique,
            cl.secteur_activite,
            cl.famille_secteur_activite,
            cl.date_naissance,
            cl.type_client,
            {_PROFIL} AS profil_derive,
            agg.etat_client,
            agg.date_ouverture,
            agg.code_agence,
            agg.agence,
            agg.nb_comptes,
            agg.nb_comptes_ouverts,
            agg.nb_agences,
            cl.date_extraction,
            cl.premiere_extraction,
            cl.updated_at
        FROM clientele_clients cl
        JOIN (
            SELECT
                co.racine_client,
                CASE WHEN bool_and(co.etat_compte = 'FERME') THEN 'CLOTURE' ELSE 'OUVERT' END
                    AS etat_client,
                min(co.date_ouverture) AS date_ouverture,
                (array_agg(ag.code ORDER BY co.date_ouverture ASC NULLS LAST, co.compte ASC))[1]
                    AS code_agence,
                (array_agg(ag.libelle ORDER BY co.date_ouverture ASC NULLS LAST, co.compte ASC))[1]
                    AS agence,
                count(*)::int AS nb_comptes,
                count(*) FILTER (WHERE co.etat_compte = 'OUVERT')::int AS nb_comptes_ouverts,
                count(DISTINCT co.agence_id)::int AS nb_agences
            FROM clientele_comptes co
            JOIN agences ag ON ag.id = co.agence_id
            GROUP BY co.racine_client
        ) agg ON agg.racine_client = cl.racine_client
    """))

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            INSERT INTO plateforme_modules
                (id, espace_id, domaine_id, code, label, description, entry_path, statut,
                 status_message, sort_order, is_active, icon)
            SELECT gen_random_uuid(), e.id,
                   (SELECT d.id FROM plateforme_domaines d WHERE d.code = :domaine_code),
                   :code, :label, :description, '/clientele/dashboard', 'developpement',
                   :status_message, 1, true, 'groups'
            FROM plateforme_espaces e
            WHERE e.code = :espace_code
            ON CONFLICT (code) DO NOTHING
            """
        ),
        {
            "espace_code": ESPACE_CODE,
            "domaine_code": DOMAINE_CODE,
            "code": MODULE_CODE,
            "label": "Référentiel clients",
            "description": (
                "Base clientèle consolidée sur la racine ORION (1 client, N comptes, N RIB) : "
                "import État des comptes, Situation PP / PM, fiche client."
            ),
            "status_message": (
                "Module en cours de construction — import ORION et situations PP / PM."
            ),
        },
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM plateforme_modules WHERE code = :c"), {"c": MODULE_CODE})
    op.execute(sa.text("DROP VIEW IF EXISTS clientele_situation"))
    for table in ("clientele_import_anomalies", "clientele_import_lignes", "clientele_imports"):
        op.drop_table(table)
