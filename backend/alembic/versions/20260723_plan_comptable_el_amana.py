"""Plan comptable El Amana — types et parametrage ecritures

Revision ID: 20260723_el_amana
Revises:
Create Date: 2026-07-23

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260723_el_amana"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_TYPEIMMO_VALUES = ("AUTRES", "COFFRES", "AUTRES_CORPORELLES", "FRAIS_EMRT")


def upgrade() -> None:
    for value in NEW_TYPEIMMO_VALUES:
        op.execute(
            sa.text(
                "DO $$ BEGIN "
                f"ALTER TYPE typeimmobilisation ADD VALUE IF NOT EXISTS '{value}'; "
                "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
            )
        )

    op.add_column("categories_immobilisation", sa.Column("compte_immobilisation", sa.String(length=20), nullable=True))
    op.add_column("categories_immobilisation", sa.Column("compte_amortissement", sa.String(length=20), nullable=True))
    op.add_column("categories_immobilisation", sa.Column("compte_dotation", sa.String(length=20), nullable=True))
    op.add_column(
        "categories_immobilisation", sa.Column("comptes_amortissement_alternatifs", sa.String(length=120), nullable=True)
    )
    op.add_column(
        "categories_immobilisation",
        sa.Column("amortissable", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("categories_immobilisation", sa.Column("duree_annees_defaut", sa.Integer(), nullable=True))
    op.add_column("categories_immobilisation", sa.Column("taux_lineaire_defaut", sa.Numeric(8, 4), nullable=True))
    op.add_column(
        "categories_immobilisation",
        sa.Column(
            "mode_amortissement_defaut",
            postgresql.ENUM("LINEAIRE", "DEGRESSIF", name="modeamortissement", create_type=False),
            server_default="LINEAIRE",
            nullable=False,
        ),
    )
    op.add_column(
        "categories_immobilisation",
        sa.Column("periodicite_defaut", sa.String(length=20), server_default="annuel", nullable=False),
    )
    op.add_column(
        "categories_immobilisation",
        sa.Column("prorata_temporis", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.add_column(
        "categories_immobilisation",
        sa.Column("journal_code", sa.String(length=10), server_default="OD", nullable=False),
    )
    op.create_index("ix_categories_immobilisation_compte_immobilisation", "categories_immobilisation", ["compte_immobilisation"])

    op.create_table(
        "parametrage_ecritures",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("categorie_id", sa.UUID(), nullable=False),
        sa.Column("journal_code", sa.String(length=10), nullable=False),
        sa.Column("compte_debit", sa.String(length=20), nullable=False),
        sa.Column("compte_credit", sa.String(length=20), nullable=False),
        sa.Column("libelle_modele", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(["categorie_id"], ["categories_immobilisation.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("categorie_id"),
    )
    op.create_index("ix_parametrage_ecritures_categorie_id", "parametrage_ecritures", ["categorie_id"])


def downgrade() -> None:
    op.drop_index("ix_parametrage_ecritures_categorie_id", table_name="parametrage_ecritures")
    op.drop_table("parametrage_ecritures")
    op.drop_index("ix_categories_immobilisation_compte_immobilisation", table_name="categories_immobilisation")
    op.drop_column("categories_immobilisation", "journal_code")
    op.drop_column("categories_immobilisation", "prorata_temporis")
    op.drop_column("categories_immobilisation", "periodicite_defaut")
    op.drop_column("categories_immobilisation", "mode_amortissement_defaut")
    op.drop_column("categories_immobilisation", "taux_lineaire_defaut")
    op.drop_column("categories_immobilisation", "duree_annees_defaut")
    op.drop_column("categories_immobilisation", "amortissable")
    op.drop_column("categories_immobilisation", "comptes_amortissement_alternatifs")
    op.drop_column("categories_immobilisation", "compte_dotation")
    op.drop_column("categories_immobilisation", "compte_amortissement")
    op.drop_column("categories_immobilisation", "compte_immobilisation")
