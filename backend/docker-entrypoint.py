"""Démarre l'API après application des migrations Alembic."""

from __future__ import annotations

import os
import subprocess
import sys


def main() -> None:
    if os.environ.get("SKIP_MIGRATIONS") != "1":
        subprocess.check_call(["alembic", "upgrade", "head"], cwd="/app")
    if len(sys.argv) < 2:
        raise SystemExit("commande manquante après docker-entrypoint")
    os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == "__main__":
    main()
