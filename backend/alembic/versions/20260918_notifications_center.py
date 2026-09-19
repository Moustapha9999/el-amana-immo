"""Centre global notifications : catégorie, priorité, destinataire, archive.

Revision ID: 20260918_notif_center
Revises: 20260918_core_admin_ops
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260918_notif_center"
down_revision: Union[str, None] = "20260918_core_admin_ops"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "notifications",
        sa.Column("categorie", sa.String(length=40), nullable=False, server_default="systeme"),
    )
    op.add_column(
        "notifications",
        sa.Column("priorite", sa.String(length=20), nullable=False, server_default="info"),
    )
    op.add_column(
        "notifications",
        sa.Column("event_type", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "notifications",
        sa.Column("event_code", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "notifications",
        sa.Column("emetteur_type", sa.String(length=40), nullable=False, server_default="systeme"),
    )
    op.add_column(
        "notifications",
        sa.Column("emetteur_label", sa.String(length=255), nullable=False, server_default="Systeme"),
    )
    op.add_column(
        "notifications",
        sa.Column("destinataire_type", sa.String(length=40), nullable=False, server_default="utilisateur"),
    )
    op.add_column(
        "notifications",
        sa.Column("destinataire_label", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "notifications",
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "notifications",
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index("ix_notifications_categorie", "notifications", ["categorie"])
    op.create_index("ix_notifications_priorite", "notifications", ["priorite"])
    op.create_index("ix_notifications_archived", "notifications", ["archived"])
    op.create_index("ix_notifications_event_code", "notifications", ["event_code"])
    op.create_foreign_key(
        "fk_notifications_actor_user_id",
        "notifications",
        "users",
        ["actor_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Backfill catégorie / priorité / codes depuis l’existant
    # (enum PG stocké en NOM : SYSTEME, MAINTENANCE, …)
    op.execute(
        """
        UPDATE notifications SET
          categorie = CASE
            WHEN type_notification::text = 'FIN_AMORTISSEMENT' THEN 'amortissements'
            WHEN type_notification::text IN ('INVENTAIRE', 'ASSURANCE') THEN 'immobilisations'
            WHEN type_notification::text = 'MAINTENANCE' THEN 'maintenance'
            ELSE 'systeme'
          END,
          priorite = CASE
            WHEN lower(titre || ' ' || coalesce(message, '')) LIKE '%echou%'
              OR lower(titre || ' ' || coalesce(message, '')) LIKE '%erreur%'
              OR lower(titre || ' ' || coalesce(message, '')) LIKE '%critique%'
              OR lower(titre || ' ' || coalesce(message, '')) LIKE '%indisponible%'
              OR lower(titre || ' ' || coalesce(message, '')) LIKE '%failed%'
              THEN 'avertissement'
            ELSE 'info'
          END,
          event_type = lower(type_notification::text),
          event_code = 'EVT-' || to_char(created_at, 'YYYY') || '-' || upper(substr(replace(id::text, '-', ''), 1, 8)),
          emetteur_type = 'systeme',
          emetteur_label = 'Syst' || chr(232) || 'me',
          destinataire_type = 'utilisateur'
        WHERE true
        """
    )
    op.execute(
        """
        UPDATE notifications n
        SET destinataire_label = coalesce(nullif(u.full_name, ''), u.email)
        FROM users u
        WHERE u.id = n.user_id AND (n.destinataire_label IS NULL OR n.destinataire_label = '')
        """
    )
    # Purge des notifications de test évidentes
    op.execute(
        """
        DELETE FROM notifications
        WHERE lower(trim(titre)) IN ('test', 'teste', 'testing', 'tests')
           OR lower(trim(message)) IN ('test', 'teste', 'testing', 'tests')
           OR lower(trim(titre)) LIKE 'test %'
           OR lower(titre || ' ' || coalesce(message, '')) LIKE '%rabia%'
           OR lower(titre || ' ' || coalesce(message, '')) LIKE '%love%me%'
        """
    )


def downgrade() -> None:
    op.drop_constraint("fk_notifications_actor_user_id", "notifications", type_="foreignkey")
    op.drop_index("ix_notifications_event_code", table_name="notifications")
    op.drop_index("ix_notifications_archived", table_name="notifications")
    op.drop_index("ix_notifications_priorite", table_name="notifications")
    op.drop_index("ix_notifications_categorie", table_name="notifications")
    for col in (
        "archived",
        "actor_user_id",
        "destinataire_label",
        "destinataire_type",
        "emetteur_label",
        "emetteur_type",
        "event_code",
        "event_type",
        "priorite",
        "categorie",
    ):
        op.drop_column("notifications", col)
