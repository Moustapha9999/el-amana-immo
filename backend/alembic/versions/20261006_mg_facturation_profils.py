"""Facturation Fournisseurs — profils par fournisseur, arriérés / réglage, détail des paiements.

* ``mg_facturation_profils`` : configuration des champs applicables par profil de facturation
  (un fournisseur du référentiel peut porter plusieurs profils : MATTEL USSD / MATTEL SMS…).
* ``mg_achat_factures`` : ``profil_id``, ``arrieres``, ``reglage``, ``controle_at`` / ``controle_by``.
* ``mg_points_facturation`` : ``profil_id``.
* ``mg_achat_paiements`` : ``compte``, ``banque``, ``numero_cheque``, ``carte_masquee``.
* Seed des 8 profils initiaux ; MATTEL, RIMATEL et CHINGUITEL sont ajoutés au référentiel
  ``fournisseurs`` s'ils n'existent pas. Taux de TVA renseigné uniquement quand il figure sur
  les factures (18 % télécoms) ; NULL = non confirmé, aucun calcul supposé.

Revision ID: 20261006_mg_facturation_profils
Revises: 20261006_mg_facturation_module
"""

import json
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261006_mg_facturation_profils"
down_revision: Union[str, None] = "20261006_mg_facturation_module"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OB, F, M = "obligatoire", "facultatif", "masque"

# (code, libellé, fournisseur, type, taux TVA, champs, libellés)
PROFILS = [
    (
        "SOMELEC", "SOMELEC", "SOMELEC", "ELECTRICITE", None,
        {"numero_fournisseur": OB, "reference_fournisseur": F, "periode": F, "periode_debut": F, "periode_fin": F,
         "montant_ht": F, "montant_tva": M, "autres_taxes": F, "remise": M, "montant_ttc": OB, "arrieres": F,
         "reglage": M, "montant_a_payer": F, "date_echeance": F},
        {"reference_fournisseur": "Référence siège / PDV Amanty", "periode": "Mois de livraison",
         "periode_debut": "Date début", "periode_fin": "Date fin", "montant_ht": "Montant HT",
         "autres_taxes": "Taxes", "montant_ttc": "Total facture", "arrieres": "Arriérés",
         "montant_a_payer": "Total à payer"},
    ),
    (
        "MATTEL_USSD", "MATTEL USSD", "MATTEL", "TELEPHONE", "18",
        {"numero_fournisseur": OB, "reference_fournisseur": F, "periode": F, "periode_debut": M, "periode_fin": M,
         "montant_ht": F, "montant_tva": F, "autres_taxes": M, "remise": M, "montant_ttc": OB, "arrieres": M,
         "reglage": M, "montant_a_payer": M, "date_echeance": F},
        {"reference_fournisseur": "Référence siège / PDV", "montant_ht": "Total montant facture",
         "montant_tva": "TVA 18 %", "montant_ttc": "Total à payer TTC"},
    ),
    (
        "MATTEL_SMS", "MATTEL SMS", "MATTEL", "TELEPHONE", "18",
        {"numero_fournisseur": OB, "reference_fournisseur": M, "periode": F, "periode_debut": M, "periode_fin": M,
         "montant_ht": F, "montant_tva": F, "autres_taxes": M, "remise": M, "montant_ttc": OB, "arrieres": M,
         "reglage": M, "montant_a_payer": M, "date_echeance": F},
        {"montant_ht": "Total montant facture", "montant_tva": "TVA 18 %", "montant_ttc": "Total TTC"},
    ),
    (
        "MAURITEL_ADSL", "MAURITEL ADSL", "MAURITEL", "INTERNET", "18",
        {"numero_fournisseur": OB, "reference_fournisseur": F, "periode": OB, "periode_debut": M, "periode_fin": M,
         "montant_ht": F, "montant_tva": F, "autres_taxes": M, "remise": M, "montant_ttc": OB, "arrieres": M,
         "reglage": M, "montant_a_payer": M, "date_echeance": F},
        {"periode": "Période facturée", "montant_ht": "Montant HT", "montant_tva": "TVA 18 %",
         "montant_ttc": "Montant TTC", "date_echeance": "Date limite de paiement"},
    ),
    (
        "MAURITEL_GFU", "MAURITEL GFU", "MAURITEL", "TELEPHONE", "18",
        {"numero_fournisseur": OB, "reference_fournisseur": F, "periode": OB, "periode_debut": M, "periode_fin": M,
         "montant_ht": F, "montant_tva": F, "autres_taxes": M, "remise": M, "montant_ttc": OB, "arrieres": M,
         "reglage": M, "montant_a_payer": M, "date_echeance": F},
        {"periode": "Période facturée", "montant_ht": "Montant HT", "montant_tva": "TVA 18 %",
         "montant_ttc": "Montant total facturé TTC", "date_echeance": "Date limite de paiement"},
    ),
    (
        "CHINGUITEL_BEA_SMS", "BEA-SMS (CHINGUITEL)", "CHINGUITEL", "TELEPHONE", "18",
        {"numero_fournisseur": OB, "reference_fournisseur": F, "periode": F, "periode_debut": F, "periode_fin": F,
         "montant_ht": F, "montant_tva": F, "autres_taxes": M, "remise": M, "montant_ttc": OB, "arrieres": M,
         "reglage": F, "montant_a_payer": M, "date_echeance": F},
        {"periode": "Mois de facture", "periode_debut": "Date début", "periode_fin": "Date fin",
         "montant_ht": "Total HT", "montant_tva": "TVA 18 %", "reglage": "Réglage", "montant_ttc": "Total TTC"},
    ),
    (
        "RIMATEL", "RIMATEL", "RIMATEL", "INTERNET", None,
        {"numero_fournisseur": F, "reference_fournisseur": F, "periode": F, "periode_debut": F, "periode_fin": F,
         "montant_ht": M, "montant_tva": M, "autres_taxes": M, "remise": M, "montant_ttc": OB, "arrieres": M,
         "reglage": M, "montant_a_payer": M, "date_echeance": F},
        {"periode_debut": "Date début", "periode_fin": "Date fin", "montant_ttc": "Montant total TTC"},
    ),
    (
        "SNDE", "SNDE", "SNDE", "EAU", None,
        {"numero_fournisseur": OB, "reference_fournisseur": F, "periode": F, "periode_debut": F, "periode_fin": F,
         "montant_ht": F, "montant_tva": F, "autres_taxes": M, "remise": M, "montant_ttc": OB, "arrieres": M,
         "reglage": M, "montant_a_payer": F, "date_echeance": F},
        {"montant_ht": "Montant HT", "montant_tva": "TVA", "montant_ttc": "Montant TTC",
         "montant_a_payer": "Total net à payer"},
    ),
]


