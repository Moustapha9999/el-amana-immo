from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import get_password_hash, verify_password
from app.models import Role, User
from app.schemas.auth import UserCreate, UserUpdate
from app.services.auth_session_service import AuthSessionService


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

    async def list_roles(self) -> list[Role]:
        result = await self.db.execute(select(Role).order_by(Role.label.asc()))
        return list(result.scalars().all())

    async def _roles_by_codes(self, codes: list[str]) -> list[Role]:
        if not codes:
            return []
        roles_result = await self.db.execute(select(Role).where(Role.code.in_(codes)))
        roles = list(roles_result.scalars().all())
        found = {r.code for r in roles}
        missing = [c for c in codes if c not in found]
        if missing:
            raise ValueError(f"Rôle(s) inconnu(s) : {', '.join(missing)}")
        return roles

    async def create_user(self, payload: UserCreate) -> User:
        existing = await self.db.execute(select(User).where(User.email == payload.email))
        if existing.scalar_one_or_none():
            raise ValueError("Email déjà utilisé")

        user = User(
            email=payload.email,
            full_name=payload.full_name,
            hashed_password=get_password_hash(payload.password),
            is_superuser=payload.is_superuser,
            agence_id=payload.agence_id,
        )
        if payload.role_codes:
            user.roles = await self._roles_by_codes(payload.role_codes)

        self.db.add(user)
        await self.db.flush()
        return await self.get_by_id(user.id)  # type: ignore[return-value]

    async def update_user(self, user_id: UUID, payload: UserUpdate) -> User:
        user = await self.get_by_id(user_id)
        if user is None:
            raise ValueError("Utilisateur introuvable")

        data = payload.model_dump(exclude_unset=True)
        if "email" in data and data["email"] is not None and data["email"] != user.email:
            existing = await self.db.execute(
                select(User).where(User.email == data["email"], User.id != user_id)
            )
            if existing.scalar_one_or_none():
                raise ValueError("Email déjà utilisé")
            user.email = data["email"]

        if "full_name" in data and data["full_name"] is not None:
            user.full_name = data["full_name"]
        if "phone" in data:
            user.phone = data["phone"]
        if "agence_id" in data:
            user.agence_id = data["agence_id"]
        if "is_active" in data and data["is_active"] is not None:
            user.is_active = data["is_active"]
            if data["is_active"] is False:
                await AuthSessionService(self.db).revoke_all_for_user(user_id)
        if "is_superuser" in data and data["is_superuser"] is not None:
            user.is_superuser = data["is_superuser"]
        if "password" in data and data["password"]:
            user.hashed_password = get_password_hash(data["password"])
        if "role_codes" in data and data["role_codes"] is not None:
            user.roles = await self._roles_by_codes(data["role_codes"])

        await self.db.flush()
        return await self.get_by_id(user.id)  # type: ignore[return-value]

    async def soft_delete_user(self, user_id: UUID, *, actor_id: UUID) -> None:
        if user_id == actor_id:
            raise ValueError("Impossible de supprimer votre propre compte")
        user = await self.get_by_id(user_id)
        if user is None:
            raise ValueError("Utilisateur introuvable")
        user.is_active = False
        user.deleted_at = datetime.now(UTC)
        await AuthSessionService(self.db).revoke_all_for_user(user_id)
        await self.db.flush()

    async def get_by_id(self, user_id: UUID) -> User | None:
        result = await self.db.execute(
            select(User)
            .options(selectinload(User.roles))
            .where(User.id == user_id, User.is_active.is_(True), User.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def count_users(self) -> int:
        result = await self.db.execute(
            select(func.count()).select_from(User).where(User.is_active.is_(True), User.deleted_at.is_(None))
        )
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
        # Invalide toutes les sessions après reset mot de passe
        await AuthSessionService(self.db).revoke_all_for_user(user.id)
        await self.db.flush()

    async def find_active_by_email(self, email: str) -> User | None:
        normalized = email.strip().lower()
        result = await self.db.execute(
            select(User).where(
                func.lower(User.email) == normalized,
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_users(
        self, page: int, size: int, *, search: str | None = None
    ) -> tuple[list[User], int]:
        from app.core.pagination import page_offset

        filters = [User.is_active.is_(True), User.deleted_at.is_(None)]
        if search and search.strip():
            term = f"%{search.strip().lower()}%"
            filters.append(
                func.lower(User.full_name).like(term) | func.lower(User.email).like(term)
            )

        count = await self.db.execute(select(func.count()).select_from(User).where(*filters))
        total = int(count.scalar_one())
        result = await self.db.execute(
            select(User)
            .options(selectinload(User.roles))
            .where(*filters)
            .order_by(User.full_name.asc())
            .offset(page_offset(page, size))
            .limit(size)
        )
        return list(result.scalars().all()), total
