"""Moteur synchrone des sauvegardes CORE ADMIN — pg_dump / psql / fichiers / empreintes.

Format d'une sauvegarde (dossier ``BACKUP_DIR``), préfixe commun ``<base>`` :

- ``<base>.dump``          pg_dump custom (base entière en GLOBAL, tables exclusives sinon)
- ``<base>.ged.copy``      lignes ``ged_documents`` du périmètre (DÉPARTEMENT / MODULE)
- ``<base>.files.tar.gz``  fichiers (uploads + GED) du périmètre
- ``<base>.manifest.json`` périmètre, comptages, empreintes SHA-256

Restauration SQL = un seul ``psql --single-transaction`` : purge des tables du
périmètre, rechargement, puis contrôle de toutes les clés étrangères touchant le
périmètre. La moindre erreur annule tout (la base n'est jamais à moitié restaurée).
Les fichiers ne sont remplacés qu'après validation SQL.

Appelé via ``asyncio.to_thread`` : aucune I/O base asynchrone ici.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlparse

from app.core.config import get_settings

PG_TIMEOUT_SECONDS = 3600
LOCK_TIMEOUT = "30s"
MANIFEST_FORMAT = "bea-backup/2"
_IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
_TOC_RE = re.compile(r"^(\d+);\s+\d+\s+\d+\s+(TABLE DATA|SEQUENCE SET)\s+(\S+)\s+(\S+)\s")
FK_VIOLATION_MARKER = "BEA_FK_VIOLATION"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def backup_root() -> Path:
    settings = get_settings()
    raw = Path(settings.backup_dir)
    if raw.is_absolute():
        path = raw
    else:
        # Conteneur Docker : /backups monté ; sinon racine dépôt.
        docker = Path("/backups")
        path = docker if docker.is_dir() else (_project_root() / raw)
    path.mkdir(parents=True, exist_ok=True)
    return path


def upload_root() -> Path:
    settings = get_settings()
    raw = Path(settings.upload_dir)
    if raw.is_absolute():
        return raw
    candidate = Path("/app") / raw
    if candidate.exists() or str(raw).startswith("storage"):
        base = Path("/app") if Path("/app").is_dir() else _project_root()
        return base / raw
    return _project_root() / raw


def ged_root() -> Path:
    raw = Path(get_settings().ged_dir)
    return raw if raw.is_absolute() else raw.resolve()


def safe_ident(name: str) -> str:
    """Identifiant SQL issu du catalogue (pg_tables / config) — refuse tout le reste."""
    if not _IDENT_RE.match(name or ""):
        raise ValueError(f"Identifiant SQL refusé : {name!r}")
    return name


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


@dataclass
class PgDsn:
    host: str
    port: str
    user: str
    password: str
    dbname: str

    def conn_args(self) -> list[str]:
        return ["-h", self.host, "-p", self.port, "-U", self.user, "-d", self.dbname]


def pg_dsn() -> PgDsn:
    settings = get_settings()
    url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    parsed = urlparse(url)
    return PgDsn(
        host=parsed.hostname or "localhost",
        port=str(parsed.port or 5432),
        user=unquote(parsed.username or "admin"),
        password=unquote(parsed.password or ""),
        dbname=(parsed.path or "/bea_digital").lstrip("/") or "bea_digital",
    )


def run_pg(
    cmd: list[str],
    *,
    password: str | None = None,
    stdout_path: Path | None = None,
    timeout: int = PG_TIMEOUT_SECONDS,
) -> str:
    """Lance un outil client PostgreSQL ; le mot de passe ne passe que par l'environnement."""
    env = os.environ.copy()
    if password is not None:
        env["PGPASSWORD"] = password
    if stdout_path is not None:
        with stdout_path.open("wb") as fh:
            proc = subprocess.run(
                cmd, env=env, stdout=fh, stderr=subprocess.PIPE, check=False, timeout=timeout
            )
        out = ""
    else:
        proc = subprocess.run(cmd, env=env, capture_output=True, check=False, timeout=timeout)
        out = proc.stdout.decode("utf-8", "replace")
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace").strip() or out.strip()
        raise RuntimeError((err or f"échec {cmd[0]}")[:4000])
    return out


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dir_stats(path: Path) -> tuple[int, int]:
    files = 0
    size = 0
    if not path.exists():
        return 0, 0
    for root, _dirs, names in os.walk(path):
        for name in names:
            try:
                size += (Path(root) / name).stat().st_size
                files += 1
            except OSError:
                continue
    return files, size


def artifact_entry(path: Path) -> dict:
    return {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)}


# ——— Sauvegarde ———


