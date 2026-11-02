"""Stock — historique des clôtures / réouvertures de période (additif).

- ``mg_stock_periodes`` : ``premiere_cloture_at/by`` (clôture initiale), ``nb_reouvertures`` ;
- ``mg_stock_periode_evenements`` : journal des clôtures, réouvertures et refus, jamais purgé.

Reprise : les clôtures / réouvertures déjà tracées dans ``audit_logs`` (entité ``mg_stock_periode``)
alimentent l'historique, y compris les clôtures d'office qu'imposait l'ancienne réouverture
(« verrouillée »). Aucune donnée existante n'est modifiée hormis le remplissage des nouvelles colonnes.

Revision ID: 20261102_mg_stock_periodes_02
Revises: 20261026_auth_01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261102_mg_stock_periodes_02"
down_revision: Union[str, None] = "20261026_auth_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
retour_arriere = "compatible"

_LABEL_NOUVEAU = "Réouverture de période, saisie / correction en période rouverte et suppression administrateur"
_LABEL_ANCIEN = "Réouverture de période et suppression administrateur (périodes clôturées, workflows)"


def _label(depuis: str, vers: str) -> None:
    op.execute(
        sa.text(
            "UPDATE permissions SET label = :vers WHERE code = 'mg.stock.period.reopen' AND label = :depuis"
        ).bindparams(depuis=depuis, vers=vers)
    )


def upgrade() -> None:
    _label(_LABEL_ANCIEN, _LABEL_NOUVEAU)
    op.add_column("mg_stock_periodes", sa.Column("premiere_cloture_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "mg_stock_periodes",
        sa.Column("premiere_cloture_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    op.add_column(
        "mg_stock_periodes",
        sa.Column("nb_reouvertures", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_table(
        "mg_stock_periode_evenements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "periode_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mg_stock_periodes.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("resultat", sa.String(10), nullable=False, server_default="SUCCES"),
        sa.Column("statut_avant", sa.String(20), nullable=True),
        sa.Column("statut_apres", sa.String(20), nullable=True),
        sa.Column("motif", sa.Text(), nullable=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("user_nom", sa.String(255), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("resultat IN ('SUCCES', 'ECHEC')", name="ck_mg_stock_periode_evt_resultat"),
    )
    op.create_index(
        "ix_mg_stock_periode_evenements_periode", "mg_stock_periode_evenements", ["periode_id", "created_at"]
    )
    op.create_index("ix_mg_stock_periode_evenements_action", "mg_stock_periode_evenements", ["action"])
    op.create_index("ix_mg_stock_periode_evenements_user_id", "mg_stock_periode_evenements", ["user_id"])

    # Reprise de l'historique tracé dans l'audit (clôtures, réouvertures, clôtures d'office).
    op.execute(
        sa.text(
            """
            INSERT INTO mg_stock_periode_evenements
                (id, periode_id, action, resultat, statut_avant, statut_apres, motif,
                 user_id, user_nom, details, created_at, updated_at)
            SELECT gen_random_uuid(), p.id,
                   CASE a.action WHEN 'cloture_periode' THEN 'CLOTURE' ELSE 'REOUVERTURE' END,
                   'SUCCES',
                   CASE a.action WHEN 'cloture_periode' THEN 'OUVERTE' ELSE 'CLOTUREE' END,
                   CASE a.action WHEN 'cloture_periode' THEN 'CLOTUREE' ELSE 'OUVERTE' END,
                   a.after_data ->> 'motif',
                   a.user_id, u.full_name,
                   jsonb_build_object('repris_de_audit', a.id::text, 'audit', a.after_data),
                   a.created_at, a.created_at
            FROM audit_logs a
            JOIN mg_stock_periodes p ON p.id::text = a.entity_id
            LEFT JOIN users u ON u.id = a.user_id
            WHERE a.entity = 'mg_stock_periode'
              AND a.action IN ('cloture_periode', 'reouverture_periode')
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO mg_stock_periode_evenements
                (id, periode_id, action, resultat, statut_avant, statut_apres, motif,
                 user_id, user_nom, details, created_at, updated_at)
            SELECT gen_random_uuid(), p.id, 'CLOTURE_OFFICE', 'SUCCES', 'OUVERTE', 'CLOTUREE',
                   'Clôture imposée par la réouverture de ' || (a.after_data ->> 'libelle')
                     || ' (ancienne règle : une seule période ouverte)',
                   a.user_id, u.full_name,
                   jsonb_build_object('repris_de_audit', a.id::text, 'periode_rouverte', a.entity_id,
                                      'audit', a.after_data),
                   a.created_at, a.created_at
            FROM audit_logs a
            JOIN mg_stock_periodes p ON p.id::text = a.after_data -> 'verrouilee' ->> 'id'
            LEFT JOIN users u ON u.id = a.user_id
            WHERE a.entity = 'mg_stock_periode'
              AND a.action = 'reouverture_periode'
              AND jsonb_typeof(a.after_data -> 'verrouilee') = 'object'
            """
        )
    )
    # L'ancienne reclôture rouvrait silencieusement la période clôturée d'office : on la trace.
    op.execute(
        sa.text(
            """
            INSERT INTO mg_stock_periode_evenements
                (id, periode_id, action, resultat, statut_avant, statut_apres, motif,
                 user_id, user_nom, details, created_at, updated_at)
            SELECT gen_random_uuid(), o.periode_id, 'REOUVERTURE_OFFICE', 'SUCCES', 'CLOTUREE', 'OUVERTE',
                   'Réouverture automatique à la reclôture de la période précédente (ancienne règle)',
                   r.user_id, u.full_name,
                   jsonb_build_object('repris_de_audit', r.id::text),
                   COALESCE(r.created_at, o.created_at), COALESCE(r.created_at, o.created_at)
            FROM mg_stock_periode_evenements o
            JOIN mg_stock_periodes p ON p.id = o.periode_id
            LEFT JOIN LATERAL (
                SELECT a.id, a.user_id, a.created_at FROM audit_logs a
                WHERE a.entity = 'mg_stock_periode' AND a.action = 'cloture_periode'
                  AND a.entity_id = o.details ->> 'periode_rouverte'
                  AND a.created_at >= o.created_at
                ORDER BY a.created_at LIMIT 1
            ) r ON TRUE
            LEFT JOIN users u ON u.id = r.user_id
            WHERE o.action = 'CLOTURE_OFFICE' AND (r.id IS NOT NULL OR p.statut <> 'CLOTUREE')
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE mg_stock_periodes p
            SET premiere_cloture_at = COALESCE(e.premiere, p.cloture_at),
                premiere_cloture_by = CASE WHEN e.premiere IS NOT NULL THEN e.premiere_by ELSE p.cloture_by END
            FROM (
                SELECT p2.id,
                       (SELECT min(created_at) FROM mg_stock_periode_evenements x
                         WHERE x.periode_id = p2.id AND x.action IN ('CLOTURE', 'CLOTURE_OFFICE')) AS premiere,
                       (SELECT x.user_id FROM mg_stock_periode_evenements x
                         WHERE x.periode_id = p2.id AND x.action IN ('CLOTURE', 'CLOTURE_OFFICE')
                         ORDER BY x.created_at LIMIT 1) AS premiere_by
                FROM mg_stock_periodes p2
            ) e
            WHERE e.id = p.id AND (p.cloture_at IS NOT NULL OR e.premiere IS NOT NULL)
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE mg_stock_periodes p
            SET nb_reouvertures = n.total
            FROM (SELECT periode_id, count(*) AS total FROM mg_stock_periode_evenements
                  WHERE action IN ('REOUVERTURE', 'REOUVERTURE_OFFICE') GROUP BY periode_id) n
            WHERE n.periode_id = p.id
            """
        )
    )


def downgrade() -> None:
    _label(_LABEL_NOUVEAU, _LABEL_ANCIEN)
    op.execute(sa.text("UPDATE mg_stock_periodes SET statut = 'OUVERTE' WHERE statut = 'ROUVERTE'"))
    op.drop_index("ix_mg_stock_periode_evenements_user_id", table_name="mg_stock_periode_evenements")
    op.drop_index("ix_mg_stock_periode_evenements_action", table_name="mg_stock_periode_evenements")
    op.drop_index("ix_mg_stock_periode_evenements_periode", table_name="mg_stock_periode_evenements")
    op.drop_table("mg_stock_periode_evenements")
    op.drop_column("mg_stock_periodes", "nb_reouvertures")
    op.drop_column("mg_stock_periodes", "premiere_cloture_by")
    op.drop_column("mg_stock_periodes", "premiere_cloture_at")
