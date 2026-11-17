"""Reporting BCM SM — fondations tables rbcm_* + module catalogue.

Additif. Ne pas appliquer en production v1.0.0 sans procédure de release.

Prérequis DEV :
    alembic -c backend/alembic.ini heads
    alembic -c backend/alembic.ini current

Revision ID: 20261116_rbcm_01
Revises: 20261105_mg_stock_mvt_ref_uq
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261116_rbcm_01"
down_revision: Union[str, None] = "20261105_mg_stock_mvt_ref_uq"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
retour_arriere = "compatible"

MODULE_CODE = "reporting-bcm-sm"
ESPACE_CODE = "comptabilite"

PARAM_DEFS = [
    ("caisse_devises", "Caisse devises", True),
    ("publics_mru", "Publics MRU", False),
    ("publics_dev", "Publics devises", False),
    ("prives_dev", "Privés devises", False),
    ("projets", "Projets", False),
    ("dat_public", "DAT public", False),
    ("amort_frais_immo", "Amortissement frais immobiliers", False),
    ("cautions_dev", "Cautions devises", False),
]


def upgrade() -> None:
    op.create_table(
        "rbcm_campaign",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("period_year", sa.Integer(), nullable=False),
        sa.Column("period_month", sa.Integer(), nullable=False),
        sa.Column("closing_date", sa.Date(), nullable=True),
        sa.Column("bank_code", sa.String(16), nullable=False, server_default="BEA"),
        sa.Column("status", sa.String(24), nullable=False, server_default="BROUILLON"),
        sa.Column("campaign_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("reopened_from_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rbcm_campaign.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("preparer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("controller_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approver_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("mapping_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("template_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("current_batch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("period_month BETWEEN 1 AND 12", name="ck_rbcm_campaign_month"),
        sa.CheckConstraint("campaign_version >= 1", name="ck_rbcm_campaign_version"),
        sa.UniqueConstraint("bank_code", "period_year", "period_month", "campaign_version", name="uq_rbcm_campaign_period_version"),
    )
    op.create_index("ix_rbcm_campaign_period_year", "rbcm_campaign", ["period_year"])
    op.create_index("ix_rbcm_campaign_period_month", "rbcm_campaign", ["period_month"])
    op.create_index("ix_rbcm_campaign_status", "rbcm_campaign", ["status"])

    op.create_table(
        "rbcm_import",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rbcm_campaign.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("file_type", sa.String(16), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("stored_path", sa.String(500), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(24), nullable=False, server_default="UPLOADED"),
        sa.Column("period_year_detected", sa.Integer(), nullable=True),
        sa.Column("period_month_detected", sa.Integer(), nullable=True),
        sa.Column("control_report", postgresql.JSONB(), nullable=True),
        sa.Column("uploaded_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("validated_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("supersedes_import_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rbcm_import.id", ondelete="SET NULL"), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("sum_debit", sa.Numeric(18, 2), nullable=True),
        sa.Column("sum_credit", sa.Numeric(18, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("campaign_id", "file_type", "sha256", name="uq_rbcm_import_sha"),
    )
    op.create_index("ix_rbcm_import_campaign_id", "rbcm_import", ["campaign_id"])
    op.create_index("ix_rbcm_import_sha256", "rbcm_import", ["sha256"])

    op.create_table(
        "rbcm_balance_ncg",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rbcm_campaign.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("import_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rbcm_import.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("ncg", sa.String(32), nullable=False),
        sa.Column("libelle", sa.String(255), nullable=True),
        sa.Column("tot_debit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("tot_credit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("import_id", "ncg", name="uq_rbcm_balance_ncg"),
    )
    op.create_index("ix_rbcm_balance_ncg_campaign_id", "rbcm_balance_ncg", ["campaign_id"])
    op.create_index("ix_rbcm_balance_ncg_ncg", "rbcm_balance_ncg", ["ncg"])

    op.create_table(
        "rbcm_import_line_det",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rbcm_campaign.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("import_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rbcm_import.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("ncg", sa.String(32), nullable=True),
        sa.Column("compte", sa.String(64), nullable=True),
        sa.Column("libelle", sa.String(255), nullable=True),
        sa.Column("devise", sa.String(8), nullable=True),
        sa.Column("debit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("credit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("raw", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_rbcm_import_line_det_import_id", "rbcm_import_line_det", ["import_id"])
    op.create_index("ix_rbcm_import_line_det_ncg", "rbcm_import_line_det", ["ncg"])

    op.create_table(
        "rbcm_reconcile_issue",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rbcm_campaign.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("ncg", sa.String(32), nullable=True),
        sa.Column("severity", sa.String(16), nullable=False, server_default="WARNING"),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=True),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "rbcm_parameter_definition",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("calculable", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("code", name="uq_rbcm_parameter_definition_code"),
    )

    op.create_table(
        "rbcm_parameter_value",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rbcm_campaign.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("parameter_code", sa.String(64), nullable=False),
        sa.Column("value", sa.Numeric(18, 2), nullable=True),
        sa.Column("source", sa.String(64), nullable=True),
        sa.Column("justification", sa.Text(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="EN_ATTENTE"),
        sa.Column("authored_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("validated_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("supersedes_value_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rbcm_parameter_value.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "rbcm_mapping_version",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "rbcm_mapping_rule",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("mapping_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rbcm_mapping_version.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("cell_ref", sa.String(32), nullable=False),
        sa.Column("match_type", sa.String(16), nullable=False, server_default="EXACT"),
        sa.Column("pattern", sa.String(64), nullable=False),
        sa.Column("exclusions", postgresql.JSONB(), nullable=True),
        sa.Column("amount_basis", sa.String(16), nullable=False, server_default="SIGNED"),
        sa.Column("signed_balance_mode", sa.String(32), nullable=False, server_default="NATURAL"),
        sa.Column("sign_multiplier", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("provenance", sa.String(32), nullable=False, server_default="CORRESPONDANCE"),
        sa.Column("divergence_group", sa.String(64), nullable=True),
        sa.Column("lifecycle_status", sa.String(16), nullable=False, server_default="A_VALIDER"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_rbcm_mapping_rule_cell_ref", "rbcm_mapping_rule", ["cell_ref"])

    op.create_table(
        "rbcm_mapping_rule_source",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rbcm_mapping_rule.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_name", sa.String(64), nullable=False),
        sa.Column("source_payload", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "rbcm_unmapped_rubric",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("cell_ref", sa.String(32), nullable=False),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="NON_RESOLUE"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("cell_ref", name="uq_rbcm_unmapped_rubric_cell"),
    )

    op.create_table(
        "rbcm_calculation_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rbcm_campaign.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("engine_version", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="RUNNING"),
        sa.Column("fingerprint_imports", sa.String(64), nullable=True),
        sa.Column("fingerprint_mapping", sa.String(64), nullable=True),
        sa.Column("fingerprint_params", sa.String(64), nullable=True),
        sa.Column("fingerprint_template", sa.String(64), nullable=True),
        sa.Column("started_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("report", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "rbcm_cell_result",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rbcm_calculation_run.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rbcm_campaign.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("cell_ref", sa.String(32), nullable=False),
        sa.Column("calculated_value", sa.Numeric(18, 2), nullable=True),
        sa.Column("retained_value", sa.Numeric(18, 2), nullable=True),
        sa.Column("value_status", sa.String(32), nullable=False, server_default="NON_RENSEIGNE"),
        sa.Column("traces", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("run_id", "cell_ref", name="uq_rbcm_cell_result_run_cell"),
    )

    op.create_table(
        "rbcm_cell_decision",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rbcm_campaign.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("cell_ref", sa.String(32), nullable=False),
        sa.Column("calculation_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rbcm_calculation_run.id", ondelete="SET NULL"), nullable=True),
        sa.Column("calculated_value", sa.Numeric(18, 2), nullable=True),
        sa.Column("decided_value", sa.Numeric(18, 2), nullable=True),
        sa.Column("decision_type", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("reviewed_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("supersedes_decision_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rbcm_cell_decision.id", ondelete="SET NULL"), nullable=True),
    )

    op.create_table(
        "rbcm_ecart_snapshot",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rbcm_campaign.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rbcm_calculation_run.id", ondelete="SET NULL"), nullable=True),
        sa.Column("amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("formula_key", sa.String(64), nullable=True),
        sa.Column("source_description", sa.Text(), nullable=True),
        sa.Column("is_active_in_run", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("state", sa.String(24), nullable=False, server_default="DESACTIVE"),
        sa.Column("historical_ref_2873223", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("historical_ref_2873218", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "rbcm_control_result",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rbcm_campaign.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rbcm_calculation_run.id", ondelete="SET NULL"), nullable=True),
        sa.Column("control_code", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("result", sa.String(16), nullable=False),
        sa.Column("justification", sa.Text(), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=True),
    )

    op.create_table(
        "rbcm_validation_event",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rbcm_campaign.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("from_status", sa.String(24), nullable=True),
        sa.Column("to_status", sa.String(24), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "rbcm_deliverable",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rbcm_campaign.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rbcm_calculation_run.id", ondelete="SET NULL"), nullable=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("stored_path", sa.String(500), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="GENERATED"),
        sa.Column("warnings", postgresql.JSONB(), nullable=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # Seed paramètres + module catalogue (si espace comptabilité présent)
    conn = op.get_bind()
    for code, label, calc in PARAM_DEFS:
        conn.execute(
            sa.text(
                """
                INSERT INTO rbcm_parameter_definition (id, code, label, calculable, active)
                SELECT gen_random_uuid(), :code, :label, :calc, true
                WHERE NOT EXISTS (SELECT 1 FROM rbcm_parameter_definition WHERE code = :code)
                """
            ),
            {"code": code, "label": label, "calc": calc},
        )

    conn.execute(
        sa.text(
            """
            INSERT INTO plateforme_modules
                (id, espace_id, domaine_id, code, label, description, entry_path, statut,
                 status_message, sort_order, is_active, icon)
            SELECT gen_random_uuid(), e.id, NULL, :code,
                   'Reporting BCM — Situation Mensuelle',
                   'Situation Mensuelle BCM : campagnes, balances, paramètres, correspondances, calculs.',
                   '/reporting-bcm-sm/accueil',
                   'developpement',
                   'Module en construction — mapping A_VALIDER, ECART désactivé.',
                   6, true, 'assessment'
            FROM plateforme_espaces e
            WHERE e.code = :espace
            ON CONFLICT (code) DO NOTHING
            """
        ),
        {"code": MODULE_CODE, "espace": ESPACE_CODE},
    )


def downgrade() -> None:
    for table in [
        "rbcm_deliverable",
        "rbcm_validation_event",
        "rbcm_control_result",
        "rbcm_ecart_snapshot",
        "rbcm_cell_decision",
        "rbcm_cell_result",
        "rbcm_calculation_run",
        "rbcm_unmapped_rubric",
        "rbcm_mapping_rule_source",
        "rbcm_mapping_rule",
        "rbcm_mapping_version",
        "rbcm_parameter_value",
        "rbcm_parameter_definition",
        "rbcm_reconcile_issue",
        "rbcm_import_line_det",
        "rbcm_balance_ncg",
        "rbcm_import",
        "rbcm_campaign",
    ]:
        op.drop_table(table)
    op.execute(sa.text("DELETE FROM plateforme_modules WHERE code = 'reporting-bcm-sm'"))
