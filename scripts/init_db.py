import asyncio

from app.db.base import Base
from app.db.session import engine
from app.models import entities  # noqa: F401


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print("Tables créées.")


if __name__ == "__main__":
    asyncio.run(main())
