"""Seed idempotent du canevas officiel Reporting BCM SM (T3.5-3-B).

Usage (PYTHONPATH=backend, depuis le conteneur avec le dépôt monté) :
  python scripts/rbcm_seed_template.py --file /workspace/BEA-SM-10-2026.xlsx
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.services.reporting_bcm_sm.template_seed import seed_official_template  # noqa: E402
from app.services.reporting_bcm_sm.template_storage import OFFICIAL_SHA256  # noqa: E402


async def _run(path: Path) -> dict:
    async with AsyncSessionLocal() as db:
        result = await seed_official_template(db, path, expected_sha256=OFFICIAL_SHA256)
        await db.commit()
        return result


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--file", required=True, type=Path)
    args = p.parse_args()
    if not args.file.is_file():
        print(json.dumps({"error": f"fichier introuvable: {args.file}", "code": "TEMPLATE_NOT_FOUND"}))
        return 2
    result = asyncio.run(_run(args.file))
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
