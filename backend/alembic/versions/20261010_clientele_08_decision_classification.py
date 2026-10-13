"""Classification : séparation calcul / source / décision, lots persistants, réexamens.

Directive du 10/10/2026. Additif : aucune classification n'est recalculée ni réécrite.
Copie de test / recette uniquement, jamais ``bea_digital`` sans restauration du dump.

Revision ID: 20261010_clientele_08
Revises: 20261008_clientele_07
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261010_clientele_08"
down_revision: Union[str, None] = "20261008_clientele_07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UUID = postgresql.UUID(as_uuid=True)
_JSONB = postgresql.JSONB()


def _user(name: str) -> sa.Column:
    return sa.Column(name, _UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


def _trace_colonnes() -> list[sa.Column]:
    return [
        sa.Column("score_calcule", sa.Integer(), nullable=True),
        sa.Column("niveau_propose", sa.String(12), nullable=True),
        sa.Column("classe_source_fichier", sa.String(12), nullable=True),
        sa.Column("mode_decision", sa.String(12), nullable=True),
        sa.Column("motif_moteur", sa.Text(), nullable=True),
        sa.Column("motif_source", sa.Text(), nullable=True),
        sa.Column("motif_decision_manuelle", sa.Text(), nullable=True),
        sa.Column("evaluation_id", _UUID,
                  sa.ForeignKey("clientele_classif_evaluations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("lot_id", _UUID, sa.ForeignKey("clientele_classif_lots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ligne_source", sa.Integer(), nullable=True),
        sa.Column("date_maj_metier", sa.Date(), nullable=True),
        sa.Column("analyste_kyc", sa.String(120), nullable=True),
        sa.Column("date_reference", sa.Date(), nullable=True),
        sa.Column("version_moteur", sa.String(40), nullable=True),
        sa.Column("version_regles", sa.String(40), nullable=True),
        sa.Column("force", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("blocage_leve", sa.Boolean(), nullable=False, server_default=sa.false()),
    ]


_TRACE = [c.name for c in _trace_colonnes()]


def upgrade() -> None:
    op.create_table(
        "clientele_classif_lots",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("fichier_nom", sa.String(255), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("type", sa.String(16), nullable=False, server_default="LISTE"),
        sa.Column("periode_reference", sa.Date(), nullable=True),
        sa.Column("feuille", sa.String(120), nullable=True),
        sa.Column("ligne_entete", sa.Integer(), nullable=True),
        sa.Column("entetes", _JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("mapping", _JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("stats", _JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("evaluation", _JSONB, nullable=True),
        sa.Column("dernier_classement", _JSONB, nullable=True),
        sa.Column("statut", sa.String(16), nullable=False, server_default="ANALYSE"),
        _user("created_by_id"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("type IN ('LISTE','SITUATION')", name="ck_clientele_classif_lots_type"),
        sa.CheckConstraint("statut IN ('ANALYSE','EVALUE','ENREGISTRE','FERME')",
                           name="ck_clientele_classif_lots_statut"),
    )
    op.create_index("ix_clientele_classif_lots_sha", "clientele_classif_lots", ["sha256"])

    op.create_table(
        "clientele_classif_lot_lignes",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("lot_id", _UUID, sa.ForeignKey("clientele_classif_lots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ligne", sa.Integer(), nullable=False),
        sa.Column("brut", sa.String(40), nullable=True),
        sa.Column("racine_client", sa.String(6), nullable=True),
        sa.Column("statut", sa.String(12), nullable=False),
        sa.Column("nom", sa.String(255), nullable=True),
        sa.Column("donnees", _JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("classe_source", sa.String(12), nullable=True),
        sa.Column("classe_source_brut", sa.String(40), nullable=True),
        sa.Column("motif_source", sa.Text(), nullable=True),
        sa.Column("entreprise_recente_brut", sa.String(40), nullable=True),
        sa.Column("date_ouverture_entreprise", sa.Date(), nullable=True),
        sa.Column("date_ouverture_brut", sa.String(40), nullable=True),
        sa.Column("source_date_ouverture", sa.String(20), nullable=True),
        _user("date_ouverture_saisie_par_id"),
        sa.Column("date_ouverture_saisie_le", sa.DateTime(timezone=True), nullable=True),
        sa.Column("date_maj_metier", sa.Date(), nullable=True),
        sa.Column("date_maj_brut", sa.String(40), nullable=True),
        sa.Column("analyste_kyc", sa.String(120), nullable=True),
        sa.Column("anomalies", _JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("classe_actuelle", sa.String(12), nullable=True),
        sa.Column("source_actuelle", sa.String(32), nullable=True),
        sa.Column("evaluation_id", _UUID,
                  sa.ForeignKey("clientele_classif_evaluations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("niveau_propose", sa.String(12), nullable=True),
        sa.Column("statut_moteur", sa.String(24), nullable=True),
        sa.Column("motif_moteur", sa.Text(), nullable=True),
        sa.Column("admissible", sa.Boolean(), nullable=True),
        sa.Column("divergence_fichier_moteur", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("decision", sa.String(24), nullable=True),
        sa.Column("decision_detail", _JSONB, nullable=True),
        sa.UniqueConstraint("lot_id", "ligne", name="uq_clientele_classif_lot_ligne"),
        sa.CheckConstraint("statut IN ('OK','INCONNUE','INVALIDE','DOUBLON')",
                           name="ck_clientele_classif_lot_lignes_statut"),
    )
    op.create_index("ix_clientele_classif_lot_lignes_racine", "clientele_classif_lot_lignes", ["racine_client"])

    op.create_table(
        "clientele_classif_reexamens",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("racine_client", sa.String(6),
                  sa.ForeignKey("clientele_clients.racine_client", ondelete="RESTRICT", onupdate="RESTRICT"),
                  nullable=False),
        sa.Column("origine", sa.String(16), nullable=False),
        sa.Column("lot_id", _UUID, sa.ForeignKey("clientele_classif_lots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ligne_source", sa.Integer(), nullable=True),
        sa.Column("niveau_actuel", sa.String(12), nullable=True),
        sa.Column("source_actuelle", sa.String(32), nullable=True),
        sa.Column("niveau_suggere", sa.String(12), nullable=False),
        sa.Column("source_suggestion", sa.String(12), nullable=False),
        sa.Column("motif", sa.Text(), nullable=False),
        sa.Column("statut", sa.String(12), nullable=False, server_default="OUVERT"),
        sa.Column("decision", sa.Text(), nullable=True),
        _user("created_by_id"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        _user("traite_par_id"),
        sa.Column("traite_le", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("statut IN ('OUVERT','TRAITE','CLOS')", name="ck_clientele_classif_reexamens_statut"),
        sa.CheckConstraint("source_suggestion IN ('MOTEUR','FICHIER')",
                           name="ck_clientele_classif_reexamens_source"),
    )
    op.create_index("ix_clientele_classif_reexamens_statut", "clientele_classif_reexamens",
                    ["statut", "racine_client"])
    op.create_index("uq_clientele_classif_reexamen_ouvert", "clientele_classif_reexamens",
                    ["racine_client", "source_suggestion", "niveau_suggere"], unique=True,
                    postgresql_where=sa.text("statut = 'OUVERT'"))

    op.create_table(
        "clientele_classif_divergence_decisions",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("divergence_id", _UUID,
                  sa.ForeignKey("clientele_classif_divergences.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ancien_statut", sa.String(24), nullable=True),
        sa.Column("nouveau_statut", sa.String(24), nullable=False),
        sa.Column("decision", sa.Text(), nullable=True),
        sa.Column("justification", sa.Text(), nullable=False),
        _user("created_by_id"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_clientele_classif_divergence_decisions_divergence_id",
                    "clientele_classif_divergence_decisions", ["divergence_id"])

    for table in ("clientele_classifications", "clientele_classif_historique"):
        for col in _trace_colonnes():
            op.add_column(table, col)
        op.create_check_constraint(
            f"ck_{table}_mode_decision", table,
            "mode_decision IS NULL OR mode_decision IN ('MOTEUR','FICHIER','MANUEL')")
        op.execute(f"""
            UPDATE {table} SET mode_decision = CASE
                WHEN source = 'MOTEUR' THEN 'MOTEUR'
                WHEN source IN ('EXCEL','EXCEL_CONFORMITE') THEN 'FICHIER'
                WHEN source IN ('MANUEL','MANUEL_SURCHARGE') THEN 'MANUEL'
            END
            WHERE mode_decision IS NULL
        """)

    op.add_column("clientele_classif_evaluations", sa.Column("date_reference", sa.Date(), nullable=True))
    op.add_column("clientele_classif_evaluations",
                  sa.Column("source_date_reference", sa.String(20), nullable=True))
    op.add_column("clientele_classif_evaluations",
                  sa.Column("lot_id", _UUID, sa.ForeignKey("clientele_classif_lots.id", ondelete="SET NULL"),
                            nullable=True))
    op.add_column("clientele_classif_evaluations", sa.Column("ligne_source", sa.Integer(), nullable=True))

    op.execute("""
        UPDATE clientele_classif_criteres
        SET libelle = 'Entreprise à ouverture récente',
            description = '[VALIDEE_METIER] Décision métier 10/10/2026 : ancienneté > 366 jours → 100 ; '
                          '≤ 366 jours → 10000, toutes PM. Date : colonne Date ouverture du fichier ou '
                          'saisie analyste, sinon EER. Déclaratif KYC à défaut. Contradiction → À vérifier.',
            champ_defaut = 'date_ouverture_entreprise'
        WHERE code = 'ENTREPRISE_RECENTE'
    """)


def downgrade() -> None:
    op.drop_column("clientele_classif_evaluations", "ligne_source")
    op.drop_column("clientele_classif_evaluations", "lot_id")
    op.drop_column("clientele_classif_evaluations", "source_date_reference")
    op.drop_column("clientele_classif_evaluations", "date_reference")
    for table in ("clientele_classif_historique", "clientele_classifications"):
        op.drop_constraint(f"ck_{table}_mode_decision", table, type_="check")
        for name in reversed(_TRACE):
            op.drop_column(table, name)
    op.drop_table("clientele_classif_divergence_decisions")
    op.drop_index("uq_clientele_classif_reexamen_ouvert", table_name="clientele_classif_reexamens")
    op.drop_table("clientele_classif_reexamens")
    op.drop_table("clientele_classif_lot_lignes")
    op.drop_table("clientele_classif_lots")
