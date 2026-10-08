"""Référentiel maître LBC/FT (CDC 1.0 LOT 1) : dimensions + valeurs.

Additif. ``actif`` = false. Ne classe personne. Ne s'applique pas à la production
``bea_digital``. Copie de test / recette uniquement.

Revision ID: 20261008_clientele_07
Revises: 20261008_clientele_06
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.data.clientele_classif_valeurs import DIMENSIONS, valeurs_maitres
from app.data.clientele_classif_matrice import VERSION_REGLES

revision: str = "20261008_clientele_07"
down_revision: Union[str, None] = "20261008_clientele_06"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UUID = postgresql.UUID(as_uuid=True)


def _table(name: str, *cols: sa.Column, **kwargs) -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(name):
        op.create_table(name, *cols, **kwargs)


def upgrade() -> None:
    _table(
        "clientele_classif_dimensions",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("code", sa.String(40), nullable=False, unique=True),
        sa.Column("libelle", sa.String(120), nullable=False),
        sa.Column("ordre", sa.Integer(), nullable=False, server_default="0"),
    )
    _table(
        "clientele_classif_valeurs",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("dimension", sa.String(40), nullable=False),
        sa.Column("critere", sa.String(40), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("libelle", sa.String(255), nullable=False),
        sa.Column("score_v1", sa.Integer(), nullable=True),
        sa.Column("niveau_v1", sa.String(12), nullable=True),
        sa.Column("score_v4", sa.Integer(), nullable=True),
        sa.Column("niveau_v4", sa.String(12), nullable=True),
        sa.Column("score_retenu", sa.Integer(), nullable=True),
        sa.Column("niveau_retenu", sa.String(12), nullable=True),
        sa.Column("is_blocking", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("version_regles", sa.String(40), nullable=False),
        sa.Column("conflit", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("statut", sa.String(24), nullable=False, server_default="A_ARBITRER"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("actif", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("dimension", "critere", "code", "version_regles",
                            name="uq_clientele_classif_valeurs"),
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_clientele_classif_valeurs_dim "
               "ON clientele_classif_valeurs (dimension, statut)")

    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("clientele_classif_evaluation_lignes"):
        cols = {c["name"] for c in insp.get_columns("clientele_classif_evaluation_lignes")}
        if "famille" not in cols:
            op.execute("ALTER TABLE clientele_classif_evaluation_lignes "
                       "ADD COLUMN famille varchar(40) NOT NULL DEFAULT 'CLIENT'")
        if "contribue_au_score" not in cols:
            op.execute("ALTER TABLE clientele_classif_evaluation_lignes "
                       "ADD COLUMN contribue_au_score boolean NOT NULL DEFAULT false")

    _seed()


def _seed() -> None:
    bind = op.get_bind()
    vr = VERSION_REGLES
    for i, dim in enumerate(DIMENSIONS):
        bind.execute(sa.text("""
            INSERT INTO clientele_classif_dimensions (id, code, libelle, ordre)
            VALUES (gen_random_uuid(), :code, :libelle, :ordre)
            ON CONFLICT (code) DO UPDATE SET libelle = EXCLUDED.libelle, ordre = EXCLUDED.ordre
        """), {"code": dim["code"], "libelle": dim["libelle"], "ordre": i})

    deja = bind.execute(sa.text(
        "SELECT 1 FROM clientele_classif_valeurs WHERE version_regles = :v LIMIT 1"
    ), {"v": vr}).scalar()
    if deja:
        return
    for r in valeurs_maitres():
        bind.execute(sa.text("""
            INSERT INTO clientele_classif_valeurs
                (id, dimension, critere, code, libelle, score_v1, niveau_v1,
                 score_v4, niveau_v4, score_retenu, niveau_retenu, is_blocking,
                 source, version_regles, conflit, statut, note, actif)
            VALUES (gen_random_uuid(), :dimension, :critere, :code, :libelle,
                    :score_v1, :niveau_v1, :score_v4, :niveau_v4, :score_retenu,
                    :niveau_retenu, :is_blocking, :source, :vr, :conflit,
                    :statut, :note, false)
            ON CONFLICT DO NOTHING
        """), {
            "dimension": r["dimension"][:40],
            "critere": r["critere"][:40],
            "code": r["code"][:80],
            "libelle": r["libelle"][:255],
            "score_v1": r["score_v1"],
            "niveau_v1": r["niveau_v1"],
            "score_v4": r["score_v4"],
            "niveau_v4": r["niveau_v4"],
            "score_retenu": r["score_retenu"],
            "niveau_retenu": r["niveau_retenu"],
            "is_blocking": r["is_blocking"],
            "source": r["source"][:80],
            "vr": r["version"][:40],
            "conflit": r["conflit"],
            "statut": r["statut"][:24],
            "note": r.get("note"),
        })


def downgrade() -> None:
    op.drop_table("clientele_classif_valeurs")
    op.drop_table("clientele_classif_dimensions")
