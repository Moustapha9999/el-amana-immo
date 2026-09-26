-- Phase 1 Archives MG: extend ged_documents
ALTER TABLE ged_documents ADD COLUMN IF NOT EXISTS title varchar(255);
ALTER TABLE ged_documents ADD COLUMN IF NOT EXISTS description text;
ALTER TABLE ged_documents ADD COLUMN IF NOT EXISTS doc_type varchar(80);
ALTER TABLE ged_documents ADD COLUMN IF NOT EXISTS reference varchar(120);
ALTER TABLE ged_documents ADD COLUMN IF NOT EXISTS date_document date;
ALTER TABLE ged_documents ADD COLUMN IF NOT EXISTS archived_at timestamptz;
ALTER TABLE ged_documents ADD COLUMN IF NOT EXISTS agence_id uuid;
ALTER TABLE ged_documents ADD COLUMN IF NOT EXISTS department_id uuid;
ALTER TABLE ged_documents ADD COLUMN IF NOT EXISTS fournisseur_id uuid;
ALTER TABLE ged_documents ADD COLUMN IF NOT EXISTS version integer NOT NULL DEFAULT 1;
ALTER TABLE ged_documents ADD COLUMN IF NOT EXISTS parent_document_id uuid;
ALTER TABLE ged_documents ADD COLUMN IF NOT EXISTS deleted_by_id uuid;
ALTER TABLE ged_documents ADD COLUMN IF NOT EXISTS delete_reason varchar(500);

DO $$ BEGIN
  ALTER TABLE ged_documents ADD CONSTRAINT ged_documents_agence_id_fkey FOREIGN KEY (agence_id) REFERENCES agences(id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  ALTER TABLE ged_documents ADD CONSTRAINT ged_documents_department_id_fkey FOREIGN KEY (department_id) REFERENCES departements(id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  ALTER TABLE ged_documents ADD CONSTRAINT ged_documents_fournisseur_id_fkey FOREIGN KEY (fournisseur_id) REFERENCES fournisseurs(id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  ALTER TABLE ged_documents ADD CONSTRAINT ged_documents_parent_document_id_fkey FOREIGN KEY (parent_document_id) REFERENCES ged_documents(id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  ALTER TABLE ged_documents ADD CONSTRAINT ged_documents_deleted_by_id_fkey FOREIGN KEY (deleted_by_id) REFERENCES users(id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS ix_ged_documents_doc_type ON ged_documents (doc_type);
CREATE INDEX IF NOT EXISTS ix_ged_documents_reference ON ged_documents (reference);
CREATE INDEX IF NOT EXISTS ix_ged_documents_archived_at ON ged_documents (archived_at);
CREATE INDEX IF NOT EXISTS ix_ged_documents_agence_id ON ged_documents (agence_id);
CREATE INDEX IF NOT EXISTS ix_ged_documents_department_id ON ged_documents (department_id);
CREATE INDEX IF NOT EXISTS ix_ged_documents_fournisseur_id ON ged_documents (fournisseur_id);
CREATE INDEX IF NOT EXISTS ix_ged_documents_parent_document_id ON ged_documents (parent_document_id);
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS ix_ged_documents_filename_trgm ON ged_documents USING gin (filename gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_ged_documents_title_trgm ON ged_documents USING gin (title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_ged_documents_reference_trgm ON ged_documents USING gin (reference gin_trgm_ops);

-- Stamp alembic if contrats + this revision not applied
INSERT INTO alembic_version (version_num)
SELECT '20260926_ged_archives_meta'
WHERE NOT EXISTS (SELECT 1 FROM alembic_version WHERE version_num = '20260926_ged_archives_meta');
