"""Contrats MG — agence, échéances, paiements, historique, types, paramètres.

Revision ID: 20260925_mg_contrats_v2
Revises: 20260924_mg_notes_v2
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260925_mg_contrats_v2"
down_revision: Union[str, None] = "20260924_mg_notes_v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _cols(bind, table: str) -> set[str]:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def _tables(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)
    cols = _cols(bind, "mg_contrats")
    additions = [
        ("agence_id", postgresql.UUID(as_uuid=True)),
        ("agence_libelle_snapshot", sa.String(255)),
        ("type_contrat", sa.String(40)),
        ("numero_contrat", sa.String(80)),
        ("description", sa.Text()),
        ("date_signature", sa.Date()),
        ("devise", sa.String(8)),
        ("montant_ht", sa.Numeric(18, 2)),
        ("taux_tva", sa.Numeric(6, 2)),
        ("responsable_id", postgresql.UUID(as_uuid=True)),
        ("responsable_nom", sa.String(255)),
        ("mode_paiement", sa.String(40)),
        ("contrat_precedent_id", postgresql.UUID(as_uuid=True)),
    ]
    for name, coltype in additions:
        if name not in cols:
            op.add_column("mg_contrats", sa.Column(name, coltype, nullable=True))
    if "type_contrat" in _cols(bind, "mg_contrats"):
        op.execute("UPDATE mg_contrats SET type_contrat = 'AUTRE' WHERE type_contrat IS NULL")
        op.execute("UPDATE mg_contrats SET devise = 'MRU' WHERE devise IS NULL")
    op.execute(
        """
        DO $$ BEGIN
          ALTER TABLE mg_contrats
            ADD CONSTRAINT fk_mg_contrats_agence
            FOREIGN KEY (agence_id) REFERENCES agences(id);
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
          ALTER TABLE mg_contrats
            ADD CONSTRAINT fk_mg_contrats_responsable
            FOREIGN KEY (responsable_id) REFERENCES users(id);
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
          ALTER TABLE mg_contrats
            ADD CONSTRAINT fk_mg_contrats_precedent
            FOREIGN KEY (contrat_precedent_id) REFERENCES mg_contrats(id);
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_mg_contrats_agence_id ON mg_contrats (agence_id)")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_mg_contrats_renouvellement
        ON mg_contrats (contrat_precedent_id)
        WHERE contrat_precedent_id IS NOT NULL
          AND deleted_at IS NULL
          AND statut <> 'ANNULE'
        """
    )

    if "mg_contrat_echeances" not in tables:
        op.create_table(
            "mg_contrat_echeances",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("contrat_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mg_contrats.id", ondelete="CASCADE"), nullable=False),
            sa.Column("type_echeance", sa.String(40), nullable=False, server_default="AUTRE"),
            sa.Column("date_prevue", sa.Date(), nullable=False),
            sa.Column("date_reelle", sa.Date(), nullable=True),
            sa.Column("montant", sa.Numeric(18, 2), nullable=True),
            sa.Column("responsable_nom", sa.String(255), nullable=True),
            sa.Column("statut", sa.String(30), nullable=False, server_default="A_VENIR"),
            sa.Column("commentaire", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_mg_contrat_echeances_contrat_id", "mg_contrat_echeances", ["contrat_id"])

    if "mg_contrat_paiements" not in tables:
        op.create_table(
            "mg_contrat_paiements",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("contrat_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mg_contrats.id", ondelete="CASCADE"), nullable=False),
            sa.Column("echeance_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mg_contrat_echeances.id", ondelete="SET NULL"), nullable=True),
            sa.Column("reference", sa.String(40), nullable=True),
            sa.Column("date_prevue", sa.Date(), nullable=False),
            sa.Column("date_reelle", sa.Date(), nullable=True),
            sa.Column("montant_prevu", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("montant_paye", sa.Numeric(18, 2), nullable=False, server_default="0"),
            sa.Column("devise", sa.String(8), nullable=False, server_default="MRU"),
            sa.Column("statut", sa.String(30), nullable=False, server_default="A_VENIR"),
            sa.Column("mode", sa.String(40), nullable=True),
            sa.Column("commentaire", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_mg_contrat_paiements_contrat_id", "mg_contrat_paiements", ["contrat_id"])
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_mg_contrat_paiements_ref
        ON mg_contrat_paiements (contrat_id, reference)
        WHERE reference IS NOT NULL
        """
    )

    if "mg_contrat_historique" not in tables:
        op.create_table(
            "mg_contrat_historique",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("contrat_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mg_contrats.id", ondelete="CASCADE"), nullable=False),
            sa.Column("action", sa.String(60), nullable=False),
            sa.Column("from_statut", sa.String(30), nullable=True),
            sa.Column("to_statut", sa.String(30), nullable=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("user_nom", sa.String(255), nullable=True),
            sa.Column("commentaire", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_mg_contrat_historique_contrat_id", "mg_contrat_historique", ["contrat_id"])

    if "mg_contrat_types" not in tables:
        op.create_table(
            "mg_contrat_types",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("code", sa.String(40), nullable=False),
            sa.Column("libelle", sa.String(120), nullable=False),
            sa.Column("actif", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("code", name="uq_mg_contrat_types_code"),
        )

    if "mg_contrat_parametres" not in tables:
        op.create_table(
            "mg_contrat_parametres",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("cle", sa.String(80), nullable=False),
            sa.Column("valeur", sa.String(255), nullable=False, server_default=""),
            sa.Column("libelle", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("cle", name="uq_mg_contrat_parametres_cle"),
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_mg_contrats_renouvellement")
    op.execute("DROP INDEX IF EXISTS ix_mg_contrats_agence_id")
    for table in (
        "mg_contrat_parametres",
        "mg_contrat_types",
        "mg_contrat_historique",
        "mg_contrat_paiements",
        "mg_contrat_echeances",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table}")
    for col in (
        "contrat_precedent_id",
        "mode_paiement",
        "responsable_nom",
        "responsable_id",
        "taux_tva",
        "montant_ht",
        "devise",
        "date_signature",
        "description",
        "numero_contrat",
        "type_contrat",
        "agence_libelle_snapshot",
        "agence_id",
    ):
        op.execute(f"ALTER TABLE mg_contrats DROP COLUMN IF EXISTS {col}")
