"""Snapshot et vérification d'intégrité — base bea_digital_loadtest uniquement.

    python loadtest/integrite.py snapshot  loadtest/reports/<palier>
    python loadtest/integrite.py verifier  loadtest/reports/<palier>

Compare le journal Locust (écritures acceptées) au contenu réel de la base :
soldes (SF = SI + E − S ± A), stock_actuel, mouvements et demandes ni perdus
ni dupliqués. Refuse toute autre base que bea_digital_loadtest.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

BASE = "bea_digital_loadtest"
MARQUE = "LT-CHARGE"


def _psql(sql: str) -> str:
    r = subprocess.run(
        ["docker", "exec", "-i", "bea-postgres", "psql", "-U", "admin", "-d", BASE, "-X", "-v", "ON_ERROR_STOP=1", "-tA"],
        input=sql,
        text=True,
        capture_output=True,
        check=False,
    )
    if r.returncode != 0:
        raise SystemExit(f"psql : {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout.strip()


def _exiger_base() -> None:
    nom = _psql("select current_database();")
    if nom != BASE:
        raise SystemExit(f"ARRÊT : base « {nom} » — uniquement {BASE}.")


def _json(sql: str):
    raw = _psql(sql)
    return json.loads(raw) if raw and raw != "" else []


def _dec(v) -> Decimal:
    return Decimal(str(v or 0))


def snapshot(dossier: Path) -> dict:
    _exiger_base()
    data = {
        "base": _psql("select current_database();"),
        "instant": _psql("select now();"),
        "articles": _json(
            "select coalesce(json_agg(row_to_json(t)), '[]'::json) from ("
            "  select id::text, code, stock_actuel::text"
            "  from mg_articles where deleted_at is null and code like 'LT%' order by code"
            ") t;"
        ),
        "soldes": _json(
            "select coalesce(json_agg(row_to_json(t)), '[]'::json) from ("
            "  select a.id::text as article_id, a.code, a.stock_actuel::text,"
            "         p.annee, p.mois, p.statut,"
            "         s.stock_initial::text, s.entrees::text, s.sorties::text, s.ajustements::text"
            "  from mg_articles a"
            "  join mg_stock_soldes s on s.article_id = a.id"
            "  join mg_stock_periodes p on p.id = s.periode_id"
            "  where a.deleted_at is null and a.code like 'LT%'"
            "    and p.statut in ('OUVERTE', 'ROUVERTE')"
            "  order by a.code, p.annee, p.mois"
            ") t;"
        ),
        "nb_mouvements": int(_psql("select count(*) from mg_stock_mouvements;")),
        "nb_demandes": int(_psql("select count(*) from mg_employee_requests;")),
        "deadlocks": int(_psql(
            "select deadlocks from pg_stat_database where datname = current_database();"
        ) or 0),
    }
    (dossier / "snapshot.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Snapshot : {len(data['articles'])} articles, {data['nb_mouvements']} mouvements, "
          f"{data['nb_demandes']} demandes → {dossier / 'snapshot.json'}")
    return data


def _journal(dossier: Path) -> list[dict]:
    chemin = dossier / "journal.jsonl"
    if not chemin.exists():
        return []
    out = []
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if ligne:
            out.append(json.loads(ligne))
    return out


def _check(code: str, ok: bool, detail: str) -> dict:
    return {"code": code, "ok": ok, "detail": detail}


def verifier(dossier: Path) -> int:
    _exiger_base()
    snap_path = dossier / "snapshot.json"
    if not snap_path.exists():
        raise SystemExit(f"snapshot.json absent dans {dossier}")
    snap = json.loads(snap_path.read_text(encoding="utf-8"))
    journal = _journal(dossier)

    entrees = [j for j in journal if j.get("kind") == "entree"]
    sorties = [j for j in journal if j.get("kind") == "sortie"]
    demandes = [j for j in journal if j.get("kind") == "demande"]
    refuses = [j for j in journal if j.get("kind") == "refuse"]

    ids_mvt = [j["id"] for j in entrees + sorties if j.get("id")]
    ids_dem = [j["id"] for j in demandes if j.get("id")]
    depuis = snap.get("instant") or "1970-01-01"

    db_mvt = {
        r["id"]: r
        for r in _json(
            "select coalesce(json_agg(row_to_json(t)), '[]'::json) from ("
            "  select id::text, reference, type_mouvement, article_id::text, quantite::text, observation"
            f"  from mg_stock_mouvements where observation like '{MARQUE}%'"
            f"    and created_at > timestamptz '{depuis}'"
            ") t;"
        )
    }
    db_dem = {
        r["id"]: r
        for r in _json(
            "select coalesce(json_agg(row_to_json(t)), '[]'::json) from ("
            "  select id::text, request_number, title"
            f"  from mg_employee_requests where title like '{MARQUE}%'"
            f"    and created_at > timestamptz '{depuis}'"
            ") t;"
        )
    }
    articles = {
        r["id"]: r
        for r in _json(
            "select coalesce(json_agg(row_to_json(t)), '[]'::json) from ("
            "  select id::text, code, stock_actuel::text"
            "  from mg_articles where deleted_at is null and code like 'LT%'"
            ") t;"
        )
    }
    soldes = _json(
        "select coalesce(json_agg(row_to_json(t)), '[]'::json) from ("
        "  select a.id::text as article_id, a.code, a.stock_actuel::text,"
        "         p.annee, p.mois, p.statut,"
        "         s.stock_initial::text, s.entrees::text, s.sorties::text, s.ajustements::text"
        "  from mg_articles a"
        "  join mg_stock_soldes s on s.article_id = a.id"
        "  join mg_stock_periodes p on p.id = s.periode_id"
        "  where a.deleted_at is null and a.code like 'LT%'"
        "    and p.statut in ('OUVERTE', 'ROUVERTE')"
        ") t;"
    )
    refs_dup = _json(
        "select coalesce(json_agg(row_to_json(t)), '[]'::json) from ("
        "  select reference, count(*) as n from mg_stock_mouvements"
        f"  where observation like '{MARQUE}%' and created_at > timestamptz '{depuis}'"
        "  group by 1 having count(*) > 1"
        ") t;"
    )
    nums_dup = _json(
        "select coalesce(json_agg(row_to_json(t)), '[]'::json) from ("
        "  select request_number, count(*) as n from mg_employee_requests"
        f"  where title like '{MARQUE}%' and created_at > timestamptz '{depuis}'"
        "  group by 1 having count(*) > 1"
        ") t;"
    )
    deadlocks = int(_psql("select deadlocks from pg_stat_database where datname = current_database();") or 0)
    idx_mvt = _psql(
        "select count(*) from pg_indexes where tablename = 'mg_stock_mouvements' "
        "and indexdef ilike '%UNIQUE%' and indexdef ilike '%(reference)%';"
    )
    idx_dem = _psql(
        "select count(*) from pg_indexes where tablename = 'mg_employee_requests' "
        "and indexdef ilike '%UNIQUE%' and indexdef ilike '%request_number%';"
    )
    doubles = [r for r in refuses if r.get("code") == "DOUBLE_OPERATION"]
    stocks_neg = [a for a in articles.values() if _dec(a["stock_actuel"]) < 0]

    manquants_mvt = [i for i in ids_mvt if i not in db_mvt]
    extras_mvt = [i for i in db_mvt if i not in set(ids_mvt)]
    manquants_dem = [i for i in ids_dem if i not in db_dem]
    extras_dem = [i for i in db_dem if i not in set(ids_dem)]
    journal_dup_mvt = [i for i, n in Counter(ids_mvt).items() if n > 1]
    journal_dup_dem = [i for i, n in Counter(ids_dem).items() if n > 1]

    snap_stock = {a["id"]: _dec(a["stock_actuel"]) for a in snap.get("articles", [])}
    delta: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for j in entrees:
        if j.get("article_id"):
            delta[j["article_id"]] += _dec(j.get("quantite"))
    for j in sorties:
        if j.get("article_id"):
            delta[j["article_id"]] -= _dec(j.get("quantite"))

    ecarts_stock = []
    for aid, d in delta.items():
        attendu = snap_stock.get(aid, Decimal("0")) + d
        actuel = _dec(articles.get(aid, {}).get("stock_actuel"))
        if attendu != actuel:
            ecarts_stock.append(
                f"{articles.get(aid, {}).get('code', aid)} : attendu {attendu} (snapshot+journal), "
                f"stock_actuel {actuel}"
            )

    # stock_actuel = solde de la dernière période ouverte (les périodes antérieures
    # encore ouvertes ont un SI+E−S±A qui n'est plus le stock courant).
    dernier_solde: dict[str, dict] = {}
    for s in soldes:
        prev = dernier_solde.get(s["article_id"])
        if prev is None or (s["annee"], s["mois"]) > (prev["annee"], prev["mois"]):
            dernier_solde[s["article_id"]] = s
    ecarts_formule = []
    for s in dernier_solde.values():
        theorique = _dec(s["stock_initial"]) + _dec(s["entrees"]) - _dec(s["sorties"]) + _dec(s["ajustements"])
        actuel = _dec(s["stock_actuel"])
        if theorique != actuel:
            ecarts_formule.append(
                f"{s['code']} {s['annee']}-{s['mois']:02d} : SI+E−S±A = {theorique}, stock_actuel = {actuel}"
            )

    checks = [
        _check("journal_non_vide", bool(journal),
               f"{len(entrees)} entrées, {len(sorties)} sorties, {len(demandes)} demandes, {len(refuses)} refus"),
        _check("mouvements_perdus", not manquants_mvt,
               f"{len(manquants_mvt)} id journalisés absents de la base" + (f" : {manquants_mvt[:5]}" if manquants_mvt else "")),
        _check("mouvements_extra", not extras_mvt,
               f"{len(extras_mvt)} mouvements {MARQUE} sans ligne de journal"),
        _check("journal_mvt_doublon", not journal_dup_mvt, f"{len(journal_dup_mvt)} id journalisés plusieurs fois"),
        _check("references_mvt_doublon", not refs_dup,
               f"{len(refs_dup)} références de mouvement en double" + (f" : {refs_dup[:5]}" if refs_dup else "")),
        _check("stock_vs_journal", not ecarts_stock,
               "OK" if not ecarts_stock else " ; ".join(ecarts_stock[:8])),
        _check("formule_soldes", not ecarts_formule,
               "OK" if not ecarts_formule else " ; ".join(ecarts_formule[:8])),
        _check("stock_negatif", not stocks_neg,
               f"{len(stocks_neg)} article(s) à stock négatif"),
        _check("demandes_perdues", not manquants_dem,
               f"{len(manquants_dem)} demandes journalisées absentes"),
        _check("demandes_extra", not extras_dem,
               f"{len(extras_dem)} demandes {MARQUE} sans ligne de journal"),
        _check("journal_dem_doublon", not journal_dup_dem, f"{len(journal_dup_dem)} id journalisés plusieurs fois"),
        _check("numeros_demande_doublon", not nums_dup,
               f"{len(nums_dup)} numéros de demande en double" + (f" : {nums_dup[:5]}" if nums_dup else "")),
        _check("deadlocks", deadlocks == int(snap.get("deadlocks") or 0),
               f"deadlocks {snap.get('deadlocks')} → {deadlocks}"),
        _check("unique_reference_mvt", idx_mvt == "1",
               f"{idx_mvt} index UNIQUE(reference) sur mg_stock_mouvements"),
        _check("unique_numero_demande", idx_dem == "1",
               f"{idx_dem} index UNIQUE(request_number) sur mg_employee_requests"),
        _check("double_clic", not doubles,
               "OK" if not doubles else f"{len(doubles)} double(s) clic ont créé deux opérations"),
    ]
    ok = all(c["ok"] for c in checks)
    rapport = {
        "ok": ok,
        "journal": {"entrees": len(entrees), "sorties": len(sorties), "demandes": len(demandes), "refuses": len(refuses)},
        "controles": checks,
    }
    (dossier / "integrite.json").write_text(json.dumps(rapport, ensure_ascii=False, indent=2), encoding="utf-8")
    print(("INTEGRITE OK" if ok else "INTEGRITE KO") + f" — {dossier}")
    for c in checks:
        print(f"  [{'OK' if c['ok'] else 'KO'}] {c['code']}: {c['detail']}")
    return 0 if ok else 2


def main(argv: list[str]) -> int:
    if len(argv) < 3 or argv[1] not in {"snapshot", "verifier"}:
        print(__doc__)
        return 1
    dossier = Path(argv[2])
    dossier.mkdir(parents=True, exist_ok=True)
    if argv[1] == "snapshot":
        snapshot(dossier)
        return 0
    return verifier(dossier)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
