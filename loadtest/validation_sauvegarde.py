"""Validation 3 — sauvegarde / restauration PostgreSQL. Isolé uniquement.

    python loadtest/validation_sauvegarde.py

Cible : base de test bea_digital_test sur le conteneur bea-postgres.
Ne touche jamais à bea_digital. Ne fait jamais docker compose down -v.
La pile de charge est reconnectée à la copie restaurée le temps des lectures,
puis rétablie sur bea_digital_test ; la copie restaurée est supprimée à la fin.
"""

from __future__ import annotations

import hashlib
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
SOURCE = "bea_digital_test"
RESTAUREE = "bea_digital_restauration_tmp"
INTERDITES = {"bea_digital"}
PG = "bea-postgres"
DUMP_TMP = f"/tmp/{SOURCE}.dump"
GLOBALS_TMP = "/tmp/pg_globals.sql"
RACINE = Path(__file__).resolve().parent.parent
DOSSIER = Path(__file__).resolve().parent / "reports" / f"validation3-{datetime.now():%Y%m%d-%H%M%S}"
COMPOSE_F = RACINE / "loadtest" / "docker-compose.loadtest.yml"
ENV_LT = RACINE / "loadtest" / ".env.loadtest"
INDEX_UNIQUES = (
    "uq_mg_stock_mouvements_reference",
    "uq_mg_stock_mouvements_cle_idempotence",
    "ix_mg_employee_requests_number",
)
INVENTAIRE_SQL = r"""
SELECT json_build_object(
  'base', current_database(),
  'alembic', (SELECT coalesce(json_agg(version_num ORDER BY version_num), '[]'::json) FROM alembic_version),
  'extensions', (SELECT coalesce(json_agg(json_build_object('name', extname, 'version', extversion) ORDER BY extname), '[]'::json) FROM pg_extension),
  'tables', (SELECT coalesce(json_agg(relname ORDER BY relname), '[]'::json)
             FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = 'public' AND c.relkind = 'r'),
  'views', (SELECT coalesce(json_agg(relname ORDER BY relname), '[]'::json)
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind = 'v'),
  'functions', (SELECT coalesce(json_agg(p.proname ORDER BY p.proname), '[]'::json)
                FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname = 'public'),
  'pk', (SELECT coalesce(json_agg(conname ORDER BY conname), '[]'::json)
         FROM pg_constraint WHERE contype = 'p' AND connamespace = 'public'::regnamespace),
  'fk', (SELECT coalesce(json_agg(conname ORDER BY conname), '[]'::json)
         FROM pg_constraint WHERE contype = 'f' AND connamespace = 'public'::regnamespace),
  'unique_constraints', (SELECT coalesce(json_agg(conname ORDER BY conname), '[]'::json)
                         FROM pg_constraint WHERE contype = 'u' AND connamespace = 'public'::regnamespace),
  'indexes', (SELECT coalesce(json_agg(indexname ORDER BY indexname), '[]'::json)
              FROM pg_indexes WHERE schemaname = 'public'),
  'sequences', (SELECT coalesce(json_agg(json_build_object(
                    'name', sequencename, 'last_value', last_value
                 ) ORDER BY sequencename), '[]'::json)
                FROM pg_sequences WHERE schemaname = 'public'),
  'index_uniques_metier', (SELECT coalesce(json_agg(indexname ORDER BY indexname), '[]'::json)
                           FROM pg_indexes WHERE schemaname = 'public'
                             AND indexname = ANY(ARRAY[
                               'uq_mg_stock_mouvements_reference',
                               'uq_mg_stock_mouvements_cle_idempotence',
                               'ix_mg_employee_requests_number'
                             ]))
);
"""
COUNTS_SQL = r"""
SELECT coalesce(json_object_agg(t.relname, t.n), '{}'::json) FROM (
  SELECT c.relname,
         (xpath('row/c/text()', query_to_xml(
            format('select count(*) as c from %I.%I', n.nspname, c.relname),
            false, true, '')))[1]::text::bigint AS n
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public' AND c.relkind = 'r'
) t;
"""
PRIVS_SQL = """
SELECT json_build_object(
  'connect', has_database_privilege('bea_app', current_database(), 'CONNECT'),
  'users_insert', has_table_privilege('bea_app', 'public.users', 'INSERT'),
  'audit_update', has_table_privilege('bea_app', 'public.audit_logs', 'UPDATE'),
  'alembic_select', has_table_privilege('bea_app', 'public.alembic_version', 'SELECT'),
  'alembic_insert', has_table_privilege('bea_app', 'public.alembic_version', 'INSERT')
);
"""


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


