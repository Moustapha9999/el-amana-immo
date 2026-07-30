import asyncio

from sqlalchemy import select

from app.core.security import verify_password
from app.db.session import AsyncSessionLocal, engine
from app.models import User


async def main() -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.email == "admin@el-amana.mr"))
        user = result.scalar_one_or_none()
        if user is None:
            print("USER_MISSING")
            return
        ok = verify_password("Admin@2026", user.hashed_password)
        print("USER_FOUND", user.is_active, "PASSWORD_OK" if ok else "PASSWORD_BAD")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
