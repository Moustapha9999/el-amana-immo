"""Sessions duales BEA DIGITAL (kind=platform) et module (kind=module).

Revision ID: 20260917_dual_auth
Revises: 20260914_orion_lock
"""

from typing import Sequence, Union
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260917_dual_auth"
down_revision: Union[str, None] = "20260914_orion_lock"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ESPACES = [
    {
        "code": "comptabilite",
        "label": "Comptabilité",
        "description": (
            "Immobilisations, amortissements, pièces et contrôles autour d’ORION "
            "— sans remplacer le core banking."
        ),
        "route": "/comptabilite",
        "statut": "actif",
        "sort_order": 1,
    },
    {
        "code": "credit",
        "label": "Crédit",
        "description": "Processus crédit autour d’ORION (dossiers, contrôles, workflows).",
        "route": None,
        "statut": "bientot",
        "sort_order": 2,
    },
    {
        "code": "rh",
        "label": "RH",
        "description": "Processus ressources humaines internes.",
        "route": None,
        "statut": "bientot",
        "sort_order": 3,
    },
    {
        "code": "informatique",
        "label": "Informatique",
        "description": "Demandes, suivi et outils internes DSI.",
        "route": None,
        "statut": "bientot",
        "sort_order": 4,
    },
    {
        "code": "achats",
        "label": "Achats",
        "description": "Demandes d’achat, validations et suivi documentaire.",
        "route": None,
        "statut": "bientot",
        "sort_order": 5,
    },
]

MODULES = [
    {
        "code": "immobilisations",
        "espace_code": "comptabilite",
        "label": "Immobilisations & Amortissements",
        "description": (
            "Parc, dotations, cessions, rebuts, réévaluations, inventaire, écritures, "
            "archives et rapports."
        ),
        "entry_path": "/dashboard",
        "statut": "actif",
        "sort_order": 1,
    },
    {
        "code": "rapprochements",
        "espace_code": "comptabilite",
        "label": "Rapprochements",
        "description": "Rapprochements Excel / ORION et contrôles de cohérence.",
        "entry_path": None,
        "statut": "bientot",
        "sort_order": 2,
    },
    {
        "code": "controles",
        "espace_code": "comptabilite",
        "label": "Contrôles comptables",
        "description": "Contrôles périodiques et anomalies.",
        "entry_path": None,
        "statut": "bientot",
        "sort_order": 3,
    },
    {
        "code": "cloture",
        "espace_code": "comptabilite",
        "label": "Clôture comptable",
        "description": "Préparation et suivi de clôture.",
        "entry_path": None,
        "statut": "bientot",
        "sort_order": 4,
    },
    {
        "code": "reporting-compta",
        "espace_code": "comptabilite",
        "label": "Reporting comptable",
        "description": "Tableaux de bord et exports transverses.",
        "entry_path": None,
        "statut": "bientot",
        "sort_order": 5,
    },
]

PERMISSIONS = [
    ("immobilisations.read", "Consultation immobilisations", "immobilisations"),
    ("immobilisations.create", "Création immobilisations", "immobilisations"),
    ("immobilisations.update", "Modification immobilisations", "immobilisations"),
    ("immobilisations.validate", "Validation immobilisations", "immobilisations"),
    ("immobilisations.delete", "Suppression immobilisations", "immobilisations"),
    ("immobilisations.cession", "Cessions", "immobilisations"),
    ("immobilisations.rebut", "Rebuts", "immobilisations"),
    ("immobilisations.reevaluation", "Réévaluations", "immobilisations"),
    ("immobilisations.amortissement", "Amortissements", "immobilisations"),
    ("immobilisations.reporting", "Reporting immobilisations", "immobilisations"),
    ("immobilisations.admin", "Administration du module", "immobilisations"),
]


