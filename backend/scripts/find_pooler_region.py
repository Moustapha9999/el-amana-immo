"""
Trouve la région Supavisor (pooler IPv4) pour un projet Supabase.

Usage (depuis backend/) :
  $env:PYTHONPATH="."
  python scripts/find_pooler_region.py
"""

import asyncio
import ssl
import sys
from urllib.parse import quote_plus

import asyncpg

from app.core.config import get_settings

REGIONS = [
    "eu-west-1",
    "eu-west-2",
    "eu-west-3",
    "eu-central-1",
    "eu-central-2",
    "eu-north-1",
    "us-east-1",
    "us-east-2",
    "us-west-1",
    "us-west-2",
    "ap-southeast-1",
    "ap-southeast-2",
    "ap-northeast-1",
    "ap-south-1",
    "sa-east-1",
]


def project_ref_from_url(supabase_url: str | None, database_url: str) -> str | None:
    if supabase_url and "supabase.co" in supabase_url:
        host = supabase_url.replace("https://", "").replace("http://", "").split("/")[0]
        return host.split(".")[0]
    if "supabase.co" in database_url and "@" in database_url:
        host = database_url.split("@", 1)[1].split("/")[0].split(":")[0]
        if host.startswith("db."):
            return host.removeprefix("db.").removesuffix(".supabase.co")
    return None


async def try_region(region: str, project_ref: str, password: str) -> bool:
    user = f"postgres.{project_ref}"
    host = f"aws-0-{region}.pooler.supabase.com"
    ssl_ctx = ssl.create_default_context()
    try:
        conn = await asyncio.wait_for(
            asyncpg.connect(
                host=host,
                port=5432,
                user=user,
                password=password,
                database="postgres",
                ssl=ssl_ctx,
            ),
            timeout=12,
        )
        await conn.close()
        return True
    except Exception:
        return False


async def main() -> int:
    settings = get_settings()
    project_ref = project_ref_from_url(settings.supabase_url, settings.database_url)
    if not project_ref:
        print("Impossible de déduire SUPABASE_PROJECT_REF depuis .env", file=sys.stderr)
        return 1

    # Mot de passe : extraire de DATABASE_URL si possible, sinon variable dédiée
    password = None
    if "://" in settings.database_url and "@" in settings.database_url:
        userinfo = settings.database_url.split("://", 1)[1].split("@", 1)[0]
        if ":" in userinfo:
            from urllib.parse import unquote

            password = unquote(userinfo.split(":", 1)[1])

    if not password:
        print("Mot de passe introuvable dans DATABASE_URL", file=sys.stderr)
        return 1

    print(f"Projet: {project_ref} — test des poolers Supavisor (IPv4)...")
    for region in REGIONS:
        ok = await try_region(region, project_ref, password)
        status = "OK" if ok else "—"
        print(f"  aws-0-{region}.pooler.supabase.com : {status}")
        if ok:
            encoded = quote_plus(password)
            url = (
                f"postgresql+asyncpg://postgres.{project_ref}:{encoded}"
                f"@aws-0-{region}.pooler.supabase.com:5432/postgres"
            )
            print("\nAjoutez dans .env (remplacez DATABASE_URL direct) :\n")
            print(f"DATABASE_URL={url}")
            print("DATABASE_SSL=true")
            return 0

    print("\nAucune région testée n'a répondu.", file=sys.stderr)
    print("Copiez la chaîne « Session pooler » depuis Supabase → Project Settings → Database.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
