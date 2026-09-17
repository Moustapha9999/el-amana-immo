"""Contrôles BEA DIGITAL (Supabase ou Docker).

Usage (depuis backend/, PYTHONPATH=. ) :

  python scripts/bea_digital_ops.py verify
  python scripts/bea_digital_ops.py status

Lit DATABASE_URL dans l'environnement / .env (Session pooler pour Supabase).
N'écrit aucune donnée métier.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from sqlalchemy import text

from app.db.session import engine

logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

_QUERIES: list[tuple[str, str]] = [
    ("database", "SELECT current_database()"),
    ("alembic", "SELECT version_num FROM alembic_version"),
    ("tables_public", "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'"),
    ("rls_policies_public", "SELECT COUNT(*) FROM pg_policies WHERE schemaname='public'"),
    ("nb_immobilisations", "SELECT COUNT(*) FROM immobilisations"),
    ("somme_valeur_brute", "SELECT COALESCE(SUM(valeur_brute), 0) FROM immobilisations"),
    ("nb_amortissements", "SELECT COUNT(*) FROM amortissements"),
    ("nb_archive_lignes", "SELECT COUNT(*) FROM archive_lignes"),
    ("users_actifs", "SELECT COUNT(*) FROM users WHERE deleted_at IS NULL"),
    ("espaces", "SELECT COUNT(*) FROM plateforme_espaces"),
    ("modules", "SELECT COUNT(*) FROM plateforme_modules"),
    ("grants_espace", "SELECT COUNT(*) FROM user_espace_acces"),
    ("grants_module", "SELECT COUNT(*) FROM user_module_acces"),
]


async def _verify() -> int:
    rows: list[tuple[str, object]] = []
    try:
        async with engine.connect() as conn:
            for label, sql in _QUERIES:
                value = (await conn.execute(text(sql))).scalar()
                rows.append((label, value))
            espaces = (
                await conn.execute(
                    text("SELECT code, label, statut FROM plateforme_espaces ORDER BY sort_order")
                )
            ).all()
            sans_immo = (
                await conn.execute(
                    text(
                        """
                        SELECT u.email
                        FROM users u
                        WHERE u.deleted_at IS NULL
                          AND NOT EXISTS (
                            SELECT 1
                            FROM user_module_acces uma
                            JOIN plateforme_modules m ON m.id = uma.module_id
                            WHERE uma.user_id = u.id
                              AND m.code = 'immobilisations'
                              AND uma.status = 'actif'
                          )
                        ORDER BY u.email
                        """
                    )
                )
            ).scalars().all()
    except Exception as exc:
        print(f"ERREUR connexion: {exc}", file=sys.stderr)
        return 1
    finally:
        await engine.dispose()

    print("BEA DIGITAL — contrôles")
    for label, value in rows:
        print(f"  {label:24} {value}")
    print("  espaces:")
    for code, label, statut in espaces:
        print(f"    - {code:16} {label:28} {statut}")
    if sans_immo:
        print("  users sans module immobilisations:")
        for email in sans_immo:
            print(f"    - {email}")
    else:
        print("  users sans module immobilisations: 0")

    checks = {k: v for k, v in rows}
    errors: list[str] = []
    head = str(checks.get("alembic") or "")
    if head == "20260917_audit_context":
        print("  note: alembic upgrade head pour poser les commentaires BEA DIGITAL")
    elif head != "20260917_bea_comments":
        errors.append(f"alembic_version inattendue: {head or '(vide)'}")
    if int(checks.get("rls_policies_public") or 0) != 0:
        errors.append("RLS public inattendu (doit rester 0)")
    if int(checks.get("espaces") or 0) < 5:
        errors.append("catalogue espaces incomplet")
    if int(checks.get("modules") or 0) < 5:
        errors.append("catalogue modules incomplet")
    if errors:
        print("ALERTE:")
        for err in errors:
            print(f"  - {err}")
        return 2
    print("OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Contrôles BEA DIGITAL")
    parser.add_argument("action", choices=("verify", "status"), nargs="?", default="verify")
    args = parser.parse_args()
    if args.action in ("verify", "status"):
        return asyncio.run(_verify())
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
