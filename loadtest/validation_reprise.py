"""Validation 2 — reprise après incident. Environnement isolé uniquement.

    python loadtest/validation_reprise.py

Cible : http://127.0.0.1:8081 (bea_digital_loadtest). N'arrête jamais tous les
processus backend à la fois, ni PostgreSQL (validation 3). WEB_CONCURRENCY et
pools inchangés.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

HOTE = "http://127.0.0.1:8081"
API = f"{HOTE}/api/v1"
BASE = "bea_digital_loadtest"
MARQUE = "LT-REPRISE"
TIMEOUT = 5
RACINE = Path(__file__).resolve().parent.parent
DOSSIER = Path(__file__).resolve().parent / "reports" / f"validation2-{datetime.now():%Y%m%d-%H%M%S}"


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def journal(entree: dict) -> None:
    DOSSIER.mkdir(parents=True, exist_ok=True)
    chemin = DOSSIER / "journal.jsonl"
    with chemin.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": utc(), **entree}, ensure_ascii=False) + "\n")


def sh(args: list[str], *, check: bool = True, input_text: str | None = None) -> subprocess.CompletedProcess:
    r = subprocess.run(args, input=input_text, text=True, capture_output=True, check=False)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} → {r.returncode}\n{r.stderr or r.stdout}")
    return r


def psql(sql: str) -> str:
    r = sh(["docker", "exec", "-i", "bea-postgres", "psql", "-U", "admin", "-d", BASE, "-X", "-v", "ON_ERROR_STOP=1", "-tA"],
           input_text=sql)
    return r.stdout.strip()


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return sh(["docker", *args], check=check)


def mot_de_passe() -> str:
    env = Path(__file__).resolve().parent / ".env.loadtest"
    for ligne in env.read_text(encoding="utf-8").splitlines():
        if ligne.startswith("LOADTEST_PASSWORD="):
            return ligne.split("=", 1)[1].strip()
    raise SystemExit("LOADTEST_PASSWORD absent")


def sante(timeout: float = TIMEOUT) -> dict:
    try:
        r = requests.get(f"{HOTE}/health", timeout=timeout)
        return {"ok": r.status_code == 200, "status": r.status_code, "ms": r.elapsed.total_seconds() * 1000}
    except Exception as exc:
        return {"ok": False, "status": 0, "erreur": type(exc).__name__}


def pret() -> dict:
    try:
        r = requests.get(f"{HOTE}/health/ready", timeout=TIMEOUT)
        return {"status": r.status_code, "corps": r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text[:200]}
    except Exception as exc:
        return {"status": 0, "erreur": type(exc).__name__}


def pids_workers() -> list[int]:
    code = (
        "import pathlib\n"
        "for p in pathlib.Path('/proc').iterdir():\n"
        "    if p.name.isdigit():\n"
        "        try:\n"
        "            cmd = (p / 'cmdline').read_bytes().replace(bytes([0]), b' ').decode(errors='replace')\n"
        "        except Exception:\n"
        "            continue\n"
        "        if 'spawn_main' in cmd:\n"
        "            print(p.name)\n"
    )
    r = docker("exec", "bea-lt-backend", "python", "-c", code)
    return [int(x) for x in r.stdout.split() if x.isdigit()]


def login(email: str, password: str) -> dict:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    r.raise_for_status()
    return r.json()


def login_module(tokens: dict, password: str, email: str, module: str = "stock-fournitures") -> dict:
    r = requests.post(
        f"{API}/auth/modules/{module}/login",
        json={"email": email, "password": password},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()


def sonder(n: int = 24, timeout: float = TIMEOUT) -> dict:
    ok = ko = 0
    codes: dict[str, int] = {}
    debut = time.monotonic()
    for _ in range(n):
        s = sante(timeout=timeout)
        cle = str(s.get("status") or s.get("erreur") or "?")
        codes[cle] = codes.get(cle, 0) + 1
        if s.get("ok"):
            ok += 1
        else:
            ko += 1
    return {"ok": ok, "ko": ko, "codes": codes, "duree_s": round(time.monotonic() - debut, 2)}


def refs_stock(module_tokens: dict) -> dict:
    h = {"Authorization": f"Bearer {module_tokens['access_token']}"}
    e = requests.get(f"{API}/mg/stock/entrees/referentiels", headers=h, timeout=20).json()
    articles = sorted(e.get("articles") or [], key=lambda a: float(a.get("stock_actuel") or 0), reverse=True)
    motif = next((m for m in (e.get("motifs") or []) if m.get("is_active")), None)
    return {"article": articles[0], "motif": motif}


def creer_entree(module_tokens: dict, refs: dict, *, cle: str, observation: str) -> requests.Response:
    return requests.post(
        f"{API}/mg/stock/entrees",
        json={
            "article_id": refs["article"]["id"],
            "quantite": 1,
            "provenance_type": "AUTRE",
            "motif_id": refs["motif"]["id"],
            "observation": observation,
            "remis_par": "validation-2",
        },
        headers={
            "Authorization": f"Bearer {module_tokens['access_token']}",
            "Idempotency-Key": cle,
        },
        timeout=20,
    )


def file_celery() -> dict:
    r = docker("exec", "bea-lt-redis", "redis-cli", "llen", "celery", check=False)
    return {"llen_celery": (r.stdout or "").strip(), "rc": r.returncode}


def signal_worker(pid: int, sig: str) -> None:
    docker(
        "exec", "bea-lt-backend", "python", "-c",
        f"import os, signal; os.kill({int(pid)}, signal.SIG{sig})",
    )


def taches_celery() -> str:
    r = docker("logs", "bea-lt-worker", "--tail", "30", check=False)
    return (r.stdout or "") + (r.stderr or "")


def ecrire_rapport(tests: list[dict]) -> None:
    ok = all(t.get("reussi") for t in tests)
    data = {"ok": ok, "hote": HOTE, "base": BASE, "tests": tests}
    (DOSSIER / "rapport.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    lignes = [
        "# Validation 2 — reprise après incident",
        "",
        f"Cible isolée : `{HOTE}` / `{BASE}`. Dossier : `{DOSSIER.name}`.",
        f"Résultat global : **{'OK' if ok else 'KO'}**.",
        "",
    ]
    for t in tests:
        lignes.append(f"## {t['id']} — {t['titre']}")
        lignes.append("")
        lignes.append(f"- Incident : {t.get('debut')}")
        lignes.append(f"- Reprise : {t.get('reprise')}")
        lignes.append(f"- Réussi : {'oui' if t.get('reussi') else 'non'}")
        if t.get("detail"):
            lignes.append(f"- Détail : {t['detail']}")
        if t.get("http"):
            lignes.append(f"- HTTP : {t['http']}")
        if t.get("celery"):
            lignes.append(f"- Celery : {t['celery']}")
        if t.get("postgres"):
            lignes.append(f"- PostgreSQL : {t['postgres']}")
        if t.get("cles"):
            lignes.append(f"- Clés / références : {t['cles']}")
        if t.get("delai_s") is not None:
            lignes.append(f"- Retour à la normale : {t['delai_s']} s")
        lignes.append("")
    (DOSSIER / "rapport.md").write_text("\n".join(lignes), encoding="utf-8")


def test_21() -> dict:
    """Arrêt (STOP) d'un worker uvicorn sur quatre."""
    debut = utc()
    workers = pids_workers()
    if len(workers) < 2:
        return {"id": "2.1", "titre": "Arrêt d'un processus backend", "debut": debut,
                "reussi": False, "detail": f"moins de 2 workers : {workers}"}
    victime = workers[0]
    avant = sonder(12)
    signal_worker(victime, "STOP")
    journal({"etape": "2.1", "action": "SIGSTOP", "pid": victime, "workers": workers})
    pendant = sonder(20, timeout=3)
    # Ne pas tuer les autres : on laisse le STOP jusqu'au 2.2, mais on vérifie déjà.
    reussi = pendant["ok"] >= 1 and pendant["ok"] + pendant["ko"] == 20
    return {
        "id": "2.1", "titre": "Arrêt d'un processus backend sur quatre",
        "debut": debut, "reprise": None, "reussi": reussi,
        "detail": f"pid={victime} ; santé avant {avant} ; pendant STOP {pendant} ; "
                  f"{len(workers)} workers (les autres doivent encore répondre)",
        "victime": victime, "workers": workers, "avant": avant, "pendant": pendant,
        "http": f"avant={avant} pendant={pendant}",
        "postgres": "non touché (sondes /health uniquement)",
    }