@dataclass
class BackupPlan:
    base: Path
    level: str
    tables: list[str] | None  # None = base entière
    ged_codes: list[str] = field(default_factory=list)
    ged_columns: list[str] = field(default_factory=list)
    file_targets: list[tuple[str, Path]] = field(default_factory=list)


def execute_backup(plan: BackupPlan, dsn: PgDsn) -> dict:
    """Produit les artefacts ; en cas d'erreur, supprime les fichiers partiels et relève."""
    artifacts: dict[str, dict] = {}
    produced: list[Path] = []
    try:
        if plan.tables is None or plan.tables:
            dump = Path(f"{plan.base}.dump")
            cmd = [
                "pg_dump",
                *dsn.conn_args(),
                "--format=custom",
                "--no-owner",
                "--no-acl",
                "-f",
                str(dump),
            ]
            for table in plan.tables or []:
                cmd.extend(["-t", f"public.{safe_ident(table)}"])
            produced.append(dump)
            run_pg(cmd, password=dsn.password)
            if not dump.exists() or dump.stat().st_size < 64:
                raise RuntimeError("Dump PostgreSQL vide ou incomplet")
            artifacts["dump"] = artifact_entry(dump)

        if plan.ged_codes:
            ged_file = Path(f"{plan.base}.ged.copy")
            cols = ", ".join(f'"{safe_ident(c)}"' for c in plan.ged_columns)
            codes = ", ".join(sql_literal(c) for c in plan.ged_codes)
            query = (
                f"COPY (SELECT {cols} FROM public.ged_documents "
                f"WHERE module_code IN ({codes}) ORDER BY created_at, id) TO STDOUT"
            )
            produced.append(ged_file)
            run_pg(
                ["psql", "-X", *dsn.conn_args(), "-v", "ON_ERROR_STOP=1", "-c", query],
                password=dsn.password,
                stdout_path=ged_file,
            )
            artifacts["ged_rows"] = artifact_entry(ged_file)

        present = [(arc, p) for arc, p in plan.file_targets if p.exists()]
        if present:
            archive = Path(f"{plan.base}.files.tar.gz")
            produced.append(archive)
            files = 0
            raw = 0
            with tarfile.open(archive, "w:gz") as tar:
                for arc, path in present:
                    tar.add(str(path), arcname=arc)
                    count, size = dir_stats(path)
                    files += count
                    raw += size
            artifacts["files"] = {**artifact_entry(archive), "files": files, "raw_bytes": raw}
        return artifacts
    except BaseException:
        for path in produced:
            path.unlink(missing_ok=True)
        raise


def write_manifest(base: Path, manifest: dict) -> dict:
    path = Path(f"{base}.manifest.json")
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return artifact_entry(path)


def remove_artifacts(directory: Path, artifacts: dict | None, legacy: list[str | None]) -> None:
    for entry in (artifacts or {}).values():
        name = entry.get("file") if isinstance(entry, dict) else None
        if name:
            (directory / name).unlink(missing_ok=True)
    for raw in legacy:
        if not raw:
            continue
        path = Path(raw)
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)


# ——— Intégrité ———


def verify_artifacts(directory: Path, artifacts: dict | None, legacy_dump: str | None) -> list[dict]:
    """Contrôle chaque artefact : présence, empreinte SHA-256, lisibilité du format."""
    checks: list[dict] = []
    entries = dict(artifacts or {})
    if not entries and legacy_dump:
        path = Path(legacy_dump)
        entries = {"dump": {"file": path.name, "sha256": None}}
        directory = path.parent
    if not entries:
        return [{"artifact": "sauvegarde", "ok": False, "detail": "Aucun artefact enregistré"}]
    for key, entry in entries.items():
        path = directory / entry["file"]
        if not path.exists():
            checks.append({"artifact": key, "ok": False, "detail": f"Fichier absent : {path.name}"})
            continue
        expected = entry.get("sha256")
        actual = sha256_file(path)
        if expected and actual != expected:
            checks.append(
                {
                    "artifact": key,
                    "ok": False,
                    "detail": "Empreinte SHA-256 différente — fichier altéré",
                    "sha256": actual,
                }
            )
            continue
        try:
            if key == "dump":
                toc = run_pg(["pg_restore", "-l", str(path)])
                n = sum(1 for line in toc.splitlines() if "TABLE DATA" in line)
                detail = f"Archive PostgreSQL lisible ({n} tables de données)"
            elif key == "files":
                with tarfile.open(path, "r:gz") as tar:
                    n = sum(1 for m in tar.getmembers() if m.isfile())
                detail = f"Archive fichiers lisible ({n} fichiers)"
            elif key == "manifest":
                json.loads(path.read_text(encoding="utf-8"))
                detail = "Manifeste JSON valide"
            else:
                detail = "Lisible"
        except Exception as exc:  # noqa: BLE001 — un artefact illisible = KO, pas une 500
            checks.append({"artifact": key, "ok": False, "detail": f"Illisible : {str(exc)[:300]}"})
            continue
        if not expected:
            detail += " — pas d'empreinte de référence (sauvegarde v1)"
        checks.append({"artifact": key, "ok": True, "detail": detail, "sha256": actual})
    return checks


