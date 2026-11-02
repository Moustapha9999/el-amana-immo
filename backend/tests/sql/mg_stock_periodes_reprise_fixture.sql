-- Données SYNTHÉTIQUES (année 2091) pour vérifier la reprise de la migration 20261102_mg_stock_periodes_02.
-- À exécuter uniquement sur une base de test jetable, AVANT l'upgrade.
INSERT INTO mg_stock_periodes (id, annee, mois, libelle, date_debut, date_fin, statut, cloture_at)
VALUES
  ('00000000-0000-0000-0000-000000209101', 2091, 1, 'Janvier 2091', '2091-01-01', '2091-01-31', 'CLOTUREE', '2091-02-03 10:00+00'),
  ('00000000-0000-0000-0000-000000209102', 2091, 2, 'Février 2091', '2091-02-01', '2091-02-28', 'OUVERTE', '2091-03-05 09:00+00');

INSERT INTO audit_logs (id, action, entity, entity_id, after_data, created_at) VALUES
  (gen_random_uuid(), 'cloture_periode', 'mg_stock_periode', '00000000-0000-0000-0000-000000209101',
   '{"libelle": "Janvier 2091"}', '2091-02-01 08:00+00'),
  (gen_random_uuid(), 'reouverture_periode', 'mg_stock_periode', '00000000-0000-0000-0000-000000209101',
   '{"libelle": "Janvier 2091", "motif": "Facture oubliée", "verrouilee": {"id": "00000000-0000-0000-0000-000000209102", "libelle": "Février 2091"}}',
   '2091-02-02 08:00+00'),
  (gen_random_uuid(), 'cloture_periode', 'mg_stock_periode', '00000000-0000-0000-0000-000000209101',
   '{"libelle": "Janvier 2091"}', '2091-02-03 10:00+00');

-- Période clôturée d'office, rouverte par la reclôture de la précédente puis clôturée normalement.
INSERT INTO mg_stock_periodes (id, annee, mois, libelle, date_debut, date_fin, statut, cloture_at)
VALUES
  ('00000000-0000-0000-0000-000000209201', 2092, 1, 'Janvier 2092', '2092-01-01', '2092-01-31', 'CLOTUREE', '2092-02-11 10:00+00'),
  ('00000000-0000-0000-0000-000000209202', 2092, 2, 'Février 2092', '2092-02-01', '2092-02-29', 'CLOTUREE', '2092-03-02 10:00+00');

INSERT INTO audit_logs (id, action, entity, entity_id, after_data, created_at) VALUES
  (gen_random_uuid(), 'cloture_periode', 'mg_stock_periode', '00000000-0000-0000-0000-000000209201',
   '{"libelle": "Janvier 2092"}', '2092-02-01 08:00+00'),
  (gen_random_uuid(), 'reouverture_periode', 'mg_stock_periode', '00000000-0000-0000-0000-000000209201',
   '{"libelle": "Janvier 2092", "motif": "Contrôle", "verrouilee": {"id": "00000000-0000-0000-0000-000000209202", "libelle": "Février 2092"}}',
   '2092-02-10 08:00+00'),
  (gen_random_uuid(), 'cloture_periode', 'mg_stock_periode', '00000000-0000-0000-0000-000000209201',
   '{"libelle": "Janvier 2092", "periode_suivante": "Février 2092"}', '2092-02-11 10:00+00'),
  (gen_random_uuid(), 'cloture_periode', 'mg_stock_periode', '00000000-0000-0000-0000-000000209202',
   '{"libelle": "Février 2092"}', '2092-03-02 10:00+00');
