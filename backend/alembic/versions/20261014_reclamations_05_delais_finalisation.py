"""Réclamations — délais centralisés, classification à valider, permissions obsolètes.

Additif, sans réécriture de l'historique :
- ``reclamation_regles_delai`` : sous-motif ciblé, événement de fin (``point_arrivee``), unité
  ``HEURES``, lien de version (``remplace_id``) — une règle déjà appliquée ne se modifie plus, elle
  est remplacée à une date d'effet ;
- ``reclamations`` : ``etat_delai`` (pourquoi une échéance existe ou non) et ``niveau_alerte`` /
  ``alerte_notifiee_le`` (une notification par changement de niveau, pas une par jour) ;
- ``reclamation_referentiels`` : ``statut_validation`` PROPOSEE / VALIDEE (rien n'est validé
  d'office : toutes les valeurs existantes restent PROPOSEE) ;
- retrait des permissions sans usage ``reclamations.suspend``, ``reclamations.response.prepare``,
  ``reclamations.response.validate``, ``reclamations.audit.view`` (liens rôle supprimés en cascade ;
  aucun utilisateur ne les détenait hors rôles catalogue) ; ajout de ``reclamations.references.validate``
  par la synchronisation additive du catalogue (connexion / hub).

Revision ID: 20261014_reclamations_05
Revises: 20261014_reclamations_04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261014_reclamations_05"
down_revision: Union[str, None] = "20261014_reclamations_04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PERMISSIONS_RETIREES = (
    ("reclamations.suspend", "Suspension et reprise d'une réclamation"),
    ("reclamations.response.prepare", "Rédaction de la réponse au client"),
    ("reclamations.response.validate", "Validation de la réponse au client"),
    ("reclamations.audit.view", "Consultation du journal d'audit réclamations"),
)


def _colonnes(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _contrainte(table: str, nom: str, condition: str) -> None:
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {nom}")
    op.create_check_constraint(nom, table, condition)


def upgrade() -> None:
    regles = _colonnes("reclamation_regles_delai")
    if "sous_motif_id" not in regles:
        op.add_column("reclamation_regles_delai", sa.Column(
            "sous_motif_id", sa.UUID(), sa.ForeignKey("reclamation_referentiels.id"), nullable=True))
        op.create_index("ix_reclamation_regles_delai_sous_motif_id", "reclamation_regles_delai", ["sous_motif_id"])
    if "point_arrivee" not in regles:
        op.add_column("reclamation_regles_delai", sa.Column(
            "point_arrivee", sa.String(30), nullable=False, server_default="CLOTURE"))
    if "remplace_id" not in regles:
        op.add_column("reclamation_regles_delai", sa.Column(
            "remplace_id", sa.UUID(), sa.ForeignKey("reclamation_regles_delai.id", ondelete="SET NULL"),
            nullable=True))
    _contrainte("reclamation_regles_delai", "ck_reclamation_regles_delai_unite",
                "unite_duree IN ('JOURS_CALENDAIRES','JOURS_OUVRES','HEURES')")
    _contrainte("reclamation_regles_delai", "ck_reclamation_regles_delai_arrivee",
                "point_arrivee IN ('CLOTURE','REPONSE_CLIENT')")

    dossiers = _colonnes("reclamations")
    if "etat_delai" not in dossiers:
        op.add_column("reclamations", sa.Column("etat_delai", sa.String(30), nullable=True))
    if "niveau_alerte" not in dossiers:
        op.add_column("reclamations", sa.Column("niveau_alerte", sa.String(10), nullable=True))
    if "alerte_notifiee_le" not in dossiers:
        op.add_column("reclamations", sa.Column("alerte_notifiee_le", sa.DateTime(timezone=True), nullable=True))
    if "date_alerte" not in dossiers:
        op.add_column("reclamations", sa.Column("date_alerte", sa.DateTime(timezone=True), nullable=True))
    if "date_fin_delai" not in dossiers:
        op.add_column("reclamations", sa.Column("date_fin_delai", sa.DateTime(timezone=True), nullable=True))
    _contrainte("reclamations", "ck_reclamations_etat_delai",
                "etat_delai IS NULL OR etat_delai IN "
                "('CALCULE','NON_CONFIGURE','EN_ATTENTE_VALIDATION','CONFLIT','SANS_DEPART')")
    _contrainte("reclamations", "ck_reclamations_niveau_alerte",
                "niveau_alerte IS NULL OR niveau_alerte IN ('PROCHE','RETARD')")
    # État constaté, pas inventé : une échéance déjà posée a été calculée, sinon aucune règle ne s'appliquait.
    op.execute("UPDATE reclamations SET etat_delai = CASE WHEN echeance IS NOT NULL THEN 'CALCULE' "
               "ELSE 'NON_CONFIGURE' END WHERE etat_delai IS NULL")
    # Fin du délai = clôture (événement de fin par défaut) pour les dossiers terminés.
    op.execute("UPDATE reclamations SET date_fin_delai = date_cloture "
               "WHERE date_fin_delai IS NULL AND statut IN ('CLOTUREE','REJETEE','ANNULEE')")

    refs = _colonnes("reclamation_referentiels")
    if "statut_validation" not in refs:
        op.add_column("reclamation_referentiels", sa.Column(
            "statut_validation", sa.String(20), nullable=False, server_default="PROPOSEE"))
    if "valide_par_id" not in refs:
        op.add_column("reclamation_referentiels", sa.Column(
            "valide_par_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True))
    if "valide_le" not in refs:
        op.add_column("reclamation_referentiels", sa.Column("valide_le", sa.DateTime(timezone=True), nullable=True))
    _contrainte("reclamation_referentiels", "ck_reclamation_referentiels_validation",
                "statut_validation IN ('PROPOSEE','VALIDEE')")

    codes = ",".join(f"'{c}'" for c, _ in PERMISSIONS_RETIREES)
    op.execute(f"DELETE FROM permissions WHERE code IN ({codes})")


def downgrade() -> None:
    for code, libelle in PERMISSIONS_RETIREES:
        op.execute(sa.text("INSERT INTO permissions (id, code, label, module) "
                           "SELECT gen_random_uuid(), :c, :l, 'reclamations' "
                           "WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = :c)").bindparams(c=code, l=libelle))
    for table, nom in (("reclamation_referentiels", "ck_reclamation_referentiels_validation"),
                       ("reclamations", "ck_reclamations_niveau_alerte"),
                       ("reclamations", "ck_reclamations_etat_delai"),
                       ("reclamation_regles_delai", "ck_reclamation_regles_delai_arrivee")):
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {nom}")
    for col in ("valide_le", "valide_par_id", "statut_validation"):
        op.drop_column("reclamation_referentiels", col)
    for col in ("date_fin_delai", "date_alerte", "alerte_notifiee_le", "niveau_alerte", "etat_delai"):
        op.drop_column("reclamations", col)
    op.execute("UPDATE reclamation_regles_delai SET unite_duree = 'JOURS_CALENDAIRES' WHERE unite_duree = 'HEURES'")
    _contrainte("reclamation_regles_delai", "ck_reclamation_regles_delai_unite",
                "unite_duree IN ('JOURS_CALENDAIRES','JOURS_OUVRES')")
    op.drop_index("ix_reclamation_regles_delai_sous_motif_id", table_name="reclamation_regles_delai")
    for col in ("remplace_id", "point_arrivee", "sous_motif_id"):
        op.drop_column("reclamation_regles_delai", col)
