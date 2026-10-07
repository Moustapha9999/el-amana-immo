"""Fournisseurs — code FRS-NNN attribué automatiquement par une séquence PostgreSQL.

La séquence démarre après le plus grand code FRS-<n> existant (fiches supprimées comprises,
le code reste unique). Le DEFAULT de colonne couvre aussi les insertions SQL directes.

Revision ID: 20261007_fournisseurs_code_seq
Revises: 20261006_mg_facturation_circuit
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20261007_fournisseurs_code_seq"
down_revision: Union[str, None] = "20261006_mg_facturation_circuit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS fournisseurs_code_seq START WITH 1 MINVALUE 1")
    op.execute(
        """
        SELECT setval(
            'fournisseurs_code_seq',
            COALESCE((SELECT max(substring(code FROM '^FRS-([0-9]+)$')::bigint) FROM fournisseurs), 0) + 1,
            false
        )
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fournisseur_code_suivant() RETURNS varchar AS $$
        DECLARE
            n bigint;
            candidat varchar;
        BEGIN
            LOOP
                n := nextval('fournisseurs_code_seq');
                candidat := 'FRS-' || lpad(n::text, greatest(3, length(n::text)), '0');
                EXIT WHEN NOT EXISTS (SELECT 1 FROM fournisseurs WHERE code = candidat);
            END LOOP;
            RETURN candidat;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute("ALTER TABLE fournisseurs ALTER COLUMN code SET DEFAULT fournisseur_code_suivant()")


def downgrade() -> None:
    op.execute("ALTER TABLE fournisseurs ALTER COLUMN code DROP DEFAULT")
    op.execute("DROP FUNCTION IF EXISTS fournisseur_code_suivant()")
    op.execute("DROP SEQUENCE IF EXISTS fournisseurs_code_seq")
