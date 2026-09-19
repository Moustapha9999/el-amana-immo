"""Répare les libellés catalogue dont les accents sont devenus '?'."""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from app.data.plateforme_catalogue import (
    FUNCTIONAL_PERMISSIONS,
    PLATEFORME_ESPACES,
    PLATEFORME_MODULES,
    RBAC_ROLES,
)
from app.db.session import AsyncSessionLocal
from app.models import Permission, PlateformeEspace, PlateformeModule, Role


def needs_repair(value: str | None) -> bool:
    return bool(value) and "?" in value


async def main() -> int:
    async with AsyncSessionLocal() as db:
        espaces = {
            r.code: r for r in (await db.execute(select(PlateformeEspace))).scalars().all()
        }
        for item in PLATEFORME_ESPACES:
            row = espaces.get(item["code"])
            if row is None:
                continue
            if needs_repair(row.label):
                row.label = item["label"]
            if needs_repair(row.description):
                row.description = item["description"]

        modules = {
            r.code: r for r in (await db.execute(select(PlateformeModule))).scalars().all()
        }
        for item in PLATEFORME_MODULES:
            row = modules.get(item["code"])
            if row is None:
                continue
            if needs_repair(row.label):
                row.label = item["label"]
            if needs_repair(row.description):
                row.description = item["description"]

        perms = {r.code: r for r in (await db.execute(select(Permission))).scalars().all()}
        for code, label, _module in FUNCTIONAL_PERMISSIONS:
            row = perms.get(code)
            if row is not None and needs_repair(row.label):
                row.label = label

        roles = {r.code: r for r in (await db.execute(select(Role))).scalars().all()}
        for code, label, description in RBAC_ROLES:
            row = roles.get(code)
            if row is None:
                continue
            if needs_repair(row.label):
                row.label = label
            if needs_repair(row.description):
                row.description = description

        await db.commit()

        # Contrôle
        rows = (await db.execute(select(PlateformeEspace.code, PlateformeEspace.label))).all()
        for code, label in rows:
            print(f"{code}={label}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
