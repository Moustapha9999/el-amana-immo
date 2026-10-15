"""Classification simplifiée : journal des actions clients, données KYC, historique protégé. Additif.

- ``clientele_journal`` : une ligne par action (création, mise à jour de données, proposition,
  acceptation, modification, rejet, vérification), saisie individuelle ou import. Ni modifiable ni
  supprimable (déclencheurs) ;
- ``clientele_kyc`` : données KYC déclarées absentes d'ORION (date EER, profil, sous-profil, statut gel,
  date de mise à jour, analyste, date de création d'entreprise). Jamais une donnée ORION ;
- ``clientele_classif_historique`` : suppression interdite ; mise à jour limitée au passage à NULL des
  références (lot, version, évaluation, utilisateur) imposé par les clés étrangères ;
- ``clientele_classif_lot_lignes.statut`` : ajout de ``AMBIGU`` (identité à vérifier manuellement).

Les restaurations de sauvegarde (``session_replication_role = replica``) ne déclenchent pas ces contrôles.

Revision ID: 20261015_clientele_11
Revises: 20261015_reclamations_09
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261015_clientele_11"
down_revision: Union[str, None] = "20261015_reclamations_09"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UUID = postgresql.UUID(as_uuid=True)
_REFERENCES_HISTO = "ARRAY['lot_id','version_id','evaluation_id','created_by_id']"


def upgrade() -> None:
    op.create_table(
        "clientele_journal",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("racine_client", sa.String(6), nullable=False),
        sa.Column("type_action", sa.String(16), nullable=False),
        sa.Column("champ", sa.String(60), nullable=True),
        sa.Column("ancienne_valeur", sa.Text(), nullable=True),
        sa.Column("nouvelle_valeur", sa.Text(), nullable=True),
        sa.Column("motif", sa.Text(), nullable=True),
        sa.Column("analyste_kyc", sa.String(120), nullable=True),
        sa.Column("origine", sa.String(8), nullable=False),
        sa.Column("lot_id", _UUID, nullable=True),
        sa.Column("ligne_source", sa.Integer(), nullable=True),
        sa.Column("groupe_id", _UUID, nullable=True),
        sa.Column("detail", postgresql.JSONB(), nullable=True),
        sa.Column("utilisateur_id", _UUID, nullable=True),
        sa.Column("utilisateur_nom", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "type_action IN ('CREATION','MAJ_DONNEES','PROPOSITION','ACCEPTATION','MODIFICATION','REJET',"
            "'VERIFICATION')", name="ck_clientele_journal_type"),
        sa.CheckConstraint("origine IN ('SAISIE','IMPORT')", name="ck_clientele_journal_origine"),
    )
    op.create_index("ix_clientele_journal_racine", "clientele_journal", ["racine_client", "created_at"])
    op.create_index("ix_clientele_journal_lot", "clientele_journal", ["lot_id", "ligne_source"])
    op.create_index("ix_clientele_journal_date", "clientele_journal", ["created_at"])

    op.create_table(
        "clientele_kyc",
        sa.Column("racine_client", sa.String(6),
                  sa.ForeignKey("clientele_clients.racine_client", ondelete="RESTRICT", onupdate="RESTRICT"),
                  primary_key=True),
        sa.Column("date_eer", sa.Date(), nullable=True),
        sa.Column("profil", sa.String(80), nullable=True),
        sa.Column("sous_profil", sa.String(80), nullable=True),
        sa.Column("statut_gel", sa.String(80), nullable=True),
        sa.Column("date_maj_client", sa.Date(), nullable=True),
        sa.Column("analyste_kyc", sa.String(120), nullable=True),
        sa.Column("date_creation_entreprise", sa.Date(), nullable=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("lot_id", _UUID, nullable=True),
        sa.Column("ligne_source", sa.Integer(), nullable=True),
        sa.Column("maj_par_id", _UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("maj_le", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.execute("""
        CREATE OR REPLACE FUNCTION clientele_journal_immuable() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Journal clientèle : modification ou suppression interdite'
                USING ERRCODE = 'P0001';
        END $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_clientele_journal_immuable BEFORE UPDATE OR DELETE ON clientele_journal
        FOR EACH ROW EXECUTE FUNCTION clientele_journal_immuable()
    """)
    op.execute("""
        CREATE TRIGGER trg_clientele_journal_truncate BEFORE TRUNCATE ON clientele_journal
        FOR EACH STATEMENT EXECUTE FUNCTION clientele_journal_immuable()
    """)

    op.execute(f"""
        CREATE OR REPLACE FUNCTION clientele_classif_historique_protege() RETURNS trigger AS $$
        BEGIN
            IF TG_OP IN ('DELETE', 'TRUNCATE') THEN
                RAISE EXCEPTION 'Historique de classification : suppression interdite' USING ERRCODE = 'P0001';
            END IF;
            IF (to_jsonb(NEW) - {_REFERENCES_HISTO}) IS DISTINCT FROM (to_jsonb(OLD) - {_REFERENCES_HISTO})
               OR (NEW.lot_id IS NOT NULL AND NEW.lot_id IS DISTINCT FROM OLD.lot_id)
               OR (NEW.version_id IS NOT NULL AND NEW.version_id IS DISTINCT FROM OLD.version_id)
               OR (NEW.evaluation_id IS NOT NULL AND NEW.evaluation_id IS DISTINCT FROM OLD.evaluation_id)
               OR (NEW.created_by_id IS NOT NULL AND NEW.created_by_id IS DISTINCT FROM OLD.created_by_id) THEN
                RAISE EXCEPTION 'Historique de classification : modification interdite' USING ERRCODE = 'P0001';
            END IF;
            RETURN NEW;
        END $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_clientele_classif_historique_protege
        BEFORE UPDATE OR DELETE ON clientele_classif_historique
        FOR EACH ROW EXECUTE FUNCTION clientele_classif_historique_protege()
    """)
    op.execute("""
        CREATE TRIGGER trg_clientele_classif_historique_truncate BEFORE TRUNCATE ON clientele_classif_historique
        FOR EACH STATEMENT EXECUTE FUNCTION clientele_classif_historique_protege()
    """)

    op.drop_constraint("ck_clientele_classif_lot_lignes_statut", "clientele_classif_lot_lignes", type_="check")
    op.create_check_constraint("ck_clientele_classif_lot_lignes_statut", "clientele_classif_lot_lignes",
                               "statut IN ('OK','INCONNUE','INVALIDE','DOUBLON','AMBIGU')")


def downgrade() -> None:
    op.drop_constraint("ck_clientele_classif_lot_lignes_statut", "clientele_classif_lot_lignes", type_="check")
    op.create_check_constraint("ck_clientele_classif_lot_lignes_statut", "clientele_classif_lot_lignes",
                               "statut IN ('OK','INCONNUE','INVALIDE','DOUBLON')")
    for trg, table in (("trg_clientele_classif_historique_truncate", "clientele_classif_historique"),
                       ("trg_clientele_classif_historique_protege", "clientele_classif_historique"),
                       ("trg_clientele_journal_truncate", "clientele_journal"),
                       ("trg_clientele_journal_immuable", "clientele_journal")):
        op.execute(f"DROP TRIGGER IF EXISTS {trg} ON {table}")
    op.execute("DROP FUNCTION IF EXISTS clientele_classif_historique_protege()")
    op.execute("DROP FUNCTION IF EXISTS clientele_journal_immuable()")
    op.drop_table("clientele_kyc")
    op.drop_index("ix_clientele_journal_date", table_name="clientele_journal")
    op.drop_index("ix_clientele_journal_lot", table_name="clientele_journal")
    op.drop_index("ix_clientele_journal_racine", table_name="clientele_journal")
    op.drop_table("clientele_journal")
