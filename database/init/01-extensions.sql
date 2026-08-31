-- Exécuté uniquement à la première initialisation du volume PostgreSQL.
-- gen_random_uuid() est dans le cœur de PostgreSQL 13+ ; pgcrypto reste
-- utile pour d'éventuels scripts de réparation historiques.
CREATE EXTENSION IF NOT EXISTS pgcrypto;
