"""Construit un classeur banque AAI (142010) depuis le collage texte et importe."""

from __future__ import annotations

import asyncio
import re
import sys
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.models import entities  # noqa: F401, E402
from app.services.bank_immo_import import (  # noqa: E402
    BankImmoImportService,
    parse_bank_workbook,
    parse_date,
)

RAW_PATH = Path(__file__).resolve().parent / "data" / "aai_142010_paste.txt"
OUT_XLSX = Path(__file__).resolve().parent / "data" / "aai_142010_import.xlsx"


def paste_to_grid(text: str) -> list[list[str | None]]:
    """Convertit le collage TSV en grille de cellules pour openpyxl."""
    grid: list[list[str | None]] = []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        cells = [c.strip() if c.strip() else None for c in raw.split("\t")]
        # REPORT historique sans date → 01/01/AAAA + colonnes Date/Qté/Désignation
        first = next((c for c in cells if c), None)
        if first and re.match(r"^REPORT\s+(19|20)\d{2}\s*$", first, re.I):
            year_m = re.search(r"(19|20)\d{2}", first, re.I)
            year = year_m.group(0) if year_m else "2003"
            while cells and cells[0] is None:
                cells.pop(0)
            # cells[0] == REPORT YYYY, puis montants…
            cells = [f"01/01/{year}", None, cells[0], *cells[1:]]
        # Ligne avec date en col 0, ou déjà structurée
        if cells and (parse_date(cells[0]) is not None or (cells[0] or "").upper().startswith("REPORT")):
            grid.append(cells)
            continue
        # Lignes d'en-tête utiles (compte)
        joined = " ".join(c for c in cells if c)
        if "142010" in joined or "TABLEAU" in joined.upper() or joined.upper().startswith("BEA"):
            grid.append(cells)
    return grid


