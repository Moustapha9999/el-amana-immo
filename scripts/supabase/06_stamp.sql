-- BEA DIGITAL — pointer Alembic après un upgrade SQL Editor (pas via alembic CLI)
--
-- À n’utiliser QUE si 01_upgrade + 02_catalogue + 03_comments ont été joués à la main.
-- Si vous avez déjà fait `alembic upgrade head`, NE PAS exécuter ce fichier.

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'alembic_version'
  ) THEN
    RAISE EXCEPTION 'alembic_version absent — ce n’est pas le dump BEA DIGITAL attendu';
  END IF;

  UPDATE alembic_version
  SET version_num = '20260917_bea_comments'
  WHERE version_num IN (
    '20260914_orion_lock',
    '20260917_dual_auth',
    '20260917_audit_context'
  );

  INSERT INTO alembic_version (version_num)
  SELECT '20260917_bea_comments'
  WHERE NOT EXISTS (SELECT 1 FROM alembic_version);
END $$;

SELECT version_num AS alembic_head FROM alembic_version;
