-- BEA DIGITAL — compte PostgreSQL de l'application (backend + worker), sans superutilisateur.
--
-- Idempotent. À exécuter avec le compte propriétaire des tables (admin), sur CHAQUE base
-- (bea_digital et les copies *_test) :
--   docker exec -i -e BEA_APP_DB_PASSWORD bea-postgres psql -U admin -d <base> -X -q < database/roles/bea_app.sql
-- Le mot de passe est lu dans l'environnement : jamais en argument, jamais dans ce fichier.
--
-- admin reste réservé aux migrations (service compose « migrate »), pgAdmin et restaurations DSI.
-- Retour arrière : BEA_APP_DB_USER=admin et BEA_APP_DB_PASSWORD=<mot de passe admin> dans
-- .env.docker, puis recréer backend et worker. Le rôle bea_app peut rester en place.

\set ON_ERROR_STOP on
\getenv bea_app_password BEA_APP_DB_PASSWORD
\if :{?bea_app_password}
\else
  DO $$ BEGIN RAISE EXCEPTION 'BEA_APP_DB_PASSWORD absent de l''environnement'; END $$;
\endif
SELECT length(:'bea_app_password') >= 24 AS mdp_ok \gset
\if :mdp_ok
\else
  DO $$ BEGIN RAISE EXCEPTION 'BEA_APP_DB_PASSWORD trop court (24 caractères minimum)'; END $$;
\endif

SET log_statement = 'none';

SELECT NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'bea_app') AS creer_role \gset
\if :creer_role
  CREATE ROLE bea_app;
\endif
ALTER ROLE bea_app WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS INHERIT
  PASSWORD :'bea_app_password';
\unset bea_app_password

BEGIN;

SELECT pg_catalog.format('GRANT CONNECT, TEMPORARY ON DATABASE %I TO bea_app', current_database()) \gexec

-- Structure : seul le propriétaire (admin) crée ou modifie des objets.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

-- Données métier. Les options de transmission (WITH GRANT OPTION) servent uniquement à CORE QUERY,
-- qui redonne SELECT à son rôle de lecture bea_core_query_reader (executor.ensure_reader_role).
GRANT USAGE ON SCHEMA public TO bea_app WITH GRANT OPTION;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO bea_app;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO bea_app WITH GRANT OPTION;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO bea_app;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO bea_app WITH GRANT OPTION;

-- Journaux en ajout seul, version de schéma en lecture seule.
REVOKE UPDATE, DELETE ON public.audit_logs, public.core_query_logs FROM bea_app;
REVOKE INSERT, UPDATE, DELETE ON public.alembic_version FROM bea_app;

-- Tables et séquences créées plus tard par les migrations (exécutées en admin).
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO bea_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO bea_app WITH GRANT OPTION;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO bea_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON SEQUENCES TO bea_app WITH GRANT OPTION;

-- Restauration CORE ADMIN : désactivation temporaire des clés étrangères (platform_backup_engine).
GRANT SET ON PARAMETER session_replication_role TO bea_app;

-- CORE QUERY : bea_app administre son rôle de lecture et en reprend les droits au démarrage.
SELECT NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'bea_core_query_reader') AS creer_lecteur \gset
\if :creer_lecteur
  CREATE ROLE bea_core_query_reader NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
\endif
GRANT bea_core_query_reader TO bea_app WITH ADMIN OPTION;
GRANT USAGE ON SCHEMA public TO bea_core_query_reader;
-- Ne retire que les droits accordés par admin ; ceux accordés par bea_app restent en place.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM bea_core_query_reader;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM bea_core_query_reader;

COMMIT;

SELECT r.rolname, r.rolsuper, r.rolcreaterole, r.rolcreatedb, r.rolcanlogin,
       has_schema_privilege('bea_app', 'public', 'CREATE') AS peut_creer,
       has_table_privilege('bea_app', 'public.audit_logs', 'UPDATE,DELETE') AS audit_modifiable,
       has_table_privilege('bea_app', 'public.users', 'SELECT,INSERT,UPDATE,DELETE') AS donnees_rw
FROM pg_catalog.pg_roles r WHERE r.rolname = 'bea_app';