def test_22(etat_21: dict) -> dict:
    debut = utc()
    victime = etat_21.get("victime")
    if not victime:
        return {"id": "2.2", "titre": "Redémarrage du processus arrêté", "debut": debut,
                "reussi": False, "detail": "pas de pid victime (2.1 incomplet)"}
    signal_worker(victime, "CONT")
    t0 = time.monotonic()
    ok = False
    for _ in range(20):
        if sante(timeout=3).get("ok"):
            ok = True
            break
        time.sleep(0.5)
    apres = sonder(12)
    encore = pids_workers()
    return {
        "id": "2.2", "titre": "Redémarrage du processus arrêté (SIGCONT)",
        "debut": etat_21["debut"], "reprise": utc(),
        "reussi": ok and apres["ok"] == 12 and victime in encore,
        "detail": f"retour santé en {time.monotonic() - t0:.1f}s ; après {apres} ; workers {encore}",
        "apres": apres, "workers": encore,
        "http": f"après CONT {apres}",
        "delai_s": round(time.monotonic() - t0, 1),
    }


def test_23(password: str) -> dict:
    debut = utc()
    docker("stop", "bea-lt-worker")
    journal({"etape": "2.3", "action": "stop worker"})
    # Enfile une tâche pendant l'arrêt : elle doit rester dans Redis.
    envoyer = docker(
        "exec", "-e", "PYTHONPATH=/app", "bea-lt-backend", "python", "-c",
        "from app.workers.celery_app import celery_app; r=celery_app.send_task('app.workers.tasks.ping'); print(r.id)",
        check=False,
    )
    task_id = (envoyer.stdout or "").strip()
    file_avant = file_celery()
    docker("start", "bea-lt-worker")
    t0 = time.monotonic()
    pret_w = False
    for _ in range(30):
        logs = taches_celery()
        if "ready." in logs or "celery@" in logs:
            pret_w = True
            break
        time.sleep(1)
    # Résultat de la tâche
    resultat = docker(
        "exec", "-e", "PYTHONPATH=/app", "bea-lt-backend", "python", "-c",
        f"from app.workers.celery_app import celery_app; "
        f"r=celery_app.AsyncResult('{task_id}'); print(r.state, r.result)",
        check=False,
    )
    for _ in range(20):
        resultat = docker(
            "exec", "-e", "PYTHONPATH=/app", "bea-lt-backend", "python", "-c",
            f"from app.workers.celery_app import celery_app; "
            f"r=celery_app.AsyncResult('{task_id}'); print(r.state, r.result)",
            check=False,
        )
        if "SUCCESS" in (resultat.stdout or "") or "pong" in (resultat.stdout or ""):
            break
        time.sleep(0.5)
    file_apres = file_celery()
    sorti = (resultat.stdout or "") + (resultat.stderr or "")
    reussi = pret_w and ("SUCCESS" in sorti or "pong" in sorti)
    return {
        "id": "2.3", "titre": "Arrêt du worker Celery puis reprise",
        "debut": debut, "reprise": utc(), "reussi": reussi,
        "detail": f"task={task_id} file_avant={file_avant} résultat={sorti.strip()[:200]} "
                  f"file_apres={file_apres} ready_en={time.monotonic() - t0:.1f}s",
        "task_id": task_id, "file_avant": file_avant, "resultat": sorti.strip()[:400],
        "celery": f"id={task_id} file_avant={file_avant} resultat={sorti.strip()[:120]} file_apres={file_apres}",
        "delai_s": round(time.monotonic() - t0, 1),
    }


