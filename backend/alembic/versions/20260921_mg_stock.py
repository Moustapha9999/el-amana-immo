"""Stock & Fournitures — révision additive Moyens Généraux Phase 1.

Revision ID: 20260921_mg_stock
Revises: 20260919_security_center
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260921_mg_stock"
down_revision: Union[str, None] = "20260919_security_center"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mg_article_familles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("libelle", sa.String(120), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("code", name="uq_mg_article_familles_code"),
    )
    op.create_index("ix_mg_article_familles_code", "mg_article_familles", ["code"])

    op.create_table(
        "mg_articles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("designation", sa.String(255), nullable=False),
        sa.Column("famille_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mg_article_familles.id"), nullable=False),
        sa.Column("uom", sa.String(20), nullable=False, server_default="U"),
        sa.Column("stock_actuel", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("stock_min", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("stock_max", sa.Numeric(18, 3), nullable=True),
        sa.Column("agence_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agences.id"), nullable=True),
        sa.Column("emplacement", sa.String(120), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("code", name="uq_mg_articles_code"),
    )
    op.create_index("ix_mg_articles_code", "mg_articles", ["code"])
    op.create_index("ix_mg_articles_famille_id", "mg_articles", ["famille_id"])
    op.create_index("ix_mg_articles_agence_id", "mg_articles", ["agence_id"])

    op.create_table(
        "mg_stock_mouvements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("reference", sa.String(40), nullable=False),
        sa.Column("date_mouvement", sa.DateTime(timezone=True), nullable=False),
        sa.Column("type_mouvement", sa.String(20), nullable=False),
        sa.Column("article_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mg_articles.id"), nullable=False),
        sa.Column("quantite", sa.Numeric(18, 3), nullable=False),
        sa.Column("agence_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agences.id"), nullable=True),
        sa.Column("departement", sa.String(120), nullable=True),
        sa.Column("initiateur_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("motif", sa.String(255), nullable=True),
        sa.Column("observation", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(40), nullable=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_mg_stock_mouvements_reference", "mg_stock_mouvements", ["reference"])
    op.create_index("ix_mg_stock_mouvements_type", "mg_stock_mouvements", ["type_mouvement"])
    op.create_index("ix_mg_stock_mouvements_article_id", "mg_stock_mouvements", ["article_id"])
    op.create_index("ix_mg_stock_mouvements_agence_id", "mg_stock_mouvements", ["agence_id"])

    op.create_table(
        "mg_demandes_fourniture",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("reference", sa.String(40), nullable=False),
        sa.Column("date_demande", sa.Date(), nullable=False),
        sa.Column("agence_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agences.id"), nullable=False),
        sa.Column("agence_libelle_snapshot", sa.String(255), nullable=True),
        sa.Column("agence_adresse_snapshot", sa.Text(), nullable=True),
        sa.Column("departement", sa.String(120), nullable=True),
        sa.Column("demandeur_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("demandeur_nom", sa.String(255), nullable=True),
        sa.Column("fonction", sa.String(120), nullable=True),
        sa.Column("statut", sa.String(30), nullable=False, server_default="BROUILLON"),
        sa.Column("visa_agence_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("visa_agence_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("visa_mg_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("visa_mg_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("observation", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("reference", name="uq_mg_demandes_fourniture_reference"),
    )
    op.create_index("ix_mg_demandes_fourniture_reference", "mg_demandes_fourniture", ["reference"])
    op.create_index("ix_mg_demandes_fourniture_agence_id", "mg_demandes_fourniture", ["agence_id"])
    op.create_index("ix_mg_demandes_fourniture_statut", "mg_demandes_fourniture", ["statut"])

    op.create_table(
        "mg_demande_fourniture_lignes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "demande_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mg_demandes_fourniture.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("article_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mg_articles.id"), nullable=True),
        sa.Column("designation", sa.String(255), nullable=False),
        sa.Column("quantite_demandee", sa.Numeric(18, 3), nullable=False),
        sa.Column("quantite_accordee", sa.Numeric(18, 3), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_mg_demande_fourniture_lignes_demande_id", "mg_demande_fourniture_lignes", ["demande_id"])

    # Familles seed (idempotent via codes)
    op.execute(
        """
        INSERT INTO mg_article_familles (id, code, libelle, sort_order, is_active, created_at, updated_at)
        VALUES
          (gen_random_uuid(), 'economat', 'Économat', 1, true, now(), now()),
          (gen_random_uuid(), 'papeterie', 'Papeterie', 2, true, now(), now()),
          (gen_random_uuid(), 'pre_imprime', 'Pré-imprimé', 3, true, now(), now()),
          (gen_random_uuid(), 'conso_gab', 'Consommables GAB', 4, true, now(), now())
        ON CONFLICT (code) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("mg_demande_fourniture_lignes")
    op.drop_table("mg_demandes_fourniture")
    op.drop_table("mg_stock_mouvements")
    op.drop_table("mg_articles")
    op.drop_table("mg_article_familles")
