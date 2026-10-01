"""Enrichissement référentiel fournisseurs (additif Achats).

Revision ID: 20260923_fournisseurs_enrich
Revises: 20260921_mg_achats_v1
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260923_fournisseurs_enrich"
down_revision: Union[str, None] = "20260921_mg_achats_v1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _cols(bind) -> set[str]:
    insp = sa.inspect(bind)
    return {c["name"] for c in insp.get_columns("fournisseurs")}


def _indexes(bind) -> set[str]:
    insp = sa.inspect(bind)
    return {i["name"] for i in insp.get_indexes("fournisseurs")}


def upgrade() -> None:
    bind = op.get_bind()
    existing = _cols(bind)
    idxs = _indexes(bind)

    def add(name: str, col: sa.Column) -> None:
        if name not in existing:
            op.add_column("fournisseurs", col)

    add("nom_commercial", sa.Column("nom_commercial", sa.String(255), nullable=True))
    add(
        "type_fournisseur",
        sa.Column("type_fournisseur", sa.String(40), nullable=False, server_default="FOURNITURE"),
    )
    add("contact_fonction", sa.Column("contact_fonction", sa.String(120), nullable=True))
    add("telephone_secondaire", sa.Column("telephone_secondaire", sa.String(40), nullable=True))
    add("site_web", sa.Column("site_web", sa.String(255), nullable=True))
    add("ville", sa.Column("ville", sa.String(120), nullable=True))
    add("pays", sa.Column("pays", sa.String(80), nullable=False, server_default="Mauritanie"))
    add("nif", sa.Column("nif", sa.String(60), nullable=True))
    add("rc", sa.Column("rc", sa.String(60), nullable=True))
    add("devise_defaut", sa.Column("devise_defaut", sa.String(10), nullable=False, server_default="MRU"))
    add("mode_paiement_defaut", sa.Column("mode_paiement_defaut", sa.String(80), nullable=True))
    add("delai_paiement_jours", sa.Column("delai_paiement_jours", sa.Integer(), nullable=True))
    add("conditions_commerciales", sa.Column("conditions_commerciales", sa.Text(), nullable=True))
    add("created_by", sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True))
    add("updated_by", sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True))

    if "ix_fournisseurs_ville" not in idxs:
        op.create_index("ix_fournisseurs_ville", "fournisseurs", ["ville"])
    if "ix_fournisseurs_type" not in idxs:
        op.create_index("ix_fournisseurs_type", "fournisseurs", ["type_fournisseur"])
    if "ix_fournisseurs_nif" not in idxs:
        op.create_index("ix_fournisseurs_nif", "fournisseurs", ["nif"])


def downgrade() -> None:
    bind = op.get_bind()
    existing = _cols(bind)
    idxs = _indexes(bind)
    for name in ("ix_fournisseurs_nif", "ix_fournisseurs_type", "ix_fournisseurs_ville"):
        if name in idxs:
            op.drop_index(name, table_name="fournisseurs")
    for col in (
        "updated_by",
        "created_by",
        "conditions_commerciales",
        "delai_paiement_jours",
        "mode_paiement_defaut",
        "devise_defaut",
        "rc",
        "nif",
        "pays",
        "ville",
        "site_web",
        "telephone_secondaire",
        "contact_fonction",
        "type_fournisseur",
        "nom_commercial",
    ):
        if col in existing:
            op.drop_column("fournisseurs", col)
