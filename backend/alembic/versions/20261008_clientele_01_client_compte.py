"""Base clientèle — modèle CLIENT (racine ORION) / COMPTE / RIB.

Additif : ``clientele_clients`` et ``clientele_comptes`` (docs/conformite/clientele-phase1.md).
Une ligne de l'État Compte ORION = un compte ; le client est consolidé sur ``racine_client``
(6 chiffres, zéros initiaux conservés, jamais un entier). Aucune table existante modifiée.

Revision ID: 20261008_clientele_01
Revises: 20261008_admin_powers
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261008_clientele_01"
down_revision: Union[str, None] = "20261008_admin_powers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UUID = postgresql.UUID(as_uuid=True)


def _horodatage() -> list[sa.Column]:
    return [
        sa.Column("source", sa.String(30), nullable=False, server_default="ORION_ETAT_COMPTE"),
        sa.Column("premiere_extraction", sa.Date(), nullable=False),
        sa.Column("date_extraction", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if not inspector.has_table("clientele_clients"):
        op.create_table(
            "clientele_clients",
            sa.Column("id", _UUID, primary_key=True),
            sa.Column("racine_client", sa.String(6), nullable=False),
            sa.Column("raison_sociale", sa.String(255), nullable=False),
            sa.Column("prenoms", sa.Text(), nullable=True),
            sa.Column("date_naissance", sa.Date(), nullable=True),
            sa.Column("date_naissance_orion", sa.String(120), nullable=True),
            sa.Column("nationalite", sa.String(80), nullable=True),
            sa.Column("statut_resident", sa.String(1), nullable=True),
            sa.Column("agent_economique", sa.String(80), nullable=True),
            sa.Column("situation_juridique", sa.String(120), nullable=True),
            sa.Column("categorie_juridique", sa.String(80), nullable=True),
            sa.Column("secteur_activite", sa.String(160), nullable=True),
            sa.Column("famille_secteur_activite", sa.String(120), nullable=True),
            sa.Column("type_identifiant", sa.String(3), nullable=True),
            sa.Column("identifiant_orion", sa.String(255), nullable=True),
            sa.Column("nni", sa.String(40), nullable=True),
            sa.Column("nif", sa.String(40), nullable=True),
            sa.Column("rcs", sa.String(255), nullable=True),
            sa.Column("type_client", sa.String(20), nullable=True),
            *_horodatage(),
            sa.CheckConstraint("racine_client ~ '^[0-9]{6}$'", name="ck_clientele_clients_racine"),
            sa.CheckConstraint("statut_resident IS NULL OR statut_resident IN ('R','N')",
                               name="ck_clientele_clients_resident"),
            sa.CheckConstraint("type_identifiant IS NULL OR type_identifiant IN ('NNI','NIF')",
                               name="ck_clientele_clients_type_identifiant"),
            sa.CheckConstraint(
                "type_client IS NULL OR type_client IN ('PP','PM_PRIVEE','PM_PUBLIQUE','ASSOCIATION')",
                name="ck_clientele_clients_type_client"),
            sa.CheckConstraint("date_extraction >= premiere_extraction", name="ck_clientele_clients_extraction"),
            sa.UniqueConstraint("racine_client", name="uq_clientele_clients_racine"),
        )
        op.create_index("ix_clientele_clients_raison_sociale", "clientele_clients", ["raison_sociale"])
        op.create_index("ix_clientele_clients_nni", "clientele_clients", ["nni"])
        op.create_index("ix_clientele_clients_nif", "clientele_clients", ["nif"])
        op.create_index("ix_clientele_clients_type_client", "clientele_clients", ["type_client"])

    if not inspector.has_table("clientele_comptes"):
        op.create_table(
            "clientele_comptes",
            sa.Column("id", _UUID, primary_key=True),
            sa.Column("compte", sa.String(11), nullable=False),
            sa.Column("rib", sa.String(23), nullable=False),
            sa.Column(
                "racine_client",
                sa.String(6),
                sa.ForeignKey("clientele_clients.racine_client", ondelete="RESTRICT", onupdate="RESTRICT",
                              name="fk_clientele_comptes_racine"),
                nullable=False,
            ),
            sa.Column(
                "agence_id",
                _UUID,
                sa.ForeignKey("agences.id", ondelete="RESTRICT", name="fk_clientele_comptes_agence"),
                nullable=False,
            ),
            sa.Column("ncg", sa.String(6), nullable=True),
            sa.Column("rubrique_comptable", sa.String(80), nullable=True),
            sa.Column("etat_compte", sa.String(10), nullable=False),
            sa.Column("date_ouverture", sa.Date(), nullable=True),
            sa.Column("ddc", sa.Date(), nullable=True),
            sa.Column("ddd", sa.Date(), nullable=True),
            sa.Column("devise", sa.String(3), nullable=False),
            sa.Column("conformite_compte", sa.String(15), nullable=True),
            sa.Column("liste_interdiction", sa.Text(), nullable=True),
            *_horodatage(),
            sa.CheckConstraint("compte ~ '^[0-9]{11}$'", name="ck_clientele_comptes_compte"),
            sa.CheckConstraint("rib ~ '^[0-9]{23}$'", name="ck_clientele_comptes_rib"),
            sa.CheckConstraint("substr(rib, 11, 11) = compte", name="ck_clientele_comptes_rib_compte"),
            sa.CheckConstraint("etat_compte IN ('OUVERT','FERME')", name="ck_clientele_comptes_etat"),
            sa.CheckConstraint("devise ~ '^[A-Z]{3}$'", name="ck_clientele_comptes_devise"),
            sa.CheckConstraint("conformite_compte IS NULL OR conformite_compte IN ('CONFORME','NON_CONFORME')",
                               name="ck_clientele_comptes_conformite"),
            sa.CheckConstraint("date_extraction >= premiere_extraction", name="ck_clientele_comptes_extraction"),
            sa.UniqueConstraint("compte", name="uq_clientele_comptes_compte"),
            sa.UniqueConstraint("rib", name="uq_clientele_comptes_rib"),
        )
        op.create_index("ix_clientele_comptes_racine", "clientele_comptes", ["racine_client"])
        op.create_index("ix_clientele_comptes_agence_etat", "clientele_comptes", ["agence_id", "etat_compte"])


def downgrade() -> None:
    op.drop_table("clientele_comptes")
    op.drop_table("clientele_clients")
