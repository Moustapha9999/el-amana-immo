"""Exercices comptables — clôture définitive et ouverture N+1.

Revision ID: 20260729_exercices
Revises: 20260726_auth_sessions
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260729_exercices"
down_revision: Union[str, None] = "20260726_auth_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "exercices_comptables",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("annee", sa.Integer(), nullable=False),
        sa.Column("statut", sa.String(length=20), nullable=False, server_default="ouvert"),
        sa.Column("archive_dossier_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cloture_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cloture_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ouverture_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ouverture_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("total_valeur_brute", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_amortissement", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_vnc", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_dotation_68", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("nb_immobilisations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=True),
        sa.Column("message", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["archive_dossier_id"], ["archive_dossiers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["cloture_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["ouverture_by_id"], ["users.id"]),
        sa.UniqueConstraint("annee", name="uq_exercices_comptables_annee"),
    )
    op.create_index("ix_exercices_comptables_annee", "exercices_comptables", ["annee"])
    op.create_index("ix_exercices_comptables_statut", "exercices_comptables", ["statut"])

    op.create_table(
        "soldes_ouverture_immobilisations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("exercice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("immobilisation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("annee", sa.Integer(), nullable=False),
        sa.Column("annee_source", sa.Integer(), nullable=False),
        sa.Column("valeur_brute_142", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("cumul_148", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("vnc", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("code_inventaire", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["exercice_id"], ["exercices_comptables.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["immobilisation_id"], ["immobilisations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "exercice_id",
            "immobilisation_id",
            name="uq_solde_ouverture_exercice_immo",
        ),
    )
    op.create_index(
        "ix_soldes_ouverture_immobilisations_exercice_id",
        "soldes_ouverture_immobilisations",
        ["exercice_id"],
    )
    op.create_index(
        "ix_soldes_ouverture_immobilisations_immobilisation_id",
        "soldes_ouverture_immobilisations",
        ["immobilisation_id"],
    )
    op.create_index(
        "ix_soldes_ouverture_immobilisations_annee",
        "soldes_ouverture_immobilisations",
        ["annee"],
    )
    op.create_index(
        "ix_soldes_ouverture_immobilisations_annee_source",
        "soldes_ouverture_immobilisations",
        ["annee_source"],
    )

    # Marquer comme clôturés les dossiers ayant une clôture système existante.
    op.execute(
        """
        INSERT INTO exercices_comptables (
            id, annee, statut, archive_dossier_id, cloture_at,
            total_valeur_brute, total_amortissement, total_vnc, total_dotation_68,
            nb_immobilisations, message, created_at, updated_at
        )
        SELECT
            gen_random_uuid(),
            d.annee,
            'cloture',
            d.id,
            COALESCE(d.updated_at, now()),
            0, 0, 0, 0, 0,
            'Migré depuis dossier Archives (clôture système)',
            now(),
            now()
        FROM archive_dossiers d
        WHERE EXISTS (
            SELECT 1 FROM archive_fichiers f
            WHERE f.dossier_id = d.id AND f.kind = 'cloture_systeme'
        )
        ON CONFLICT (annee) DO NOTHING
        """
    )

    # Convertir les lignes synthétiques d'ouverture {N}-12 (montant=0) en soldes d'ouverture.
    # Créer l'exercice OUVERT N+1 s'il n'existe pas encore, puis inserer les soldes.
    op.execute(
        """
        INSERT INTO exercices_comptables (
            id, annee, statut, ouverture_at,
            total_valeur_brute, total_amortissement, total_vnc, total_dotation_68,
            nb_immobilisations, message, created_at, updated_at
        )
        SELECT
            gen_random_uuid(),
            CAST(split_part(a.periode, '-', 1) AS integer) + 1,
            'ouvert',
            now(),
            0, 0, 0, 0, 0,
            'Migré depuis lignes d''ouverture synthétiques',
            now(),
            now()
        FROM amortissements a
        WHERE a.periode ~ '^[0-9]{4}-12$'
          AND a.montant = 0
          AND a.valide IS TRUE
          AND NOT EXISTS (
            SELECT 1 FROM exercices_comptables e
            WHERE e.annee = CAST(split_part(a.periode, '-', 1) AS integer) + 1
          )
        GROUP BY CAST(split_part(a.periode, '-', 1) AS integer) + 1
        """
    )

    op.execute(
        """
        INSERT INTO soldes_ouverture_immobilisations (
            id, exercice_id, immobilisation_id, annee, annee_source,
            valeur_brute_142, cumul_148, vnc, code_inventaire,
            created_at, updated_at
        )
        SELECT
            gen_random_uuid(),
            e.id,
            a.immobilisation_id,
            e.annee,
            CAST(split_part(a.periode, '-', 1) AS integer),
            COALESCE(i.valeur_brute, 0),
            COALESCE(a.cumul, 0),
            COALESCE(a.vnc, COALESCE(i.valeur_brute, 0) - COALESCE(a.cumul, 0)),
            i.code_inventaire,
            now(),
            now()
        FROM amortissements a
        JOIN immobilisations i ON i.id = a.immobilisation_id
        JOIN exercices_comptables e
          ON e.annee = CAST(split_part(a.periode, '-', 1) AS integer) + 1
        WHERE a.periode ~ '^[0-9]{4}-12$'
          AND a.montant = 0
          AND a.valide IS TRUE
          AND NOT EXISTS (
            SELECT 1 FROM soldes_ouverture_immobilisations s
            WHERE s.exercice_id = e.id AND s.immobilisation_id = a.immobilisation_id
          )
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_soldes_ouverture_immobilisations_annee_source",
        table_name="soldes_ouverture_immobilisations",
    )
    op.drop_index(
        "ix_soldes_ouverture_immobilisations_annee",
        table_name="soldes_ouverture_immobilisations",
    )
    op.drop_index(
        "ix_soldes_ouverture_immobilisations_immobilisation_id",
        table_name="soldes_ouverture_immobilisations",
    )
    op.drop_index(
        "ix_soldes_ouverture_immobilisations_exercice_id",
        table_name="soldes_ouverture_immobilisations",
    )
    op.drop_table("soldes_ouverture_immobilisations")
    op.drop_index("ix_exercices_comptables_statut", table_name="exercices_comptables")
    op.drop_index("ix_exercices_comptables_annee", table_name="exercices_comptables")
    op.drop_table("exercices_comptables")