def test_24(password: str, email: str) -> dict:
    debut = utc()
    docker("pause", "bea-lt-redis")
    journal({"etape": "2.4", "action": "pause redis"})
    time.sleep(1)
    ready_ko = pret()
    sondes = []
    for _ in range(8):
        try:
            r = requests.post(
                f"{API}/auth/login",
                json={"email": email, "password": password},
                timeout=15,
            )
            sondes.append({"status": r.status_code, "limite": r.headers.get("X-RateLimit-Remaining")})
        except Exception as exc:
            sondes.append({"status": 0, "erreur": type(exc).__name__})
    docker("unpause", "bea-lt-redis")
    time.sleep(1)
    ready_ok = pret()
    # Limiteur partagé de nouveau
    partage = docker(
        "exec", "bea-lt-backend", "python", "-c",
        "import asyncio\n"
        "from app.middleware import rate_limit as rl\n"
        "async def m():\n"
        "    print(await rl._hit_partage('test:val2', limit=5))\n"
        "asyncio.run(m())\n",
        check=False,
    )
    login_ok = any(s.get("status") == 200 for s in sondes)
    redis_degrade = (ready_ko.get("status") == 503) or (
        isinstance(ready_ko.get("corps"), dict)
        and (ready_ko.get("corps") or {}).get("checks", {}).get("redis", {}).get("status") == "ko"
    )
    redis_revient = ready_ok.get("status") == 200
    return {
        "id": "2.4", "titre": "Indisponibilité temporaire de Redis",
        "debut": debut, "reprise": utc(),
        "reussi": login_ok and redis_revient,
        "detail": f"ready pendant pause={ready_ko} ; logins={sondes} ; ready après={ready_ok} ; "
                  f"limiteur={ (partage.stdout or '')[:120] } ; redis_degrade_signale={redis_degrade}",
        "ready_pause": ready_ko, "logins": sondes, "ready_apres": ready_ok,
        "http": f"ready_pause={ready_ko.get('status')} logins={[s.get('status') for s in sondes]} ready_apres={ready_ok.get('status')}",
    }


