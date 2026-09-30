"""Achats — invariants du circuit BC → réception → facture → paiement.

- BC : suppression des visas MG / DR (reprise VISA_MG / VISA_DR → SOUMIS),
  horodatage soumis / validé / envoyé / clôturé / annulé.
- Lignes de facture : lien ligne BC, TVA et TTC arrondis par ligne.
- Facture : montant payé recalculé, statut de paiement automatique.
- Réception / facture / paiement : traçabilité d'annulation.

Revision ID: 20260930_achats_invariants
Revises: 20260930_mg_bc_detail_paiement
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260930_achats_invariants"
down_revision: Union[str, None] = "20260930_mg_bc_detail_paiement"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TS = sa.DateTime(timezone=True)
_UUID = postgresql.UUID(as_uuid=True)

_COLONNES = {
    "mg_bons_commande": [
        ("soumis_at", _TS),
        ("soumis_by", _UUID),
        ("valide_at", _TS),
        ("valide_by", _UUID),
        ("envoye_at", _TS),
        ("envoye_by", _UUID),
        ("cloture_at", _TS),
        ("cloture_by", _UUID),
        ("annule_at", _TS),
        ("annule_by", _UUID),
        ("motif_annulation", sa.Text()),
    ],
    "mg_achat_receptions": [
        ("annule_at", _TS),
        ("annule_by", _UUID),
        ("motif_annulation", sa.Text()),
    ],
    "mg_achat_factures": [
        ("montant_paye", sa.Numeric(18, 2)),
        ("valide_at", _TS),
        ("valide_by", _UUID),
        ("motif_validation", sa.Text()),
        ("annule_at", _TS),
        ("annule_by", _UUID),
    ],
    "mg_achat_facture_lignes": [
        ("bc_ligne_id", _UUID),
        ("taux_tva", sa.Numeric(5, 2)),
        ("montant_tva", sa.Numeric(18, 2)),
        ("total_ttc", sa.Numeric(18, 2)),
    ],
    "mg_achat_paiements": [
        ("annule_at", _TS),
        ("annule_by", _UUID),
    ],
}

_NORM = "lower(regexp_replace(trim({}), '\\s+', ' ', 'g'))"


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    for table, cols in _COLONNES.items():
        existing = {c["name"] for c in insp.get_columns(table)}
        for name, type_ in cols:
            if name not in existing:
                op.add_column(table, sa.Column(name, type_, nullable=True))

    fk_names = {fk["name"] for fk in insp.get_foreign_keys("mg_achat_facture_lignes")}
    if "fk_mg_achat_facture_lignes_bc_ligne" not in fk_names:
        op.create_foreign_key(
            "fk_mg_achat_facture_lignes_bc_ligne",
            "mg_achat_facture_lignes",
            "mg_bc_lignes",
            ["bc_ligne_id"],
            ["id"],
        )
    idx_names = {i["name"] for i in insp.get_indexes("mg_achat_facture_lignes")}
    if "ix_mg_achat_facture_lignes_bc_ligne_id" not in idx_names:
        op.create_index(
            "ix_mg_achat_facture_lignes_bc_ligne_id", "mg_achat_facture_lignes", ["bc_ligne_id"]
        )

    # BC : les visas deviennent une signature papier.
    op.execute(
        """
        UPDATE mg_bons_commande
           SET valide_at = visa_dr_at, valide_by = visa_dr_by
         WHERE valide_at IS NULL AND visa_dr_at IS NOT NULL
           AND statut NOT IN ('BROUILLON', 'SOUMIS', 'VISA_MG', 'VISA_DR')
        """
    )
    op.execute("UPDATE mg_bons_commande SET statut = 'SOUMIS' WHERE statut IN ('VISA_MG', 'VISA_DR')")
    op.execute("UPDATE mg_bons_commande SET statut = 'ANNULEE' WHERE statut = 'ANNULE'")

    # Lignes de facture : lien ligne BC par désignation unique, puis TVA / TTC par ligne.
    op.execute(
        f"""
        UPDATE mg_achat_facture_lignes fl
           SET bc_ligne_id = m.bc_ligne_id
          FROM (
                SELECT fl2.id AS fl_id,
                       (array_agg(bl.id))[1] AS bc_ligne_id,
                       count(*) AS n
                  FROM mg_achat_facture_lignes fl2
                  JOIN mg_achat_factures f ON f.id = fl2.facture_id
                  JOIN mg_bc_lignes bl
                    ON bl.bc_id = f.bon_id
                   AND {_NORM.format('bl.description')} = {_NORM.format('fl2.designation')}
                 GROUP BY fl2.id
               ) m
         WHERE fl.id = m.fl_id AND m.n = 1 AND fl.bc_ligne_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE mg_achat_facture_lignes fl
           SET taux_tva = COALESCE(bl.taux_tva, 0)
          FROM mg_bc_lignes bl
         WHERE bl.id = fl.bc_ligne_id AND fl.taux_tva IS NULL
        """
    )
    op.execute(
        """
        UPDATE mg_achat_facture_lignes fl
           SET taux_tva = CASE WHEN f.montant_ht > 0
                               THEN round(f.montant_tva * 100 / f.montant_ht, 2) ELSE 0 END
          FROM mg_achat_factures f
         WHERE f.id = fl.facture_id AND fl.taux_tva IS NULL
        """
    )
    op.execute(
        """
        UPDATE mg_achat_facture_lignes
           SET montant_tva = round(COALESCE(total_ht, 0) * taux_tva / 100, 2)
         WHERE montant_tva IS NULL
        """
    )
    op.execute(
        "UPDATE mg_achat_facture_lignes SET total_ttc = COALESCE(total_ht, 0) + montant_tva WHERE total_ttc IS NULL"
    )

    # Factures : montant payé et statut de paiement déduits des paiements PAYE.
    op.execute(
        """
        UPDATE mg_achat_factures f
           SET montant_paye = COALESCE((
                SELECT sum(p.montant) FROM mg_achat_paiements p
                 WHERE p.facture_id = f.id AND p.statut = 'PAYE' AND p.deleted_at IS NULL
               ), 0)
        """
    )
    op.execute(
        """
        UPDATE mg_achat_factures
           SET statut = CASE
                 WHEN montant_paye <= 0 THEN 'A_PAYER'
                 WHEN montant_paye + 0.01 > montant_ttc THEN 'PAYEE'
                 ELSE 'PARTIELLEMENT_PAYEE' END
         WHERE statut IN ('VALIDEE', 'A_PAYER', 'PAYE', 'PAYEE', 'PARTIELLEMENT_PAYEE')
            OR (statut IN ('RECUE', 'ANOMALIE') AND montant_paye > 0)
        """
    )

    for table, cols in (
        ("mg_achat_facture_lignes", ("taux_tva", "montant_tva", "total_ttc")),
        ("mg_achat_factures", ("montant_paye",)),
    ):
        for col in cols:
            op.alter_column(table, col, server_default="0")


def downgrade() -> None:
    op.drop_index("ix_mg_achat_facture_lignes_bc_ligne_id", table_name="mg_achat_facture_lignes")
    op.drop_constraint(
        "fk_mg_achat_facture_lignes_bc_ligne", "mg_achat_facture_lignes", type_="foreignkey"
    )
    for table, cols in _COLONNES.items():
        for name, _ in cols:
            op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {name}")
