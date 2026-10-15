"""Stock & Fournitures — sortie de stock avec destination, demandeur et motif configurable. Additif.

Une seule table de mouvements (``mg_stock_mouvements``) : la sortie y gagne
- ``destination_type`` : ``DEPARTEMENT`` | ``AGENCE`` (NULL = mouvement historique ou autre type) ;
- ``service_id`` : service / section / cellule de l'organigramme (sous-arbre de ``org_entite_id``) ;
- ``demandeur_id`` (utilisateur référencé) ou ``demandeur_nom`` (identité déclarée) ;
- ``motif_id`` → ``mg_stock_motifs_sortie`` (le libellé reste copié dans ``motif``) ;
- ``cle_idempotence`` : une même action (double clic, relance réseau) ne crée jamais deux sorties.

Le département destinataire réutilise ``org_entite_id`` (référentiel CORE ``departements``) et
l'agence destinataire ``agence_id`` (référentiel ``agences``) : aucune liste locale.

Exclusion des destinations garantie en base (``ck_mg_stock_mvt_destination``) : DEPARTEMENT ⇒
département renseigné et agence vide ; AGENCE ⇒ agence renseignée, département et service vides.
Les 8 000+ mouvements existants (``destination_type`` NULL) ne sont pas concernés.

Revision ID: 20261015_mg_stock_sorties
Revises: 20261015_clientele_11
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261015_mg_stock_sorties"
down_revision: Union[str, None] = "20261015_clientele_11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UUID = postgresql.UUID(as_uuid=True)

MOTIFS = (
    ("CONSOMMATION", "Consommation courante", False),
    ("DOTATION", "Dotation initiale / nouvel agent", False),
    ("REMPLACEMENT", "Remplacement d'un article usé ou défectueux", False),
    ("EVENEMENT", "Réunion, formation ou événement", False),
    ("PROJET", "Projet ou opération ponctuelle", False),
    ("AUTRE", "Autre motif (à préciser en observation)", True),
)


def upgrade() -> None:
    op.create_table(
        "mg_stock_motifs_sortie",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("libelle", sa.String(160), nullable=False),
        sa.Column("observation_obligatoire", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("ordre", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("code", name="uq_mg_stock_motifs_sortie_code"),
    )
    for ordre, (code, libelle, obs) in enumerate(MOTIFS, start=1):
        op.execute(sa.text(
            "INSERT INTO mg_stock_motifs_sortie (id, code, libelle, observation_obligatoire, ordre) "
            "SELECT gen_random_uuid(), :c, :l, :o, :r "
            "WHERE NOT EXISTS (SELECT 1 FROM mg_stock_motifs_sortie WHERE code = :c)"
        ).bindparams(c=code, l=libelle, o=obs, r=ordre * 10))

    t = "mg_stock_mouvements"
    op.add_column(t, sa.Column("destination_type", sa.String(20), nullable=True))
    op.add_column(t, sa.Column("service_id", _UUID, nullable=True))
    op.add_column(t, sa.Column("demandeur_id", _UUID, nullable=True))
    op.add_column(t, sa.Column("demandeur_nom", sa.String(255), nullable=True))
    op.add_column(t, sa.Column("motif_id", _UUID, nullable=True))
    op.add_column(t, sa.Column("cle_idempotence", sa.String(120), nullable=True))
    op.create_foreign_key("fk_mg_stock_mvt_service", t, "departements", ["service_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_mg_stock_mvt_demandeur", t, "users", ["demandeur_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_mg_stock_mvt_motif", t, "mg_stock_motifs_sortie", ["motif_id"], ["id"],
                          ondelete="RESTRICT")
    op.create_index("ix_mg_stock_mouvements_destination_type", t, ["destination_type"])
    op.create_index("ix_mg_stock_mouvements_service_id", t, ["service_id"])
    op.create_index("ix_mg_stock_mouvements_demandeur_id", t, ["demandeur_id"])
    op.create_index("ix_mg_stock_mouvements_motif_id", t, ["motif_id"])
    op.create_index("uq_mg_stock_mouvements_cle_idempotence", t, ["cle_idempotence"], unique=True,
                    postgresql_where=sa.text("cle_idempotence IS NOT NULL"))
    op.create_check_constraint(
        "ck_mg_stock_mvt_destination", t,
        "destination_type IS NULL"
        " OR (destination_type = 'DEPARTEMENT' AND org_entite_id IS NOT NULL AND agence_id IS NULL)"
        " OR (destination_type = 'AGENCE' AND agence_id IS NOT NULL AND org_entite_id IS NULL"
        "     AND service_id IS NULL)",
    )
    op.create_check_constraint(
        "ck_mg_stock_mvt_demandeur", t,
        "destination_type IS NULL OR demandeur_id IS NOT NULL OR btrim(coalesce(demandeur_nom, '')) <> ''",
    )

    op.execute(sa.text(
        "INSERT INTO mg_stock_parametres (id, cle, valeur, libelle) "
        "SELECT gen_random_uuid(), 'sortie_demandeur_libre', '1', "
        "'Sortie : demandeur saisi librement autorisé (1 = oui, 0 = utilisateurs référencés seulement)' "
        "WHERE NOT EXISTS (SELECT 1 FROM mg_stock_parametres WHERE cle = 'sortie_demandeur_libre')"
    ))


def downgrade() -> None:
    t = "mg_stock_mouvements"
    op.execute("DELETE FROM mg_stock_parametres WHERE cle = 'sortie_demandeur_libre'")
    op.drop_constraint("ck_mg_stock_mvt_demandeur", t, type_="check")
    op.drop_constraint("ck_mg_stock_mvt_destination", t, type_="check")
    op.drop_index("uq_mg_stock_mouvements_cle_idempotence", table_name=t)
    for col in ("motif_id", "demandeur_id", "service_id", "destination_type"):
        op.drop_index(f"ix_mg_stock_mouvements_{col}", table_name=t)
    op.drop_constraint("fk_mg_stock_mvt_motif", t, type_="foreignkey")
    op.drop_constraint("fk_mg_stock_mvt_demandeur", t, type_="foreignkey")
    op.drop_constraint("fk_mg_stock_mvt_service", t, type_="foreignkey")
    for col in ("cle_idempotence", "motif_id", "demandeur_nom", "demandeur_id", "service_id", "destination_type"):
        op.drop_column(t, col)
    op.drop_table("mg_stock_motifs_sortie")
