"""Contrats & échéances — Gestion des factures (facturation récurrente).

Réutilise le registre unique des factures fournisseurs ``mg_achat_factures`` (colonne
``origine`` : ACHAT = circuit BC/réception, FACTURATION = factures de points de facturation),
ses lignes, ses paiements (``mg_achat_paiements``) et son journal (``mg_achat_evenements``).
Seule entité nouvelle : ``mg_points_facturation`` (compteur / abonnement fournisseur d'un site).

Revision ID: 20261005_mg_facturation
Revises: 20261004_eer_05_suppression
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "20261005_mg_facturation"
down_revision: Union[str, None] = "20261004_eer_05_suppression"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add(table: str, existing: set[str], column: sa.Column) -> None:
    if column.name not in existing:
        op.add_column(table, column)


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())

    if not insp.has_table("mg_points_facturation"):
        op.create_table(
            "mg_points_facturation",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("code", sa.String(20), nullable=False),
            sa.Column("type_point", sa.String(20), nullable=False, server_default="AGENCE"),
            sa.Column("nom", sa.String(255), nullable=False),
            sa.Column("agence_id", UUID(as_uuid=True), sa.ForeignKey("agences.id"), nullable=True),
            sa.Column("fournisseur_id", UUID(as_uuid=True), sa.ForeignKey("fournisseurs.id"), nullable=False),
            sa.Column("contrat_id", UUID(as_uuid=True), sa.ForeignKey("mg_contrats.id"), nullable=True),
            sa.Column("reference_fournisseur", sa.String(80), nullable=False),
            sa.Column("reference_normalisee", sa.String(80), nullable=False),
            sa.Column("compteur", sa.String(40), nullable=True),
            sa.Column("type_facture", sa.String(40), nullable=True),
            sa.Column("periodicite", sa.String(20), nullable=False, server_default="MENSUEL"),
            sa.Column("adresse", sa.Text(), nullable=True),
            sa.Column("date_debut", sa.Date(), nullable=True),
            sa.Column("date_fin", sa.Date(), nullable=True),
            sa.Column("statut", sa.String(20), nullable=False, server_default="ACTIF"),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("updated_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("code", name="uq_mg_points_facturation_code"),
            sa.CheckConstraint(
                "type_point IN ('AGENCE','SIEGE','PDV','AUTRE')", name="ck_mg_points_facturation_type"
            ),
            sa.CheckConstraint("statut IN ('ACTIF','INACTIF')", name="ck_mg_points_facturation_statut"),
        )
        op.create_index("ix_mg_points_facturation_agence_id", "mg_points_facturation", ["agence_id"])
        op.create_index("ix_mg_points_facturation_fournisseur_id", "mg_points_facturation", ["fournisseur_id"])
        op.create_index("ix_mg_points_facturation_type_point", "mg_points_facturation", ["type_point"])
        op.create_index(
            "uq_mg_points_facturation_ref",
            "mg_points_facturation",
            ["fournisseur_id", "reference_normalisee"],
            unique=True,
            postgresql_where=sa.text("deleted_at IS NULL"),
        )

    fac = {c["name"] for c in insp.get_columns("mg_achat_factures")}
    _add("mg_achat_factures", fac, sa.Column("origine", sa.String(20), nullable=False, server_default="ACHAT"))
    _add(
        "mg_achat_factures",
        fac,
        sa.Column("point_facturation_id", UUID(as_uuid=True), sa.ForeignKey("mg_points_facturation.id"), nullable=True),
    )
    _add("mg_achat_factures", fac, sa.Column("contrat_id", UUID(as_uuid=True), sa.ForeignKey("mg_contrats.id"), nullable=True))
    _add("mg_achat_factures", fac, sa.Column("agence_id", UUID(as_uuid=True), sa.ForeignKey("agences.id"), nullable=True))
    _add("mg_achat_factures", fac, sa.Column("type_facture", sa.String(40), nullable=True))
    _add("mg_achat_factures", fac, sa.Column("reference_fournisseur", sa.String(80), nullable=True))
    _add("mg_achat_factures", fac, sa.Column("date_reception", sa.Date(), nullable=True))
    _add("mg_achat_factures", fac, sa.Column("periode_debut", sa.Date(), nullable=True))
    _add("mg_achat_factures", fac, sa.Column("periode_fin", sa.Date(), nullable=True))
    _add("mg_achat_factures", fac, sa.Column("mois", sa.Integer(), nullable=True))
    _add("mg_achat_factures", fac, sa.Column("annee", sa.Integer(), nullable=True))
    _add("mg_achat_factures", fac, sa.Column("autres_taxes", sa.Numeric(18, 2), nullable=False, server_default="0"))
    _add("mg_achat_factures", fac, sa.Column("remise", sa.Numeric(18, 2), nullable=False, server_default="0"))
    _add("mg_achat_factures", fac, sa.Column("montant_a_payer", sa.Numeric(18, 2), nullable=True))
    _add("mg_achat_factures", fac, sa.Column("statut_paiement", sa.String(30), nullable=True))
    _add("mg_achat_factures", fac, sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True))
    _add("mg_achat_factures", fac, sa.Column("updated_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True))
    _add("mg_achat_factures", fac, sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.alter_column("mg_achat_factures", "bon_id", existing_type=UUID(as_uuid=True), nullable=True)
    # Une facture de facturation peut ne porter que le montant à payer : HT / TVA inconnus = NULL.
    op.alter_column("mg_achat_factures", "montant_ht", existing_type=sa.Numeric(18, 2), nullable=True)
    op.alter_column("mg_achat_factures", "montant_tva", existing_type=sa.Numeric(18, 2), nullable=True)

    idx = {i["name"] for i in insp.get_indexes("mg_achat_factures")}
    for name, cols in (
        ("ix_mg_achat_factures_origine", ["origine"]),
        ("ix_mg_achat_factures_point_facturation_id", ["point_facturation_id"]),
        ("ix_mg_achat_factures_agence_id", ["agence_id"]),
        ("ix_mg_achat_factures_contrat_id", ["contrat_id"]),
        ("ix_mg_achat_factures_periode", ["annee", "mois"]),
        ("ix_mg_achat_factures_statut_paiement", ["statut_paiement"]),
        ("ix_mg_achat_factures_reference_fournisseur", ["reference_fournisseur"]),
    ):
        if name not in idx:
            op.create_index(name, "mg_achat_factures", cols)
    cks = {c["name"] for c in insp.get_check_constraints("mg_achat_factures")}
    if "ck_mg_achat_factures_origine_bon" not in cks:
        op.create_check_constraint(
            "ck_mg_achat_factures_origine_bon",
            "mg_achat_factures",
            "origine IN ('ACHAT','FACTURATION') AND (origine <> 'ACHAT' OR bon_id IS NOT NULL)",
        )

    lig = {c["name"] for c in insp.get_columns("mg_achat_facture_lignes")}
    _add("mg_achat_facture_lignes", lig, sa.Column("unite", sa.String(20), nullable=True))
    _add("mg_achat_facture_lignes", lig, sa.Column("type_ligne", sa.String(40), nullable=True))

    pay = {c["name"] for c in insp.get_columns("mg_achat_paiements")}
    _add("mg_achat_paiements", pay, sa.Column("origine", sa.String(20), nullable=False, server_default="ACHAT"))
    _add(
        "mg_achat_paiements",
        pay,
        sa.Column("justificatif_document_id", UUID(as_uuid=True), sa.ForeignKey("ged_documents.id"), nullable=True),
    )
    _add("mg_achat_paiements", pay, sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True))
    if "ix_mg_achat_paiements_origine" not in {i["name"] for i in insp.get_indexes("mg_achat_paiements")}:
        op.create_index("ix_mg_achat_paiements_origine", "mg_achat_paiements", ["origine"])


def downgrade() -> None:
    op.execute("DELETE FROM mg_achat_paiements WHERE origine = 'FACTURATION'")
    op.execute("DELETE FROM mg_achat_facture_lignes WHERE facture_id IN (SELECT id FROM mg_achat_factures WHERE origine = 'FACTURATION')")
    op.execute("DELETE FROM mg_achat_factures WHERE origine = 'FACTURATION'")
    op.execute("DROP INDEX IF EXISTS ix_mg_achat_paiements_origine")
    for col in ("created_by", "justificatif_document_id", "origine"):
        op.execute(f"ALTER TABLE mg_achat_paiements DROP COLUMN IF EXISTS {col}")
    op.execute("ALTER TABLE mg_achat_facture_lignes DROP COLUMN IF EXISTS type_ligne")
    op.execute("ALTER TABLE mg_achat_facture_lignes DROP COLUMN IF EXISTS unite")
    op.execute("ALTER TABLE mg_achat_factures DROP CONSTRAINT IF EXISTS ck_mg_achat_factures_origine_bon")
    op.alter_column("mg_achat_factures", "bon_id", existing_type=UUID(as_uuid=True), nullable=False)
    op.execute("UPDATE mg_achat_factures SET montant_ht = 0 WHERE montant_ht IS NULL")
    op.execute("UPDATE mg_achat_factures SET montant_tva = 0 WHERE montant_tva IS NULL")
    op.alter_column("mg_achat_factures", "montant_ht", existing_type=sa.Numeric(18, 2), nullable=False)
    op.alter_column("mg_achat_factures", "montant_tva", existing_type=sa.Numeric(18, 2), nullable=False)
    for col in (
        "archived_at", "updated_by", "created_by", "statut_paiement", "montant_a_payer", "remise",
        "autres_taxes", "annee", "mois", "periode_fin", "periode_debut", "date_reception",
        "reference_fournisseur", "type_facture", "agence_id", "contrat_id", "point_facturation_id", "origine",
    ):
        op.execute(f"ALTER TABLE mg_achat_factures DROP COLUMN IF EXISTS {col}")
    op.execute("DROP TABLE IF EXISTS mg_points_facturation")
