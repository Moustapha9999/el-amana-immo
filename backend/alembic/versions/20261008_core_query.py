"""CORE ADMIN — CORE QUERY (Data Explorer en lecture seule).

Additif : tables ``core_query_logs`` / ``core_query_favorites``, permissions
``core.admin.query.*`` et favoris système. Le rôle PostgreSQL restreint
``bea_core_query_reader`` est créé/synchronisé à l'exécution (voir
``app/services/core_query/executor.py``) ; aucune table métier modifiée.

Revision ID: 20261008_core_query
Revises: 20261008_backup_recovery_v2
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261008_core_query"
down_revision: Union[str, None] = "20261008_backup_recovery_v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_PERMS = [
    ("core.admin.query.view", "CORE QUERY — consultation et analyse (CORE ADMIN)", "core"),
    ("core.admin.query.execute", "CORE QUERY — exécution assistant / builder (CORE ADMIN)", "core"),
    ("core.admin.query.sql", "CORE QUERY — exécution SQL libre (CORE ADMIN)", "core"),
    ("core.admin.query.export", "CORE QUERY — export des résultats (CORE ADMIN)", "core"),
]

_SYSTEM_FAVORITES = [
    ("Utilisateurs connectés aujourd'hui", "utilisateurs connectés aujourd'hui"),
    ("Sessions de plus de 8 heures", "sessions de plus de 8 heures"),
    ("Activité des administrateurs", "activité des administrateurs aujourd'hui"),
    ("Utilisateurs inactifs (30 jours)", "utilisateurs qui ne se sont pas connectés depuis 30 jours"),
    ("Dernières opérations administratives", "dernières opérations administratives"),
    ("Modules les plus utilisés aujourd'hui", "modules les plus utilisés aujourd'hui"),
]

_JSONB = postgresql.JSONB(astext_type=sa.Text())
_UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "core_query_logs",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("user_id", _UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("question", sa.Text(), nullable=True),
        sa.Column("generated_sql", sa.Text(), nullable=True),
        sa.Column("tables_used", _JSONB, nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_code", sa.String(60), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("result_count", sa.Integer(), nullable=True),
        sa.Column("truncated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("execution_time_ms", sa.Integer(), nullable=True),
        sa.Column("export_format", sa.String(10), nullable=True),
        sa.Column("favorite_id", _UUID, nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_core_query_logs_created_at", "core_query_logs", ["created_at"])
    op.create_index("ix_core_query_logs_user_id", "core_query_logs", ["user_id"])
    op.create_index("ix_core_query_logs_status", "core_query_logs", ["status"])

    op.create_table(
        "core_query_favorites",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("user_id", _UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("question", sa.Text(), nullable=True),
        sa.Column("sql_text", sa.Text(), nullable=True),
        sa.Column("builder_spec", _JSONB, nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("run_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_core_query_favorites_user_id", "core_query_favorites", ["user_id"])

    conn = op.get_bind()
    for code, label, module in _NEW_PERMS:
        conn.execute(
            sa.text(
                """
                INSERT INTO permissions (id, code, label, module, created_at, updated_at)
                SELECT gen_random_uuid(), :code, :label, :module, NOW(), NOW()
                WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = :code)
                """
            ),
            {"code": code, "label": label, "module": module},
        )
    for name, question in _SYSTEM_FAVORITES:
        conn.execute(
            sa.text(
                """
                INSERT INTO core_query_favorites (id, user_id, name, source, question, is_system)
                SELECT gen_random_uuid(), NULL, :name, 'assistant', :question, TRUE
                WHERE NOT EXISTS (
                    SELECT 1 FROM core_query_favorites WHERE is_system AND name = :name
                )
                """
            ),
            {"name": name, "question": question},
        )


def downgrade() -> None:
    conn = op.get_bind()
    for code, _, _ in _NEW_PERMS:
        conn.execute(sa.text("DELETE FROM permissions WHERE code = :code"), {"code": code})
    op.drop_index("ix_core_query_favorites_user_id", table_name="core_query_favorites")
    op.drop_table("core_query_favorites")
    op.drop_index("ix_core_query_logs_status", table_name="core_query_logs")
    op.drop_index("ix_core_query_logs_user_id", table_name="core_query_logs")
    op.drop_index("ix_core_query_logs_created_at", table_name="core_query_logs")
    op.drop_table("core_query_logs")
