"""Studio d'intégration API — applications clientes et demandes de droits (Phase 2). Additif.

- ``integration_clients`` : fiches de configuration (identité stable ``code``, environnement DEV/TEST,
  service responsable rattaché à l'organigramme, statut contrôlé, archivage sans suppression).
- ``integration_client_grants`` : opérations du catalogue demandées par une application, puis décidées
  explicitement (approuvée / refusée / révoquée). Une ligne par application et opération.
- ``integration_client_grant_events`` : historique immuable des changements de statut.

Aucune donnée d'authentification (ni clé, ni secret, ni client ID) : aucune application ne peut
s'authentifier à ce stade. ``downgrade`` supprime les trois tables.

Revision ID: 20261021_integrations_01
Revises: 20261020_clientele_14
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261021_integrations_01"
down_revision: Union[str, None] = "20261020_clientele_14"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
retour_arriere = "compatible"

_UUID = postgresql.UUID(as_uuid=True)


def _user_fk(nom: str) -> sa.Column:
    return sa.Column(nom, _UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


def upgrade() -> None:
    op.create_table(
        "integration_clients",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("nom", sa.String(120), nullable=False),
        sa.Column("nom_normalise", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("org_entite_id", _UUID, sa.ForeignKey("departements.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("contact_technique", sa.String(160), nullable=True),
        sa.Column("environnement", sa.String(10), nullable=False),
        sa.Column("finalite", sa.Text(), nullable=True),
        sa.Column("statut", sa.String(20), nullable=False, server_default="brouillon"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        _user_fk("created_by_id"),
        _user_fk("updated_by_id"),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        _user_fk("archived_by_id"),
        sa.Column("motif_archivage", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("code", name="uq_integration_clients_code"),
        sa.CheckConstraint(
            "statut IN ('brouillon', 'en_preparation', 'active', 'suspendue', 'archivee')",
            name="ck_integration_clients_statut",
        ),
        sa.CheckConstraint("environnement IN ('DEV', 'TEST')", name="ck_integration_clients_environnement"),
    )
    op.create_index(
        "uq_integration_clients_nom_env",
        "integration_clients",
        ["nom_normalise", "environnement"],
        unique=True,
        postgresql_where=sa.text("statut <> 'archivee'"),
    )
    op.create_index("ix_integration_clients_statut", "integration_clients", ["statut"])
    op.create_index("ix_integration_clients_environnement", "integration_clients", ["environnement"])
    op.create_index("ix_integration_clients_org_entite_id", "integration_clients", ["org_entite_id"])

    op.create_table(
        "integration_client_grants",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("client_id", _UUID, sa.ForeignKey("integration_clients.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("operation_id", sa.String(160), nullable=False),
        sa.Column("methode", sa.String(10), nullable=False),
        sa.Column("chemin", sa.String(300), nullable=False),
        sa.Column("permissions", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("exigence_permissions", sa.Text(), nullable=True),
        sa.Column("statut", sa.String(20), nullable=False, server_default="demandee"),
        sa.Column("justification", sa.Text(), nullable=True),
        _user_fk("demande_par_id"),
        _user_fk("decide_par_id"),
        sa.Column("decide_le", sa.DateTime(timezone=True), nullable=True),
        sa.Column("motif", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("client_id", "operation_id", name="uq_integration_client_grants_operation"),
        sa.CheckConstraint(
            "statut IN ('demandee', 'en_attente', 'approuvee', 'refusee', 'revoquee', 'retiree')",
            name="ck_integration_client_grants_statut",
        ),
    )
    op.create_index("ix_integration_client_grants_client_id", "integration_client_grants", ["client_id"])
    op.create_index("ix_integration_client_grants_statut", "integration_client_grants", ["statut"])

    op.create_table(
        "integration_client_grant_events",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column(
            "grant_id", _UUID, sa.ForeignKey("integration_client_grants.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("client_id", _UUID, sa.ForeignKey("integration_clients.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("operation_id", sa.String(160), nullable=False),
        sa.Column("ancien_statut", sa.String(20), nullable=True),
        sa.Column("nouveau_statut", sa.String(20), nullable=False),
        sa.Column("motif", sa.Text(), nullable=True),
        _user_fk("acteur_id"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_integration_client_grant_events_grant_id", "integration_client_grant_events", ["grant_id"])
    op.create_index("ix_integration_client_grant_events_client_id", "integration_client_grant_events", ["client_id"])
    op.create_index(
        "ix_integration_client_grant_events_created_at", "integration_client_grant_events", ["created_at"]
    )


def downgrade() -> None:
    op.drop_table("integration_client_grant_events")
    op.drop_table("integration_client_grants")
    op.drop_index("uq_integration_clients_nom_env", table_name="integration_clients")
    op.drop_table("integration_clients")
