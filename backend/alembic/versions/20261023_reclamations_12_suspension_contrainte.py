"""Réclamations : contrainte de suspension — ``statut_avant_suspension`` obligatoire si suspendu.

PostgreSQL traite un CHECK dont le résultat est NULL comme satisfait : ``NULL IN (…)`` ne refusait
pas un dossier ``SUSPENDUE`` sans statut d'origine. La contrainte exige désormais explicitement
cette valeur (statut ouvert d'avant la suspension).

Revision ID: 20261023_reclamations_12
Revises: 20261023_reclamations_11
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20261023_reclamations_12"
down_revision: Union[str, None] = "20261023_reclamations_11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STATUTS_SUSPENDABLES = ("A_QUALIFIER", "A_AFFECTER", "EN_TRAITEMENT", "RETOUR_RECU", "A_CLOTURER", "REOUVERTE")


def _in(colonne: str, valeurs: tuple[str, ...]) -> str:
    return f"{colonne} IN ({','.join(repr(v) for v in valeurs)})"


def upgrade() -> None:
    op.drop_constraint("ck_reclamations_suspension", "reclamations")
    op.create_check_constraint(
        "ck_reclamations_suspension", "reclamations",
        f"statut <> 'SUSPENDUE' OR (statut_avant_suspension IS NOT NULL AND "
        f"{_in('statut_avant_suspension', STATUTS_SUSPENDABLES)})")


def downgrade() -> None:
    op.drop_constraint("ck_reclamations_suspension", "reclamations")
    op.create_check_constraint(
        "ck_reclamations_suspension", "reclamations",
        f"statut <> 'SUSPENDUE' OR ({_in('statut_avant_suspension', STATUTS_SUSPENDABLES)})")
