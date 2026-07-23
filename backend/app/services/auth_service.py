from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import create_access_token, create_refresh_token, get_password_hash, verify_password
from app.models import Role, User
from app.schemas.auth import TokenPair, UserCreate


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def authenticate(self, email: str, password: str) -> User | None:
        result = await self.db.execute(
            select(User).options(selectinload(User.roles)).where(User.email == email, User.is_active.is_(True))
        )
        user = result.scalar_one_or_none()
        if user is None or not verify_password(password, user.hashed_password):
            return None
        user.last_login_at = datetime.now(UTC)
        await self.db.flush()
        return user

    def build_tokens(self, user: User) -> TokenPair:
        role_codes = [r.code for r in user.roles]
        claims = {"roles": role_codes, "is_superuser": user.is_superuser}
        return TokenPair(
            access_token=create_access_token(user.id, claims),
            refresh_token=create_refresh_token(user.id),
        )

    async def create_user(self, payload: UserCreate) -> User:
        existing = await self.db.execute(select(User).where(User.email == payload.email))
        if existing.scalar_one_or_none():
            raise ValueError("Email déjà utilisé")

        user = User(
            email=payload.email,
            full_name=payload.full_name,
            hashed_password=get_password_hash(payload.password),
            agence_id=payload.agence_id,
        )
        if payload.role_codes:
            roles_result = await self.db.execute(select(Role).where(Role.code.in_(payload.role_codes)))
            user.roles = list(roles_result.scalars().all())

        self.db.add(user)
        await self.db.flush()
        return user

    async def get_by_id(self, user_id: UUID) -> User | None:
        result = await self.db.execute(
            select(User).options(selectinload(User.roles)).where(User.id == user_id, User.is_active.is_(True))
        )
        return result.scalar_one_or_none()

    async def count_users(self) -> int:
        result = await self.db.execute(select(func.count()).select_from(User))
        return int(result.scalar_one())

    async def reset_password(self, token: str, new_password: str) -> None:
        from app.core.security import decode_token

        payload = decode_token(token)
        if payload.get("type") != "password_reset":
            raise ValueError("Token invalide")
        user = await self.get_by_id(UUID(payload["sub"]))
        if user is None:
            raise ValueError("Utilisateur introuvable")
        user.hashed_password = get_password_hash(new_password)
        await self.db.flush()

    async def find_active_by_email(self, email: str) -> User | None:
        result = await self.db.execute(
            select(User).where(User.email == email, User.is_active.is_(True), User.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def list_users(self, page: int, size: int) -> tuple[list[User], int]:
        from app.core.pagination import page_offset

        count = await self.db.execute(select(func.count()).select_from(User).where(User.is_active.is_(True)))
        total = int(count.scalar_one())
        result = await self.db.execute(
            select(User)
            .options(selectinload(User.roles))
            .where(User.is_active.is_(True))
            .order_by(User.full_name.asc())
            .offset(page_offset(page, size))
            .limit(size)
        )
        return list(result.scalars().all()), total
