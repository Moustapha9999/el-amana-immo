"""Test PostgreSQL connectivity (Supabase or local)."""

import asyncio
import sys

from sqlalchemy import text

from app.db.session import engine


async def main() -> int:
    try:
        async with engine.connect() as conn:
            version = (await conn.execute(text("select version()"))).scalar_one()
            db_name = (await conn.execute(text("select current_database()"))).scalar_one()
        print(f"OK — database={db_name}")
        print(version[:80] + "...")
        return 0
    except Exception as exc:
        msg = str(exc).lower()
        if "getaddrinfo" in msg or "11001" in msg or "no address associated" in msg:
            print(
                "ERREUR connexion: résolution DNS / IPv6.\n"
                "  • db.<ref>.supabase.co est souvent IPv6-only.\n"
                "  • Sur Windows sans IPv6 fonctionnel → utiliser le pooler Supavisor (IPv4).\n"
                "  • Lancez: python scripts/find_pooler_region.py\n"
                "  • Ou copiez « Session pooler » dans Supabase → Settings → Database.",
                file=sys.stderr,
            )
        else:
            print(f"ERREUR connexion: {exc}", file=sys.stderr)
        return 1
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
