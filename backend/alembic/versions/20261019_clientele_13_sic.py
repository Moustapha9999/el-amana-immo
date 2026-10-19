"""Déclaration SIC : référentiel BCM versionné, correspondances, déclarations et compléments KYC. Additif.

- ``clientele_bcm_ref_versions`` / ``clientele_bcm_ref_codes`` : versions importées de la feuille ``ref`` ;
  codes immuables, version non brouillon jamais supprimée.
- ``clientele_sic_agences`` : valeur SIC « MoughataaAgence » par agence.
- ``clientele_sic_secteurs`` : correspondance libellé secteur ORION → code secteur BCM.
- ``clientele_declarations_sic`` / ``clientele_sic_lignes`` : déclarations SIC PP / PM, lignes et anomalies.
- ``clientele_kyc`` : genre, téléphone, codes CSP / secteur BCM (données KYC absentes d'ORION), colonnes nullables.

Aucune donnée existante n'est modifiée.

Revision ID: 20261019_clientele_13
Revises: 20261019_clientele_12
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261019_clientele_13"
down_revision: Union[str, None] = "20261019_clientele_12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid(nom: str = "id", **kw) -> sa.Column:
    return sa.Column(nom, postgresql.UUID(as_uuid=True), **kw)


def _user(nom: str) -> sa.Column:
    return sa.Column(nom, postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"),
                     nullable=True)


def _ts(nom: str, defaut: bool = False) -> sa.Column:
    if defaut:
        return sa.Column(nom, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    return sa.Column(nom, sa.DateTime(timezone=True), nullable=True)


def upgrade() -> None:
    op.create_table(
        "clientele_bcm_ref_versions",
        _uuid(primary_key=True),
        sa.Column("libelle", sa.String(120), nullable=False),
        sa.Column("fichier_nom", sa.String(255), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("feuille", sa.String(60), nullable=False),
        sa.Column("statut", sa.String(12), nullable=False, server_default="BROUILLON"),
        sa.Column("nb_codes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("nb_pp", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("nb_pm", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("anomalies", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("observations", sa.Text(), nullable=True),
        _user("importe_par_id"),
        sa.Column("importe_par_nom", sa.String(255), nullable=True),
        _ts("created_at", True),
        _ts("activee_le"),
        _user("activee_par_id"),
        _ts("archivee_le"),
        sa.CheckConstraint("statut IN ('BROUILLON','ACTIVE','ARCHIVEE')", name="ck_clientele_bcm_ref_versions_statut"),
    )
    op.create_index("ix_clientele_bcm_ref_versions_statut", "clientele_bcm_ref_versions", ["statut"])
    op.execute("CREATE UNIQUE INDEX uq_clientele_bcm_ref_versions_active ON clientele_bcm_ref_versions (statut) "
               "WHERE statut = 'ACTIVE'")

    op.create_table(
        "clientele_bcm_ref_codes",
        _uuid(primary_key=True),
        _uuid("version_id", nullable=False),
        sa.Column("ligne", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column("libelle", sa.Text(), nullable=False),
        sa.Column("categorie", sa.String(160), nullable=True),
        sa.Column("usage", sa.String(5), nullable=False),
        sa.Column("actif", sa.Boolean(), nullable=False, server_default="true"),
        sa.ForeignKeyConstraint(["version_id"], ["clientele_bcm_ref_versions.id"], ondelete="CASCADE"),
        sa.CheckConstraint("usage IN ('PP','PM','AUTRE')", name="ck_clientele_bcm_ref_codes_usage"),
    )
    op.create_index("ix_clientele_bcm_ref_codes_version_code", "clientele_bcm_ref_codes", ["version_id", "code"])
    op.execute("""
        CREATE OR REPLACE FUNCTION clientele_bcm_ref_immuable() RETURNS trigger AS $$
        BEGIN
            IF TG_TABLE_NAME = 'clientele_bcm_ref_codes' THEN
                IF TG_OP = 'DELETE' AND NOT EXISTS (
                    SELECT 1 FROM clientele_bcm_ref_versions v
                    WHERE v.id = OLD.version_id AND v.statut <> 'BROUILLON') THEN
                    RETURN OLD;
                END IF;
                RAISE EXCEPTION 'Référentiel BCM : code d''une version importée ni modifiable ni supprimable'
                    USING ERRCODE = 'P0001';
            END IF;
            IF OLD.statut = 'BROUILLON' THEN
                RETURN OLD;
            END IF;
            RAISE EXCEPTION 'Référentiel BCM : seule une version brouillon peut être supprimée'
                USING ERRCODE = 'P0001';
        END $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_clientele_bcm_ref_codes_immuable BEFORE UPDATE OR DELETE ON clientele_bcm_ref_codes
        FOR EACH ROW EXECUTE FUNCTION clientele_bcm_ref_immuable()
    """)
    op.execute("""
        CREATE TRIGGER trg_clientele_bcm_ref_versions_suppression BEFORE DELETE ON clientele_bcm_ref_versions
        FOR EACH ROW EXECUTE FUNCTION clientele_bcm_ref_immuable()
    """)

    op.create_table(
        "clientele_sic_agences",
        _uuid(primary_key=True),
        _uuid("agence_id", nullable=False),
        sa.Column("valeur", sa.String(120), nullable=False),
        sa.Column("observation", sa.Text(), nullable=True),
        _user("maj_par_id"),
        sa.Column("maj_par_nom", sa.String(255), nullable=True),
        _ts("maj_le", True),
        sa.ForeignKeyConstraint(["agence_id"], ["agences.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("agence_id", name="uq_clientele_sic_agences_agence"),
    )
    op.create_table(
        "clientele_sic_secteurs",
        _uuid(primary_key=True),
        sa.Column("libelle_orion", sa.String(160), nullable=False),
        sa.Column("code_bcm", sa.String(10), nullable=False),
        sa.Column("statut", sa.String(12), nullable=False, server_default="A_VALIDER"),
        sa.Column("observation", sa.Text(), nullable=True),
        _user("maj_par_id"),
        sa.Column("maj_par_nom", sa.String(255), nullable=True),
        _ts("maj_le", True),
        sa.UniqueConstraint("libelle_orion", name="uq_clientele_sic_secteurs_libelle"),
        sa.CheckConstraint("statut IN ('CONFIRMEE','A_VALIDER')", name="ck_clientele_sic_secteurs_statut"),
    )

    op.create_table(
        "clientele_declarations_sic",
        _uuid(primary_key=True),
        sa.Column("type", sa.String(2), nullable=False),
        sa.Column("date_reference", sa.Date(), nullable=False),
        sa.Column("date_debut", sa.Date(), nullable=True),
        sa.Column("statut", sa.String(16), nullable=False, server_default="BROUILLON"),
        _uuid("ref_version_id", nullable=True),
        sa.Column("regles", postgresql.JSONB(), nullable=True),
        sa.Column("controles", postgresql.JSONB(), nullable=True),
        sa.Column("nb_candidats", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("nb_lignes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("nb_exclus", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("nb_bloquantes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("nb_a_corriger", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("nb_avertissements", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fichier_nom", sa.String(255), nullable=True),
        sa.Column("fichier_sha256", sa.String(64), nullable=True),
        sa.Column("fichier", sa.LargeBinary(), nullable=True),
        sa.Column("controle_fichier", postgresql.JSONB(), nullable=True),
        sa.Column("commentaire_validation", sa.Text(), nullable=True),
        sa.Column("depot_le", sa.Date(), nullable=True),
        sa.Column("depot_resultat", sa.String(24), nullable=True),
        sa.Column("depot_commentaire", sa.Text(), nullable=True),
        _user("created_by_id"),
        _ts("created_at", True),
        _ts("controlee_le"),
        _user("controlee_par_id"),
        _ts("validee_le"),
        _user("validee_par_id"),
        _ts("generee_le"),
        _user("generee_par_id"),
        _user("depot_par_id"),
        _ts("depot_saisi_le"),
        sa.ForeignKeyConstraint(["ref_version_id"], ["clientele_bcm_ref_versions.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("type IN ('PP','PM')", name="ck_clientele_declarations_sic_type"),
        sa.CheckConstraint(
            "statut IN ('BROUILLON','A_CORRIGER','CONTROLEE','VALIDEE_EXPORT','GENEREE','DEPOSEE')",
            name="ck_clientele_declarations_sic_statut"),
    )
    op.create_index("ix_clientele_declarations_sic_type_date", "clientele_declarations_sic",
                    ["type", "date_reference"])
    op.create_table(
        "clientele_sic_lignes",
        _uuid(primary_key=True),
        _uuid("declaration_id", nullable=False),
        sa.Column("racine_client", sa.String(40), nullable=False),
        sa.Column("statut", sa.String(8), nullable=False),
        sa.Column("gravite_max", sa.String(14), nullable=True),
        sa.Column("valeurs", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("anomalies", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.ForeignKeyConstraint(["declaration_id"], ["clientele_declarations_sic.id"], ondelete="CASCADE"),
        sa.CheckConstraint("statut IN ('EXPORTEE','EXCLUE')", name="ck_clientele_sic_lignes_statut"),
    )
    op.create_index("ix_clientele_sic_lignes_decl", "clientele_sic_lignes",
                    ["declaration_id", "statut", "racine_client"])

    op.add_column("clientele_kyc", sa.Column("genre", sa.String(1), nullable=True))
    op.add_column("clientele_kyc", sa.Column("telephone", sa.String(40), nullable=True))
    op.add_column("clientele_kyc", sa.Column("code_csp_bcm", sa.String(10), nullable=True))
    op.add_column("clientele_kyc", sa.Column("code_secteur_bcm", sa.String(10), nullable=True))
    op.add_column("clientele_kyc", sa.Column("sic_source", sa.String(30), nullable=True))
    op.add_column("clientele_kyc", _user("sic_maj_par_id"))
    op.add_column("clientele_kyc", _ts("sic_maj_le"))
    op.create_check_constraint("ck_clientele_kyc_genre", "clientele_kyc", "genre IS NULL OR genre IN ('H','F')")


def downgrade() -> None:
    op.drop_constraint("ck_clientele_kyc_genre", "clientele_kyc", type_="check")
    for col in ("sic_maj_le", "sic_maj_par_id", "sic_source", "code_secteur_bcm", "code_csp_bcm", "telephone",
                "genre"):
        op.drop_column("clientele_kyc", col)
    op.drop_index("ix_clientele_sic_lignes_decl", table_name="clientele_sic_lignes")
    op.drop_table("clientele_sic_lignes")
    op.drop_index("ix_clientele_declarations_sic_type_date", table_name="clientele_declarations_sic")
    op.drop_table("clientele_declarations_sic")
    op.drop_table("clientele_sic_secteurs")
    op.drop_table("clientele_sic_agences")
    op.execute("DROP TRIGGER IF EXISTS trg_clientele_bcm_ref_versions_suppression ON clientele_bcm_ref_versions")
    op.execute("DROP TRIGGER IF EXISTS trg_clientele_bcm_ref_codes_immuable ON clientele_bcm_ref_codes")
    op.execute("DROP FUNCTION IF EXISTS clientele_bcm_ref_immuable()")
    op.drop_index("ix_clientele_bcm_ref_codes_version_code", table_name="clientele_bcm_ref_codes")
    op.drop_table("clientele_bcm_ref_codes")
    op.execute("DROP INDEX IF EXISTS uq_clientele_bcm_ref_versions_active")
    op.drop_index("ix_clientele_bcm_ref_versions_statut", table_name="clientele_bcm_ref_versions")
    op.drop_table("clientele_bcm_ref_versions")
