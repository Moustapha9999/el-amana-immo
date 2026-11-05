"""Validation 4 — sauvegarde physique, WAL, PITR. Isolé uniquement.

    python loadtest/validation_pitr.py

Cluster dédié bea-lt-pitr (volumes bea_lt_pitr_*). N'active JAMAIS archive_mode
sur bea-postgres. Ne touche jamais à bea_digital ni à bea_postgres_data.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

HOTE = "http://127.0.0.1:8081"
API = f"{HOTE}/api/v1"
SOURCE = "bea_digital_loadtest"
INTERDITES = {"bea_digital"}
PG = "bea-postgres"
PITR = "bea-lt-pitr"
VOLUMES_OK = {"bea_lt_pitr_data", "bea_lt_pitr_wal", "bea_lt_pitr_base"}
VOLUME_INTERDIT = "bea_postgres_data"
RACINE = Path(__file__).resolve().parent.parent
DOSSIER = Path(__file__).resolve().parent / "reports" / f"validation4-{datetime.now():%Y%m%d-%H%M%S}"
COMPOSE_LT = RACINE / "loadtest" / "docker-compose.loadtest.yml"
COMPOSE_PITR = RACINE / "loadtest" / "docker-compose.pitr.yml"
ENV_LT = RACINE / "loadtest" / ".env.loadtest"
MARQUE_AVANT = "PITR-AVANT"
MARQUE_ERREUR = "PITR-ERREUR-VOLONTAIRE"


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def journal(entree: dict) -> None:
    DOSSIER.mkdir(parents=True, exist_ok=True)
    with (DOSSIER / "journal.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": utc(), **entree}, ensure_ascii=False) + "\n")


def sh(args: list[str], *, check: bool = True, input_text: str | None = None,
       env: dict | None = None) -> subprocess.CompletedProcess:
    r = subprocess.run(args, input=input_text, text=True, capture_output=True, check=False, env=env)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} → {r.returncode}\n{r.stderr or r.stdout}")
    return r


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return sh(["docker", *args], check=check)


def env_fichier(chemin: Path, cle: str) -> str:
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        if ligne.startswith(f"{cle}="):
            return ligne.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit(f"{cle} absent de {chemin}")


def mot_de_passe() -> str:
    return env_fichier(ENV_LT, "LOADTEST_PASSWORD")


def mdp_bea_app() -> str:
    return env_fichier(RACINE / ".env.docker", "BEA_APP_DB_PASSWORD")


def mdp_admin() -> str:
    return env_fichier(RACINE / ".env.docker", "POSTGRES_PASSWORD")


def psql_src(base: str, sql: str) -> str:
    if base in INTERDITES:
        raise SystemExit(f"ARRÊT : opération refusée sur {base}")
    r = sh(
        ["docker", "exec", "-i", PG, "psql", "-U", "admin", "-d", base, "-X", "-v", "ON_ERROR_STOP=1", "-tA"],
        input_text=sql,
    )
    return r.stdout.strip()


def psql_pitr(base: str, sql: str, *, check: bool = True) -> str:
    r = sh(
        ["docker", "exec", "-i", PITR, "psql", "-U", "admin", "-d", base, "-X", "-v", "ON_ERROR_STOP=1", "-tA"],
        input_text=sql, check=check,
    )
    return r.stdout.strip()


def compose_pitr(args: list[str]) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["POSTGRES_PASSWORD"] = mdp_admin()
    return sh(["docker", "compose", "-f", str(COMPOSE_PITR), *args], env=env)


def compose_lt(args: list[str], extra_file: Path | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["BEA_APP_DB_PASSWORD"] = mdp_bea_app()
    cmd = ["docker", "compose", "-f", str(COMPOSE_LT)]
    if extra_file:
        cmd += ["-f", str(extra_file)]
    cmd += ["--env-file", str(ENV_LT), *args]
    return sh(cmd, env=env)


def verifier_volumes() -> None:
    r = docker("volume", "ls", "--format", "{{.Name}}")
    noms = set(r.stdout.split())
    if VOLUME_INTERDIT not in noms:
        raise SystemExit(f"ARRÊT : volume {VOLUME_INTERDIT} introuvable — on refuse de continuer")
    for interdit in ("bea_postgres_data",):
        if any(a == "volume" and interdit in args for a in []):
            pass
    # Interdiction d'opérer sur le volume métier.
    cmd = " ".join(sys.argv)
    if VOLUME_INTERDIT in cmd and "inspect" not in cmd:
        raise SystemExit("ARRÊT : bea_postgres_data est hors périmètre")


def ecrire_rapport(tests: list[dict]) -> None:
    ok = all(t.get("reussi") for t in tests)
    (DOSSIER / "rapport.json").write_text(
        json.dumps({"ok": ok, "tests": tests}, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    lignes = [
        "# Validation 4 — sauvegarde physique, WAL, PITR",
        "",
        "Cluster isolé : `bea-lt-pitr` / volumes `bea_lt_pitr_*`. `bea-postgres` et `bea_digital` inchangés.",
        f"Dossier : `{DOSSIER.name}`. Résultat global : **{'OK' if ok else 'KO'}**.",
        "",
    ]
    for t in tests:
        lignes += [
            f"## {t['id']} — {t['titre']}",
            "",
            f"- Début : {t.get('debut')}",
            f"- Fin : {t.get('fin')}",
            f"- Réussi : {'oui' if t.get('reussi') else 'non'}",
        ]
        if t.get("detail"):
            lignes.append(f"- Détail : {t['detail']}")
        lignes.append("")
    (DOSSIER / "rapport.md").write_text("\n".join(lignes), encoding="utf-8")


def test_41() -> dict:
    debut = utc()
    inspect = docker("inspect", PG, "--format",
                     "image={{.Config.Image}} cmd={{json .Config.Cmd}} pgdata={{range .Mounts}}{{if eq .Destination \"/var/lib/postgresql/data\"}}{{.Name}}{{end}}{{end}}")
    mounts = docker("inspect", PG, "--format",
                    "{{range .Mounts}}{{.Type}} {{.Name}}{{.Source}} -> {{.Destination}}\n{{end}}")
    vol = docker("volume", "inspect", VOLUME_INTERDIT, "--format", "{{.Name}} {{.Mountpoint}}")
    conf = json.loads(psql_src("postgres", """
        SELECT json_build_object(
          'data_directory', current_setting('data_directory'),
          'config_file', current_setting('config_file'),
          'wal_level', current_setting('wal_level'),
          'archive_mode', current_setting('archive_mode'),
          'archive_command', current_setting('archive_command'),
          'max_connections', current_setting('max_connections'),
          'max_wal_senders', current_setting('max_wal_senders')
        );
    """))
    pgdata = docker("exec", PG, "sh", "-c", "ls -1 /var/lib/postgresql/data | tr '\\n' ','").stdout.strip()
    reussi = (
        conf.get("archive_mode") == "off"
        and conf.get("wal_level") == "replica"
        and conf.get("data_directory") == "/var/lib/postgresql/data"
        and VOLUME_INTERDIT in vol.stdout
    )
    return {
        "id": "4.1", "titre": "Examiner volumes, command, configuration",
        "debut": debut, "fin": utc(), "reussi": reussi,
        "detail": (
            f"{inspect.stdout.strip()} volume={vol.stdout.strip()} "
            f"conf={conf} pgdata_racine={pgdata} mounts={mounts.stdout.strip()[:300]}"
        ),
        "conf_bea_postgres": conf,
    }


def attendre_pitr(timeout: int = 60) -> bool:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        r = docker("inspect", "-f", "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}",
                   PITR, check=False)
        if r.stdout.strip() == "healthy":
            return True
        time.sleep(1)
    return False


def activer_replication_hba() -> None:
    docker("exec", PITR, "sh", "-c",
           "grep -q 'replication all' /var/lib/postgresql/data/pg_hba.conf || "
           "printf '\\nlocal replication all trust\\nhost replication all 127.0.0.1/32 trust\\n' "
           ">> /var/lib/postgresql/data/pg_hba.conf")
    psql_pitr("postgres", "SELECT pg_reload_conf();")


def test_42_43() -> dict:
    """Démarrer le cluster isolé avec archive_mode=on, y charger loadtest."""
    debut = utc()
    compose_pitr(["down", "--remove-orphans"])
    for vol in sorted(VOLUMES_OK):
        if not vol.startswith("bea_lt_pitr_") or vol == VOLUME_INTERDIT:
            raise SystemExit(f"ARRÊT : volume hors périmètre {vol}")
        docker("volume", "rm", vol, check=False)
    compose_pitr(["up", "-d"])
    if not attendre_pitr(90):
        logs = docker("logs", PITR, "--tail", "40", check=False)
        return {"id": "4.2-4.3", "titre": "Cluster PITR isolé + archivage WAL",
                "debut": debut, "fin": utc(), "reussi": False,
                "detail": f"bea-lt-pitr pas healthy : {(logs.stdout or '')[-400:]}"}
    activer_replication_hba()
    conf = json.loads(psql_pitr("postgres", """
        SELECT json_build_object(
          'archive_mode', current_setting('archive_mode'),
          'archive_command', current_setting('archive_command'),
          'archive_timeout', current_setting('archive_timeout'),
          'wal_level', current_setting('wal_level'),
          'data_directory', current_setting('data_directory')
        );
    """))
    # Dump logique de la base isolée loadtest (lecture seule sur bea-postgres).
    dump_tmp = f"/tmp/{SOURCE}.dump"
    docker("exec", PG, "pg_dump", "-U", "admin", "-Fc", "-d", SOURCE, "-f", dump_tmp)
    docker("cp", f"{PG}:{dump_tmp}", str(DOSSIER / f"{SOURCE}.dump"))
    docker("cp", str(DOSSIER / f"{SOURCE}.dump"), f"{PITR}:/tmp/{SOURCE}.dump")

    loc = psql_src("postgres",
                   f"select datcollate || '|' || datctype || '|' || pg_encoding_to_char(encoding) "
                   f"from pg_database where datname = '{SOURCE}';")
    collate, ctype, enc = loc.split("|")
    existe = psql_pitr("postgres", f"select 1 from pg_database where datname = '{SOURCE}';")
    if existe == "1":
        psql_pitr("postgres",
                  f"select pg_terminate_backend(pid) from pg_stat_activity where datname = '{SOURCE}';")
        psql_pitr("postgres", f"drop database {SOURCE};")
    psql_pitr("postgres",
              f"create database {SOURCE} owner admin template template0 "
              f"encoding '{enc}' lc_collate '{collate}' lc_ctype '{ctype}';")
    # Rôles globaux AVANT pg_restore (les ACL du dump les référencent).
    app_pwd = mdp_bea_app().replace("'", "''")
    psql_pitr("postgres", f"""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bea_app') THEN
            CREATE ROLE bea_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
          END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bea_core_query_reader') THEN
            CREATE ROLE bea_core_query_reader NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
          END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'immo_user') THEN
            CREATE ROLE immo_user NOLOGIN NOSUPERUSER;
          END IF;
        END $$;
        ALTER ROLE bea_app PASSWORD '{app_pwd}';
        GRANT CONNECT, TEMPORARY ON DATABASE {SOURCE} TO bea_app;
    """)
    r = docker("exec", PITR, "pg_restore", "-U", "admin", f"--dbname={SOURCE}",
               f"/tmp/{SOURCE}.dump", check=False)
    restore_log = (r.stdout or "") + (r.stderr or "")
    (DOSSIER / "pg_restore-pitr.log").write_text(restore_log, encoding="utf-8")
    erreurs = [ln for ln in restore_log.splitlines() if "ERROR" in ln]
    psql_pitr(SOURCE, """
        GRANT USAGE ON SCHEMA public TO bea_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO bea_app;
        GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO bea_app;
        REVOKE UPDATE, DELETE ON public.audit_logs FROM bea_app;
        REVOKE INSERT, UPDATE, DELETE ON public.alembic_version FROM bea_app;
    """)
    n_tables = int(psql_pitr(SOURCE,
                             "select count(*) from information_schema.tables "
                             "where table_schema='public' and table_type='BASE TABLE';") or 0)
    archive_on = conf.get("archive_mode") == "on"
    reussi = archive_on and n_tables > 50 and not erreurs
    return {
        "id": "4.2-4.3", "titre": "Stratégie isolée + archivage WAL activé",
        "debut": debut, "fin": utc(), "reussi": reussi,
        "detail": (
            f"conf={conf} tables={n_tables} restore_err={len(erreurs)} "
            f"volumes={sorted(VOLUMES_OK)} bea_postgres_data=intouché"
        ),
        "conf": conf, "n_tables": n_tables, "erreurs": erreurs[:10],
    }


def wal_archives() -> list[str]:
    r = docker("exec", PITR, "sh", "-c", "ls -1 /wal-archive 2>/dev/null | grep -v '.tmp' || true", check=False)
    return [x for x in r.stdout.split() if x]


def attendre_archive(min_fichiers: int, timeout: int = 40) -> list[str]:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        fichiers = wal_archives()
        if len(fichiers) >= min_fichiers:
            return fichiers
        time.sleep(1)
    return wal_archives()


def test_44() -> dict:
    debut = utc()
    psql_pitr(SOURCE, "select pg_switch_wal();")
    avant = attendre_archive(1, 30)
    docker("exec", PITR, "sh", "-c", "rm -rf /basebackup/ref && mkdir -p /basebackup/ref && chown postgres /basebackup/ref")
    bb = docker("exec", "-u", "postgres", PITR, "pg_basebackup",
                "-U", "admin", "-D", "/basebackup/ref", "-Fp", "-Xs", "--checkpoint=fast")
    (DOSSIER / "pg_basebackup.log").write_text((bb.stdout or "") + (bb.stderr or ""), encoding="utf-8")
    contenu = docker("exec", PITR, "sh", "-c", "ls /basebackup/ref | tr '\\n' ','").stdout.strip()
    taille = docker("exec", PITR, "sh", "-c", "du -sh /basebackup/ref | awk '{print $1}'").stdout.strip()
    a_pgdata = "PG_VERSION" in contenu and "base" in contenu
    reussi = a_pgdata and bb.returncode == 0
    return {
        "id": "4.4", "titre": "Sauvegarde physique de référence (pg_basebackup)",
        "debut": debut, "fin": utc(), "reussi": reussi,
        "detail": f"taille={taille} contenu={contenu} wal_archives_avant={len(avant)}",
        "taille": taille,
    }


def test_45() -> dict:
    debut = utc()
    psql_pitr(SOURCE, f"""
        CREATE TABLE IF NOT EXISTS pitr_marqueurs (
          id serial PRIMARY KEY,
          libelle text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT clock_timestamp()
        );
        INSERT INTO pitr_marqueurs(libelle) VALUES ('{MARQUE_AVANT}');
        SELECT pg_switch_wal();
    """)
    t_avant = psql_pitr(SOURCE, f"select created_at from pitr_marqueurs where libelle = '{MARQUE_AVANT}' order by id desc limit 1;")
    fichiers = attendre_archive(2, 30)
    archiver = json.loads(psql_pitr("postgres", """
        SELECT json_build_object(
          'archived_count', archived_count,
          'failed_count', failed_count,
          'last_archived_wal', last_archived_wal,
          'last_failed_wal', last_failed_wal
        ) FROM pg_stat_archiver;
    """))
    reussi = int(archiver.get("archived_count") or 0) >= 1 and int(archiver.get("failed_count") or 0) == 0
    return {
        "id": "4.5", "titre": "Générer des transactions et vérifier l'archivage WAL",
        "debut": debut, "fin": utc(), "reussi": reussi,
        "detail": f"t_avant={t_avant} archives={len(fichiers)} pg_stat_archiver={archiver}",
        "t_avant": t_avant, "archiver": archiver, "wal_fichiers": fichiers,
    }


def test_46(etat_45: dict) -> dict:
    debut = utc()
    # Instant cible = après la transaction « bonne », avant l'erreur.
    time.sleep(2)
    t_cible = psql_pitr("postgres", "select clock_timestamp();")
    time.sleep(1)
    psql_pitr(SOURCE, f"""
        INSERT INTO pitr_marqueurs(libelle) VALUES ('{MARQUE_ERREUR}');
        UPDATE mg_stock_mouvements
           SET observation = '{MARQUE_ERREUR}'
         WHERE reference = 'ENT-2026-02754';
        SELECT pg_switch_wal();
    """)
    t_erreur = psql_pitr(SOURCE, f"select created_at from pitr_marqueurs where libelle = '{MARQUE_ERREUR}' order by id desc limit 1;")
    n_err = psql_pitr(SOURCE, f"select count(*) from pitr_marqueurs where libelle = '{MARQUE_ERREUR}';")
    obs = psql_pitr(SOURCE, "select observation from mg_stock_mouvements where reference = 'ENT-2026-02754';")
    attendre_archive(len(etat_45.get("wal_fichiers") or []) + 1, 30)
    reussi = n_err == "1" and MARQUE_ERREUR in (obs or "")
    journal({"etape": "4.6", "t_cible": t_cible, "t_erreur": t_erreur, "obs": obs})
    return {
        "id": "4.6", "titre": "Simuler une erreur métier volontaire",
        "debut": debut, "fin": utc(), "reussi": reussi,
        "detail": f"t_cible={t_cible} t_erreur={t_erreur} marqueurs_erreur={n_err} obs={obs}",
        "t_cible": t_cible, "t_erreur": t_erreur,
    }


def test_47(etat_46: dict) -> dict:
    debut = utc()
    t_cible = etat_46.get("t_cible")
    if not t_cible:
        return {"id": "4.7", "titre": "Restaurer à un instant antérieur à l'erreur",
                "debut": debut, "fin": utc(), "reussi": False, "detail": "pas d'instant cible"}
    compose_pitr(["stop", "pitr-postgres"])
    # Remplacer PGDATA par la sauvegarde physique + recovery.signal.
    # Ne monte QUE les volumes PITR (jamais bea_postgres_data).
    rec_file = DOSSIER / "recovery-append.conf"
    rec_file.write_text(
        "restore_command = 'cp /wal-archive/%f %p'\n"
        f"recovery_target_time = '{t_cible}'\n"
        "recovery_target_action = 'promote'\n"
        "recovery_target_inclusive = on\n",
        encoding="utf-8",
    )
    script = """
