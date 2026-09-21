"""Moyens Généraux Phase 2 — Achats, Notes, Contrats (additif).

Revision ID: 20260921_mg_phase2
Revises: 20260921_mg_stock
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260921_mg_phase2"
down_revision: Union[str, None] = "20260921_mg_stock"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mg_bons_commande",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("reference", sa.String(40), nullable=False),
        sa.Column("date_bc", sa.Date(), nullable=False),
        sa.Column("fournisseur_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fournisseurs.id"), nullable=True),
        sa.Column("fournisseur_raison_sociale", sa.String(255), nullable=True),
        sa.Column("fournisseur_nif", sa.String(60), nullable=True),
        sa.Column("fournisseur_telephone", sa.String(40), nullable=True),
        sa.Column("fournisseur_adresse", sa.Text(), nullable=True),
        sa.Column("departement", sa.String(120), nullable=True),
        sa.Column("projet", sa.String(255), nullable=True),
        sa.Column("acheteur_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("acheteur_nom", sa.String(255), nullable=True),
        sa.Column("acheteur_tel", sa.String(40), nullable=True),
        sa.Column("adresse_facturation", sa.Text(), nullable=True),
        sa.Column("adresse_livraison", sa.Text(), nullable=True),
        sa.Column("conditions", sa.Text(), nullable=True),
        sa.Column("incoterm", sa.String(60), nullable=True),
        sa.Column("conditions_paiement", sa.String(120), nullable=True),
        sa.Column("moyen_paiement", sa.String(120), nullable=True),
        sa.Column("demandeur_nom", sa.String(255), nullable=True),
        sa.Column("demandeur_date", sa.Date(), nullable=True),
        sa.Column("statut", sa.String(30), nullable=False, server_default="BROUILLON"),
        sa.Column("visa_mg_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("visa_mg_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("visa_dr_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("visa_dr_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("total_ht", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("observation", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("reference", name="uq_mg_bons_commande_reference"),
    )
    op.create_index("ix_mg_bons_commande_reference", "mg_bons_commande", ["reference"])
    op.create_index("ix_mg_bons_commande_statut", "mg_bons_commande", ["statut"])

    op.create_table(
        "mg_bc_lignes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("bc_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mg_bons_commande.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code_produit", sa.String(60), nullable=True),
        sa.Column("departement", sa.String(120), nullable=True),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("quantite", sa.Numeric(18, 3), nullable=False, server_default="1"),
        sa.Column("uom", sa.String(20), nullable=False, server_default="U"),
        sa.Column("prix_unitaire", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("prix_total", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_mg_bc_lignes_bc_id", "mg_bc_lignes", ["bc_id"])

    op.create_table(
        "mg_notes_frais",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("reference", sa.String(40), nullable=False),
        sa.Column("date_demande", sa.Date(), nullable=False),
        sa.Column("agence_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agences.id"), nullable=True),
        sa.Column("agence_libelle_snapshot", sa.String(255), nullable=True),
        sa.Column("demandeur_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("demandeur_nom", sa.String(255), nullable=True),
        sa.Column("departement", sa.String(120), nullable=True),
        sa.Column("fonction", sa.String(120), nullable=True),
        sa.Column("statut", sa.String(30), nullable=False, server_default="BROUILLON"),
        sa.Column("visa_mg_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("visa_mg_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("visa_dr_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("visa_dr_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("total_mru", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("observation", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("reference", name="uq_mg_notes_frais_reference"),
    )
    op.create_index("ix_mg_notes_frais_reference", "mg_notes_frais", ["reference"])
    op.create_index("ix_mg_notes_frais_statut", "mg_notes_frais", ["statut"])

    op.create_table(
        "mg_note_frais_lignes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("note_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mg_notes_frais.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date_depense", sa.Date(), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("motif", sa.String(255), nullable=True),
        sa.Column("montant", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("mode_reglement", sa.String(80), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_mg_note_frais_lignes_note_id", "mg_note_frais_lignes", ["note_id"])

    op.create_table(
        "mg_contrats",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("reference", sa.String(40), nullable=False),
        sa.Column("titre", sa.String(255), nullable=False),
        sa.Column("fournisseur_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fournisseurs.id"), nullable=True),
        sa.Column("fournisseur_snapshot", sa.String(255), nullable=True),
        sa.Column("date_debut", sa.Date(), nullable=False),
        sa.Column("date_fin", sa.Date(), nullable=True),
        sa.Column("montant", sa.Numeric(18, 2), nullable=True),
        sa.Column("periodicite", sa.String(20), nullable=False, server_default="ANNUEL"),
        sa.Column("prochain_echeance", sa.Date(), nullable=True),
        sa.Column("alerte_jours", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("statut", sa.String(30), nullable=False, server_default="BROUILLON"),
        sa.Column("observation", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("reference", name="uq_mg_contrats_reference"),
    )
    op.create_index("ix_mg_contrats_reference", "mg_contrats", ["reference"])
    op.create_index("ix_mg_contrats_statut", "mg_contrats", ["statut"])


def downgrade() -> None:
    op.drop_table("mg_contrats")
    op.drop_table("mg_note_frais_lignes")
    op.drop_table("mg_notes_frais")
    op.drop_table("mg_bc_lignes")
    op.drop_table("mg_bons_commande")
