"""Facturation Fournisseurs — circuit court : suppression de l'étape « Contrôle ».

Circuit : saisie (Reçue) → facture scannée → validation (contrôles bloquants revérifiés) → paiement.
Les factures encore « À contrôler » ou « Contrôlée » reviennent à « Reçue » (prêtes à valider).
Seules les factures d'origine FACTURATION sont concernées (les Achats gardent leur cycle).

Revision ID: 20261006_mg_facturation_circuit
Revises: 20261006_mg_facturation_tva
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20261006_mg_facturation_circuit"
down_revision: Union[str, None] = "20261006_mg_facturation_tva"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE mg_achat_factures SET statut = 'RECUE', updated_at = now() "
        "WHERE origine = 'FACTURATION' AND statut IN ('A_CONTROLER', 'CONTROLEE')"
    )


def downgrade() -> None:
    pass