def test_25(password: str, email: str) -> dict:
    debut = utc()
    plat = login(email, password)
    mod = login_module(plat, password, email)
    refs = refs_stock(mod)
    cle = f"lt-reprise-{uuid.uuid4()}"
    obs = f"{MARQUE} {uuid.uuid4()}"
    # Première tentative volontairement trop courte : simule une interruption client.
    try:
        requests.post(
            f"{API}/mg/stock/entrees",
            json={
                "article_id": refs["article"]["id"],
                "quantite": 1,
                "provenance_type": "AUTRE",
                "motif_id": refs["motif"]["id"],
                "observation": obs,
                "remis_par": "validation-2",
            },
            headers={
                "Authorization": f"Bearer {mod['access_token']}",
                "Idempotency-Key": cle,
            },
            timeout=0.05,
        )
        interrompu = "termine_quand_meme"
    except Exception as exc:
        interrompu = type(exc).__name__
    # Rejeu immédiat : 409 DUPLICATE_REQUEST si le 1er est encore en cours (doc).
    r_cours = creer_entree(mod, refs, cle=cle, observation=obs)
    n = 0
    for _ in range(40):
        n = int(psql(
            f"select count(*) from mg_stock_mouvements "
            f"where cle_idempotence = '{cle}' or observation = '{obs}';"
        ) or 0)
        if n >= 1:
            break
        time.sleep(0.25)
    r_apres = creer_entree(mod, refs, cle=cle, observation=obs)
    n = int(psql(
        f"select count(*) from mg_stock_mouvements "
        f"where cle_idempotence = '{cle}' or observation = '{obs}';"
    ) or 0)
    ids = psql(
        f"select coalesce(json_agg(id::text), '[]') from mg_stock_mouvements "
        f"where cle_idempotence = '{cle}' or observation = '{obs}';"
    )
    refs_pg = psql(
        f"select coalesce(json_agg(reference), '[]') from mg_stock_mouvements "
        f"where cle_idempotence = '{cle}' or observation = '{obs}';"
    )
    replayed = r_apres.headers.get("Idempotent-Replayed")
    # Une seule ligne ; après fin du 1er, le rejeu renvoie 200/201 (cache Redis
    # ou service). 409 pendant le traitement n'est pas un doublon.
    reussi = n == 1 and r_apres.status_code in {200, 201}
    return {
        "id": "2.5", "titre": "Rejeu après interruption (une seule opération)",
        "debut": debut, "reprise": utc(), "reussi": reussi,
        "detail": (
            f"interruption={interrompu} ; en_cours={r_cours.status_code} ; "
            f"apres={r_apres.status_code} replayed={replayed} ; "
            f"lignes={n} ids={ids} refs={refs_pg} cle={cle}"
        ),
        "n": n, "cle": cle, "status": [r_cours.status_code, r_apres.status_code],
        "http": (
            f"1er={interrompu} ; pendant={r_cours.status_code} ; "
            f"rejeu={r_apres.status_code} Idempotent-Replayed={replayed}"
        ),
        "postgres": f"{n} mouvement(s) {ids}",
        "cles": f"Idempotency-Key={cle} references={refs_pg}",
    }


