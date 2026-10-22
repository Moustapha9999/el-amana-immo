"""Stock & Fournitures — alertes de stock bas persistantes et option « Autre » (département / service).

Additif :
- ``mg_stock_alertes`` : un épisode par franchissement du seuil (index unique partiel : un seul
  épisode ouvert par article), statut de traitement, suppression logique auditée ;
- ``mg_stock_mouvements`` : ``departement_autre`` / ``service_autre`` / ``service_libelle`` pour les
  libellés saisis hors référentiel. Les contraintes de destination / provenance acceptent alors
  ``org_entite_id`` NULL, uniquement avec un libellé saisi non vide ;
- paramètre ``alerte_seuil_unites`` = 5 (non écrasé s'il existe).

Aucune alerte n'est créée ici : le contrôle initial (bouton « Lancer le contrôle » ou tâche
quotidienne) détecte les articles déjà ≤ seuil à partir du stock réel.

``downgrade`` : supprime table, séquence et colonnes ; les contraintes d'origine sont recréées
``NOT VALID`` (des sorties « Autre » peuvent exister) ; le paramètre est conservé.

Revision ID: 20261022_mg_stock_alertes
Revises: 20261022_notifications_01
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261022_mg_stock_alertes"
down_revision: Union[str, None] = "20261022_notifications_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
retour_arriere = "compatible"

_DEPARTEMENT_SAISI = "(departement_autre AND btrim(COALESCE(departement, '')) <> '')"

DESTINATION = (
    "destination_type IS NULL"
    " OR (destination_type = 'DEPARTEMENT' AND agence_id IS NULL"
    f" AND (org_entite_id IS NOT NULL OR {_DEPARTEMENT_SAISI}))"
    " OR (destination_type = 'AGENCE' AND agence_id IS NOT NULL AND org_entite_id IS NULL AND service_id IS NULL)"
)
PROVENANCE = (
    "provenance_type IS NULL OR (type_mouvement = 'ENTREE' AND destination_type IS NULL AND ("
    "(provenance_type = 'FOURNISSEUR' AND fournisseur_id IS NOT NULL AND org_entite_id IS NULL"
    " AND service_id IS NULL AND agence_id IS NULL)"
    " OR (provenance_type = 'RETOUR_DEPARTEMENT' AND agence_id IS NULL AND fournisseur_id IS NULL"
    f" AND (org_entite_id IS NOT NULL OR {_DEPARTEMENT_SAISI}))"
    " OR (provenance_type = 'RETOUR_AGENCE' AND agence_id IS NOT NULL AND org_entite_id IS NULL"
    " AND service_id IS NULL AND fournisseur_id IS NULL)"
    " OR (provenance_type = 'AUTRE' AND fournisseur_id IS NULL AND org_entite_id IS NULL"
    " AND service_id IS NULL AND agence_id IS NULL)))"
)
AUTRES = (
    "(NOT departement_autre OR org_entite_id IS NULL)"
    " AND (NOT service_autre OR (service_id IS NULL AND btrim(COALESCE(service_libelle, '')) <> ''))"
)

DESTINATION_ORIGINE = (
    "destination_type IS NULL"
    " OR (destination_type = 'DEPARTEMENT' AND org_entite_id IS NOT NULL AND agence_id IS NULL)"
    " OR (destination_type = 'AGENCE' AND agence_id IS NOT NULL AND org_entite_id IS NULL AND service_id IS NULL)"
)
PROVENANCE_ORIGINE = (
    "provenance_type IS NULL OR (type_mouvement = 'ENTREE' AND destination_type IS NULL AND ("
    "(provenance_type = 'FOURNISSEUR' AND fournisseur_id IS NOT NULL AND org_entite_id IS NULL"
    " AND service_id IS NULL AND agence_id IS NULL)"
    " OR (provenance_type = 'RETOUR_DEPARTEMENT' AND org_entite_id IS NOT NULL AND agence_id IS NULL"
    " AND fournisseur_id IS NULL)"
    " OR (provenance_type = 'RETOUR_AGENCE' AND agence_id IS NOT NULL AND org_entite_id IS NULL"
    " AND service_id IS NULL AND fournisseur_id IS NULL)"
    " OR (provenance_type = 'AUTRE' AND fournisseur_id IS NULL AND org_entite_id IS NULL"
    " AND service_id IS NULL AND agence_id IS NULL)))"
)


def upgrade() -> None:
    op.add_column(
        "mg_stock_mouvements",
        sa.Column("departement_autre", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "mg_stock_mouvements",
        sa.Column("service_autre", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("mg_stock_mouvements", sa.Column("service_libelle", sa.String(120), nullable=True))
    op.drop_constraint("ck_mg_stock_mvt_destination", "mg_stock_mouvements", type_="check")
    op.drop_constraint("ck_mg_stock_mvt_provenance", "mg_stock_mouvements", type_="check")
    op.create_check_constraint("ck_mg_stock_mvt_destination", "mg_stock_mouvements", DESTINATION)
    op.create_check_constraint("ck_mg_stock_mvt_provenance", "mg_stock_mouvements", PROVENANCE)
    op.create_check_constraint("ck_mg_stock_mvt_autre", "mg_stock_mouvements", AUTRES)

    op.execute("CREATE SEQUENCE IF NOT EXISTS mg_stock_alertes_ref_seq")
    uid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "mg_stock_alertes",
        sa.Column("id", uid, primary_key=True),
        sa.Column("reference", sa.String(40), nullable=False),
        sa.Column("article_id", uid, sa.ForeignKey("mg_articles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("agence_id", uid, sa.ForeignKey("agences.id"), nullable=True),
        sa.Column("emplacement", sa.String(120), nullable=True),
        sa.Column("type_alerte", sa.String(20), nullable=False),
        sa.Column("statut", sa.String(20), nullable=False, server_default="NOUVELLE"),
        sa.Column("origine", sa.String(20), nullable=False, server_default="AUTOMATIQUE"),
        sa.Column("seuil", sa.Numeric(18, 3), nullable=False),
        sa.Column("quantite_detection", sa.Numeric(18, 3), nullable=False),
        sa.Column("quantite_actuelle", sa.Numeric(18, 3), nullable=False),
        sa.Column("uom", sa.String(20), nullable=True),
        sa.Column("detectee_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rupture_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retour_normal_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quantite_retour", sa.Numeric(18, 3), nullable=True),
        sa.Column(
            "mouvement_id", uid, sa.ForeignKey("mg_stock_mouvements.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("mouvement_reference", sa.String(40), nullable=True),
        sa.Column("responsable_id", uid, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("commentaire", sa.Text(), nullable=True),
        sa.Column("traite_par", uid, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("traite_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", uid, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("motif_suppression", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("type_alerte IN ('STOCK_FAIBLE', 'RUPTURE')", name="ck_mg_stock_alertes_type"),
        sa.CheckConstraint(
            "statut IN ('NOUVELLE', 'EN_COURS', 'RESOLUE', 'CLOTUREE')", name="ck_mg_stock_alertes_statut"
        ),
        sa.CheckConstraint("origine IN ('AUTOMATIQUE', 'CONTROLE')", name="ck_mg_stock_alertes_origine"),
        sa.CheckConstraint(
            "deleted_at IS NULL OR btrim(COALESCE(motif_suppression, '')) <> ''",
            name="ck_mg_stock_alertes_motif_suppression",
        ),
    )
    op.create_index("ix_mg_stock_alertes_reference", "mg_stock_alertes", ["reference"], unique=True)
    op.create_index("ix_mg_stock_alertes_article_id", "mg_stock_alertes", ["article_id"])
    op.create_index("ix_mg_stock_alertes_agence_id", "mg_stock_alertes", ["agence_id"])
    op.create_index("ix_mg_stock_alertes_type_alerte", "mg_stock_alertes", ["type_alerte"])
    op.create_index("ix_mg_stock_alertes_statut", "mg_stock_alertes", ["statut"])
    op.create_index("ix_mg_stock_alertes_responsable_id", "mg_stock_alertes", ["responsable_id"])
    op.create_index("ix_mg_stock_alertes_deleted_at", "mg_stock_alertes", ["deleted_at"])
    op.create_index("ix_mg_stock_alertes_detectee_at", "mg_stock_alertes", ["detectee_at"])
    op.create_index(
        "uq_mg_stock_alertes_episode_ouvert",
        "mg_stock_alertes",
        ["article_id"],
        unique=True,
        postgresql_where=sa.text("retour_normal_at IS NULL"),
    )

    op.execute(
        "INSERT INTO mg_stock_parametres (id, cle, valeur, libelle, created_at, updated_at) "
        "SELECT gen_random_uuid(), 'alerte_seuil_unites', '5', "
        "'Seuil d''alerte stock bas (unités disponibles ou moins)', now(), now() "
        "WHERE NOT EXISTS (SELECT 1 FROM mg_stock_parametres WHERE cle = 'alerte_seuil_unites')"
    )


def downgrade() -> None:
    op.drop_table("mg_stock_alertes")
    op.execute("DROP SEQUENCE IF EXISTS mg_stock_alertes_ref_seq")
    op.drop_constraint("ck_mg_stock_mvt_autre", "mg_stock_mouvements", type_="check")
    op.drop_constraint("ck_mg_stock_mvt_destination", "mg_stock_mouvements", type_="check")
    op.drop_constraint("ck_mg_stock_mvt_provenance", "mg_stock_mouvements", type_="check")
    op.execute(f"ALTER TABLE mg_stock_mouvements ADD CONSTRAINT ck_mg_stock_mvt_destination CHECK ({DESTINATION_ORIGINE}) NOT VALID")
    op.execute(f"ALTER TABLE mg_stock_mouvements ADD CONSTRAINT ck_mg_stock_mvt_provenance CHECK ({PROVENANCE_ORIGINE}) NOT VALID")
    op.drop_column("mg_stock_mouvements", "service_libelle")
    op.drop_column("mg_stock_mouvements", "service_autre")
    op.drop_column("mg_stock_mouvements", "departement_autre")
