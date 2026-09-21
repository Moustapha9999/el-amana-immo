"""Stock — inventaires campagne + paramètres module (additif).

Revision ID: 20260921_mg_stock_v2
Revises: 20260921_mg_phase2
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260921_mg_stock_v2"
down_revision: Union[str, None] = "20260921_mg_phase2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mg_stock_parametres",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("cle", sa.String(60), nullable=False),
        sa.Column("valeur", sa.String(255), nullable=False),
        sa.Column("libelle", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("cle", name="uq_mg_stock_parametres_cle"),
    )

    op.create_table(
        "mg_inventaires",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("reference", sa.String(40), nullable=False),
        sa.Column("libelle", sa.String(255), nullable=False),
        sa.Column("date_debut", sa.Date(), nullable=False),
        sa.Column("date_fin", sa.Date(), nullable=True),
        sa.Column("agence_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agences.id"), nullable=True),
        sa.Column("statut", sa.String(30), nullable=False, server_default="OUVERT"),
        sa.Column("observation", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("cloture_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cloture_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("reference", name="uq_mg_inventaires_reference"),
    )
    op.create_index("ix_mg_inventaires_statut", "mg_inventaires", ["statut"])
    op.create_index("ix_mg_inventaires_agence_id", "mg_inventaires", ["agence_id"])

    op.create_table(
        "mg_inventaire_lignes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "inventaire_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mg_inventaires.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("article_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mg_articles.id"), nullable=False),
        sa.Column("stock_theorique", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("stock_physique", sa.Numeric(18, 3), nullable=True),
        sa.Column("ecart", sa.Numeric(18, 3), nullable=True),
        sa.Column("observation", sa.String(255), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_mg_inventaire_lignes_inventaire_id", "mg_inventaire_lignes", ["inventaire_id"])
    op.create_index("ix_mg_inventaire_lignes_article_id", "mg_inventaire_lignes", ["article_id"])

    # Seed paramètres numérotation / alertes
    import uuid as _uuid

    params = sa.table(
        "mg_stock_parametres",
        sa.column("id", postgresql.UUID),
        sa.column("cle", sa.String),
        sa.column("valeur", sa.String),
        sa.column("libelle", sa.String),
    )
    op.bulk_insert(
        params,
        [
            {"id": str(_uuid.uuid4()), "cle": "prefix_entree", "valeur": "ENT", "libelle": "Préfixe entrées"},
            {"id": str(_uuid.uuid4()), "cle": "prefix_sortie", "valeur": "SOR", "libelle": "Préfixe sorties"},
            {
                "id": str(_uuid.uuid4()),
                "cle": "prefix_inventaire",
                "valeur": "INV",
                "libelle": "Préfixe inventaires",
            },
            {"id": str(_uuid.uuid4()), "cle": "prefix_demande", "valeur": "DF", "libelle": "Préfixe demandes"},
            {
                "id": str(_uuid.uuid4()),
                "cle": "alerte_seuil_actif",
                "valeur": "1",
                "libelle": "Alertes stock bas actives",
            },
        ],
    )


def downgrade() -> None:
    op.drop_table("mg_inventaire_lignes")
    op.drop_table("mg_inventaires")
    op.drop_table("mg_stock_parametres")
