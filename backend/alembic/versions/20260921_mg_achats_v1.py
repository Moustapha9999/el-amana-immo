"""Achats & Approvisionnements v1 — cycle d'achat complet (additif).

Revision ID: 20260921_mg_achats_v1
Revises: 20260921_mg_stock_v3
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260921_mg_achats_v1"
down_revision: Union[str, None] = "20260921_mg_stock_v3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Extend mg_bons_commande ---
    op.add_column(
        "mg_bons_commande",
        sa.Column("demande_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "mg_bons_commande",
        sa.Column("consultation_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "mg_bons_commande",
        sa.Column("comparaison_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "mg_bons_commande",
        sa.Column(
            "contrat_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mg_contrats.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "mg_bons_commande",
        sa.Column(
            "agence_facturation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agences.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "mg_bons_commande",
        sa.Column(
            "agence_livraison_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agences.id"),
            nullable=True,
        ),
    )
    op.add_column("mg_bons_commande", sa.Column("agence_facturation_snapshot", sa.Text(), nullable=True))
    op.add_column("mg_bons_commande", sa.Column("agence_livraison_snapshot", sa.Text(), nullable=True))
    op.add_column(
        "mg_bons_commande",
        sa.Column("type_achat", sa.String(40), nullable=False, server_default="FOURNITURE"),
    )
    op.add_column(
        "mg_bons_commande",
        sa.Column("devise", sa.String(10), nullable=False, server_default="MRU"),
    )
    op.add_column(
        "mg_bons_commande",
        sa.Column("total_tva", sa.Numeric(18, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "mg_bons_commande",
        sa.Column("total_ttc", sa.Numeric(18, 2), nullable=False, server_default="0"),
    )
    op.add_column("mg_bons_commande", sa.Column("date_livraison_prevue", sa.Date(), nullable=True))
    op.add_column(
        "mg_bons_commande",
        sa.Column("pdf_version", sa.Integer(), nullable=False, server_default="1"),
    )

    # --- Extend mg_bc_lignes ---
    op.add_column(
        "mg_bc_lignes",
        sa.Column("remise_pct", sa.Numeric(5, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "mg_bc_lignes",
        sa.Column("taux_tva", sa.Numeric(5, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "mg_bc_lignes",
        sa.Column("total_ttc", sa.Numeric(18, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "mg_bc_lignes",
        sa.Column("stockable", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    # --- Paramètres ---
    op.create_table(
        "mg_achat_parametres",
        sa.Column("cle", sa.String(80), primary_key=True),
        sa.Column("valeur", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # --- Demandes ---
    op.create_table(
        "mg_achat_demandes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("reference", sa.String(40), nullable=False),
        sa.Column("date_demande", sa.Date(), nullable=False),
        sa.Column(
            "agence_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agences.id"),
            nullable=False,
        ),
        sa.Column(
            "departement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("departements.id"),
            nullable=True,
        ),
        sa.Column(
            "demandeur_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("demandeur_nom", sa.String(255), nullable=True),
        sa.Column("fonction", sa.String(120), nullable=True),
        sa.Column("type_achat", sa.String(40), nullable=False, server_default="FOURNITURE"),
        sa.Column("priorite", sa.String(20), nullable=False, server_default="NORMAL"),
        sa.Column("projet", sa.String(255), nullable=True),
        sa.Column("motif", sa.Text(), nullable=True),
        sa.Column("date_souhaitee", sa.Date(), nullable=True),
        sa.Column("budget_estime", sa.Numeric(18, 2), nullable=True),
        sa.Column("statut", sa.String(30), nullable=False, server_default="BROUILLON"),
        sa.Column("observation", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("reference", name="uq_mg_achat_demandes_reference"),
    )
    op.create_index("ix_mg_achat_demandes_reference", "mg_achat_demandes", ["reference"])
    op.create_index("ix_mg_achat_demandes_agence_id", "mg_achat_demandes", ["agence_id"])
    op.create_index("ix_mg_achat_demandes_statut", "mg_achat_demandes", ["statut"])

    op.create_table(
        "mg_achat_demande_lignes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "demande_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mg_achat_demandes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("designation", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("quantite", sa.Numeric(18, 3), nullable=False, server_default="1"),
        sa.Column("uom", sa.String(20), nullable=False, server_default="U"),
        sa.Column("prix_estime", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("montant_estime", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column(
            "article_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mg_articles.id"),
            nullable=True,
        ),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_mg_achat_demande_lignes_demande_id", "mg_achat_demande_lignes", ["demande_id"])

    # --- Consultations ---
    op.create_table(
        "mg_achat_consultations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("reference", sa.String(40), nullable=False),
        sa.Column("date_consultation", sa.Date(), nullable=False),
        sa.Column(
            "demande_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mg_achat_demandes.id"),
            nullable=True,
        ),
        sa.Column(
            "agence_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agences.id"),
            nullable=False,
        ),
        sa.Column("objet", sa.String(255), nullable=False),
        sa.Column("date_limite", sa.Date(), nullable=True),
        sa.Column(
            "responsable_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("statut", sa.String(30), nullable=False, server_default="BROUILLON"),
        sa.Column("observation", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("reference", name="uq_mg_achat_consultations_reference"),
    )
    op.create_index("ix_mg_achat_consultations_reference", "mg_achat_consultations", ["reference"])
    op.create_index("ix_mg_achat_consultations_statut", "mg_achat_consultations", ["statut"])

    op.create_table(
        "mg_achat_consultation_fournisseurs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "consultation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mg_achat_consultations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "fournisseur_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("fournisseurs.id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "consultation_id",
            "fournisseur_id",
            name="uq_mg_achat_cons_fourn",
        ),
    )
    op.create_index(
        "ix_mg_achat_cons_fourn_consultation_id",
        "mg_achat_consultation_fournisseurs",
        ["consultation_id"],
    )

    # --- Devis ---
    op.create_table(
        "mg_achat_devis",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("reference", sa.String(40), nullable=False),
        sa.Column(
            "fournisseur_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("fournisseurs.id"),
            nullable=False,
        ),
        sa.Column(
            "consultation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mg_achat_consultations.id"),
            nullable=True,
        ),
        sa.Column("date_devis", sa.Date(), nullable=False),
        sa.Column("date_validite", sa.Date(), nullable=True),
        sa.Column("montant_ht", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("montant_tva", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("montant_ttc", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("devise", sa.String(10), nullable=False, server_default="MRU"),
        sa.Column("conditions", sa.Text(), nullable=True),
        sa.Column("delai_livraison", sa.String(120), nullable=True),
        sa.Column("conditions_paiement", sa.String(120), nullable=True),
        sa.Column("statut", sa.String(30), nullable=False, server_default="RECU"),
        sa.Column("observation", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("reference", name="uq_mg_achat_devis_reference"),
    )
    op.create_index("ix_mg_achat_devis_reference", "mg_achat_devis", ["reference"])
    op.create_index("ix_mg_achat_devis_fournisseur_id", "mg_achat_devis", ["fournisseur_id"])

    op.create_table(
        "mg_achat_devis_lignes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "devis_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mg_achat_devis.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("designation", sa.String(255), nullable=False),
        sa.Column("quantite", sa.Numeric(18, 3), nullable=False, server_default="1"),
        sa.Column("prix_unitaire", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("remise_pct", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("taux_tva", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("total_ht", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_mg_achat_devis_lignes_devis_id", "mg_achat_devis_lignes", ["devis_id"])

    # --- Comparaisons ---
    op.create_table(
        "mg_achat_comparaisons",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("reference", sa.String(40), nullable=False),
        sa.Column(
            "consultation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mg_achat_consultations.id"),
            nullable=False,
        ),
        sa.Column(
            "demande_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mg_achat_demandes.id"),
            nullable=True,
        ),
        sa.Column("statut", sa.String(30), nullable=False, server_default="BROUILLON"),
        sa.Column(
            "fournisseur_retenu_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("fournisseurs.id"),
            nullable=True,
        ),
        sa.Column("motif_choix", sa.Text(), nullable=True),
        sa.Column("snapshot_json", sa.Text(), nullable=True),
        sa.Column("observation", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("reference", name="uq_mg_achat_comparaisons_reference"),
    )
    op.create_index("ix_mg_achat_comparaisons_reference", "mg_achat_comparaisons", ["reference"])

    # --- BL ---
    op.create_table(
        "mg_achat_bl",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("reference", sa.String(40), nullable=False),
        sa.Column(
            "bon_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mg_bons_commande.id"),
            nullable=False,
        ),
        sa.Column(
            "fournisseur_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("fournisseurs.id"),
            nullable=False,
        ),
        sa.Column("date_bl", sa.Date(), nullable=False),
        sa.Column("date_livraison", sa.Date(), nullable=True),
        sa.Column(
            "agence_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agences.id"),
            nullable=True,
        ),
        sa.Column("transporteur", sa.String(255), nullable=True),
        sa.Column("observation", sa.Text(), nullable=True),
        sa.Column("statut", sa.String(30), nullable=False, server_default="RECU"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("reference", name="uq_mg_achat_bl_reference"),
    )
    op.create_index("ix_mg_achat_bl_reference", "mg_achat_bl", ["reference"])
    op.create_index("ix_mg_achat_bl_bon_id", "mg_achat_bl", ["bon_id"])

    # --- Réceptions ---
    op.create_table(
        "mg_achat_receptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("reference", sa.String(40), nullable=False),
        sa.Column(
            "bon_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mg_bons_commande.id"),
            nullable=False,
        ),
        sa.Column(
            "bl_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mg_achat_bl.id"),
            nullable=True,
        ),
        sa.Column("date_reception", sa.Date(), nullable=False),
        sa.Column(
            "agence_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agences.id"),
            nullable=True,
        ),
        sa.Column("statut", sa.String(30), nullable=False, server_default="PARTIEL"),
        sa.Column("observation", sa.Text(), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("reference", name="uq_mg_achat_receptions_reference"),
    )
    op.create_index("ix_mg_achat_receptions_reference", "mg_achat_receptions", ["reference"])
    op.create_index("ix_mg_achat_receptions_bon_id", "mg_achat_receptions", ["bon_id"])

    op.create_table(
        "mg_achat_reception_lignes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "reception_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mg_achat_receptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "bc_ligne_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mg_bc_lignes.id"),
            nullable=False,
        ),
        sa.Column("quantite_recue", sa.Numeric(18, 3), nullable=False),
        sa.Column(
            "article_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mg_articles.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_mg_achat_reception_lignes_reception_id",
        "mg_achat_reception_lignes",
        ["reception_id"],
    )

    # --- Factures ---
    op.create_table(
        "mg_achat_factures",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("reference", sa.String(40), nullable=False),
        sa.Column("numero_fournisseur", sa.String(80), nullable=True),
        sa.Column(
            "fournisseur_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("fournisseurs.id"),
            nullable=False,
        ),
        sa.Column(
            "bon_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mg_bons_commande.id"),
            nullable=False,
        ),
        sa.Column(
            "bl_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mg_achat_bl.id"),
            nullable=True,
        ),
        sa.Column(
            "reception_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mg_achat_receptions.id"),
            nullable=True,
        ),
        sa.Column("date_facture", sa.Date(), nullable=False),
        sa.Column("date_echeance", sa.Date(), nullable=True),
        sa.Column("montant_ht", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("montant_tva", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("montant_ttc", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("devise", sa.String(10), nullable=False, server_default="MRU"),
        sa.Column("statut", sa.String(30), nullable=False, server_default="RECUE"),
        sa.Column("ecart_quantite", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("ecart_montant", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("observation", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("reference", name="uq_mg_achat_factures_reference"),
    )
    op.create_index("ix_mg_achat_factures_reference", "mg_achat_factures", ["reference"])
    op.create_index("ix_mg_achat_factures_bon_id", "mg_achat_factures", ["bon_id"])

    op.create_table(
        "mg_achat_facture_lignes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "facture_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mg_achat_factures.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("designation", sa.String(255), nullable=False),
        sa.Column("quantite", sa.Numeric(18, 3), nullable=False, server_default="1"),
        sa.Column("prix_unitaire", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("total_ht", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_mg_achat_facture_lignes_facture_id", "mg_achat_facture_lignes", ["facture_id"])

    # --- Paiements ---
    op.create_table(
        "mg_achat_paiements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("reference", sa.String(40), nullable=False),
        sa.Column(
            "facture_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mg_achat_factures.id"),
            nullable=False,
        ),
        sa.Column(
            "fournisseur_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("fournisseurs.id"),
            nullable=False,
        ),
        sa.Column("montant", sa.Numeric(18, 2), nullable=False),
        sa.Column("date_echeance", sa.Date(), nullable=True),
        sa.Column("date_paiement", sa.Date(), nullable=True),
        sa.Column("mode_paiement", sa.String(80), nullable=True),
        sa.Column("reference_paiement", sa.String(120), nullable=True),
        sa.Column("statut", sa.String(30), nullable=False, server_default="A_PAYER"),
        sa.Column("observation", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("reference", name="uq_mg_achat_paiements_reference"),
    )
    op.create_index("ix_mg_achat_paiements_reference", "mg_achat_paiements", ["reference"])
    op.create_index("ix_mg_achat_paiements_facture_id", "mg_achat_paiements", ["facture_id"])

    # --- Timeline événements ---
    op.create_table(
        "mg_achat_evenements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_type", sa.String(40), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_mg_achat_evenements_entity", "mg_achat_evenements", ["entity_type", "entity_id"])

    # FKs BC → nouvelles tables (après création)
    op.create_foreign_key(
        "fk_mg_bons_demande_id",
        "mg_bons_commande",
        "mg_achat_demandes",
        ["demande_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_mg_bons_consultation_id",
        "mg_bons_commande",
        "mg_achat_consultations",
        ["consultation_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_mg_bons_comparaison_id",
        "mg_bons_commande",
        "mg_achat_comparaisons",
        ["comparaison_id"],
        ["id"],
    )
    op.create_index("ix_mg_bons_commande_demande_id", "mg_bons_commande", ["demande_id"])
    op.create_index("ix_mg_bons_commande_contrat_id", "mg_bons_commande", ["contrat_id"])

    # Seed paramètres
    op.execute(
        """
        INSERT INTO mg_achat_parametres (cle, valeur, description, created_at, updated_at)
        VALUES
          ('prefix_demande', 'DA', 'Préfixe références demandes', now(), now()),
          ('prefix_consultation', 'CONS', 'Préfixe consultations', now(), now()),
          ('prefix_devis', 'DEV', 'Préfixe devis', now(), now()),
          ('prefix_bc', 'BEA', 'Préfixe bons de commande', now(), now()),
          ('prefix_bl', 'BL', 'Préfixe bons de livraison', now(), now()),
          ('prefix_facture', 'FAC', 'Préfixe factures', now(), now()),
          ('prefix_paiement', 'PAY', 'Préfixe paiements', now(), now()),
          ('tva_defaut', '0', 'Taux TVA par défaut (%)', now(), now()),
          ('alerte_jours', '15', 'Horizon alertes (jours)', now(), now()),
          ('devise_defaut', 'MRU', 'Devise par défaut', now(), now())
        ON CONFLICT (cle) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_constraint("fk_mg_bons_comparaison_id", "mg_bons_commande", type_="foreignkey")
    op.drop_constraint("fk_mg_bons_consultation_id", "mg_bons_commande", type_="foreignkey")
    op.drop_constraint("fk_mg_bons_demande_id", "mg_bons_commande", type_="foreignkey")
    op.drop_index("ix_mg_bons_commande_contrat_id", table_name="mg_bons_commande")
    op.drop_index("ix_mg_bons_commande_demande_id", table_name="mg_bons_commande")

    op.drop_table("mg_achat_evenements")
    op.drop_table("mg_achat_paiements")
    op.drop_table("mg_achat_facture_lignes")
    op.drop_table("mg_achat_factures")
    op.drop_table("mg_achat_reception_lignes")
    op.drop_table("mg_achat_receptions")
    op.drop_table("mg_achat_bl")
    op.drop_table("mg_achat_comparaisons")
    op.drop_table("mg_achat_devis_lignes")
    op.drop_table("mg_achat_devis")
    op.drop_table("mg_achat_consultation_fournisseurs")
    op.drop_table("mg_achat_consultations")
    op.drop_table("mg_achat_demande_lignes")
    op.drop_table("mg_achat_demandes")
    op.drop_table("mg_achat_parametres")

    for col in (
        "stockable",
        "total_ttc",
        "taux_tva",
        "remise_pct",
    ):
        op.drop_column("mg_bc_lignes", col)

    for col in (
        "pdf_version",
        "date_livraison_prevue",
        "total_ttc",
        "total_tva",
        "devise",
        "type_achat",
        "agence_livraison_snapshot",
        "agence_facturation_snapshot",
        "agence_livraison_id",
        "agence_facturation_id",
        "contrat_id",
        "comparaison_id",
        "consultation_id",
        "demande_id",
    ):
        op.drop_column("mg_bons_commande", col)