def build_xlsx(grid: list[list[str | None]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "aai"
    # En-tête banque attendu par le parser
    ws.append(["BEA"])
    ws.append(["DEPARTEMENT FINANCE ET COMPTABILITE"])
    ws.append(["TABLEAU D'AMORTISSEMENT AAI"])
    ws.append([None, None, "30/06/2026"])
    ws.append(["COMPTE N°: 142010  Compte Amort: 148211"])
    ws.append(
        [
            "Date",
            "Qté",
            "Désignation",
            "d'Acquisition MRU",
            "Taux",
            "Fin Exr.Précé",
            "Exer. En. C",
            "Fin Exercice",
            "Comptable",
            "AGENCE",
        ]
    )
    for row in grid:
        # Ignore doublons d'en-tête déjà injectés
        head = " ".join(str(c) for c in row if c).upper()
        if head.startswith("BEA") or "TABLEAU" in head or "COMPTE N" in head:
            continue
        if row and str(row[0] or "").lower() in {"date", "désignation", "designation"}:
            continue
        # Normalise à 10 colonnes
        cells = list(row) + [None] * 10
        ws.append(cells[:10])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def run_import(content: bytes) -> None:
    async with AsyncSessionLocal() as session:
        svc = BankImmoImportService(session)
        result = await svc.import_from_bytes(content, "aai_142010_import.xlsx")
        await session.commit()
        print(
            f"Import OK — created={result.created} amort={result.amortissements_created} "
            f"reports={result.reports_created} negatives={result.negatives} errors={len(result.errors)}"
        )
        for t in result.totaux_par_compte:
            print(
                f"  compte {t['compte']}: n={t['created']} VB={t['valeur_brute']:.2f} "
                f"amt_fin={t['amt_fin']:.2f} VNC={t['vnc']:.2f}"
            )
        if result.errors:
            print("--- errors (max 40) ---")
            for e in result.errors[:40]:
                print(" ", e)


async def analyze_dotations() -> None:
    """Vérifie si les dotations importées sont ~6 mois (H1) ou 12 mois."""
    from sqlalchemy import func, select

    from app.models import Amortissement, Immobilisation
    from app.services.bank_immo_import import PERIODE_ARRETE, _q

    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Immobilisation, Amortissement)
                .join(Amortissement, Amortissement.immobilisation_id == Immobilisation.id)
                .where(
                    Amortissement.periode == PERIODE_ARRETE,
                    Immobilisation.valeur_brute > 0,
                    Immobilisation.taux > 0,
                )
            )
        ).all()
        n6 = n12 = n_other = n_prorata_2026 = 0
        samples_6: list[str] = []
        samples_12: list[str] = []
        total_dot = Decimal("0.00")
        for immo, a in rows:
            annual = _q(immo.valeur_brute * (immo.taux or 0) / Decimal("100"))
            if annual <= 0:
                continue
            ratio = float(a.montant / annual)
            total_dot += a.montant
            if immo.date_acquisition and immo.date_acquisition.year >= 2026:
                n_prorata_2026 += 1
                continue
            if 0.45 <= ratio <= 0.55:
                n6 += 1
                if len(samples_6) < 3:
                    samples_6.append(
                        f"{immo.designation[:40]} dot={a.montant} annual={annual} ratio={ratio:.2f}"
                    )
            elif 0.95 <= ratio <= 1.05:
                n12 += 1
                if len(samples_12) < 3:
                    samples_12.append(
                        f"{immo.designation[:40]} dot={a.montant} annual={annual} ratio={ratio:.2f}"
                    )
            else:
                n_other += 1

        tot_vb = (
            await session.execute(select(func.coalesce(func.sum(Immobilisation.valeur_brute), 0)))
        ).scalar()
        n_immo = (await session.execute(select(func.count()).select_from(Immobilisation))).scalar()
        print("--- Analyse dotations (periode 2026-06) ---")
        print(f"Immobilisations: {n_immo}  VB={tot_vb}")
        print(f"Total dotation H1 importée: {total_dot}")
        print(f"Biens acquis < 2026 - ratio ~6 mois: {n6}")
        print(f"Biens acquis < 2026 - ratio ~12 mois: {n12}")
        print(f"Biens acquis < 2026 - autre ratio: {n_other}")
        print(f"Biens acquis en 2026 (prorata acquis->30/06): {n_prorata_2026}")
        for s in samples_6:
            print("  [6m]", s)
        for s in samples_12:
            print("  [12m]", s)
        verdict = (
            "6 mois (H1 jusqu'au 30/06)"
            if n6 >= n12
            else "12 mois (annee pleine)"
            if n12 > n6
            else "mixte"
        )
        print(f"VERDICT: les dotations banque importees sont en logique {verdict}")


async def main() -> None:
    if not RAW_PATH.exists():
        raise SystemExit(f"Fichier paste manquant: {RAW_PATH}")
    text = RAW_PATH.read_text(encoding="utf-8")
    grid = paste_to_grid(text)
    print(f"Lignes grille: {len(grid)}")
    content = build_xlsx(grid)
    OUT_XLSX.parent.mkdir(parents=True, exist_ok=True)
    OUT_XLSX.write_bytes(content)
    parsed = parse_bank_workbook(content, OUT_XLSX.name)
    print(f"Lignes retenues parse_bank_workbook: {len(parsed)}")
    vb = sum((r.valeur_brute for r in parsed), Decimal("0"))
    vnc = sum((r.vnc for r in parsed), Decimal("0"))
    amt = sum((r.amt_fin for r in parsed), Decimal("0"))
    dot = sum((r.dotation for r in parsed), Decimal("0"))
    print(f"Totaux parser — VB={vb} amt_fin={amt} VNC={vnc} dotation={dot}")
    # Contrôle Aménagement
    amen = next((r for r in parsed if "ménagement" in r.designation.lower() or "menagement" in r.designation.lower()), None)
    if amen:
        print(
            f"Aménagement — VB={amen.valeur_brute} n1={amen.amt_n1} "
            f"dot={amen.dotation} fin={amen.amt_fin} vnc={amen.vnc}"
        )
    await run_import(content)
    await analyze_dotations()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