def psql(base: str, sql: str, *, check: bool = True) -> str:
    if base in INTERDITES:
        raise SystemExit(f"ARRÊT : opération refusée sur {base}")
    r = sh(
        ["docker", "exec", "-i", PG, "psql", "-U", "admin", "-d", base, "-X", "-v", "ON_ERROR_STOP=1", "-tA"],
        input_text=sql, check=check,
    )
    return r.stdout.strip()


def env_fichier(chemin: Path, cle: str) -> str:
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        if ligne.startswith(f"{cle}="):
            return ligne.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit(f"{cle} absent de {chemin}")


def mot_de_passe() -> str:
    return env_fichier(ENV_LT, "LOADTEST_PASSWORD")


def mdp_bea_app() -> str:
    return env_fichier(RACINE / ".env.docker", "BEA_APP_DB_PASSWORD")


def compose(args: list[str], extra_file: Path | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["BEA_APP_DB_PASSWORD"] = mdp_bea_app()
    cmd = ["docker", "compose", "-f", str(COMPOSE_F)]
    if extra_file:
        cmd += ["-f", str(extra_file)]
    cmd += ["--env-file", str(ENV_LT), *args]
    return sh(cmd, env=env)


def ecrire_rapport(tests: list[dict]) -> None:
    ok = all(t.get("reussi") for t in tests)
    (DOSSIER / "rapport.json").write_text(
        json.dumps({"ok": ok, "source": SOURCE, "restauree": RESTAUREE, "tests": tests},
                   ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    lignes = [
        "# Validation 3 — sauvegarde et restauration PostgreSQL",
        "",
        f"Source : `{SOURCE}` (conteneur `{PG}`). Restauration : `{RESTAUREE}`.",
        f"`bea_digital` n’a pas été touchée. Dossier : `{DOSSIER.name}`.",
        f"Résultat global : **{'OK' if ok else 'KO'}**.",
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


def diff_listes(avant, apres) -> dict:
    a, b = set(avant or []), set(apres or [])
    return {"manquants": sorted(a - b), "en_trop": sorted(b - a)}


def test_31() -> dict:
    debut = utc()
    version = psql("postgres", "show server_version;")
    nom = docker("inspect", "-f", "{{.Name}} {{.Config.Image}}", PG).stdout.strip()
    sante = docker("inspect", "-f", "{{.State.Health.Status}}", PG).stdout.strip()
    conf = json.loads(psql("postgres", """
        SELECT json_build_object(
          'max_connections', current_setting('max_connections'),
          'shared_buffers', current_setting('shared_buffers'),
          'wal_level', current_setting('wal_level'),
          'archive_mode', current_setting('archive_mode'),
          'data_directory', current_setting('data_directory'),
          'bases', (SELECT json_agg(datname ORDER BY datname) FROM pg_database WHERE datistemplate = false)
        );
    """))
    bases = conf.get("bases") or []
    reussi = (
        sante == "healthy"
        and SOURCE in bases
        and "bea_digital" in bases
        and version.startswith("17")
        and PG in nom
    )
    return {
        "id": "3.1", "titre": "Identifier version PostgreSQL et configuration",
        "debut": debut, "fin": utc(), "reussi": reussi,
        "detail": (
            f"conteneur={nom} santé={sante} version={version} "
            f"wal_level={conf.get('wal_level')} archive_mode={conf.get('archive_mode')} "
            f"max_connections={conf.get('max_connections')} bases={bases}"
        ),
        "version": version, "conf": conf,
    }


def _pauser_ecritures() -> None:
    docker("unpause", "bea-lt-backend", check=False)
    docker("unpause", "bea-lt-worker", check=False)
    docker("pause", "bea-lt-backend")
    docker("pause", "bea-lt-worker")


def _relacher_ecritures() -> None:
    docker("unpause", "bea-lt-backend", check=False)
    docker("unpause", "bea-lt-worker", check=False)


def test_32(inventaire_src: dict, counts_src: dict) -> dict:
    debut = utc()
    docker("exec", PG, "pg_dump", "-U", "admin", "-Fc", "-d", SOURCE, "-f", DUMP_TMP)
    docker("exec", PG, "pg_dumpall", "-U", "admin", "--globals-only", "-f", GLOBALS_TMP)
    taille = docker("exec", PG, "stat", "-c", "%s", DUMP_TMP).stdout.strip()
    dump_host = DOSSIER / f"{SOURCE}.dump"
    glob_host = DOSSIER / "globals.sql"
    docker("cp", f"{PG}:{DUMP_TMP}", str(dump_host))
    docker("cp", f"{PG}:{GLOBALS_TMP}", str(glob_host))
    sha = hashlib.sha256(dump_host.read_bytes()).hexdigest()
    roles = []
    for ligne in glob_host.read_text(encoding="utf-8", errors="replace").splitlines():
        if ligne.startswith("CREATE ROLE "):
            roles.append(ligne.split()[2].rstrip(";"))
    # Ne pas conserver les hachages de mots de passe dans le dossier de rapport.
    glob_host.unlink(missing_ok=True)
    (DOSSIER / "roles-globaux.json").write_text(
        json.dumps({"roles": roles, "note": "pg_dumpall --globals-only ; hachages non conservés"},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    backups = RACINE / "backups" / DOSSIER.name
    backups.mkdir(parents=True, exist_ok=True)
    (backups / dump_host.name).write_bytes(dump_host.read_bytes())
    reussi = dump_host.exists() and dump_host.stat().st_size > 10_000 and "bea_app" in roles
    return {
        "id": "3.2", "titre": "Sauvegarder la base (pg_dump -Fc)",
        "debut": debut, "fin": utc(), "reussi": reussi,
        "detail": (
            f"fichier={dump_host.name} octets={taille} sha256={sha} "
            f"roles_globaux={roles} copie=backups/{DOSSIER.name}/"
        ),
        "octets": int(taille), "sha256": sha, "roles": roles,
        "inventaire": inventaire_src, "counts": counts_src,
    }


def test_33() -> dict:
    debut = utc()
    listing = docker("exec", PG, "pg_restore", "-l", DUMP_TMP)
    lignes = [ln for ln in listing.stdout.splitlines() if ln.strip() and not ln.startswith(";")]
    (DOSSIER / "pg_restore-list.txt").write_text(listing.stdout, encoding="utf-8")
    tables = [ln for ln in lignes if " TABLE " in ln and " TABLE DATA " not in ln]
    uniques = [name for name in INDEX_UNIQUES if name in listing.stdout]
    alembic = "alembic_version" in listing.stdout
    reussi = listing.returncode == 0 and len(lignes) > 50 and alembic and len(uniques) == len(INDEX_UNIQUES)
    return {
        "id": "3.3", "titre": "Vérifier que la sauvegarde est exploitable",
        "debut": debut, "fin": utc(), "reussi": reussi,
        "detail": (
            f"toc={len(lignes)} tables={len(tables)} alembic={alembic} "
            f"index_uniques={uniques}"
        ),
        "toc": len(lignes),
    }


def test_34() -> dict:
    debut = utc()
    existe = psql("postgres", f"select 1 from pg_database where datname = '{RESTAUREE}';")
    if existe == "1":
        psql("postgres",
             f"select pg_terminate_backend(pid) from pg_stat_activity where datname = '{RESTAUREE}';")
        psql("postgres", f"drop database {RESTAUREE};")
    loc = psql("postgres",
               f"select datcollate || '|' || datctype || '|' || pg_encoding_to_char(encoding) "
               f"from pg_database where datname = '{SOURCE}';")
    collate, ctype, enc = loc.split("|")
    psql("postgres",
         f"create database {RESTAUREE} owner admin template template0 "
         f"encoding '{enc}' lc_collate '{collate}' lc_ctype '{ctype}';")
    verif = psql("postgres", f"select 1 from pg_database where datname = '{RESTAUREE}';")
    return {
        "id": "3.4", "titre": "Créer une base vierge de restauration",
        "debut": debut, "fin": utc(), "reussi": verif == "1",
        "detail": f"{RESTAUREE} encodage={enc} collate={collate} ctype={ctype}",
    }


def test_35() -> dict:
    debut = utc()
    r = docker(
        "exec", PG, "pg_restore", "-U", "admin",
        f"--dbname={RESTAUREE}", "--verbose", DUMP_TMP,
        check=False,
    )
    log = (r.stdout or "") + "\n" + (r.stderr or "")
    (DOSSIER / "pg_restore.log").write_text(log, encoding="utf-8")
    erreurs = [ln for ln in log.splitlines() if "ERROR" in ln]
    # CONNECT n'est pas dans le dump de base : c'est un privilège global sur l'objet DATABASE.
    psql("postgres", f"grant connect, temporary on database {RESTAUREE} to bea_app;")
    n_tables = int(psql(RESTAUREE,
                        "select count(*) from information_schema.tables "
                        "where table_schema = 'public' and table_type = 'BASE TABLE';") or 0)
    reussi = n_tables > 50 and not erreurs
    return {
        "id": "3.5", "titre": "Restaurer le dump dans la base vierge",
        "debut": debut, "fin": utc(), "reussi": reussi,
        "detail": (
            f"rc={r.returncode} erreurs={len(erreurs)} tables={n_tables} "
            f"grant_connect=bea_app (hors dump, privilège DATABASE)"
        ),
        "erreurs": erreurs[:20], "n_tables": n_tables,
    }


def test_36(inv_src: dict, counts_src: dict) -> dict:
    debut = utc()
    inv_dst = json.loads(psql(RESTAUREE, INVENTAIRE_SQL))
    counts_dst = json.loads(psql(RESTAUREE, COUNTS_SQL))
    privs = json.loads(psql(RESTAUREE, PRIVS_SQL))
    (DOSSIER / "inventaire-source.json").write_text(
        json.dumps({"inventaire": inv_src, "counts": counts_src}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (DOSSIER / "inventaire-restaure.json").write_text(
        json.dumps({"inventaire": inv_dst, "counts": counts_dst, "privileges": privs},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    diffs = {}
    for cle in ("tables", "views", "functions", "pk", "fk", "unique_constraints", "indexes", "alembic", "extensions"):
        diffs[cle] = diff_listes(
            inv_src.get(cle) if cle != "extensions" else [e["name"] for e in inv_src.get("extensions") or []],
            inv_dst.get(cle) if cle != "extensions" else [e["name"] for e in inv_dst.get("extensions") or []],
        )
        if cle == "alembic":
            diffs[cle] = diff_listes(inv_src.get("alembic"), inv_dst.get("alembic"))
    seq_src = {s["name"]: s for s in inv_src.get("sequences") or []}
    seq_dst = {s["name"]: s for s in inv_dst.get("sequences") or []}
    seq_diff = {
        "manquants": sorted(set(seq_src) - set(seq_dst)),
        "en_trop": sorted(set(seq_dst) - set(seq_src)),
        "valeurs": [
            {"name": n, "source": seq_src[n], "restaure": seq_dst[n]}
            for n in sorted(set(seq_src) & set(seq_dst))
            if seq_src[n].get("last_value") != seq_dst[n].get("last_value")
        ],
    }
    counts_diff = {
        k: {"source": counts_src.get(k), "restaure": counts_dst.get(k)}
        for k in sorted(set(counts_src) | set(counts_dst))
        if counts_src.get(k) != counts_dst.get(k)
    }
    uniques_ok = set(inv_dst.get("index_uniques_metier") or []) == set(INDEX_UNIQUES)
    schema_ok = all(not d["manquants"] and not d["en_trop"] for d in diffs.values())
    seq_ok = not seq_diff["manquants"] and not seq_diff["en_trop"] and not seq_diff["valeurs"]
    counts_ok = not counts_diff
    privs_ok = (
        privs.get("connect") is True
        and privs.get("users_insert") is True
        and privs.get("audit_update") is False
        and privs.get("alembic_select") is True
        and privs.get("alembic_insert") is False
    )
    reussi = schema_ok and seq_ok and counts_ok and uniques_ok and privs_ok
    return {
        "id": "3.6", "titre": "Contrôler données, contraintes, index, séquences",
        "debut": debut, "fin": utc(), "reussi": reussi,
        "detail": (
            f"schema_ok={schema_ok} sequences_ok={seq_ok} counts_diff={len(counts_diff)} "
            f"uniques={sorted(inv_dst.get('index_uniques_metier') or [])} "
            f"privileges={privs} alembic={inv_dst.get('alembic')}"
        ),
        "diffs": diffs, "seq_diff": seq_diff, "counts_diff": counts_diff, "privileges": privs,
    }


def _attendre_sante(timeout: int = 45) -> bool:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        try:
            if requests.get(f"{HOTE}/health", timeout=3).status_code == 200:
                r = requests.get(f"{HOTE}/health/ready", timeout=3)
                if r.status_code == 200:
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False


def _sondes_app(password: str, email: str) -> dict:
    out: dict = {}
    try:
        h = requests.get(f"{HOTE}/health", timeout=10)
        out["health"] = h.status_code
        ready = requests.get(f"{HOTE}/health/ready", timeout=10)
        out["ready"] = ready.status_code
        login = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
        out["login"] = login.status_code
        if login.status_code != 200:
            out["login_corps"] = login.text[:300]
            return out
        tokens = login.json()
        me = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}, timeout=15)
        out["me"] = me.status_code
        mod = requests.post(
            f"{API}/auth/modules/stock-fournitures/login",
            json={"email": email, "password": password},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
            timeout=20,
        )
        out["login2"] = mod.status_code
        if mod.status_code != 200:
            out["login2_corps"] = mod.text[:300]
            return out
        mh = {"Authorization": f"Bearer {mod.json()['access_token']}"}
        dash = requests.get(f"{API}/mg/stock/dashboard", headers=mh, timeout=20)
        out["dashboard"] = dash.status_code
        mvts = requests.get(f"{API}/mg/stock/mouvements", headers=mh, timeout=20)
        out["mouvements"] = mvts.status_code
        refs = requests.get(f"{API}/mg/stock/entrees/referentiels", headers=mh, timeout=20)
        out["referentiels"] = refs.status_code
        n_mvt = psql(RESTAUREE, "select count(*) from mg_stock_mouvements;")
        n_users = psql(RESTAUREE, "select count(*) from users;")
        ref_val2 = psql(RESTAUREE, "select count(*) from mg_stock_mouvements where reference = 'ENT-2026-02754';")
        out["postgres"] = {"mouvements": n_mvt, "users": n_users, "ent_val2": ref_val2}
    except Exception as exc:
        out["erreur"] = f"{type(exc).__name__}: {exc}"
    return out


def _url_backend() -> str:
    r = docker("exec", "bea-lt-backend", "printenv", "DATABASE_URL", check=False)
    return (r.stdout or "").strip()


def test_37(password: str, email: str) -> dict:
    debut = utc()
    override = DOSSIER / "compose-restore-test.yml"
    override.write_text(
        "services:\n"
        "  lt-backend:\n"
        "    environment:\n"
        "      DATABASE_URL: postgresql+asyncpg://bea_app:${BEA_APP_DB_PASSWORD}@postgres:5432/"
        f"{RESTAUREE}\n"
        "  lt-worker:\n"
        "    environment:\n"
        "      DATABASE_URL: postgresql+asyncpg://bea_app:${BEA_APP_DB_PASSWORD}@postgres:5432/"
        f"{RESTAUREE}\n",
        encoding="ascii",
    )
    sondes: dict = {}
    url_pendant = ""
    url_apres = ""
    sante_ok = False
    try:
        compose(["up", "-d", "--force-recreate", "lt-backend", "lt-worker"], extra_file=override)
        sante_ok = _attendre_sante(60)
        url_pendant = _url_backend()
        sondes = _sondes_app(password, email)
    finally:
        compose(["up", "-d", "--force-recreate", "lt-backend", "lt-worker"])
        _attendre_sante(60)
        url_apres = _url_backend()
    codes = [sondes.get(k) for k in ("health", "ready", "login", "me", "login2", "dashboard", "mouvements", "referentiels")]
    app_ok = sante_ok and all(c == 200 for c in codes)
    bonne_base = url_pendant.endswith("/" + RESTAUREE) and url_apres.endswith("/" + SOURCE)
    reussi = app_ok and bonne_base and "erreur" not in sondes
    return {
        "id": "3.7", "titre": "Reconnecter BEA DIGITAL à la base restaurée (lectures)",
        "debut": debut, "fin": utc(), "reussi": reussi,
        "detail": (
            f"sante={sante_ok} sondes={ {k: sondes.get(k) for k in ('health','ready','login','me','login2','dashboard','mouvements','referentiels')} } "
            f"url_pendant_ok={RESTAUREE in url_pendant} url_apres_ok={SOURCE in url_apres} "
            f"postgres={sondes.get('postgres')}"
        ),
        "sondes": sondes,
        "base_pendant": RESTAUREE if RESTAUREE in url_pendant else "?",
        "base_apres": SOURCE if SOURCE in url_apres else "?",
    }


def main() -> int:
    DOSSIER.mkdir(parents=True, exist_ok=True)
    if psql(SOURCE, "select current_database();") != SOURCE:
        print("ARRÊT : pas sur la base de charge")
        return 1
    if psql("postgres", "select 1 from pg_database where datname = 'bea_digital';") != "1":
        print("ARRÊT : bea_digital absente — on refuse de continuer sans pouvoir la protéger")
        return 1
    print(f"Validation 3 → {DOSSIER}")
    print(f"  PostgreSQL = conteneur Docker {PG} (pas une install Windows)")
    print(f"  source={SOURCE}  restauration={RESTAUREE}  bea_digital=intouchable")

    tests: list[dict] = []
    t31 = test_31()
    tests.append(t31)
    print(f"  3.1 {'OK' if t31['reussi'] else 'KO'}  {t31['detail'][:180]}")
    if not t31["reussi"]:
        ecrire_rapport(tests)
        return 2

    try:
        _pauser_ecritures()
        journal({"etape": "3.2", "action": "pause backend+worker"})
        # Seed loadtest : exercices_comptables copié sans archive_dossiers
        # (disable-triggers). Une FK orpheline empêche pg_restore d'ajouter
        # la contrainte. ON DELETE SET NULL = même sémantique que la FK.
        orphelins = psql(SOURCE, """
            update exercices_comptables e
               set archive_dossier_id = null
             where archive_dossier_id is not null
               and not exists (select 1 from archive_dossiers a where a.id = e.archive_dossier_id)
            returning id::text;
        """)
        journal({"etape": "3.2", "action": "null_archive_dossier_orphelin", "ids": orphelins})
        inv_src = json.loads(psql(SOURCE, INVENTAIRE_SQL))
        counts_src = json.loads(psql(SOURCE, COUNTS_SQL))
        t32 = test_32(inv_src, counts_src)
    finally:
        _relacher_ecritures()
        journal({"etape": "3.2", "action": "unpause backend+worker"})
    tests.append(t32)
    print(f"  3.2 {'OK' if t32['reussi'] else 'KO'}  {t32['detail'][:180]}")

    t33 = test_33()
    tests.append(t33)
    print(f"  3.3 {'OK' if t33['reussi'] else 'KO'}  {t33['detail'][:180]}")

    t34 = test_34()
    tests.append(t34)
    print(f"  3.4 {'OK' if t34['reussi'] else 'KO'}  {t34['detail'][:180]}")

    t35 = test_35()
    tests.append(t35)
    print(f"  3.5 {'OK' if t35['reussi'] else 'KO'}  {t35['detail'][:180]}")

    t36 = test_36(inv_src, counts_src)
    tests.append(t36)
    print(f"  3.6 {'OK' if t36['reussi'] else 'KO'}  {t36['detail'][:180]}")

    t37 = test_37(mot_de_passe(), "lt.mg.001@loadtest.example.com")
    tests.append(t37)
    print(f"  3.7 {'OK' if t37['reussi'] else 'KO'}  {t37['detail'][:180]}")

    if RESTAUREE not in INTERDITES | {SOURCE}:
        psql("postgres", f"select pg_terminate_backend(pid) from pg_stat_activity where datname = '{RESTAUREE}';")
        psql("postgres", f"drop database if exists {RESTAUREE};")
        journal({"etape": "fin", "action": "suppression_copie_restauree", "base": RESTAUREE})
        print(f"  copie restaurée {RESTAUREE} supprimée")

    ecrire_rapport(tests)
    ok = all(t["reussi"] for t in tests)
    print(("VALIDATION 3 OK" if ok else "VALIDATION 3 KO") + f" — {DOSSIER / 'rapport.md'}")
    return 0 if ok else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"échec : {exc}")
        try:
            _relacher_ecritures()
            compose(["up", "-d", "--force-recreate", "lt-backend", "lt-worker"])
        except Exception:
            pass
        raise
