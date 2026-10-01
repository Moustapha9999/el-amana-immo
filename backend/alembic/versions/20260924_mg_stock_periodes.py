"""Stock — périodes mensuelles, soldes, stockable, inventaire (additif).

Revision ID: 20260924_mg_stock_periodes
Revises: 20260923_fournisseurs_enrich
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260924_mg_stock_periodes"
down_revision: Union[str, None] = "20260923_fournisseurs_enrich"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_names(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def _cols(bind, table: str) -> set[str]:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def _indexes(bind, table: str) -> set[str]:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return set()
    return {i["name"] for i in insp.get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()
    tables = _table_names(bind)
    arts = _cols(bind, "mg_articles")

    if "reference" not in arts:
        op.add_column("mg_articles", sa.Column("reference", sa.String(80), nullable=True))
    if "sous_famille" not in arts:
        op.add_column("mg_articles", sa.Column("sous_famille", sa.String(120), nullable=True))
    if "stockable" not in arts:
        op.add_column(
            "mg_articles",
            sa.Column("stockable", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        )
    if "fournisseur_habituel" not in arts:
        op.add_column("mg_articles", sa.Column("fournisseur_habituel", sa.String(255), nullable=True))

    if "mg_stock_periodes" not in tables:
        op.create_table(
            "mg_stock_periodes",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("annee", sa.Integer(), nullable=False),
            sa.Column("mois", sa.Integer(), nullable=False),
            sa.Column("libelle", sa.String(80), nullable=False),
            sa.Column("date_debut", sa.Date(), nullable=False),
            sa.Column("date_fin", sa.Date(), nullable=False),
            sa.Column("statut", sa.String(20), nullable=False, server_default="OUVERTE"),
            sa.Column("agence_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agences.id"), nullable=True),
            sa.Column(
                "periode_precedente_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("mg_stock_periodes.id"),
                nullable=True,
            ),
            sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("opened_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("cloture_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cloture_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("reopen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reopen_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("reopen_motif", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("annee", "mois", name="uq_mg_stock_periodes_annee_mois"),
        )
        op.create_index("ix_mg_stock_periodes_annee", "mg_stock_periodes", ["annee"])
        op.create_index("ix_mg_stock_periodes_mois", "mg_stock_periodes", ["mois"])
        op.create_index("ix_mg_stock_periodes_statut", "mg_stock_periodes", ["statut"])
        op.create_index("ix_mg_stock_periodes_agence_id", "mg_stock_periodes", ["agence_id"])

    if "mg_stock_soldes" not in _table_names(bind):
        op.create_table(
            "mg_stock_soldes",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "periode_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("mg_stock_periodes.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "article_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("mg_articles.id"),
                nullable=False,
            ),
            sa.Column("stock_initial", sa.Numeric(18, 3), nullable=False, server_default="0"),
            sa.Column("entrees", sa.Numeric(18, 3), nullable=False, server_default="0"),
            sa.Column("sorties", sa.Numeric(18, 3), nullable=False, server_default="0"),
            sa.Column("ajustements", sa.Numeric(18, 3), nullable=False, server_default="0"),
            sa.Column("stock_theorique", sa.Numeric(18, 3), nullable=False, server_default="0"),
            sa.Column("stock_physique", sa.Numeric(18, 3), nullable=True),
            sa.Column("ecart", sa.Numeric(18, 3), nullable=True),
            sa.Column("stock_final", sa.Numeric(18, 3), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("periode_id", "article_id", name="uq_mg_stock_soldes_periode_article"),
        )
        op.create_index("ix_mg_stock_soldes_periode_id", "mg_stock_soldes", ["periode_id"])
        op.create_index("ix_mg_stock_soldes_article_id", "mg_stock_soldes", ["article_id"])

    mvts = _cols(bind, "mg_stock_mouvements")
    if "periode_id" not in mvts:
        op.add_column(
            "mg_stock_mouvements",
            sa.Column(
                "periode_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("mg_stock_periodes.id"),
                nullable=True,
            ),
        )
        op.create_index("ix_mg_stock_mouvements_periode_id", "mg_stock_mouvements", ["periode_id"])

    invs = _cols(bind, "mg_inventaires")
    if "periode_id" not in invs:
        op.add_column(
            "mg_inventaires",
            sa.Column(
                "periode_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("mg_stock_periodes.id"),
                nullable=True,
            ),
        )
        op.create_index("ix_mg_inventaires_periode_id", "mg_inventaires", ["periode_id"])
    if "valide_at" not in invs:
        op.add_column("mg_inventaires", sa.Column("valide_at", sa.DateTime(timezone=True), nullable=True))
        op.add_column(
            "mg_inventaires",
            sa.Column("valide_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        )
    if "ajustements_at" not in _cols(bind, "mg_inventaires"):
        op.add_column("mg_inventaires", sa.Column("ajustements_at", sa.DateTime(timezone=True), nullable=True))
        op.add_column(
            "mg_inventaires",
            sa.Column(
                "ajustements_by",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id"),
                nullable=True,
            ),
        )

    ligs = _cols(bind, "mg_inventaire_lignes")
    if "nature_ecart" not in ligs:
        op.add_column("mg_inventaire_lignes", sa.Column("nature_ecart", sa.String(20), nullable=True))

    idx = _indexes(bind, "mg_stock_mouvements")
    if "uq_mg_stock_mvt_demande_sortie" not in idx:
        op.execute(
            sa.text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_mg_stock_mvt_demande_sortie "
                "ON mg_stock_mouvements (source_id, article_id) "
                "WHERE source_type = 'demande_fourniture' AND type_mouvement = 'SORTIE'"
            )
        )
    if "uq_mg_stock_mvt_inv_ajust" not in _indexes(bind, "mg_stock_mouvements"):
        op.execute(
            sa.text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_mg_stock_mvt_inv_ajust "
                "ON mg_stock_mouvements (source_id, article_id) "
                "WHERE source_type = 'inventaire' AND type_mouvement = 'AJUSTEMENT'"
            )
        )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS uq_mg_stock_mvt_inv_ajust"))
    op.execute(sa.text("DROP INDEX IF EXISTS uq_mg_stock_mvt_demande_sortie"))
    bind = op.get_bind()
    if "nature_ecart" in _cols(bind, "mg_inventaire_lignes"):
        op.drop_column("mg_inventaire_lignes", "nature_ecart")
    invs = _cols(bind, "mg_inventaires")
    for col in ("ajustements_by", "ajustements_at", "valide_by", "valide_at", "periode_id"):
        if col in invs:
            if col == "periode_id":
                op.drop_index("ix_mg_inventaires_periode_id", table_name="mg_inventaires")
            op.drop_column("mg_inventaires", col)
    if "periode_id" in _cols(bind, "mg_stock_mouvements"):
        op.drop_index("ix_mg_stock_mouvements_periode_id", table_name="mg_stock_mouvements")
        op.drop_column("mg_stock_mouvements", "periode_id")
    if "mg_stock_soldes" in _table_names(bind):
        op.drop_table("mg_stock_soldes")
    if "mg_stock_periodes" in _table_names(bind):
        op.drop_table("mg_stock_periodes")
    arts = _cols(bind, "mg_articles")
    for col in ("fournisseur_habituel", "stockable", "sous_famille", "reference"):
        if col in arts:
            op.drop_column("mg_articles", col)