# ——— Restauration ———


def read_toc(dump: Path) -> list[tuple[str, str, str]]:
    """Entrées de données du dump : (ligne TOC, type, table/séquence)."""
    out = run_pg(["pg_restore", "-l", str(dump)])
    entries: list[tuple[str, str, str]] = []
    for line in out.splitlines():
        match = _TOC_RE.match(line)
        if match and match.group(3) == "public":
            entries.append((line, match.group(2), match.group(4)))
    return entries


@dataclass
class RestorePlan:
    dump: Path | None
    toc_lines: list[str]
    tables: list[str]
    ged_codes: list[str] = field(default_factory=list)
    ged_rows: Path | None = None
    ged_columns: list[str] = field(default_factory=list)
    files_archive: Path | None = None
    file_targets: list[tuple[str, Path]] = field(default_factory=list)
    legacy_uploads: Path | None = None


def fk_check_sql(tables: list[str]) -> str:
    """Bloc PL/pgSQL : lève BEA_FK_VIOLATION si une FK touchant le périmètre est rompue."""
    array = ", ".join(f"'public.{safe_ident(t)}'::regclass" for t in tables)
    return f"""
DO $bea$
DECLARE
  r record;
  cnt bigint;
  cond text;
  nn text;
  problems text := '';
BEGIN
  FOR r IN
    SELECT c.conrelid::regclass AS child, c.confrelid::regclass AS parent, c.conkey, c.confkey
    FROM pg_catalog.pg_constraint c
    WHERE c.contype = 'f'
      AND (c.conrelid = ANY (ARRAY[{array}]) OR c.confrelid = ANY (ARRAY[{array}]))
  LOOP
    SELECT pg_catalog.string_agg(pg_catalog.format('p.%I = c.%I', pa.attname, ca.attname), ' AND '),
           pg_catalog.string_agg(pg_catalog.format('c.%I IS NOT NULL', ca.attname), ' AND ')
      INTO cond, nn
      FROM unnest(r.conkey, r.confkey) AS k(ck, pk)
      JOIN pg_catalog.pg_attribute ca ON ca.attrelid = r.child AND ca.attnum = k.ck
      JOIN pg_catalog.pg_attribute pa ON pa.attrelid = r.parent AND pa.attnum = k.pk;
    EXECUTE pg_catalog.format(
      'SELECT count(*) FROM %s c WHERE %s AND NOT EXISTS (SELECT 1 FROM %s p WHERE %s)',
      r.child, nn, r.parent, cond
    ) INTO cnt;
    IF cnt > 0 THEN
      problems := problems || pg_catalog.format('%s -> %s : %s ligne(s) orpheline(s); ', r.child, r.parent, cnt);
    END IF;
  END LOOP;
  IF problems <> '' THEN
    RAISE EXCEPTION '{FK_VIOLATION_MARKER}: %', problems;
  END IF;
END
$bea$;
"""


def build_restore_script(plan: RestorePlan, work: Path, data_sql: Path | None) -> Path:
    lines = [
        f"SET lock_timeout = '{LOCK_TIMEOUT}';",
        "SET session_replication_role = replica;",
    ]
    for table in plan.tables:
        lines.append(f'DELETE FROM public."{safe_ident(table)}";')
    if plan.ged_codes:
        codes = ", ".join(sql_literal(c) for c in plan.ged_codes)
        lines.append(f"DELETE FROM public.ged_documents WHERE module_code IN ({codes});")
    if data_sql is not None:
        lines.append(f"\\i {sql_literal(data_sql.as_posix())}")
    if plan.ged_rows is not None and plan.ged_columns:
        cols = ", ".join(f'"{safe_ident(c)}"' for c in plan.ged_columns)
        lines.append(f"\\copy public.ged_documents ({cols}) FROM {sql_literal(plan.ged_rows.as_posix())}")
    lines.append("SET session_replication_role = origin;")
    checked = list(plan.tables)
    if plan.ged_codes and "ged_documents" not in checked:
        checked.append("ged_documents")
    if checked:
        lines.append(fk_check_sql(checked))
    script = work / "restore.sql"
    script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return script


