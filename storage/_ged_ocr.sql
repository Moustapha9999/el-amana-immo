-- Idempotent : colonnes OCR / security_level sur ged_documents
ALTER TABLE ged_documents ADD COLUMN IF NOT EXISTS ocr_status VARCHAR(20) NOT NULL DEFAULT 'pending';
ALTER TABLE ged_documents ADD COLUMN IF NOT EXISTS ocr_text TEXT;
ALTER TABLE ged_documents ADD COLUMN IF NOT EXISTS ocr_text_search tsvector;
ALTER TABLE ged_documents ADD COLUMN IF NOT EXISTS ocr_error TEXT;
ALTER TABLE ged_documents ADD COLUMN IF NOT EXISTS ocr_attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE ged_documents ADD COLUMN IF NOT EXISTS security_level VARCHAR(40) NOT NULL DEFAULT 'internal';

CREATE INDEX IF NOT EXISTS ix_ged_documents_ocr_status ON ged_documents (ocr_status);
CREATE INDEX IF NOT EXISTS ix_ged_documents_security_level ON ged_documents (security_level);
CREATE INDEX IF NOT EXISTS ix_ged_documents_ocr_text_search ON ged_documents USING gin (ocr_text_search);
