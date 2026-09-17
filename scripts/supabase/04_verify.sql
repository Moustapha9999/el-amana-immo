-- BEA DIGITAL — contrôles après upgrade (lecture seule)
-- Coller dans SQL Editor et vérifier les lignes.

SELECT current_database() AS database,
       current_user AS db_user,
       current_setting('search_path') AS search_path;

SELECT version_num AS alembic_head
FROM alembic_version;

SELECT COUNT(*) AS tables_public
FROM information_schema.tables
WHERE table_schema = 'public' AND table_type = 'BASE TABLE';

SELECT COUNT(*) AS rls_policies_public
FROM pg_policies
WHERE schemaname = 'public';

SELECT
  (SELECT COUNT(*) FROM immobilisations) AS nb_immobilisations,
  (SELECT COALESCE(SUM(valeur_brute), 0) FROM immobilisations) AS somme_valeur_brute,
  (SELECT COUNT(*) FROM amortissements) AS nb_amortissements,
  (SELECT COUNT(*) FROM archive_lignes) AS nb_archive_lignes,
  (SELECT COUNT(*) FROM users WHERE deleted_at IS NULL) AS users_actifs;

SELECT code, label, statut, route
FROM plateforme_espaces
ORDER BY sort_order, code;

SELECT m.code, m.label, m.statut, m.entry_path, e.code AS espace
FROM plateforme_modules m
JOIN plateforme_espaces e ON e.id = m.espace_id
ORDER BY e.sort_order, m.sort_order, m.code;

SELECT
  (SELECT COUNT(*) FROM user_espace_acces) AS grants_espace,
  (SELECT COUNT(*) FROM user_module_acces) AS grants_module,
  (SELECT COUNT(*) FROM auth_sessions WHERE kind = 'platform') AS sessions_platform,
  (SELECT COUNT(*) FROM auth_sessions WHERE kind = 'module') AS sessions_module,
  (SELECT COUNT(*) FROM ged_documents) AS ged_documents;

-- Utilisateurs actifs sans accès module Immobilisations (doit tendre vers 0)
SELECT u.email, u.full_name
FROM users u
WHERE u.deleted_at IS NULL
  AND NOT EXISTS (
    SELECT 1
    FROM user_module_acces uma
    JOIN plateforme_modules m ON m.id = uma.module_id
    WHERE uma.user_id = u.id
      AND m.code = 'immobilisations'
      AND uma.status = 'actif'
  )
ORDER BY u.email;
