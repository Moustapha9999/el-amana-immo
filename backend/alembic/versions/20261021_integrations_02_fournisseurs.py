"""Studio d'intégration API — fournisseurs d'API externes et import OpenAPI (Phase 4). Additif.

- ``integration_fournisseurs`` : fiches fournisseurs (identité ``code``, environnement DEV/TEST, URL de
  base déclarée — métadonnée jamais appelée —, statut contrôlé, archivage sans suppression).
- ``integration_fournisseur_specs`` : versions importées d'une spécification OpenAPI (fichier fourni par
  un utilisateur), avec provenance et empreinte SHA-256 ; jamais modifiées après import.
- ``integration_fournisseur_operations`` : opérations issues d'une version, ou déclarées manuellement.

Aucune donnée d'authentification, aucun secret. L'historique des fiches passe par ``audit_logs``.
``downgrade`` supprime les trois tables.

Revision ID: 20261021_integrations_02
Revises: 20261021_integrations_01
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261021_integrations_02"
down_revision: Union[str, None] = "20261021_integrations_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
retour_arriere = "compatible"

_UUID = postgresql.UUID(as_uuid=True)
_JSONB = postgresql.JSONB()


def _user_fk(nom: str) -> sa.Column:
    return sa.Column(nom, _UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


def _horodatage() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "integration_fournisseurs",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("nom", sa.String(120), nullable=False),
        sa.Column("nom_normalise", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("org_entite_id", _UUID, sa.ForeignKey("departements.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("responsable_interne", sa.String(160), nullable=True),
        sa.Column("contact_technique", sa.String(160), nullable=True),
        sa.Column("environnement", sa.String(10), nullable=False),
        sa.Column("url_base", sa.String(300), nullable=True),
        sa.Column("documentation", sa.Text(), nullable=True),
        sa.Column("statut", sa.String(20), nullable=False, server_default="brouillon"),
        sa.Column("motif_statut", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        _user_fk("created_by_id"),
        _user_fk("updated_by_id"),
        _user_fk("valide_par_id"),
        sa.Column("valide_le", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        _user_fk("archived_by_id"),
        sa.Column("motif_archivage", sa.Text(), nullable=True),
        *_horodatage(),
        sa.UniqueConstraint("code", name="uq_integration_fournisseurs_code"),
        sa.CheckConstraint(
            "statut IN ('brouillon', 'a_valider', 'valide', 'suspendu', 'archive')",
            name="ck_integration_fournisseurs_statut",
        ),
        sa.CheckConstraint("environnement IN ('DEV', 'TEST')", name="ck_integration_fournisseurs_environnement"),
    )
    op.create_index(
        "uq_integration_fournisseurs_nom_env",
        "integration_fournisseurs",
        ["nom_normalise", "environnement"],
        unique=True,
        postgresql_where=sa.text("statut <> 'archive'"),
    )
    op.create_index("ix_integration_fournisseurs_statut", "integration_fournisseurs", ["statut"])
    op.create_index("ix_integration_fournisseurs_environnement", "integration_fournisseurs", ["environnement"])
    op.create_index("ix_integration_fournisseurs_org_entite_id", "integration_fournisseurs", ["org_entite_id"])

    op.create_table(
        "integration_fournisseur_specs",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column(
            "fournisseur_id", _UUID, sa.ForeignKey("integration_fournisseurs.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("format", sa.String(10), nullable=False),
        sa.Column("nom_fichier", sa.String(255), nullable=False),
        sa.Column("taille", sa.Integer(), nullable=False),
        sa.Column("empreinte", sa.String(64), nullable=False),
        sa.Column("openapi_version", sa.String(20), nullable=False),
        sa.Column("titre", sa.String(300), nullable=False),
        sa.Column("version_api", sa.String(100), nullable=False),
        sa.Column("document", _JSONB, nullable=False),
        sa.Column("resume", _JSONB, nullable=False, server_default="{}"),
        sa.Column("avertissements", _JSONB, nullable=False, server_default="[]"),
        _user_fk("importe_par_id"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("fournisseur_id", "numero", name="uq_integration_fournisseur_specs_numero"),
        sa.UniqueConstraint("fournisseur_id", "empreinte", name="uq_integration_fournisseur_specs_empreinte"),
        sa.CheckConstraint("format IN ('json', 'yaml')", name="ck_integration_fournisseur_specs_format"),
    )
    op.create_index(
        "ix_integration_fournisseur_specs_fournisseur_id", "integration_fournisseur_specs", ["fournisseur_id"]
    )
    op.create_index("ix_integration_fournisseur_specs_created_at", "integration_fournisseur_specs", ["created_at"])

    op.create_table(
        "integration_fournisseur_operations",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column(
            "fournisseur_id", _UUID, sa.ForeignKey("integration_fournisseurs.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "spec_id", _UUID, sa.ForeignKey("integration_fournisseur_specs.id", ondelete="RESTRICT"), nullable=True
        ),
        sa.Column("origine", sa.String(10), nullable=False),
        sa.Column("statut", sa.String(10), nullable=False, server_default="active"),
        sa.Column("methode", sa.String(10), nullable=False),
        sa.Column("chemin", sa.String(300), nullable=False),
        sa.Column("operation_id", sa.String(160), nullable=True),
        sa.Column("nom", sa.String(300), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tags", _JSONB, nullable=False, server_default="[]"),
        sa.Column("deprecie", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("parametres", _JSONB, nullable=False, server_default="[]"),
        sa.Column("entetes", _JSONB, nullable=False, server_default="[]"),
        sa.Column("corps", _JSONB, nullable=True),
        sa.Column("reponses", _JSONB, nullable=False, server_default="[]"),
        sa.Column("authentification", _JSONB, nullable=False, server_default="[]"),
        sa.Column("configuration", _JSONB, nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("empreinte", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        _user_fk("created_by_id"),
        _user_fk("updated_by_id"),
        *_horodatage(),
        sa.UniqueConstraint("spec_id", "methode", "chemin", name="uq_integration_fournisseur_operations_spec"),
        sa.CheckConstraint("origine IN ('openapi', 'manuelle')", name="ck_integration_fournisseur_operations_origine"),
        sa.CheckConstraint("statut IN ('active', 'archivee')", name="ck_integration_fournisseur_operations_statut"),
        sa.CheckConstraint(
            "(origine = 'openapi') = (spec_id IS NOT NULL)", name="ck_integration_fournisseur_operations_spec"
        ),
    )
    op.create_index(
        "uq_integration_fournisseur_operations_manuelle",
        "integration_fournisseur_operations",
        ["fournisseur_id", "methode", "chemin"],
        unique=True,
        postgresql_where=sa.text("origine = 'manuelle' AND statut = 'active'"),
    )
    op.create_index(
        "ix_integration_fournisseur_operations_fournisseur_id",
        "integration_fournisseur_operations",
        ["fournisseur_id"],
    )
    op.create_index(
        "ix_integration_fournisseur_operations_spec_id", "integration_fournisseur_operations", ["spec_id"]
    )


def downgrade() -> None:
    op.drop_table("integration_fournisseur_operations")
    op.drop_table("integration_fournisseur_specs")
    op.drop_index("uq_integration_fournisseurs_nom_env", table_name="integration_fournisseurs")
    op.drop_table("integration_fournisseurs")
