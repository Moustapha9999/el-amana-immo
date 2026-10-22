"""Notifications — espace de destination (``portee``) : module, CORE ADMIN ou plateforme. Additif.

``notifications.portee`` (défaut ``module``) cloisonne les notifications : un module ne lit que
``portee = 'module'`` de son ``module_code`` et de son département (``espace_code``).

Rattachement des notifications existantes, uniquement à partir d'une origine certaine :
- ``core_admin`` : statut de module (``plateforme_module``), restauration (``platform_restore``),
  supervision (``api_error_events``) et tout ``module_code = 'core'`` — émis par CORE ADMIN ;
- ``entity = 'immobilisation'`` sans département ni module (créées avant l'ajout de ces colonnes) :
  l'entité n'existe que dans le module Immobilisations (``comptabilite`` / ``immobilisations``).
Les autres lignes gardent leur rattachement ; aucune n'est supprimée ni réattribuée au hasard.
Une notification sans module d'origine passe en ``plateforme`` : hors des espaces modules,
visible seulement en Login 1.

``downgrade`` supprime la colonne ; le rattachement Immobilisations, exact, est conservé.

Revision ID: 20261022_notifications_01
Revises: 20261021_integrations_03
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261022_notifications_01"
down_revision: Union[str, None] = "20261021_integrations_03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
retour_arriere = "compatible"


def upgrade() -> None:
    op.add_column(
        "notifications",
        sa.Column("portee", sa.String(20), nullable=False, server_default="module"),
    )
    op.create_check_constraint(
        "ck_notifications_portee", "notifications", "portee IN ('module', 'core_admin', 'plateforme')"
    )
    op.execute(
        "UPDATE notifications SET portee = 'core_admin' "
        "WHERE entity IN ('plateforme_module', 'platform_restore', 'api_error_events') "
        "OR module_code = 'core'"
    )
    op.execute(
        "UPDATE notifications SET espace_code = 'comptabilite', module_code = 'immobilisations' "
        "WHERE entity = 'immobilisation' AND module_code IS NULL AND espace_code IS NULL"
    )
    op.execute("UPDATE notifications SET portee = 'plateforme' WHERE portee = 'module' AND module_code IS NULL")
    op.create_index(
        "ix_notifications_user_portee_module",
        "notifications",
        ["user_id", "portee", "module_code", "lu"],
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_user_portee_module", table_name="notifications")
    op.drop_constraint("ck_notifications_portee", "notifications", type_="check")
    op.drop_column("notifications", "portee")