set -e
test -f /backup/ref/PG_VERSION
test -f /restore-conf/recovery-append.conf
find /data -mindepth 1 -maxdepth 1 -exec rm -rf {} +
cp -a /backup/ref/. /data/
rm -f /data/recovery.signal /data/standby.signal /data/postmaster.pid
cat /restore-conf/recovery-append.conf >> /data/postgresql.auto.conf
touch /data/recovery.signal
chown -R postgres:postgres /data
ls /data/PG_VERSION /data/recovery.signal
"""
    r = sh([
        "docker", "run", "--rm", "--user", "0",
        "-v", "bea_lt_pitr_data:/data",
        "-v", "bea_lt_pitr_base:/backup:ro",
        "-v", "bea_lt_pitr_wal:/wal-archive:ro",
        "-v", f"{DOSSIER}:/restore-conf:ro",
        "postgres:17-alpine", "sh", "-c", script,
    ])
    (DOSSIER / "restore-pgdata.log").write_text((r.stdout or "") + (r.stderr or ""), encoding="utf-8")
    compose_pitr(["start", "pitr-postgres"])
    if not attendre_pitr(90):
        logs = docker("logs", PITR, "--tail", "50", check=False)
        return {"id": "4.7", "titre": "Restaurer à un instant antérieur à l'erreur",
                "debut": debut, "fin": utc(), "reussi": False,
                "detail": f"cluster pas ready après PITR : {(logs.stderr or logs.stdout or '')[-500:]}"}
    # Attendre la fin du recovery (promote).
    en_recovery = True
    t0 = time.monotonic()
    while time.monotonic() - t0 < 60:
        v = psql_pitr("postgres", "select pg_is_in_recovery();", check=False)
        if v.strip() == "f":
            en_recovery = False
            break
        time.sleep(1)
    n_avant = psql_pitr(SOURCE, f"select count(*) from pitr_marqueurs where libelle = '{MARQUE_AVANT}';", check=False)
    n_err = psql_pitr(SOURCE, f"select count(*) from pitr_marqueurs where libelle = '{MARQUE_ERREUR}';", check=False)
    obs = psql_pitr(SOURCE, "select coalesce(observation,'') from mg_stock_mouvements where reference = 'ENT-2026-02754';", check=False)
    timeline = psql_pitr("postgres", "select pg_wal_replay_resume();", check=False)  # no-op if not in recovery
    reussi = (not en_recovery) and n_avant == "1" and n_err == "0" and MARQUE_ERREUR not in (obs or "")
    return {
        "id": "4.7", "titre": "Restaurer à un instant antérieur à l'erreur",
        "debut": debut, "fin": utc(), "reussi": reussi,
        "detail": (
            f"recovery_termine={not en_recovery} avant={n_avant} erreur={n_err} "
            f"obs={obs!r} cible={t_cible}"
        ),
        "n_avant": n_avant, "n_err": n_err, "obs": obs,
    }


def _attendre_sante(timeout: int = 45) -> bool:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        try:
            if requests.get(f"{HOTE}/health", timeout=3).status_code == 200:
                ready = requests.get(f"{HOTE}/health/ready", timeout=3)
                if ready.status_code == 200:
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False


def _sondes(password: str, email: str) -> dict:
    out: dict = {}
    try:
        out["health"] = requests.get(f"{HOTE}/health", timeout=10).status_code
        out["ready"] = requests.get(f"{HOTE}/health/ready", timeout=10).status_code
        login = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
        out["login"] = login.status_code
        if login.status_code != 200:
            out["login_corps"] = login.text[:200]
            return out
        token = login.json()["access_token"]
        out["me"] = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"}, timeout=15).status_code
        mod = requests.post(
            f"{API}/auth/modules/stock-fournitures/login",
            json={"email": email, "password": password},
            headers={"Authorization": f"Bearer {token}"}, timeout=20,
        )
        out["login2"] = mod.status_code
        if mod.status_code != 200:
            out["login2_corps"] = mod.text[:200]
            return out
        h = {"Authorization": f"Bearer {mod.json()['access_token']}"}
        out["dashboard"] = requests.get(f"{API}/mg/stock/dashboard", headers=h, timeout=20).status_code
        out["mouvements"] = requests.get(f"{API}/mg/stock/mouvements", headers=h, timeout=20).status_code
    except Exception as exc:
        out["erreur"] = f"{type(exc).__name__}: {exc}"
    return out


def _url_backend() -> str:
    r = docker("exec", "bea-lt-backend", "printenv", "DATABASE_URL", check=False)
    return (r.stdout or "").strip()


def test_48(password: str, email: str) -> dict:
    debut = utc()
    override = DOSSIER / "compose-pitr-app.yml"
    override.write_text(
        "services:\n"
        "  lt-backend:\n"
        "    environment:\n"
        "      DATABASE_URL: postgresql+asyncpg://bea_app:${BEA_APP_DB_PASSWORD}@pitr-postgres:5432/"
        f"{SOURCE}\n"
        "  lt-worker:\n"
        "    environment:\n"
        "      DATABASE_URL: postgresql+asyncpg://bea_app:${BEA_APP_DB_PASSWORD}@pitr-postgres:5432/"
        f"{SOURCE}\n",
        encoding="ascii",
    )
    sondes: dict = {}
    base_pendant = "?"
    base_apres = "?"
    sante_ok = False
    try:
        compose_lt(["up", "-d", "--force-recreate", "lt-backend", "lt-worker"], extra_file=override)
        sante_ok = _attendre_sante(60)
        url = _url_backend()
        base_pendant = "pitr-postgres" if "pitr-postgres" in url else "?"
        sondes = _sondes(password, email)
        n_err = psql_pitr(SOURCE, f"select count(*) from pitr_marqueurs where libelle = '{MARQUE_ERREUR}';")
        n_avant = psql_pitr(SOURCE, f"select count(*) from pitr_marqueurs where libelle = '{MARQUE_AVANT}';")
        sondes["marqueurs"] = {"avant": n_avant, "erreur": n_err}
    finally:
        compose_lt(["up", "-d", "--force-recreate", "lt-backend", "lt-worker"])
        _attendre_sante(60)
        url = _url_backend()
        base_apres = SOURCE if SOURCE in url and "pitr-postgres" not in url else "?"
    codes = [sondes.get(k) for k in ("health", "ready", "login", "me", "login2", "dashboard", "mouvements")]
    reussi = (
        sante_ok and all(c == 200 for c in codes)
        and base_pendant == "pitr-postgres" and base_apres == SOURCE
        and sondes.get("marqueurs", {}).get("erreur") == "0"
        and sondes.get("marqueurs", {}).get("avant") == "1"
        and "erreur" not in sondes
    )
    return {
        "id": "4.8", "titre": "Vérifier les données et reconnecter l'application",
        "debut": debut, "fin": utc(), "reussi": reussi,
        "detail": (
            f"sante={sante_ok} sondes={ {k: sondes.get(k) for k in ('health','ready','login','me','login2','dashboard','mouvements','marqueurs')} } "
            f"pendant={base_pendant} apres={base_apres}"
        ),
        "sondes": sondes, "base_pendant": base_pendant, "base_apres": base_apres,
    }


def main() -> int:
    DOSSIER.mkdir(parents=True, exist_ok=True)
    verifier_volumes()
    if psql_src(SOURCE, "select current_database();") != SOURCE:
        print("ARRÊT : pas sur la base de charge")
        return 1
    if psql_src("postgres", "select 1 from pg_database where datname = 'bea_digital';") != "1":
        print("ARRÊT : bea_digital absente")
        return 1
    print(f"Validation 4 → {DOSSIER}")
    print("  bea-postgres / bea_digital = lecture seule (dump loadtest)")
    print("  PITR = cluster bea-lt-pitr, volumes bea_lt_pitr_* uniquement")

    tests: list[dict] = []
    t41 = test_41()
    tests.append(t41)
    print(f"  4.1 {'OK' if t41['reussi'] else 'KO'}  {t41['detail'][:180]}")

    t42 = test_42_43()
    tests.append(t42)
    print(f"  4.2-4.3 {'OK' if t42['reussi'] else 'KO'}  {t42['detail'][:180]}")
    if not t42["reussi"]:
        ecrire_rapport(tests)
        return 2

    t44 = test_44()
    tests.append(t44)
    print(f"  4.4 {'OK' if t44['reussi'] else 'KO'}  {t44['detail'][:180]}")

    t45 = test_45()
    tests.append(t45)
    print(f"  4.5 {'OK' if t45['reussi'] else 'KO'}  {t45['detail'][:180]}")

    t46 = test_46(t45)
    tests.append(t46)
    print(f"  4.6 {'OK' if t46['reussi'] else 'KO'}  {t46['detail'][:180]}")

    t47 = test_47(t46)
    tests.append(t47)
    print(f"  4.7 {'OK' if t47['reussi'] else 'KO'}  {t47['detail'][:180]}")

    t48 = test_48(mot_de_passe(), "lt.mg.001@loadtest.example.com")
    tests.append(t48)
    print(f"  4.8 {'OK' if t48['reussi'] else 'KO'}  {t48['detail'][:180]}")

    ecrire_rapport(tests)
    ok = all(t["reussi"] for t in tests)
    print(("VALIDATION 4 OK" if ok else "VALIDATION 4 KO") + f" — {DOSSIER / 'rapport.md'}")
    return 0 if ok else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"échec : {exc}")
        try:
            compose_lt(["up", "-d", "--force-recreate", "lt-backend", "lt-worker"])
        except Exception:
            pass
        raise
