"""Commentaires catalogue BEA DIGITAL (aucune donnée métier).

Revision ID: 20260917_bea_comments
Revises: 20260917_audit_context
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260917_bea_comments"
down_revision: Union[str, None] = "20260917_audit_context"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Identique à scripts/supabase/03_comments.sql (auto-contenu pour le conteneur backend).
_COMMENTS = """
COMMENT ON SCHEMA public IS
  'BEA DIGITAL — schéma unique (plateforme interne + module Immobilisations). ORION reste le core banking.';

COMMENT ON TABLE plateforme_espaces IS
  'Catalogue des espaces métiers BEA DIGITAL (Comptabilité, Crédit, RH, …). Distinct de org.departements.';
COMMENT ON COLUMN plateforme_espaces.code IS 'Code stable (ex. comptabilite).';
COMMENT ON COLUMN plateforme_espaces.statut IS 'actif | bientot | inactif.';
COMMENT ON COLUMN plateforme_espaces.route IS 'Route Angular de l’espace (ex. /comptabilite).';

COMMENT ON TABLE plateforme_modules IS
  'Modules d’un espace. Premier module actif : immobilisations (entry_path /dashboard).';
COMMENT ON COLUMN plateforme_modules.code IS 'Code stable (ex. immobilisations).';
COMMENT ON COLUMN plateforme_modules.entry_path IS
  'Entrée Angular du module. Immobilisations = /dashboard (ne pas préfixer sous /comptabilite/).';
COMMENT ON COLUMN plateforme_modules.statut IS 'actif | bientot | inactif.';

COMMENT ON TABLE user_espace_acces IS
  'Habilitations utilisateur → espace BEA DIGITAL (Login 1). Pas une table d’organisation bancaire.';
COMMENT ON COLUMN user_espace_acces.status IS 'actif | revoque.';
COMMENT ON COLUMN user_espace_acces.created_by IS 'UUID users.id — FK en base, pas mappée ORM (évite AmbiguousForeignKeys).';

COMMENT ON TABLE user_module_acces IS
  'Habilitations utilisateur → module (Login 2). Indépendant des rôles métier immobilisations.*';
COMMENT ON COLUMN user_module_acces.status IS 'actif | revoque.';
COMMENT ON COLUMN user_module_acces.created_by IS 'UUID users.id — FK en base, pas mappée ORM.';

COMMENT ON TABLE auth_login_attempts IS
  'Journal des tentatives Login 1 / Login 2 (verrouillage 5 échecs / 15 min).';
COMMENT ON COLUMN auth_login_attempts.login_kind IS 'platform | module.';

COMMENT ON COLUMN auth_sessions.kind IS 'platform = Login 1 BEA DIGITAL, module = Login 2.';
COMMENT ON COLUMN auth_sessions.module_code IS 'Renseigné uniquement pour kind=module.';
COMMENT ON COLUMN auth_sessions.parent_session_id IS 'Session plateforme parente d’une session module.';

COMMENT ON COLUMN audit_logs.espace_code IS 'Contexte espace BEA DIGITAL (nullable, additif).';
COMMENT ON COLUMN audit_logs.module_code IS 'Contexte module BEA DIGITAL (nullable, additif).';
COMMENT ON COLUMN audit_logs.session_id IS 'Session auth à l’origine de l’événement (nullable).';
COMMENT ON COLUMN notifications.espace_code IS 'Contexte espace BEA DIGITAL (nullable, additif).';
COMMENT ON COLUMN notifications.module_code IS 'Contexte module BEA DIGITAL (nullable, additif).';

COMMENT ON TABLE users IS
  'Identités BEA DIGITAL (FastAPI JWT). auth.users Supabase n’est pas utilisé par l’application.';
COMMENT ON TABLE immobilisations IS
  'Module Comptabilité / Immobilisations — logique métier inchangée (VNC, dotations, parc).';
COMMENT ON TABLE amortissements IS
  'Dotations d’amortissement. Ne pas modifier la règle VNC côté application.';
COMMENT ON TABLE ecritures_comptables IS
  'Écritures du module immobilisations (complément d’ORION, pas un remplacement).';
COMMENT ON TABLE plan_comptable IS
  'Plan comptable banque (référentiel El Amana) — inchangé.';
COMMENT ON TABLE departements IS
  'Organigramme banque (directions / départements). N’est PAS le catalogue des espaces plateforme.';
COMMENT ON TABLE permissions IS
  'Permissions fonctionnelles (ex. immobilisations.read). Module = code métier, pas plateforme_modules.id.';
"""


def upgrade() -> None:
    for chunk in _COMMENTS.split(";"):
        stmt = "\n".join(
            line for line in chunk.splitlines() if line.strip() and not line.strip().startswith("--")
        ).strip()
        if stmt:
            op.execute(stmt)


def downgrade() -> None:
    op.execute("COMMENT ON SCHEMA public IS NULL")
    for table in (
        "plateforme_espaces",
        "plateforme_modules",
        "user_espace_acces",
        "user_module_acces",
        "auth_login_attempts",
        "users",
        "immobilisations",
        "amortissements",
        "ecritures_comptables",
        "plan_comptable",
        "departements",
        "permissions",
    ):
        op.execute(f"COMMENT ON TABLE {table} IS NULL")
