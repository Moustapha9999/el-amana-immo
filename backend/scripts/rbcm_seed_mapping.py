"""Dry-run / seed Correspondance SCD → rbcm_mapping_* (DEV only).

Usage (depuis /app dans le conteneur ou PYTHONPATH=backend) :
  python scripts/rbcm_seed_mapping.py --dry-run --file /data/Correspondance.xlsx
  python scripts/rbcm_seed_mapping.py --seed --file /data/Correspondance.xlsx
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Permet l'exécution depuis backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.services.reporting_bcm_sm.mapping_seed import (  # noqa: E402
    dry_run_correspondance,
    export_candidates_jsonl,
    seed_from_correspondance,
)


async def _seed(path: Path) -> dict:
    async with AsyncSessionLocal() as db:
        result = await seed_from_correspondance(db, path=path)
        await db.commit()
        return result


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--file", required=True, type=Path)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--seed", action="store_true")
    p.add_argument("--jsonl", type=Path, default=None)
    args = p.parse_args()
    if not args.file.is_file():
        print(json.dumps({"error": f"fichier introuvable: {args.file}"}))
        return 2

    if args.jsonl:
        meta = export_candidates_jsonl(args.file, args.jsonl)
        print(json.dumps({"export": meta}, ensure_ascii=False, indent=2, default=str))

    if args.dry_run or not args.seed:
        report = dry_run_correspondance(args.file)
        slim = {k: v for k, v in report.items() if k not in ("candidates", "multi_cell_comptes_detail")}
        slim["multi_cell_comptes_sample"] = dict(list(report["multi_cell_comptes_detail"].items())[:10])
        print(json.dumps({"dry_run": slim}, ensure_ascii=False, indent=2, default=str))
        if not args.seed:
            return 0

    result = asyncio.run(_seed(args.file))
    # Ne pas dumper tout dry_run candidates
    if "dry_run" in result and isinstance(result["dry_run"], dict):
        result["dry_run"].pop("candidates", None)
        result["dry_run"].pop("multi_cell_comptes_detail", None)
    print(json.dumps({"seed": result}, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
