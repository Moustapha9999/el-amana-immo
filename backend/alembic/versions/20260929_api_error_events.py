"""Supervision CORE ADMIN — journal des erreurs API (request_id).

Revision ID: 20260929_api_error_events
Revises: 20260929_audit_request_id
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260929_api_error_events"
down_revision: Union[str, None] = "20260929_audit_request_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS api_error_events (
            id uuid PRIMARY KEY,
            created_at timestamptz NOT NULL DEFAULT now(),
            request_id varchar(64),
            method varchar(10) NOT NULL,
            route varchar(255) NOT NULL,
            status_code integer NOT NULL,
            code varchar(60),
            message varchar(500),
            exception_type varchar(120),
            user_id uuid REFERENCES users (id) ON DELETE SET NULL,
            module_code varchar(80),
            ip_address varchar(45),
            duration_ms double precision
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_api_error_events_created_at ON api_error_events (created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_api_error_events_request_id ON api_error_events (request_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_api_error_events_status ON api_error_events (status_code)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_api_error_events_code ON api_error_events (code)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS api_error_events")
