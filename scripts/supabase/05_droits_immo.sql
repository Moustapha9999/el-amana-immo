-- BEA DIGITAL — (ré)accorder Comptabilité + Immobilisations à tous les users actifs
-- Idempotent. N’accorde PAS les espaces bientôt (Crédit, RH, …).

BEGIN;

INSERT INTO user_espace_acces (user_id, espace_id)
SELECT u.id, e.id
FROM users u
JOIN plateforme_espaces e ON e.code = 'comptabilite'
WHERE u.deleted_at IS NULL
ON CONFLICT (user_id, espace_id) DO UPDATE SET
  status = 'actif';

INSERT INTO user_module_acces (user_id, module_id)
SELECT u.id, m.id
FROM users u
JOIN plateforme_modules m ON m.code = 'immobilisations'
WHERE u.deleted_at IS NULL
ON CONFLICT (user_id, module_id) DO UPDATE SET
  status = 'actif';

COMMIT;
