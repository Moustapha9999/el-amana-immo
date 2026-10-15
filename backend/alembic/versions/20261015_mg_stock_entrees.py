"""Stock & Fournitures — entrée de stock avec provenance, fournisseur et motif configurable. Additif.

``mg_stock_mouvements`` gagne, pour les entrées saisies par formulaire :
- ``provenance_type`` : ``FOURNISSEUR`` | ``RETOUR_DEPARTEMENT`` | ``RETOUR_AGENCE`` | ``AUTRE``
  (NULL = mouvement historique, réception BC ou autre type) ;
- ``fournisseur_id`` → référentiel CORE ``fournisseurs`` ;
- ``piece_reference`` : n° de bon de livraison / facture.
Un retour réutilise ``org_entite_id`` / ``service_id`` (département) ou ``agence_id`` (agence).

Les motifs d'entrée partagent la table des motifs (``sens`` = ``ENTREE``).

Exclusion des provenances garantie en base (``ck_mg_stock_mvt_provenance``).

Revision ID: 20261015_mg_stock_entrees
Revises: 20261015_mg_stock_sorties
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261015_mg_stock_entrees"
down_revision: Union[str, None] = "20261015_mg_stock_sorties"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UUID = postgresql.UUID(as_uuid=True)

MOTIFS_ENTREE = (
    ("E_ACHAT", "Achat direct (hors bon de commande)", False),
    ("E_RETOUR", "Retour d'articles non utilisés", False),
    ("E_DON", "Don ou dotation reçue", False),
    ("E_TRANSFERT", "Transfert reçu d'un autre site", False),
    ("E_AUTRE", "Autre motif (à préciser en observation)", True),
)


def upgrade() -> None:
    m = "mg_stock_motifs_sortie"
    op.add_column(m, sa.Column("sens", sa.String(10), nullable=False, server_default="SORTIE"))
    op.create_check_constraint("ck_mg_stock_motif_sens", m, "sens IN ('SORTIE', 'ENTREE')")
    op.create_index("ix_mg_stock_motifs_sortie_sens", m, ["sens"])
    for ordre, (code, libelle, obs) in enumerate(MOTIFS_ENTREE, start=1):
        op.execute(sa.text(
            "INSERT INTO mg_stock_motifs_sortie (id, code, libelle, observation_obligatoire, ordre, sens) "
            "SELECT gen_random_uuid(), :c, :l, :o, :r, 'ENTREE' "
            "WHERE NOT EXISTS (SELECT 1 FROM mg_stock_motifs_sortie WHERE code = :c)"
        ).bindparams(c=code, l=libelle, o=obs, r=ordre * 10))

    t = "mg_stock_mouvements"
    op.add_column(t, sa.Column("provenance_type", sa.String(30), nullable=True))
    op.add_column(t, sa.Column("fournisseur_id", _UUID, nullable=True))
    op.add_column(t, sa.Column("piece_reference", sa.String(80), nullable=True))
    op.create_foreign_key("fk_mg_stock_mvt_fournisseur", t, "fournisseurs", ["fournisseur_id"], ["id"],
                          ondelete="RESTRICT")
    op.create_index("ix_mg_stock_mouvements_provenance_type", t, ["provenance_type"])
    op.create_index("ix_mg_stock_mouvements_fournisseur_id", t, ["fournisseur_id"])
    op.create_check_constraint(
        "ck_mg_stock_mvt_provenance", t,
        "provenance_type IS NULL"
        " OR (type_mouvement = 'ENTREE' AND destination_type IS NULL AND ("
        "   (provenance_type = 'FOURNISSEUR' AND fournisseur_id IS NOT NULL"
        "     AND org_entite_id IS NULL AND service_id IS NULL AND agence_id IS NULL)"
        "   OR (provenance_type = 'RETOUR_DEPARTEMENT' AND org_entite_id IS NOT NULL"
        "     AND agence_id IS NULL AND fournisseur_id IS NULL)"
        "   OR (provenance_type = 'RETOUR_AGENCE' AND agence_id IS NOT NULL"
        "     AND org_entite_id IS NULL AND service_id IS NULL AND fournisseur_id IS NULL)"
        "   OR (provenance_type = 'AUTRE' AND fournisseur_id IS NULL"
        "     AND org_entite_id IS NULL AND service_id IS NULL AND agence_id IS NULL)"
        " ))",
    )


def downgrade() -> None:
    t = "mg_stock_mouvements"
    op.drop_constraint("ck_mg_stock_mvt_provenance", t, type_="check")
    op.drop_index("ix_mg_stock_mouvements_fournisseur_id", table_name=t)
    op.drop_index("ix_mg_stock_mouvements_provenance_type", table_name=t)
    op.drop_constraint("fk_mg_stock_mvt_fournisseur", t, type_="foreignkey")
    for col in ("piece_reference", "fournisseur_id", "provenance_type"):
        op.drop_column(t, col)
    m = "mg_stock_motifs_sortie"
    op.execute(sa.text(
        "DELETE FROM mg_stock_motifs_sortie m WHERE m.sens = 'ENTREE'"
        " AND NOT EXISTS (SELECT 1 FROM mg_stock_mouvements v WHERE v.motif_id = m.id)"
    ))
    op.drop_index("ix_mg_stock_motifs_sortie_sens", table_name=m)
    op.drop_constraint("ck_mg_stock_motif_sens", m, type_="check")
    op.drop_column(m, "sens")
