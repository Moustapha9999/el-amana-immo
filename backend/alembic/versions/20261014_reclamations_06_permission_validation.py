"""Réclamations — permission ``reclamations.references.validate`` présente dès la migration.

Sans attendre la synchronisation du catalogue à la connexion : la permission est créée et liée
au rôle ``reclamations.admin`` (seul rôle catalogue qui la reçoit). Idempotent.

Revision ID: 20261014_reclamations_06
Revises: 20261014_reclamations_05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261014_reclamations_06"
down_revision: Union[str, None] = "20261014_reclamations_05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CODE = "reclamations.references.validate"
LIBELLE = "Validation des types, motifs et sous-motifs proposés"
ROLE = "reclamations.admin"


def upgrade() -> None:
    op.execute(sa.text(
        "INSERT INTO permissions (id, code, label, module) "
        "SELECT gen_random_uuid(), :c, :l, 'reclamations' "
        "WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = :c)").bindparams(c=CODE, l=LIBELLE))
    op.execute(sa.text(
        "INSERT INTO role_permissions (role_id, permission_id) "
        "SELECT r.id, p.id FROM roles r JOIN permissions p ON p.code = :c WHERE r.code = :r "
        "AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission_id = p.id)"
    ).bindparams(c=CODE, r=ROLE))


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM permissions WHERE code = :c").bindparams(c=CODE))
