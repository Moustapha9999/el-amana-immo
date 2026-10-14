"""Réclamations : suppression définitive d'un dossier, quel que soit son statut.

La chronologie ``reclamation_evenements`` reste en ajout seul pour un dossier existant (UPDATE et
DELETE refusés). Seule nouveauté : ses lignes disparaissent avec leur dossier, par la cascade de
``DELETE FROM reclamations`` (le dossier n'existe déjà plus quand le trigger s'exécute). La trace
de la suppression est conservée dans ``audit_logs``.

Revision ID: 20261015_reclamations_08
Revises: 20261015_org_01
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20261015_reclamations_08"
down_revision: Union[str, None] = "20261015_org_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLONNES = """(NEW.id, NEW.reclamation_id, NEW.type_evenement, NEW.statut_avant, NEW.statut_apres,
                    NEW.etape_avant, NEW.etape_apres, NEW.date_effet, NEW.enregistre_le, NEW.commentaire,
                    NEW.donnees)
                   IS NOT DISTINCT FROM
                   (OLD.id, OLD.reclamation_id, OLD.type_evenement, OLD.statut_avant, OLD.statut_apres,
                    OLD.etape_avant, OLD.etape_apres, OLD.date_effet, OLD.enregistre_le, OLD.commentaire,
                    OLD.donnees)
                   AND (NEW.auteur_id IS NOT DISTINCT FROM OLD.auteur_id OR NEW.auteur_id IS NULL)
                   AND (NEW.unite_id IS NOT DISTINCT FROM OLD.unite_id OR NEW.unite_id IS NULL)
                   AND (NEW.affectation_id IS NOT DISTINCT FROM OLD.affectation_id OR NEW.affectation_id IS NULL)
                   AND (NEW.reponse_id IS NOT DISTINCT FROM OLD.reponse_id OR NEW.reponse_id IS NULL)"""


def _fonction(avec_cascade: bool) -> str:
    cascade = """
                IF TG_OP = 'DELETE' AND NOT EXISTS (SELECT 1 FROM reclamations WHERE id = OLD.reclamation_id) THEN
                    RETURN OLD;
                END IF;""" if avec_cascade else ""
    return f"""
            CREATE OR REPLACE FUNCTION reclamation_evenements_immuable() RETURNS trigger AS $$
            BEGIN{cascade}
                IF TG_OP = 'UPDATE' AND
                   {_COLONNES} THEN
                    RETURN NEW;
                END IF;
                RAISE EXCEPTION 'reclamation_evenements : chronologie en ajout seul (% refusé)', TG_OP
                    USING ERRCODE = 'P0001';
            END
            $$ LANGUAGE plpgsql
            """


def upgrade() -> None:
    op.execute(_fonction(avec_cascade=True))


def downgrade() -> None:
    op.execute(_fonction(avec_cascade=False))
