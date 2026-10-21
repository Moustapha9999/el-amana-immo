"""Studio d'intégration API — destinations TEST, exécutions et alertes (Phases 5 et 6). Additif.

- ``integration_destinations`` : hôtes HTTPS TEST approuvés (jamais une URL saisie à l'exécution).
- ``integration_executions`` : résultats de tests explicites (sans secret ni corps complet).
- ``integration_alertes`` : alertes de supervision dédupliquées.

``downgrade`` supprime les trois tables. Aucun secret n'est stocké.

Revision ID: 20261021_integrations_03
Revises: 20261021_integrations_02
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261021_integrations_03"
down_revision: Union[str, None] = "20261021_integrations_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
retour_arriere = "compatible"

_UUID = postgresql.UUID(as_uuid=True)
_JSONB = postgresql.JSONB()


def _hn() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "integration_destinations",
        sa.Column("id", _UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("nom", sa.String(120), nullable=False),
        sa.Column("nom_normalise", sa.String(120), nullable=False),
        sa.Column("fournisseur_id", _UUID, sa.ForeignKey("integration_fournisseurs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("environnement", sa.String(10), nullable=False, server_default="TEST"),
        sa.Column("protocole", sa.String(10), nullable=False, server_default="https"),
        sa.Column("hotes", _JSONB, nullable=False, server_default="[]"),
        sa.Column("ports", _JSONB, nullable=False, server_default="[443]"),
        sa.Column("methodes", _JSONB, nullable=False, server_default='["GET","HEAD"]'),
        sa.Column("operations", _JSONB, nullable=False, server_default="[]"),
        sa.Column("statut", sa.String(20), nullable=False, server_default="brouillon"),
        sa.Column("motif_statut", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by_id", _UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by_id", _UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("valide_par_id", _UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("valide_le", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_by_id", _UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("motif_archivage", sa.Text(), nullable=True),
        *_hn(),
        sa.CheckConstraint("statut IN ('brouillon','a_valider','active','suspendue','archivee')", name="ck_integration_destinations_statut"),
        sa.CheckConstraint("environnement = 'TEST'", name="ck_integration_destinations_environnement"),
        sa.CheckConstraint("protocole = 'https'", name="ck_integration_destinations_protocole"),
        sa.UniqueConstraint("code", name="uq_integration_destinations_code"),
    )
    op.create_index("ix_integration_destinations_fournisseur_id", "integration_destinations", ["fournisseur_id"])
    op.create_index("ix_integration_destinations_statut", "integration_destinations", ["statut"])
    op.execute(
        "CREATE UNIQUE INDEX uq_integration_destinations_nom_fourn "
        "ON integration_destinations (nom_normalise, fournisseur_id) WHERE statut <> 'archivee'"
    )

    op.create_table(
        "integration_executions",
        sa.Column("id", _UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("fournisseur_id", _UUID, sa.ForeignKey("integration_fournisseurs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("operation_id", _UUID, sa.ForeignKey("integration_fournisseur_operations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("destination_id", _UUID, sa.ForeignKey("integration_destinations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("environnement", sa.String(10), nullable=False, server_default="TEST"),
        sa.Column("methode", sa.String(10), nullable=False),
        sa.Column("chemin", sa.String(400), nullable=False),
        sa.Column("hote", sa.String(253), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("duree_ms", sa.Integer(), nullable=True),
        sa.Column("statut", sa.String(30), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("erreur_categorie", sa.String(40), nullable=True),
        sa.Column("correlation_id", sa.String(40), nullable=False),
        sa.Column("user_id", _UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("controles", _JSONB, nullable=False, server_default="{}"),
        sa.Column("limites", _JSONB, nullable=False, server_default="{}"),
        sa.Column("reponse_resume", _JSONB, nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "statut IN ('succes','http_erreur','refuse_securite','timeout','trop_volumineux',"
            "'dns','tls','redirection_refusee','reponse_invalide','secret_requis','quota')",
            name="ck_integration_executions_statut",
        ),
    )
    op.create_index("ix_integration_executions_fourn_debut", "integration_executions", ["fournisseur_id", "started_at"])
    op.create_index("ix_integration_executions_dest_debut", "integration_executions", ["destination_id", "started_at"])
    op.create_index("ix_integration_executions_correlation_id", "integration_executions", ["correlation_id"])
    op.create_index("ix_integration_executions_statut", "integration_executions", ["statut"])

    op.create_table(
        "integration_alertes",
        sa.Column("id", _UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("type", sa.String(40), nullable=False),
        sa.Column("statut", sa.String(20), nullable=False, server_default="nouvelle"),
        sa.Column("cle_dedup", sa.String(200), nullable=False),
        sa.Column("fournisseur_id", _UUID, sa.ForeignKey("integration_fournisseurs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("destination_id", _UUID, sa.ForeignKey("integration_destinations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("operation_id", _UUID, sa.ForeignKey("integration_fournisseur_operations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("message", sa.String(500), nullable=False),
        sa.Column("details", _JSONB, nullable=False, server_default="{}"),
        sa.Column("occurences", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("derniere_le", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resolue_par_id", _UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolue_le", sa.DateTime(timezone=True), nullable=True),
        *_hn(),
        sa.CheckConstraint(
            "statut IN ('nouvelle','en_cours','resolue','ignoree')", name="ck_integration_alertes_statut"
        ),
        sa.CheckConstraint(
            "type IN ('echecs_consecutifs','taux_erreur','latence','non_testee','destination_suspendue','refus_securite')",
            name="ck_integration_alertes_type",
        ),
    )
    op.create_index("ix_integration_alertes_type", "integration_alertes", ["type"])
    op.create_index("ix_integration_alertes_statut", "integration_alertes", ["statut"])
    op.create_index("ix_integration_alertes_fournisseur_id", "integration_alertes", ["fournisseur_id"])
    op.execute(
        "CREATE UNIQUE INDEX uq_integration_alertes_ouverte "
        "ON integration_alertes (type, cle_dedup) WHERE statut IN ('nouvelle', 'en_cours')"
    )


def downgrade() -> None:
    op.drop_table("integration_alertes")
    op.drop_table("integration_executions")
    op.drop_table("integration_destinations")
