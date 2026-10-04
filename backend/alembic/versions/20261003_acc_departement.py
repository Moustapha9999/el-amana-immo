"""Département Audit, Contrôle & Conformité : domaines, icônes, module EER.

Schéma (additif) :
- ``plateforme_espaces.icon`` / ``plateforme_modules.icon`` (glyphe Material Icons) ;
- ``plateforme_domaines`` (domaine → sous-domaine via ``parent_id``, 2 niveaux) ;
- ``plateforme_modules.domaine_id`` (nullable, ON DELETE SET NULL).

Données (insérées seulement si absentes, jamais réécrites) : département
``audit-controle-conformite``, ses 5 domaines + sous-domaine KYC, module ``eer``
(statut ``developpement``). CORE ADMIN reste ensuite seul maître du statut,
de l'ordre, des icônes et des descriptions.

Revision ID: 20261003_acc_departement
Revises: 20261003_mg_inv_rapprochement
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "20261003_acc_departement"
down_revision: Union[str, None] = "20261003_mg_inv_rapprochement"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ESPACE_CODE = "audit-controle-conformite"
MODULE_CODE = "eer"

# (code, parent_code, label, description, icon, statut, sort_order)
DOMAINES = [
    ("audit-interne", None, "Audit interne",
     "Missions d'audit, recommandations et suivi des plans d'action.",
     "manage_search", "bientot", 1),
    ("controle-permanent", None, "Contrôle permanent & périmètre opérationnel",
     "Plans de contrôle de niveau 1 et 2, anomalies et périmètre opérationnel.",
     "fact_check", "bientot", 2),
    ("conformite-securite-financiere", None, "Conformité & sécurité financière",
     "KYC, LBC-FT, PPE, FATCA et conformité réglementaire.",
     "shield", "actif", 3),
    ("kyc", "conformite-securite-financiere", "KYC",
     "Connaissance client : entrées en relation, vérifications et pièces.",
     "badge", "actif", 1),
    ("organisation-processus", None, "Organisation & Processus",
     "Cartographie des processus, procédures et notes d'organisation.",
     "account_tree", "bientot", 4),
    ("management-qualite", None, "Management & Qualité",
     "Démarche qualité, indicateurs et amélioration continue.",
     "workspace_premium", "bientot", 5),
]


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "icon" not in _columns("plateforme_espaces"):
        op.add_column("plateforme_espaces", sa.Column("icon", sa.String(60), nullable=True))
    if "icon" not in _columns("plateforme_modules"):
        op.add_column("plateforme_modules", sa.Column("icon", sa.String(60), nullable=True))

    if not inspector.has_table("plateforme_domaines"):
        op.create_table(
            "plateforme_domaines",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "espace_id",
                UUID(as_uuid=True),
                sa.ForeignKey("plateforme_espaces.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "parent_id",
                UUID(as_uuid=True),
                sa.ForeignKey("plateforme_domaines.id", ondelete="RESTRICT"),
                nullable=True,
            ),
            sa.Column("code", sa.String(80), nullable=False),
            sa.Column("label", sa.String(160), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("icon", sa.String(60), nullable=True),
            sa.Column("statut", sa.String(20), nullable=False, server_default="bientot"),
            sa.Column("status_message", sa.Text(), nullable=False, server_default=""),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint(
                "statut IN ('actif','bientot','developpement','inactif')",
                name="ck_plateforme_domaines_statut",
            ),
            sa.CheckConstraint("parent_id IS NULL OR parent_id <> id", name="ck_plateforme_domaines_parent"),
        )
        op.create_index("ix_plateforme_domaines_code", "plateforme_domaines", ["code"], unique=True)
        op.create_index("ix_plateforme_domaines_espace_id", "plateforme_domaines", ["espace_id"])
        op.create_index("ix_plateforme_domaines_parent_id", "plateforme_domaines", ["parent_id"])
        op.create_index("ix_plateforme_domaines_statut", "plateforme_domaines", ["statut"])

    if "domaine_id" not in _columns("plateforme_modules"):
        op.add_column(
            "plateforme_modules",
            sa.Column(
                "domaine_id",
                UUID(as_uuid=True),
                sa.ForeignKey(
                    "plateforme_domaines.id",
                    ondelete="SET NULL",
                    name="fk_plateforme_modules_domaine_id",
                ),
                nullable=True,
            ),
        )
        op.create_index("ix_plateforme_modules_domaine_id", "plateforme_modules", ["domaine_id"])

    # --- Données : insérées si absentes, jamais réécrites (CORE ADMIN = source de vérité) ---
    bind.execute(
        sa.text(
            """
            INSERT INTO plateforme_espaces
                (id, code, label, description, route, statut, sort_order, is_active, icon)
            VALUES
                (gen_random_uuid(), :code, :label, :description, :route, 'actif', 8, true, 'verified_user')
            ON CONFLICT (code) DO NOTHING
            """
        ),
        {
            "code": ESPACE_CODE,
            "label": "Audit, Contrôle & Conformité",
            "description": (
                "Audit interne, contrôle permanent, conformité & sécurité financière (KYC), "
                "organisation & processus, management & qualité."
            ),
            "route": f"/{ESPACE_CODE}",
        },
    )
    for code, parent_code, label, description, icon, statut, sort_order in DOMAINES:
        bind.execute(
            sa.text(
                """
                INSERT INTO plateforme_domaines
                    (id, espace_id, parent_id, code, label, description, icon, statut,
                     sort_order, is_active)
                SELECT gen_random_uuid(), e.id,
                       (SELECT d.id FROM plateforme_domaines d WHERE d.code = :parent_code),
                       :code, :label, :description, :icon, :statut, :sort_order, true
                FROM plateforme_espaces e
                WHERE e.code = :espace_code
                ON CONFLICT (code) DO NOTHING
                """
            ),
            {
                "espace_code": ESPACE_CODE,
                "parent_code": parent_code,
                "code": code,
                "label": label,
                "description": description,
                "icon": icon,
                "statut": statut,
                "sort_order": sort_order,
            },
        )
    bind.execute(
        sa.text(
            """
            INSERT INTO plateforme_modules
                (id, espace_id, domaine_id, code, label, description, entry_path, statut,
                 status_message, sort_order, is_active, icon)
            SELECT gen_random_uuid(), e.id,
                   (SELECT d.id FROM plateforme_domaines d WHERE d.code = 'kyc'),
                   :code, :label, :description, '/eer/dashboard', 'developpement',
                   :status_message, 1, true, 'person_add'
            FROM plateforme_espaces e
            WHERE e.code = :espace_code
            ON CONFLICT (code) DO NOTHING
            """
        ),
        {
            "espace_code": ESPACE_CODE,
            "code": MODULE_CODE,
            "label": "Gestion des Entrées en Relation",
            "description": (
                "Dossiers EER reçus par e-mail : checklist KYC dynamique, contrôles, "
                "non-conformités, compléments sur le même dossier, validation et archivage."
            ),
            "status_message": (
                "Module en cours de construction — ouverture après livraison du dossier EER."
            ),
        },
    )


def downgrade() -> None:
    bind = op.get_bind()
    # Retire uniquement ce que cette révision a introduit (module EER, domaines, département
    # s'il ne porte plus aucun module). Permissions / rôles eer.* restent (seed applicatif).
    bind.execute(sa.text("DELETE FROM plateforme_modules WHERE code = :c"), {"c": MODULE_CODE})
    op.drop_index("ix_plateforme_modules_domaine_id", table_name="plateforme_modules")
    op.drop_constraint("fk_plateforme_modules_domaine_id", "plateforme_modules", type_="foreignkey")
    op.drop_column("plateforme_modules", "domaine_id")
    op.drop_table("plateforme_domaines")
    bind.execute(
        sa.text(
            """
            DELETE FROM plateforme_espaces e
            WHERE e.code = :c
              AND NOT EXISTS (SELECT 1 FROM plateforme_modules m WHERE m.espace_id = e.id)
            """
        ),
        {"c": ESPACE_CODE},
    )
    op.drop_column("plateforme_modules", "icon")
    op.drop_column("plateforme_espaces", "icon")