def upgrade() -> None:
    op.add_column(
        "auth_sessions",
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="platform"),
    )
    op.add_column("auth_sessions", sa.Column("module_code", sa.String(length=80), nullable=True))
    op.add_column(
        "auth_sessions",
        sa.Column("parent_session_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_auth_sessions_kind", "auth_sessions", ["kind"])
    op.create_index("ix_auth_sessions_module_code", "auth_sessions", ["module_code"])
    op.create_index("ix_auth_sessions_parent_session_id", "auth_sessions", ["parent_session_id"])
    op.create_foreign_key(
        "fk_auth_sessions_parent",
        "auth_sessions",
        "auth_sessions",
        ["parent_session_id"],
        ["id"],
    )

    op.create_table(
        "plateforme_espaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("route", sa.String(length=160), nullable=True),
        sa.Column("statut", sa.String(length=20), nullable=False, server_default="bientot"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_plateforme_espaces_code", "plateforme_espaces", ["code"], unique=True)
    op.create_index("ix_plateforme_espaces_statut", "plateforme_espaces", ["statut"])

    op.create_table(
        "plateforme_modules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("espace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("entry_path", sa.String(length=160), nullable=True),
        sa.Column("statut", sa.String(length=20), nullable=False, server_default="bientot"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["espace_id"], ["plateforme_espaces.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_plateforme_modules_code", "plateforme_modules", ["code"], unique=True)
    op.create_index("ix_plateforme_modules_espace_id", "plateforme_modules", ["espace_id"])
    op.create_index("ix_plateforme_modules_statut", "plateforme_modules", ["statut"])

    op.create_table(
        "user_espace_acces",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("espace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["espace_id"], ["plateforme_espaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "espace_id"),
    )
    op.create_table(
        "user_module_acces",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("module_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["module_id"], ["plateforme_modules.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "module_id"),
    )

    op.create_table(
        "auth_login_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("login_kind", sa.String(length=20), nullable=False),
        sa.Column("module_code", sa.String(length=80), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_auth_login_attempts_email", "auth_login_attempts", ["email"])
    op.create_index("ix_auth_login_attempts_ip_address", "auth_login_attempts", ["ip_address"])
    op.create_index("ix_auth_login_attempts_login_kind", "auth_login_attempts", ["login_kind"])

    bind = op.get_bind()
    espace_ids: dict[str, object] = {}
    for item in ESPACES:
        eid = uuid4()
        espace_ids[item["code"]] = eid
        bind.execute(
            sa.text(
                """
                INSERT INTO plateforme_espaces
                    (id, code, label, description, route, statut, sort_order, is_active)
                VALUES
                    (:id, :code, :label, :description, :route, :statut, :sort_order, true)
                """
            ),
            {
                "id": eid,
                "code": item["code"],
                "label": item["label"],
                "description": item["description"],
                "route": item["route"],
                "statut": item["statut"],
                "sort_order": item["sort_order"],
            },
        )

    module_ids: dict[str, object] = {}
    for item in MODULES:
        mid = uuid4()
        module_ids[item["code"]] = mid
        bind.execute(
            sa.text(
                """
                INSERT INTO plateforme_modules
                    (id, espace_id, code, label, description, entry_path, statut, sort_order, is_active)
                VALUES
                    (:id, :espace_id, :code, :label, :description, :entry_path, :statut, :sort_order, true)
                """
            ),
            {
                "id": mid,
                "espace_id": espace_ids[item["espace_code"]],
                "code": item["code"],
                "label": item["label"],
                "description": item["description"],
                "entry_path": item["entry_path"],
                "statut": item["statut"],
                "sort_order": item["sort_order"],
            },
        )

    compta_id = espace_ids["comptabilite"]
    immo_id = module_ids["immobilisations"]
    bind.execute(
        sa.text(
            """
            INSERT INTO user_espace_acces (user_id, espace_id)
            SELECT u.id, :espace_id FROM users u
            WHERE u.deleted_at IS NULL
            ON CONFLICT DO NOTHING
            """
        ),
        {"espace_id": compta_id},
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO user_module_acces (user_id, module_id)
            SELECT u.id, :module_id FROM users u
            WHERE u.deleted_at IS NULL
            ON CONFLICT DO NOTHING
            """
        ),
        {"module_id": immo_id},
    )

    for code, label, module in PERMISSIONS:
        bind.execute(
            sa.text(
                """
                INSERT INTO permissions (id, code, label, module, created_at, updated_at)
                SELECT :id, :code, :label, :module, now(), now()
                WHERE NOT EXISTS (SELECT 1 FROM permissions p WHERE p.code = :code)
                """
            ),
            {"id": uuid4(), "code": code, "label": label, "module": module},
        )


def downgrade() -> None:
    op.drop_index("ix_auth_login_attempts_login_kind", table_name="auth_login_attempts")
    op.drop_index("ix_auth_login_attempts_ip_address", table_name="auth_login_attempts")
    op.drop_index("ix_auth_login_attempts_email", table_name="auth_login_attempts")
    op.drop_table("auth_login_attempts")
    op.drop_table("user_module_acces")
    op.drop_table("user_espace_acces")
    op.drop_index("ix_plateforme_modules_statut", table_name="plateforme_modules")
    op.drop_index("ix_plateforme_modules_espace_id", table_name="plateforme_modules")
    op.drop_index("ix_plateforme_modules_code", table_name="plateforme_modules")
    op.drop_table("plateforme_modules")
    op.drop_index("ix_plateforme_espaces_statut", table_name="plateforme_espaces")
    op.drop_index("ix_plateforme_espaces_code", table_name="plateforme_espaces")
    op.drop_table("plateforme_espaces")
    op.drop_constraint("fk_auth_sessions_parent", "auth_sessions", type_="foreignkey")
    op.drop_index("ix_auth_sessions_parent_session_id", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_module_code", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_kind", table_name="auth_sessions")
    op.drop_column("auth_sessions", "parent_session_id")
    op.drop_column("auth_sessions", "module_code")
    op.drop_column("auth_sessions", "kind")