def execute_restore_sql(plan: RestorePlan, dsn: PgDsn) -> dict:
    work = Path(tempfile.mkdtemp(prefix="restore-", dir=str(backup_root())))
    try:
        data_sql: Path | None = None
        if plan.dump is not None and plan.toc_lines:
            listing = work / "restore.list"
            listing.write_text("\n".join(plan.toc_lines) + "\n", encoding="utf-8")
            data_sql = work / "data.sql"
            run_pg(
                [
                    "pg_restore",
                    "--data-only",
                    "--no-owner",
                    "--no-acl",
                    "-L",
                    str(listing),
                    "-f",
                    str(data_sql),
                    str(plan.dump),
                ]
            )
        script = build_restore_script(plan, work, data_sql)
        run_pg(
            [
                "psql",
                "-X",
                *dsn.conn_args(),
                "-v",
                "ON_ERROR_STOP=1",
                "--single-transaction",
                "-q",
                "-f",
                str(script),
            ],
            password=dsn.password,
        )
        return {"tables": len(plan.tables), "ged_codes": plan.ged_codes, "fk_check": "ok"}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _replace_dir_contents(target: Path, source: Path | None) -> None:
    """Remplace le contenu de ``target`` (peut être un point de montage) par ``source``."""
    target.mkdir(parents=True, exist_ok=True)
    for child in target.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()
    if source is not None and source.exists():
        for child in source.iterdir():
            shutil.move(str(child), str(target / child.name))


def restore_files(plan: RestorePlan) -> dict:
    if plan.files_archive is None and plan.legacy_uploads is None:
        return {"targets": 0}
    if plan.files_archive is None:
        assert plan.legacy_uploads is not None
        staging = Path(tempfile.mkdtemp(prefix="files-", dir=str(backup_root())))
        try:
            shutil.copytree(plan.legacy_uploads, staging / "uploads")
            _replace_dir_contents(upload_root(), staging / "uploads")
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        return {"targets": 1, "legacy": True}
    staging = Path(tempfile.mkdtemp(prefix="files-", dir=str(backup_root())))
    try:
        with tarfile.open(plan.files_archive, "r:gz") as tar:
            tar.extractall(staging, filter="data")
        for arc, target in plan.file_targets:
            _replace_dir_contents(target, staging / arc)
        return {"targets": len(plan.file_targets)}
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def friendly_restore_error(raw: str) -> str:
    text = raw or ""
    if FK_VIOLATION_MARKER in text:
        detail = text.split(f"{FK_VIOLATION_MARKER}:", 1)[-1].split("\n", 1)[0].strip()
        return (
            "Restauration refusée : l'intégrité référentielle serait rompue "
            f"({detail}). Aucune donnée n'a été modifiée. Restaurez un périmètre plus large "
            "(département complet ou sauvegarde globale)."
        )
    lowered = text.lower()
    if "permission denied to set parameter" in lowered:
        return (
            "Le compte PostgreSQL de l'application ne peut pas désactiver temporairement les "
            "contrôles de clés étrangères (session_replication_role). Aucune donnée n'a été "
            "modifiée. DSI : GRANT SET ON PARAMETER session_replication_role TO <compte>."
        )
    if "lock timeout" in lowered:
        return (
            "Tables verrouillées par une activité en cours. Aucune donnée n'a été modifiée. "
            "Activez la maintenance du périmètre puis réessayez."
        )
    missing_object = "does not exist" in lowered and ("column" in lowered or "relation" in lowered)
    if missing_object or any(
        marker in lowered
        for marker in ("invalid input syntax", "extra data", "missing data", "violates not-null")
    ):
        return (
            "Schéma incompatible entre la sauvegarde et la base actuelle. Aucune donnée n'a été "
            "modifiée. Détail : " + text.splitlines()[0][:400]
        )
    first = text.strip().splitlines()[0] if text.strip() else "erreur inconnue"
    return f"Échec de la restauration, aucune donnée modifiée : {first[:500]}"


def build_download_bundle(directory: Path, artifacts: dict, name: str) -> Path:
    """Archive .tar (non recompressée) de tous les artefacts — fichier temporaire."""
    fd, raw = tempfile.mkstemp(prefix="download-", suffix=".tar", dir=str(backup_root()))
    os.close(fd)
    bundle = Path(raw)
    with tarfile.open(bundle, "w") as tar:
        for entry in artifacts.values():
            path = directory / entry["file"]
            if path.exists():
                tar.add(str(path), arcname=f"{name}/{path.name}")
    return bundle
