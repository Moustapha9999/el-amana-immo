"""Vide toutes les données applicatives puis reseede le référentiel + admin.

Conserve le schéma (tables, enums, alembic_version) et la logique métier en code.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from sqlalchemy import text

from app.db.session import engine
from app.models import entities  # noqa: F401

# Ordre indifférent avec CASCADE ; alembic_version volontairement exclu.
TABLES = [
    "cessions",
    "rebuts",
    "reevaluations",
    "ajustements",
    "amortissements",
    "pieces_jointes",
    "inventaire_scans",
    "ecritures_comptables",
    "immobilisations",
    "notifications",
    "audit_logs",
    "parametrage_ecritures",
    "parametrage_amortissement",
    "categories_immobilisation",
    "plan_comptable",
    "journaux",
    "fournisseurs",
    "centres_cout",
    "departements",
    "directions",
    "user_roles",
    "role_permissions",
    "users",
    "roles",
    "permissions",
    "agences",
]


async def wipe() -> None:
    quoted = ", ".join(f'"{t}"' for t in TABLES)
    sql = f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"
    async with engine.begin() as conn:
        await conn.execute(text(sql))
    print(f"TRUNCATE OK — {len(TABLES)} tables vidées (schéma conservé).")


def clear_uploads() -> None:
    root = Path(__file__).resolve().parents[1] / "storage" / "uploads"
    if not root.exists():
        print("Aucun dossier uploads à nettoyer.")
        return
    removed = 0
    for child in root.iterdir():
        if child.is_file():
            child.unlink()
            removed += 1
        elif child.is_dir():
            shutil.rmtree(child)
            removed += 1
    print(f"Uploads nettoyés — {removed} élément(s) sous {root}")


async def main() -> None:
    await wipe()
    clear_uploads()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
