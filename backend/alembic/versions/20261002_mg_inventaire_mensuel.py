"""Stock MG — inventaire mensuel : statuts métier, période, responsable, comptage par ligne, import Excel.

Statuts : BROUILLON → EN_COURS → A_CONTROLER → VALIDE → AJUSTE → ARCHIVE (+ ANNULE).
Reprise des anciens statuts (OUVERT, EN_COMPTAGE, COMPTAGE_TERMINE, EN_CONTROLE,
AJUSTEMENTS_APPLIQUES, CLOTURE, REJETE).

Revision ID: 20261002_mg_inventaire_mensuel
Revises: 20261001_contrats_avenants
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "20261002_mg_inventaire_mensuel"
down_revision: Union[str, None] = "20261001_contrats_avenants"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ZERO_UUID = "'00000000-0000-0000-0000-000000000000'::uuid"

_STATUTS = {
    "OUVERT": "BROUILLON",
    "EN_COMPTAGE": "EN_COURS",
    "COMPTAGE_TERMINE": "A_CONTROLER",
    "EN_CONTROLE": "A_CONTROLER",
    "AJUSTEMENTS_APPLIQUES": "AJUSTE",
    "CLOTURE": "ARCHIVE",
    "REJETE": "ANNULE",
}


def _add(table: str, existing: set[str], column: sa.Column) -> None:
    if column.name not in existing:
        op.add_column(table, column)


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())

    inv_cols = {c["name"] for c in insp.get_columns("mg_inventaires")}
    _add("mg_inventaires", inv_cols, sa.Column("annee", sa.Integer(), nullable=True))
    _add("mg_inventaires", inv_cols, sa.Column("mois", sa.Integer(), nullable=True))
    _add(
        "mg_inventaires",
        inv_cols,
        sa.Column("famille_id", UUID(as_uuid=True), sa.ForeignKey("mg_article_familles.id"), nullable=True),
    )
    _add(
        "mg_inventaires",
        inv_cols,
        sa.Column("responsable_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    _add("mg_inventaires", inv_cols, sa.Column("responsable_nom", sa.String(160), nullable=True))
    _add(
        "mg_inventaires",
        inv_cols,
        sa.Column("source", sa.String(20), nullable=False, server_default="MANUEL"),
    )
    _add("mg_inventaires", inv_cols, sa.Column("import_meta", JSONB(), nullable=True))
    _add("mg_inventaires", inv_cols, sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=True))
    _add(
        "mg_inventaires",
        inv_cols,
        sa.Column("updated_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    _add(
        "mg_inventaires",
        inv_cols,
        sa.Column("validation_forcee", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    _add("mg_inventaires", inv_cols, sa.Column("annule_at", sa.DateTime(timezone=True), nullable=True))
    _add(
        "mg_inventaires",
        inv_cols,
        sa.Column("annule_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    _add("mg_inventaires", inv_cols, sa.Column("motif_annulation", sa.Text(), nullable=True))

    for ancien, nouveau in _STATUTS.items():
        op.execute(f"UPDATE mg_inventaires SET statut = '{nouveau}' WHERE statut = '{ancien}'")
    op.execute("ALTER TABLE mg_inventaires ALTER COLUMN statut SET DEFAULT 'BROUILLON'")
    op.execute(
        """
        UPDATE mg_inventaires i
           SET annee = COALESCE((SELECT p.annee FROM mg_stock_periodes p WHERE p.id = i.periode_id),
                                EXTRACT(YEAR FROM i.date_debut)::int),
               mois = COALESCE((SELECT p.mois FROM mg_stock_periodes p WHERE p.id = i.periode_id),
                               EXTRACT(MONTH FROM i.date_debut)::int)
         WHERE i.annee IS NULL OR i.mois IS NULL
        """
    )
    op.execute("UPDATE mg_inventaires SET snapshot_at = created_at WHERE snapshot_at IS NULL")

    lig_cols = {c["name"] for c in insp.get_columns("mg_inventaire_lignes")}
    _add(
        "mg_inventaire_lignes",
        lig_cols,
        sa.Column("statut_comptage", sa.String(20), nullable=False, server_default="NON_COMPTE"),
    )
    _add(
        "mg_inventaire_lignes",
        lig_cols,
        sa.Column("compte_par", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    _add("mg_inventaire_lignes", lig_cols, sa.Column("compte_at", sa.DateTime(timezone=True), nullable=True))
    _add(
        "mg_inventaire_lignes",
        lig_cols,
        sa.Column("stock_theorique_source", sa.Numeric(18, 3), nullable=True),
    )
    _add(
        "mg_inventaire_lignes",
        lig_cols,
        sa.Column("ajout_manuel", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(
        "UPDATE mg_inventaire_lignes SET statut_comptage = 'COMPTE' "
        "WHERE stock_physique IS NOT NULL AND statut_comptage = 'NON_COMPTE'"
    )

    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_mg_inventaire_lignes_inv_article "
        "ON mg_inventaire_lignes (inventaire_id, article_id)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_mg_inventaires_perimetre_periode "
        f"ON mg_inventaires (annee, mois, COALESCE(agence_id, {_ZERO_UUID}), COALESCE(famille_id, {_ZERO_UUID})) "
        "WHERE deleted_at IS NULL AND statut <> 'ANNULE'"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_mg_inventaires_annee_mois ON mg_inventaires (annee, mois)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_mg_inventaire_lignes_statut ON mg_inventaire_lignes (inventaire_id, statut_comptage)"
    )

    checks = {c["name"] for c in insp.get_check_constraints("mg_inventaire_lignes")}
    if "ck_mg_inventaire_lignes_physique_pos" not in checks:
        op.create_check_constraint(
            "ck_mg_inventaire_lignes_physique_pos",
            "mg_inventaire_lignes",
            "stock_physique IS NULL OR stock_physique >= 0",
        )
    if "ck_mg_inventaire_lignes_theorique_pos" not in checks:
        op.create_check_constraint(
            "ck_mg_inventaire_lignes_theorique_pos",
            "mg_inventaire_lignes",
            "stock_theorique >= 0",
        )
    if "ck_mg_inventaire_lignes_statut" not in checks:
        op.create_check_constraint(
            "ck_mg_inventaire_lignes_statut",
            "mg_inventaire_lignes",
            "statut_comptage IN ('NON_COMPTE', 'COMPTE', 'EXCLU')",
        )
    inv_checks = {c["name"] for c in insp.get_check_constraints("mg_inventaires")}
    if "ck_mg_inventaires_statut" not in inv_checks:
        op.create_check_constraint(
            "ck_mg_inventaires_statut",
            "mg_inventaires",
            "statut IN ('BROUILLON', 'EN_COURS', 'A_CONTROLER', 'VALIDE', 'AJUSTE', 'ARCHIVE', 'ANNULE')",
        )


def downgrade() -> None:
    op.drop_constraint("ck_mg_inventaires_statut", "mg_inventaires", type_="check")
    op.drop_constraint("ck_mg_inventaire_lignes_statut", "mg_inventaire_lignes", type_="check")
    op.drop_constraint("ck_mg_inventaire_lignes_theorique_pos", "mg_inventaire_lignes", type_="check")
    op.drop_constraint("ck_mg_inventaire_lignes_physique_pos", "mg_inventaire_lignes", type_="check")
    op.execute("DROP INDEX IF EXISTS ix_mg_inventaire_lignes_statut")
    op.execute("DROP INDEX IF EXISTS ix_mg_inventaires_annee_mois")
    op.execute("DROP INDEX IF EXISTS uq_mg_inventaires_perimetre_periode")
    op.execute("DROP INDEX IF EXISTS uq_mg_inventaire_lignes_inv_article")
    for col in ("ajout_manuel", "stock_theorique_source", "compte_at", "compte_par", "statut_comptage"):
        op.drop_column("mg_inventaire_lignes", col)
    for col in (
        "motif_annulation",
        "annule_by",
        "annule_at",
        "validation_forcee",
        "updated_by",
        "snapshot_at",
        "import_meta",
        "source",
        "responsable_nom",
        "responsable_id",
        "famille_id",
        "mois",
        "annee",
    ):
        op.drop_column("mg_inventaires", col)
    retour = {
        "EN_COURS": "EN_COMPTAGE",
        "A_CONTROLER": "EN_CONTROLE",
        "AJUSTE": "AJUSTEMENTS_APPLIQUES",
        "ARCHIVE": "CLOTURE",
    }
    for nouveau, ancien in retour.items():
        op.execute(f"UPDATE mg_inventaires SET statut = '{ancien}' WHERE statut = '{nouveau}'")
