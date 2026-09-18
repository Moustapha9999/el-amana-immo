-- BEA DIGITAL — commentaires catalogue (idempotent, zéro donnée métier)
-- La logique immobilisations / VNC / URLs / tables physiques reste inchangée.

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
COMMENT ON TABLE ged_documents IS
  'GED CORE — documents transverses (espace + module + entité). Non branchée ; pieces_jointes / archive_* restent immo.';
COMMENT ON COLUMN ged_documents.espace_code IS 'Département BEA DIGITAL (plateforme_espaces.code).';
COMMENT ON COLUMN ged_documents.module_code IS 'Module métier (plateforme_modules.code).';
COMMENT ON COLUMN ged_documents.entity IS 'Type d’objet métier (ex. immobilisation, dossier-credit).';
COMMENT ON COLUMN ged_documents.entity_id IS 'Identifiant de l’objet métier (UUID ou code).';
