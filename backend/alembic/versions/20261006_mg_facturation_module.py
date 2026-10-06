"""Facturation Fournisseurs devient un module MG à part entière.

Les permissions ``mg.factures.*`` et ``mg.facturation.manage`` sont rattachées au module
``facturation-fournisseurs`` et retirées des rôles ``contrats-echeances.*`` ; les pièces GED des
factures suivent le module. Aucun accès n'est accordé automatiquement (CORE ADMIN attribue le
module). La ligne ``plateforme_modules`` et les rôles ``facturation-fournisseurs.*`` sont créés
par le catalogue au démarrage.

Revision ID: 20261006_mg_facturation_module
Revises: 20261005_mg_points_telephone
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20261006_mg_facturation_module"
down_revision: Union[str, None] = "20261005_mg_points_telephone"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PERMS = "(code LIKE 'mg.factures.%' OR code = 'mg.facturation.manage')"


def upgrade() -> None:
    op.execute(f"UPDATE permissions SET module = 'facturation-fournisseurs' WHERE {_PERMS}")
    op.execute(
        f"""
        DELETE FROM role_permissions
        WHERE role_id IN (SELECT id FROM roles WHERE code LIKE 'contrats-echeances.%')
          AND permission_id IN (SELECT id FROM permissions WHERE {_PERMS})
        """
    )
    op.execute(
        "UPDATE ged_documents SET module_code = 'facturation-fournisseurs' "
        "WHERE module_code = 'contrats-echeances' AND entity = 'facture'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE ged_documents SET module_code = 'contrats-echeances' "
        "WHERE module_code = 'facturation-fournisseurs' AND entity = 'facture'"
    )
    op.execute(f"UPDATE permissions SET module = 'contrats-echeances' WHERE {_PERMS}")
