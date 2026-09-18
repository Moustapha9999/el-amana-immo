-- BEA DIGITAL — schéma plateforme (idempotent)
-- À coller dans Supabase → SQL Editor, ou via scripts/bea-supabase.ps1 sql
--
-- Ne renomme PAS la base, les tables métier, ni le volume Docker.
-- N’active PAS RLS sur public (l’app passe par FastAPI, pas PostgREST).
-- Ne touche PAS aux données immobilisations / amortissements / écritures.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Sessions duales (Login 1 plateforme / Login 2 module)
ALTER TABLE auth_sessions
  ADD COLUMN IF NOT EXISTS kind varchar(20) NOT NULL DEFAULT 'platform';
ALTER TABLE auth_sessions
  ADD COLUMN IF NOT EXISTS module_code varchar(80);
ALTER TABLE auth_sessions
  ADD COLUMN IF NOT EXISTS parent_session_id uuid;

CREATE INDEX IF NOT EXISTS ix_auth_sessions_kind ON auth_sessions (kind);
CREATE INDEX IF NOT EXISTS ix_auth_sessions_module_code ON auth_sessions (module_code);
CREATE INDEX IF NOT EXISTS ix_auth_sessions_parent_session_id ON auth_sessions (parent_session_id);

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_auth_sessions_parent') THEN
    ALTER TABLE auth_sessions
      ADD CONSTRAINT fk_auth_sessions_parent
      FOREIGN KEY (parent_session_id) REFERENCES auth_sessions (id);
  END IF;
END $$;

-- Catalogue espaces / modules (≠ org.departements)
CREATE TABLE IF NOT EXISTS plateforme_espaces (
  id uuid PRIMARY KEY,
  code varchar(80) NOT NULL,
  label varchar(120) NOT NULL,
  description text NOT NULL DEFAULT '',
  route varchar(160),
  statut varchar(20) NOT NULL DEFAULT 'bientot',
  sort_order integer NOT NULL DEFAULT 0,
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_plateforme_espaces_code ON plateforme_espaces (code);
CREATE INDEX IF NOT EXISTS ix_plateforme_espaces_statut ON plateforme_espaces (statut);

CREATE TABLE IF NOT EXISTS plateforme_modules (
  id uuid PRIMARY KEY,
  espace_id uuid NOT NULL REFERENCES plateforme_espaces (id) ON DELETE CASCADE,
  code varchar(80) NOT NULL,
  label varchar(160) NOT NULL,
  description text NOT NULL DEFAULT '',
  entry_path varchar(160),
  statut varchar(20) NOT NULL DEFAULT 'bientot',
  sort_order integer NOT NULL DEFAULT 0,
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_plateforme_modules_code ON plateforme_modules (code);
CREATE INDEX IF NOT EXISTS ix_plateforme_modules_espace_id ON plateforme_modules (espace_id);
CREATE INDEX IF NOT EXISTS ix_plateforme_modules_statut ON plateforme_modules (statut);

CREATE TABLE IF NOT EXISTS user_espace_acces (
  user_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  espace_id uuid NOT NULL REFERENCES plateforme_espaces (id) ON DELETE CASCADE,
  status varchar(20) NOT NULL DEFAULT 'actif',
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid,
  PRIMARY KEY (user_id, espace_id)
);
ALTER TABLE user_espace_acces ADD COLUMN IF NOT EXISTS status varchar(20) NOT NULL DEFAULT 'actif';
ALTER TABLE user_espace_acces ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE user_espace_acces ADD COLUMN IF NOT EXISTS created_by uuid;

CREATE TABLE IF NOT EXISTS user_module_acces (
  user_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  module_id uuid NOT NULL REFERENCES plateforme_modules (id) ON DELETE CASCADE,
  status varchar(20) NOT NULL DEFAULT 'actif',
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid,
  PRIMARY KEY (user_id, module_id)
);
ALTER TABLE user_module_acces ADD COLUMN IF NOT EXISTS status varchar(20) NOT NULL DEFAULT 'actif';
ALTER TABLE user_module_acces ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE user_module_acces ADD COLUMN IF NOT EXISTS created_by uuid;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_user_espace_acces_created_by') THEN
    ALTER TABLE user_espace_acces
      ADD CONSTRAINT fk_user_espace_acces_created_by
      FOREIGN KEY (created_by) REFERENCES users (id) ON DELETE SET NULL;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_user_module_acces_created_by') THEN
    ALTER TABLE user_module_acces
      ADD CONSTRAINT fk_user_module_acces_created_by
      FOREIGN KEY (created_by) REFERENCES users (id) ON DELETE SET NULL;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS auth_login_attempts (
  id uuid PRIMARY KEY,
  email varchar(255) NOT NULL,
  ip_address varchar(64),
  login_kind varchar(20) NOT NULL,
  module_code varchar(80),
  success boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_auth_login_attempts_email ON auth_login_attempts (email);
CREATE INDEX IF NOT EXISTS ix_auth_login_attempts_ip_address ON auth_login_attempts (ip_address);
CREATE INDEX IF NOT EXISTS ix_auth_login_attempts_login_kind ON auth_login_attempts (login_kind);

-- Contexte audit / notifications (colonnes additives nullable)
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS espace_code varchar(80);
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS module_code varchar(80);
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS session_id uuid;
CREATE INDEX IF NOT EXISTS ix_audit_logs_espace_code ON audit_logs (espace_code);
CREATE INDEX IF NOT EXISTS ix_audit_logs_module_code ON audit_logs (module_code);

ALTER TABLE notifications ADD COLUMN IF NOT EXISTS espace_code varchar(80);
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS module_code varchar(80);
CREATE INDEX IF NOT EXISTS ix_notifications_espace_code ON notifications (espace_code);
CREATE INDEX IF NOT EXISTS ix_notifications_module_code ON notifications (module_code);

-- GED CORE (lecture CORE ADMIN ; upload métier pas encore branché)
CREATE TABLE IF NOT EXISTS ged_documents (
  id uuid PRIMARY KEY,
  espace_code varchar(80) NOT NULL,
  module_code varchar(80) NOT NULL,
  entity varchar(80) NOT NULL,
  entity_id varchar(64) NOT NULL,
  filename varchar(255) NOT NULL,
  stored_path varchar(512) NOT NULL,
  mime_type varchar(120),
  size_bytes integer NOT NULL DEFAULT 0,
  uploaded_by_id uuid REFERENCES users (id),
  is_active boolean NOT NULL DEFAULT true,
  deleted_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_ged_documents_espace_code ON ged_documents (espace_code);
CREATE INDEX IF NOT EXISTS ix_ged_documents_module_code ON ged_documents (module_code);
CREATE INDEX IF NOT EXISTS ix_ged_documents_entity ON ged_documents (entity);
CREATE INDEX IF NOT EXISTS ix_ged_documents_entity_id ON ged_documents (entity_id);
CREATE INDEX IF NOT EXISTS ix_ged_documents_uploaded_by_id ON ged_documents (uploaded_by_id);

COMMIT;
