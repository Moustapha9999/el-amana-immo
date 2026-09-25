"""Notes de frais — catégories, historique, paiement, snapshots (additif).

Revision ID: 20260924_mg_notes_v2
Revises: 20260924_mg_stock_periodes
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260924_mg_notes_v2"
down_revision: Union[str, None] = "20260924_mg_stock_periodes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_names(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def _cols(bind, table: str) -> set[str]:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    tables = _table_names(bind)
    notes = _cols(bind, "mg_notes_frais")
    lignes = _cols(bind, "mg_note_frais_lignes")

    if "mg_note_frais_categories" not in tables:
        op.create_table(
            "mg_note_frais_categories",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("code", sa.String(40), nullable=False),
            sa.Column("libelle", sa.String(120), nullable=False),
            sa.Column("actif", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("justificatif_obligatoire", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("plafond", sa.Numeric(18, 2), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("code", name="uq_mg_note_frais_categories_code"),
        )
        op.create_index("ix_mg_note_frais_categories_code", "mg_note_frais_categories", ["code"])
    else:
        cats = _cols(bind, "mg_note_frais_categories")
        if "is_active" not in cats:
            op.add_column(
                "mg_note_frais_categories",
                sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            )

    if "mg_note_frais_parametres" not in tables:
        op.create_table(
            "mg_note_frais_parametres",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("cle", sa.String(60), nullable=False),
            sa.Column("valeur", sa.String(255), nullable=False),
            sa.Column("libelle", sa.String(120), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("cle", name="uq_mg_note_frais_parametres_cle"),
        )

    if "mg_note_frais_historique" not in tables:
        op.create_table(
            "mg_note_frais_historique",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "note_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("mg_notes_frais.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("action", sa.String(60), nullable=False),
            sa.Column("from_statut", sa.String(30), nullable=True),
            sa.Column("to_statut", sa.String(30), nullable=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("user_nom", sa.String(255), nullable=True),
            sa.Column("commentaire", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_mg_note_frais_historique_note_id", "mg_note_frais_historique", ["note_id"])

    for col, spec in [
        ("objet", sa.Column("objet", sa.String(255), nullable=True)),
        ("periode_debut", sa.Column("periode_debut", sa.Date(), nullable=True)),
        ("periode_fin", sa.Column("periode_fin", sa.Date(), nullable=True)),
        ("devise", sa.Column("devise", sa.String(10), nullable=False, server_default="MRU")),
        ("agence_code_snapshot", sa.Column("agence_code_snapshot", sa.String(40), nullable=True)),
        ("agence_adresse_snapshot", sa.Column("agence_adresse_snapshot", sa.Text(), nullable=True)),
        ("montant_paye", sa.Column("montant_paye", sa.Numeric(18, 2), nullable=False, server_default="0")),
        ("date_mise_en_paiement", sa.Column("date_mise_en_paiement", sa.Date(), nullable=True)),
        ("date_paiement", sa.Column("date_paiement", sa.Date(), nullable=True)),
        ("mode_paiement", sa.Column("mode_paiement", sa.String(80), nullable=True)),
        ("ref_paiement", sa.Column("ref_paiement", sa.String(120), nullable=True)),
        ("commentaire_paiement", sa.Column("commentaire_paiement", sa.Text(), nullable=True)),
        ("motif_rejet", sa.Column("motif_rejet", sa.Text(), nullable=True)),
        ("motif_correction", sa.Column("motif_correction", sa.Text(), nullable=True)),
        ("pdf_version", sa.Column("pdf_version", sa.Integer(), nullable=False, server_default="1")),
        ("document_final_ged_id", sa.Column("document_final_ged_id", postgresql.UUID(as_uuid=True), nullable=True)),
        ("controle_at", sa.Column("controle_at", sa.DateTime(timezone=True), nullable=True)),
        ("controle_by", sa.Column("controle_by", postgresql.UUID(as_uuid=True), nullable=True)),
    ]:
        if col not in notes:
            op.add_column("mg_notes_frais", spec)

    if "categorie_id" not in lignes:
        op.add_column(
            "mg_note_frais_lignes",
            sa.Column(
                "categorie_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("mg_note_frais_categories.id"),
                nullable=True,
            ),
        )
    if "categorie_libelle_snapshot" not in lignes:
        op.add_column(
            "mg_note_frais_lignes",
            sa.Column("categorie_libelle_snapshot", sa.String(120), nullable=True),
        )
    if "devise" not in lignes:
        op.add_column(
            "mg_note_frais_lignes",
            sa.Column("devise", sa.String(10), nullable=False, server_default="MRU"),
        )
    if "commentaire" not in lignes:
        op.add_column("mg_note_frais_lignes", sa.Column("commentaire", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    lignes = _cols(bind, "mg_note_frais_lignes")
    notes = _cols(bind, "mg_notes_frais")
    tables = _table_names(bind)

    for col in ("commentaire", "devise", "categorie_libelle_snapshot", "categorie_id"):
        if col in lignes:
            op.drop_column("mg_note_frais_lignes", col)

    for col in (
        "controle_by",
        "controle_at",
        "document_final_ged_id",
        "pdf_version",
        "motif_correction",
        "motif_rejet",
        "commentaire_paiement",
        "ref_paiement",
        "mode_paiement",
        "date_paiement",
        "date_mise_en_paiement",
        "montant_paye",
        "agence_adresse_snapshot",
        "agence_code_snapshot",
        "devise",
        "periode_fin",
        "periode_debut",
        "objet",
    ):
        if col in notes:
            op.drop_column("mg_notes_frais", col)

    if "mg_note_frais_historique" in tables:
        op.drop_table("mg_note_frais_historique")
    if "mg_note_frais_parametres" in tables:
        op.drop_table("mg_note_frais_parametres")
    if "mg_note_frais_categories" in tables:
        op.drop_table("mg_note_frais_categories")