def test_26(password: str, email: str) -> dict:
    debut = utc()
    # Plusieurs composants, pas PostgreSQL, pas les 4 workers tués un par un sans master.
    docker("restart", "bea-lt-backend")
    docker("restart", "bea-lt-worker")
    docker("restart", "bea-lt-frontend")
    t0 = time.monotonic()
    ok = False
    for _ in range(40):
        if sante(timeout=3).get("ok") and pret().get("status") == 200:
            ok = True
            break
        time.sleep(1)
    delai = round(time.monotonic() - t0, 1)
    login_ok = False
    try:
        login(email, password)
        login_ok = True
    except Exception:
        login_ok = False
    ping = docker(
        "exec", "-e", "PYTHONPATH=/app", "bea-lt-backend", "python", "-c",
        "from app.workers.celery_app import celery_app; r=celery_app.send_task('app.workers.tasks.ping'); print(r.id)",
        check=False,
    )
    task_id = (ping.stdout or "").strip()
    ping_ok = False
    for _ in range(25):
        res = docker(
            "exec", "-e", "PYTHONPATH=/app", "bea-lt-backend", "python", "-c",
            f"from app.workers.celery_app import celery_app; "
            f"r=celery_app.AsyncResult('{task_id}'); print(r.state, r.result)",
            check=False,
        )
        if "pong" in (res.stdout or "") or "SUCCESS" in (res.stdout or ""):
            ping_ok = True
            break
        time.sleep(0.5)
    workers = pids_workers()
    return {
        "id": "2.6", "titre": "Redémarrage backend + worker + nginx (pas PostgreSQL)",
        "debut": debut, "reprise": utc(),
        "reussi": ok and login_ok and ping_ok and len(workers) >= 2,
        "detail": f"santé+ready en {delai}s ; login={login_ok} ; ping={ping_ok} "
                  f"({task_id}) ; workers={workers}",
        "delai_s": delai, "workers": workers,
        "http": f"santé+ready={'ok' if ok else 'ko'} login={login_ok}",
        "celery": f"ping={ping_ok} id={task_id}",
    }


def main() -> int:
    if psql("select current_database();") != BASE:
        print("ARRÊT : pas sur la base de charge")
        return 1
    try:
        requests.get(f"{HOTE}/health", timeout=5).raise_for_status()
    except Exception:
        print(f"{HOTE} ne répond pas")
        return 1
    password = mot_de_passe()
    email = "lt.mg.001@loadtest.example.com"
    DOSSIER.mkdir(parents=True, exist_ok=True)
    print(f"Validation 2 → {DOSSIER}  (cible {HOTE})")

    tests: list[dict] = []
    t21 = test_21()
    tests.append(t21)
    print(f"  2.1 {'OK' if t21['reussi'] else 'KO'}  {t21['detail'][:160]}")
    t22 = test_22(t21)
    tests.append(t22)
    print(f"  2.2 {'OK' if t22['reussi'] else 'KO'}  {t22['detail'][:160]}")
    t23 = test_23(password)
    tests.append(t23)
    print(f"  2.3 {'OK' if t23['reussi'] else 'KO'}  {t23['detail'][:160]}")
    t24 = test_24(password, email)
    tests.append(t24)
    print(f"  2.4 {'OK' if t24['reussi'] else 'KO'}  {t24['detail'][:160]}")
    t25 = test_25(password, email)
    tests.append(t25)
    print(f"  2.5 {'OK' if t25['reussi'] else 'KO'}  {t25['detail'][:160]}")
    t26 = test_26(password, email)
    tests.append(t26)
    print(f"  2.6 {'OK' if t26['reussi'] else 'KO'}  {t26['detail'][:160]}")

    ecrire_rapport(tests)
    ok = all(t["reussi"] for t in tests)
    print(("VALIDATION 2 OK" if ok else "VALIDATION 2 KO") + f" — {DOSSIER / 'rapport.md'}")
    return 0 if ok else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"échec : {exc}")
        # Toujours relâcher un worker STOP'd et Redis en pause.
        try:
            for pid in pids_workers():
                docker(
                    "exec", "bea-lt-backend", "python", "-c",
                    f"import os, signal; os.kill({pid}, signal.SIGCONT)",
                    check=False,
                )
            docker("unpause", "bea-lt-redis", check=False)
            docker("start", "bea-lt-worker", check=False)
        except Exception:
            pass
        raise
