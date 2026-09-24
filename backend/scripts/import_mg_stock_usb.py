"""Import USB Dossier Mine → Stock & Fournitures.

Lit les TSV produits par export_stock_usb.ps1.
Vide uniquement les tables stock (détache les FK Achats, ne les supprime pas).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

try:
    import psycopg2
    from psycopg2.extras import execute_values
except ImportError:  # dry-run sur le poste Windows
    psycopg2 = None
    execute_values = None

REF_RE = re.compile(r"^[A-Za-z]\d{3,6}$")
NAV_RE = re.compile(
    r"navigation|ajouter des|v[ée]rifier l|acc[ée]der [àa] la|base de donn",
    re.I,
)
EXCEL_EPOCH = datetime(1899, 12, 30, tzinfo=timezone.utc)

FAMILLES = {
    "B": ("BUREAU", "Fournitures de bureau", 10),
    "C": ("CARTOUCHE", "Consommables impression", 20),
    "M": ("MATERIEL", "Petit matériel", 30),
    "*": ("DIVERS", "Divers stock", 90),
}

MOIS_FR = (
    "",
    "Janvier",
    "Février",
    "Mars",
    "Avril",
    "Mai",
    "Juin",
    "Juillet",
    "Août",
    "Septembre",
    "Octobre",
    "Novembre",
    "Décembre",
)


def dsn_from_env() -> str:
    raw = os.environ.get("DATABASE_URL", "")
    if not raw:
        raise SystemExit("DATABASE_URL manquant")
    return raw.replace("postgresql+asyncpg://", "postgresql://", 1)


def parse_tsv(path: Path) -> list[list[str]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    rows = []
    for line in text.splitlines():
        rows.append(line.split("\t"))
    return rows


def dec(value: object) -> Decimal | None:
    if value is None:
        return None
    s = str(value).strip().replace(" ", "").replace(",", ".")
    if s == "" or s.lower() in {"none", "null"}:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def excel_dt(value: object) -> datetime | None:
    if value is None or str(value).strip() == "":
        return None
    s = str(value).strip()
    try:
        n = float(s)
        if 20000 < n < 80000:
            return EXCEL_EPOCH + timedelta(days=n)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s[:10], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def is_ref(value: object) -> bool:
    return bool(value) and bool(REF_RE.match(str(value).strip()))


def norm_ref(value: object) -> str:
    return str(value).strip().upper()


def skip_cell(value: object) -> bool:
    s = str(value or "").strip()
    return s == "" or bool(NAV_RE.search(s))


def parse_articles(rows: list[list[str]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in rows:
        cells = [c.strip() for c in row]
        ref = None
        name = None
        for i, c in enumerate(cells):
            if is_ref(c):
                ref = norm_ref(c)
                left = [x for x in cells[:i] if x and not skip_cell(x) and not is_ref(x)]
                name = left[-1] if left else None
                break
        if ref and name and not skip_cell(name):
            out[ref] = name[:255]
    return out


def _header_map(row: list[str]) -> dict[str, int]:
    idx: dict[str, int] = {}
    for i, raw in enumerate(row):
        h = raw.strip().lower()
        if not h:
            continue
        if h in {"article", "désignation", "designation", "libellé", "libelle"}:
            idx.setdefault("article", i)
        elif h in {"ref", "réf", "reference", "référence", "code"}:
            idx.setdefault("ref", i)
        elif "stock initial" in h or h in {"initial", "si"}:
            idx.setdefault("si", i)
        elif h.startswith("entr"):
            idx.setdefault("entrees", i)
        elif h.startswith("sort"):
            idx.setdefault("sorties", i)
        elif "stock final" in h or h in {"final", "sf"}:
            idx.setdefault("sf", i)
    return idx


def parse_etat(rows: list[list[str]]) -> dict[str, dict]:
    header = None
    start = 0
    for i, row in enumerate(rows[:20]):
        m = _header_map(row)
        if "ref" in m and ("si" in m or "sf" in m):
            header = m
            start = i + 1
            break
    if header is None:
        # UsedRange parfois sans ligne titre : Article | Ref | SI | E | S | SF
        for i, row in enumerate(rows[:20]):
            joined = " ".join(c.strip().lower() for c in row)
            if "stock initial" in joined and "ref" in joined:
                header = _header_map(row)
                start = i + 1
                break
    if header is None or "ref" not in header:
        return {}
    out: dict[str, dict] = {}
    for row in rows[start:]:
        if header["ref"] >= len(row):
            continue
        raw_ref = row[header["ref"]].strip()
        if not is_ref(raw_ref):
            continue
        ref = norm_ref(raw_ref)
        name = ""
        if "article" in header and header["article"] < len(row):
            name = row[header["article"]].strip()
        def col(key: str) -> Decimal:
            i = header.get(key)
            if i is None or i >= len(row):
                return Decimal("0")
            return dec(row[i]) or Decimal("0")

        out[ref] = {
            "designation": name[:255],
            "stock_initial": col("si"),
            "entrees": col("entrees"),
            "sorties": col("sorties"),
            "stock_final": col("sf"),
        }
    return out


def parse_journal(rows: list[list[str]], year: int, month: int) -> list[dict]:
    ref_col = None
    best = 0
    scan = rows[:80] if len(rows) > 80 else rows
    width = max((len(r) for r in rows), default=0)
    counts = [0] * width
    for row in rows:
        for i, c in enumerate(row):
            if is_ref(c):
                counts[i] += 1
    if counts:
        best = max(counts)
        ref_col = counts.index(best)
    if ref_col is None or best < 3:
        return []

    date_col = ref_col - 1 if ref_col > 0 else None
    mvts: list[dict] = []
    for row in rows:
        if ref_col >= len(row) or not is_ref(row[ref_col]):
            continue
        ref = norm_ref(row[ref_col])
        when = excel_dt(row[date_col]) if date_col is not None and date_col < len(row) else None
        if when is None:
            when = datetime(year, month, 15, 12, 0, tzinfo=timezone.utc)
        after = []
        for i, c in enumerate(row):
            if i <= ref_col:
                continue
            s = c.strip()
            if skip_cell(s):
                continue
            after.append((i, s))
        texts = [(i, s) for i, s in after if dec(s) is None]
        nums = [(i, dec(s)) for i, s in after if dec(s) is not None]
        dest = texts[0][1][:120] if texts else None
        person = texts[1][1][:255] if len(texts) > 1 else None
        if dest and nums:
            kind = "SORTIE"
            qty = nums[-1][1]
        elif nums:
            kind = "ENTREE"
            qty = nums[0][1]
        else:
            continue
        if qty is None or qty <= 0:
            continue
        mvts.append(
            {
                "type": kind,
                "ref": ref,
                "date": when,
                "qty": qty,
                "departement": dest,
                "observation": person,
            }
        )
    return mvts


def month_bounds(year: int, month: int) -> tuple[date, date]:
    import calendar

    last = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


def load_export(root: Path) -> list[dict]:
    months = []
    for child in sorted(p for p in root.iterdir() if p.is_dir() and re.match(r"^\d{4}-\d{2}$", p.name)):
        year, month = (int(x) for x in child.name.split("-"))
        articles = parse_articles(parse_tsv(child / "articles.tsv"))
        etat = parse_etat(parse_tsv(child / "etat.tsv"))
        journal = parse_journal(parse_tsv(child / "journal.tsv"), year, month)
        for ref, info in etat.items():
            if info.get("designation") and ref not in articles:
                articles[ref] = info["designation"]
        months.append(
            {
                "ym": child.name,
                "year": year,
                "month": month,
                "articles": articles,
                "etat": etat,
                "journal": journal,
            }
        )
    return months


def wipe_stock(cur) -> dict[str, int]:
    cur.execute(
        """
        SELECT c.conrelid::regclass::text, a.attname
        FROM pg_constraint c
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
        WHERE c.contype = 'f' AND c.confrelid = 'mg_articles'::regclass
        """
    )
    detached = 0
    stock_tables = {
        "mg_articles",
        "mg_stock_mouvements",
        "mg_stock_soldes",
        "mg_inventaire_lignes",
        "mg_demande_fourniture_lignes",
    }
    for table, col in cur.fetchall():
        if table in stock_tables:
            continue
        cur.execute(
            f'SELECT COUNT(*) FROM {table} WHERE "{col}" IS NOT NULL'
        )
        n = cur.fetchone()[0]
        if n:
            cur.execute(f'UPDATE {table} SET "{col}" = NULL WHERE "{col}" IS NOT NULL')
            detached += n

    counts = {}
    for table in (
        "mg_stock_soldes",
        "mg_stock_mouvements",
        "mg_inventaire_lignes",
        "mg_inventaires",
        "mg_demande_fourniture_lignes",
        "mg_demandes_fourniture",
        "mg_stock_periodes",
        "mg_articles",
        "mg_article_familles",
    ):
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        counts[table] = cur.fetchone()[0]
        cur.execute(f"DELETE FROM {table}")
    counts["achats_article_id_detached"] = detached
    return counts


def apply_import(cur, months: list[dict]) -> dict:
    now = datetime.now(timezone.utc)
    famille_ids: dict[str, uuid.UUID] = {}
    for key, (code, libelle, order) in FAMILLES.items():
        fid = uuid.uuid4()
        famille_ids[key] = fid
        cur.execute(
            """
            INSERT INTO mg_article_familles
              (id, code, libelle, sort_order, is_active, deleted_at, created_at, updated_at)
            VALUES (%s, %s, %s, %s, true, NULL, %s, %s)
            """,
            (str(fid), code, libelle, order, now, now),
        )

    catalog: dict[str, str] = {}
    for m in months:
        catalog.update(m["articles"])
        for ref, info in m["etat"].items():
            if info.get("designation"):
                catalog[ref] = info["designation"]

    article_ids: dict[str, uuid.UUID] = {}
    art_rows = []
    for ref, designation in sorted(catalog.items()):
        aid = uuid.uuid4()
        article_ids[ref] = aid
        prefix = ref[0] if ref[0] in FAMILLES else "*"
        art_rows.append(
            (
                str(aid),
                ref,
                ref,
                designation or ref,
                str(famille_ids[prefix]),
                None,
                "U",
                True,
                Decimal("0"),
                Decimal("0"),
                None,
                None,
                None,
                None,
                True,
                None,
                now,
                now,
            )
        )
    execute_values(
        cur,
        """
        INSERT INTO mg_articles (
          id, code, reference, designation, famille_id, sous_famille, uom, stockable,
          stock_actuel, stock_min, stock_max, agence_id, emplacement, fournisseur_habituel,
          is_active, deleted_at, created_at, updated_at
        ) VALUES %s
        """,
        art_rows,
    )

    prev_pid = None
    last_final: dict[str, Decimal] = {}
    periode_ids: dict[str, uuid.UUID] = {}
    n_soldes = 0
    n_mvts = 0
    last_ym = months[-1]["ym"] if months else None

    for m in months:
        pid = uuid.uuid4()
        periode_ids[m["ym"]] = pid
        debut, fin = month_bounds(m["year"], m["month"])
        is_last = m["ym"] == last_ym
        statut = "OUVERTE" if is_last else "CLOTUREE"
        cur.execute(
            """
            INSERT INTO mg_stock_periodes (
              id, annee, mois, libelle, date_debut, date_fin, statut, agence_id,
              periode_precedente_id, opened_at, opened_by, cloture_at, cloture_by,
              reopen_at, reopen_by, reopen_motif, created_at, updated_at
            ) VALUES (
              %s, %s, %s, %s, %s, %s, %s, NULL,
              %s, %s, NULL, %s, NULL,
              NULL, NULL, NULL, %s, %s
            )
            """,
            (
                str(pid),
                m["year"],
                m["month"],
                f"{MOIS_FR[m['month']]} {m['year']}",
                debut,
                fin,
                statut,
                str(prev_pid) if prev_pid else None,
                datetime(m["year"], m["month"], 1, tzinfo=timezone.utc),
                None if is_last else datetime(m["year"], m["month"], fin.day, 18, 0, tzinfo=timezone.utc),
                now,
                now,
            ),
        )

        refs = set(m["etat"]) | {j["ref"] for j in m["journal"]}
        solde_rows = []
        for ref in sorted(refs):
            aid = article_ids.get(ref)
            if aid is None:
                continue
            et = m["etat"].get(ref)
            if et:
                si, en, so, sf = et["stock_initial"], et["entrees"], et["sorties"], et["stock_final"]
            else:
                si = last_final.get(ref, Decimal("0"))
                en = sum((j["qty"] for j in m["journal"] if j["ref"] == ref and j["type"] == "ENTREE"), Decimal("0"))
                so = sum((j["qty"] for j in m["journal"] if j["ref"] == ref and j["type"] == "SORTIE"), Decimal("0"))
                sf = si + en - so
            theo = si + en - so
            solde_rows.append(
                (
                    str(uuid.uuid4()),
                    str(pid),
                    str(aid),
                    si,
                    en,
                    so,
                    Decimal("0"),
                    theo,
                    None,
                    None,
                    sf,
                    now,
                    now,
                )
            )
            last_final[ref] = sf
        if solde_rows:
            execute_values(
                cur,
                """
                INSERT INTO mg_stock_soldes (
                  id, periode_id, article_id, stock_initial, entrees, sorties, ajustements,
                  stock_theorique, stock_physique, ecart, stock_final, created_at, updated_at
                ) VALUES %s
                """,
                solde_rows,
            )
            n_soldes += len(solde_rows)

        mvt_rows = []
        counters = {"ENTREE": 0, "SORTIE": 0}
        for j in m["journal"]:
            aid = article_ids.get(j["ref"])
            if aid is None:
                continue
            counters[j["type"]] += 1
            prefix = "ENT" if j["type"] == "ENTREE" else "SOR"
            ref_mvt = f"{prefix}-{m['year']}{m['month']:02d}-{counters[j['type']]:05d}"
            motif = f"Import USB {MOIS_FR[m['month']]} {m['year']}"
            mvt_rows.append(
                (
                    str(uuid.uuid4()),
                    ref_mvt,
                    j["date"],
                    j["type"],
                    str(aid),
                    j["qty"],
                    None,
                    j["departement"],
                    None,
                    motif,
                    j["observation"],
                    "usb_import",
                    None,
                    str(pid),
                    now,
                    now,
                )
            )
        if mvt_rows:
            execute_values(
                cur,
                """
                INSERT INTO mg_stock_mouvements (
                  id, reference, date_mouvement, type_mouvement, article_id, quantite,
                  agence_id, departement, initiateur_id, motif, observation,
                  source_type, source_id, periode_id, created_at, updated_at
                ) VALUES %s
                """,
                mvt_rows,
            )
            n_mvts += len(mvt_rows)
        prev_pid = pid

    for ref, qty in last_final.items():
        aid = article_ids.get(ref)
        if aid is None:
            continue
        cur.execute(
            "UPDATE mg_articles SET stock_actuel = %s, updated_at = %s WHERE id = %s",
            (qty, now, str(aid)),
        )

    return {
        "articles": len(article_ids),
        "periodes": len(periode_ids),
        "soldes": n_soldes,
        "mouvements": n_mvts,
        "periode_ouverte": last_ym,
        "stock_valorise_articles": sum(1 for q in last_final.values() if q != 0),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--wipe", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    root = Path(args.root)
    months = load_export(root)
    if not months:
        print("Aucun mois exporté.", file=sys.stderr)
        return 2
    print(f"Mois lus : {len(months)} ({months[0]['ym']} -> {months[-1]['ym']})")
    arts = set()
    n_j = 0
    n_e = 0
    for m in months:
        arts.update(m["articles"])
        arts.update(m["etat"])
        n_j += len(m["journal"])
        n_e += len(m["etat"])
        print(
            f"  {m['ym']}: articles={len(m['articles'])} etat={len(m['etat'])} "
            f"journal={len(m['journal'])} "
            f"E={sum(1 for x in m['journal'] if x['type']=='ENTREE')} "
            f"S={sum(1 for x in m['journal'] if x['type']=='SORTIE')}"
        )
    print(f"Catalogue union={len(arts)} journal_total={n_j} etat_lignes={n_e}")
    if args.dry_run:
        return 0
    if psycopg2 is None:
        print("psycopg2 requis pour l'écriture.", file=sys.stderr)
        return 2

    conn = psycopg2.connect(dsn_from_env())
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            if args.wipe:
                wiped = wipe_stock(cur)
                print("Wipe:", wiped)
            stats = apply_import(cur, months)
            print("Import:", stats)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