def _fournisseur_id(bind, nom: str) -> uuid.UUID:
    row = bind.execute(
        sa.text(
            "SELECT id FROM fournisseurs WHERE deleted_at IS NULL AND upper(trim(raison_sociale)) = :n "
            "ORDER BY created_at LIMIT 1"
        ),
        {"n": nom},
    ).first()
    if row:
        return row[0]
    codes = bind.execute(sa.text("SELECT code FROM fournisseurs WHERE code ~ '^FRS-[0-9]+$'")).scalars().all()
    n = max((int(c.split("-")[1]) for c in codes), default=0) + 1
    new_id = uuid.uuid4()
    bind.execute(
        sa.text(
            "INSERT INTO fournisseurs (id, code, raison_sociale, type_fournisseur, is_active, pays, devise_defaut) "
            "VALUES (:id, :code, :nom, 'SERVICE', true, 'Mauritanie', 'MRU')"
        ),
        {"id": new_id, "code": f"FRS-{n:03d}", "nom": nom},
    )
    return new_id


def upgrade() -> None:
    op.create_table(
        "mg_facturation_profils",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("libelle", sa.String(120), nullable=False),
        sa.Column("fournisseur_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fournisseurs.id"), nullable=False),
        sa.Column("type_facture", sa.String(40), nullable=True),
        sa.Column("taux_tva", sa.Numeric(5, 2), nullable=True),
        sa.Column("champs", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("libelles", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("actif", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("ordre", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("code", name="uq_mg_facturation_profils_code"),
    )
    op.create_index("ix_mg_facturation_profils_fournisseur_id", "mg_facturation_profils", ["fournisseur_id"])

    op.add_column("mg_achat_factures", sa.Column("profil_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("mg_achat_factures", sa.Column("arrieres", sa.Numeric(18, 2), nullable=True))
    op.add_column("mg_achat_factures", sa.Column("reglage", sa.Numeric(18, 2), nullable=True))
    op.add_column("mg_achat_factures", sa.Column("controle_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("mg_achat_factures", sa.Column("controle_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_mg_achat_factures_profil_id", "mg_achat_factures", "mg_facturation_profils", ["profil_id"], ["id"]
    )
    op.create_index("ix_mg_achat_factures_profil_id", "mg_achat_factures", ["profil_id"])

    op.add_column("mg_points_facturation", sa.Column("profil_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_mg_points_facturation_profil_id", "mg_points_facturation", "mg_facturation_profils", ["profil_id"], ["id"]
    )
    op.create_index("ix_mg_points_facturation_profil_id", "mg_points_facturation", ["profil_id"])

    op.add_column("mg_achat_paiements", sa.Column("compte", sa.String(80), nullable=True))
    op.add_column("mg_achat_paiements", sa.Column("banque", sa.String(120), nullable=True))
    op.add_column("mg_achat_paiements", sa.Column("numero_cheque", sa.String(40), nullable=True))
    op.add_column("mg_achat_paiements", sa.Column("carte_masquee", sa.String(25), nullable=True))

    bind = op.get_bind()
    fournisseurs: dict[str, uuid.UUID] = {}
    for ordre, (code, libelle, nom, type_facture, taux, champs, libelles) in enumerate(PROFILS, start=1):
        if nom not in fournisseurs:
            fournisseurs[nom] = _fournisseur_id(bind, nom)
        bind.execute(
            sa.text(
                "INSERT INTO mg_facturation_profils "
                "(id, code, libelle, fournisseur_id, type_facture, taux_tva, champs, libelles, actif, ordre) "
                "VALUES (:id, :code, :libelle, :fr, :type, :taux, CAST(:champs AS jsonb), CAST(:libelles AS jsonb), true, :ordre)"
            ),
            {
                "id": uuid.uuid4(), "code": code, "libelle": libelle, "fr": fournisseurs[nom], "type": type_facture,
                "taux": taux, "champs": json.dumps(champs), "libelles": json.dumps(libelles, ensure_ascii=False),
                "ordre": ordre,
            },
        )

    # Les points et factures SOMELEC existants héritent du profil SOMELEC (seul profil de ce fournisseur).
    for table in ("mg_points_facturation", "mg_achat_factures"):
        op.execute(
            f"""
            UPDATE {table} t SET profil_id = p.id
            FROM mg_facturation_profils p
            WHERE p.code = 'SOMELEC' AND t.fournisseur_id = p.fournisseur_id AND t.profil_id IS NULL
            """
            + (" AND t.origine = 'FACTURATION'" if table == "mg_achat_factures" else "")
        )


def downgrade() -> None:
    for col in ("carte_masquee", "numero_cheque", "banque", "compte"):
        op.drop_column("mg_achat_paiements", col)
    op.drop_index("ix_mg_points_facturation_profil_id", table_name="mg_points_facturation")
    op.drop_constraint("fk_mg_points_facturation_profil_id", "mg_points_facturation", type_="foreignkey")
    op.drop_column("mg_points_facturation", "profil_id")
    op.drop_index("ix_mg_achat_factures_profil_id", table_name="mg_achat_factures")
    op.drop_constraint("fk_mg_achat_factures_profil_id", "mg_achat_factures", type_="foreignkey")
    for col in ("controle_by", "controle_at", "reglage", "arrieres", "profil_id"):
        op.drop_column("mg_achat_factures", col)
    op.drop_index("ix_mg_facturation_profils_fournisseur_id", table_name="mg_facturation_profils")
    op.drop_table("mg_facturation_profils")
