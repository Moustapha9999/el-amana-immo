-- Libellés catalogue BEA DIGITAL (UTF-8). Corrige les "?" issus d'un insert mal encodé.

UPDATE plateforme_espaces SET
  label = 'Comptabilité',
  description = 'Immobilisations, amortissements, pièces et contrôles autour d’ORION — sans remplacer le core banking.'
WHERE code = 'comptabilite';

UPDATE plateforme_espaces SET
  label = 'Crédit',
  description = 'Processus crédit autour d’ORION (dossiers, contrôles, workflows).'
WHERE code = 'credit';

UPDATE plateforme_espaces SET
  label = 'RH',
  description = 'Processus ressources humaines internes.'
WHERE code = 'rh';

UPDATE plateforme_espaces SET
  label = 'Informatique',
  description = 'Demandes, suivi et outils internes DSI.'
WHERE code = 'informatique';

UPDATE plateforme_espaces SET
  label = 'Achats',
  description = 'Demandes d’achat, validations et suivi documentaire.'
WHERE code = 'achats';

UPDATE plateforme_modules SET
  label = 'Immobilisations & Amortissements',
  description = 'Parc, dotations, cessions, rebuts, réévaluations, inventaire, écritures, archives et rapports.'
WHERE code = 'immobilisations';

UPDATE plateforme_modules SET
  label = 'Rapprochements',
  description = 'Rapprochements Excel / ORION et contrôles de cohérence.'
WHERE code = 'rapprochements';

UPDATE plateforme_modules SET
  label = 'Contrôles comptables',
  description = 'Contrôles périodiques et anomalies.'
WHERE code = 'controles';

UPDATE plateforme_modules SET
  label = 'Clôture comptable',
  description = 'Préparation et suivi de clôture.'
WHERE code = 'cloture';

UPDATE plateforme_modules SET
  label = 'Reporting comptable',
  description = 'Tableaux de bord et exports transverses.'
WHERE code = 'reporting-compta';
