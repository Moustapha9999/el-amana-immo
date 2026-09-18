-- BEA DIGITAL — catalogue espaces / modules / permissions (idempotent)
-- Ne crée PAS de doublon departments / modules org.
-- Accorde Comptabilité + Immobilisations à tous les users actifs (deleted_at IS NULL).

BEGIN;

INSERT INTO plateforme_espaces (id, code, label, description, route, statut, sort_order, is_active)
VALUES
  (gen_random_uuid(), 'comptabilite', 'Comptabilité',
   'Immobilisations, amortissements, pièces et contrôles autour d’ORION — sans remplacer le core banking.',
   '/comptabilite', 'actif', 1, true),
  (gen_random_uuid(), 'credit', 'Crédit',
   'Processus crédit autour d’ORION (dossiers, contrôles, workflows).',
   NULL, 'bientot', 2, true),
  (gen_random_uuid(), 'rh', 'RH',
   'Processus ressources humaines internes.',
   NULL, 'bientot', 3, true),
  (gen_random_uuid(), 'informatique', 'Informatique',
   'Demandes, suivi et outils internes DSI.',
   NULL, 'bientot', 4, true),
  (gen_random_uuid(), 'achats', 'Achats',
   'Demandes d’achat, validations et suivi documentaire.',
   NULL, 'bientot', 5, true)
ON CONFLICT (code) DO UPDATE SET
  label = EXCLUDED.label,
  description = EXCLUDED.description,
  route = EXCLUDED.route,
  statut = EXCLUDED.statut,
  sort_order = EXCLUDED.sort_order,
  updated_at = now();

INSERT INTO plateforme_modules (id, espace_id, code, label, description, entry_path, statut, sort_order, is_active)
SELECT gen_random_uuid(), e.id, v.code, v.label, v.description, v.entry_path, v.statut, v.sort_order, true
FROM plateforme_espaces e
JOIN (VALUES
  ('comptabilite', 'immobilisations', 'Immobilisations & Amortissements',
   'Parc, dotations, cessions, rebuts, réévaluations, inventaire, écritures, archives et rapports.',
   '/dashboard', 'actif', 1),
  ('comptabilite', 'rapprochements', 'Rapprochements',
   'Rapprochements Excel / ORION et contrôles de cohérence.',
   NULL, 'bientot', 2),
  ('comptabilite', 'controles', 'Contrôles comptables',
   'Contrôles périodiques et anomalies.',
   NULL, 'bientot', 3),
  ('comptabilite', 'cloture', 'Clôture comptable',
   'Préparation et suivi de clôture.',
   NULL, 'bientot', 4),
  ('comptabilite', 'reporting-compta', 'Reporting comptable',
   'Tableaux de bord et exports transverses.',
   NULL, 'bientot', 5)
) AS v(espace_code, code, label, description, entry_path, statut, sort_order)
  ON e.code = v.espace_code
ON CONFLICT (code) DO UPDATE SET
  label = EXCLUDED.label,
  description = EXCLUDED.description,
  entry_path = EXCLUDED.entry_path,
  statut = EXCLUDED.statut,
  sort_order = EXCLUDED.sort_order,
  updated_at = now();

INSERT INTO permissions (id, code, label, module, created_at, updated_at)
SELECT gen_random_uuid(), v.code, v.label, v.module, now(), now()
FROM (VALUES
  ('plateforme.users.read', 'Consultation des utilisateurs', 'plateforme'),
  ('plateforme.users.admin', 'Administration des utilisateurs et des accès', 'plateforme'),
  ('plateforme.audit.read', 'Consultation de l''audit plateforme', 'plateforme'),
  ('ged.read', 'Consultation GED (réservée)', 'ged'),
  ('core.admin.access', 'Accès BEA DIGITAL CORE ADMIN', 'core'),
  ('core.admin.users', 'Administration des utilisateurs (CORE ADMIN)', 'core'),
  ('core.admin.roles', 'Administration des rôles (CORE ADMIN)', 'core'),
  ('core.admin.permissions', 'Administration des permissions (CORE ADMIN)', 'core'),
  ('core.admin.departments', 'Administration des départements (CORE ADMIN)', 'core'),
  ('core.admin.modules', 'Administration des modules (CORE ADMIN)', 'core'),
  ('core.admin.sessions', 'Administration des sessions (CORE ADMIN)', 'core'),
  ('core.admin.audit', 'Consultation de l''audit (CORE ADMIN)', 'core'),
  ('core.admin.security', 'Supervision sécurité (CORE ADMIN)', 'core'),
  ('core.admin.settings', 'Paramètres plateforme (CORE ADMIN)', 'core'),
  ('immobilisations.read', 'Consultation immobilisations', 'immobilisations'),
  ('immobilisations.create', 'Création immobilisations', 'immobilisations'),
  ('immobilisations.update', 'Modification immobilisations', 'immobilisations'),
  ('immobilisations.validate', 'Validation immobilisations', 'immobilisations'),
  ('immobilisations.delete', 'Suppression immobilisations', 'immobilisations'),
  ('immobilisations.cession', 'Cessions', 'immobilisations'),
  ('immobilisations.rebut', 'Rebuts', 'immobilisations'),
  ('immobilisations.reevaluation', 'Réévaluations', 'immobilisations'),
  ('immobilisations.amortissement', 'Amortissements', 'immobilisations'),
  ('immobilisations.reporting', 'Reporting immobilisations', 'immobilisations'),
  ('immobilisations.admin', 'Administration du module', 'immobilisations')
) AS v(code, label, module)
ON CONFLICT (code) DO UPDATE SET
  label = EXCLUDED.label,
  module = EXCLUDED.module,
  updated_at = now();

INSERT INTO user_espace_acces (user_id, espace_id)
SELECT u.id, e.id
FROM users u
JOIN plateforme_espaces e ON e.code = 'comptabilite'
WHERE u.deleted_at IS NULL
ON CONFLICT (user_id, espace_id) DO NOTHING;

INSERT INTO user_module_acces (user_id, module_id)
SELECT u.id, m.id
FROM users u
JOIN plateforme_modules m ON m.code = 'immobilisations'
WHERE u.deleted_at IS NULL
ON CONFLICT (user_id, module_id) DO NOTHING;

COMMIT;
