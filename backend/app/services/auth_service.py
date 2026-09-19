from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.password_policy import validate_password_policy
from app.core.security import get_password_hash, verify_password
from app.data.plateforme_catalogue import DEFAULT_ESPACE_CODE, DEFAULT_MODULE_CODE
from app.models import PasswordHistory, Role, User
from app.models.plateforme import PlateformeEspace, PlateformeModule
from app.schemas.auth import UserCreate, UserUpdate
from app.services.auth_session_service import AuthSessionService
from app.services.plateforme_access_service import PlateformeAccessService

PASSWORD_HISTORY_KEEP = 5


async def _apply_password(
    db: AsyncSession,
    user: User,
    password: str,
    *,
    allow_same: bool = False,
) -> None:
    validate_password_policy(password)
    if not allow_same and verify_password(password, user.hashed_password):
        raise ValueError("Le nouveau mot de passe doit être différent de l'ancien.")
    # Historique N derniers hashes (table optionnelle jusqu’à migration)
    try:
        hist = await db.execute(
            select(PasswordHistory)
            .where(PasswordHistory.user_id == user.id)
            .order_by(PasswordHistory.created_at.desc())
            .limit(PASSWORD_HISTORY_KEEP)
        )
        for row in hist.scalars().all():
            if verify_password(password, row.password_hash):
                raise ValueError("Ce mot de passe a déjà été utilisé récemment.")
    except ValueError:
        raise
    except Exception:
        pass
    old_hash = user.hashed_password
    user.hashed_password = get_password_hash(password)
    if old_hash:
        try:
            db.add(PasswordHistory(user_id=user.id, password_hash=old_hash))
        except Exception:
            pass

_USER_OPTIONS = (
    selectinload(User.roles).selectinload(Role.permissions),
    selectinload(User.espaces),
    selectinload(User.modules),
)


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def authenticate(self, email: str, password: str) -> User | None:
        normalized = email.strip().lower()
        result = await self.db.execute(
            select(User)
            .options(*_USER_OPTIONS)
            .where(func.lower(User.email) == normalized, User.is_active.is_(True), User.deleted_at.is_(None))
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
        from app.core.temp_password import generate_temporary_password

        normalized = payload.email.strip().lower()
        existing = await self.db.execute(select(User).where(func.lower(User.email) == normalized))
        if existing.scalar_one_or_none():
            raise ValueError("Email déjà utilisé")

        password = (payload.password or "").strip() or generate_temporary_password()
        validate_password_policy(password)
        user = User(
            email=payload.email,
            full_name=payload.full_name,
            hashed_password=get_password_hash(password),
            is_superuser=payload.is_superuser,
            agence_id=payload.agence_id,
            phone=payload.phone,
        )
        if payload.role_codes:
            user.roles = await self._roles_by_codes(payload.role_codes)

        self.db.add(user)
        await self.db.flush()
        access = PlateformeAccessService(self.db)
        await access.ensure_catalogue()
        espace_codes = payload.espace_codes
        module_codes = payload.module_codes
        if espace_codes is None and module_codes is None:
            espace_codes = [DEFAULT_ESPACE_CODE]
            module_codes = [DEFAULT_MODULE_CODE]
        await access.set_user_access(user, espace_codes or [], module_codes or [])
        return await self.get_by_id(user.id)  # type: ignore[return-value]

    async def update_user(
        self, user_id: UUID, payload: UserUpdate, *, include_inactive: bool = False
    ) -> User:
        user = await self.get_by_id(user_id, include_inactive=include_inactive)
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
            await _apply_password(self.db, user, data["password"])
            await AuthSessionService(self.db).revoke_all_for_user(user_id)
        if "role_codes" in data and data["role_codes"] is not None:
            user.roles = await self._roles_by_codes(data["role_codes"])
        if "espace_codes" in data or "module_codes" in data:
            access = PlateformeAccessService(self.db)
            await access.ensure_catalogue()
            current_e = list(user.espace_codes)
            current_m = list(user.module_codes)
            await access.set_user_access(
                user,
                data["espace_codes"] if "espace_codes" in data and data["espace_codes"] is not None else current_e,
                data["module_codes"] if "module_codes" in data and data["module_codes"] is not None else current_m,
            )

        await self.db.flush()
        refreshed = await self.get_by_id(user.id, include_inactive=True)
        if refreshed is None:
            raise ValueError("Utilisateur introuvable")
        return refreshed

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

    async def get_by_id(self, user_id: UUID, *, include_inactive: bool = False) -> User | None:
        filters = [User.id == user_id, User.deleted_at.is_(None)]
        if not include_inactive:
            filters.append(User.is_active.is_(True))
        result = await self.db.execute(select(User).options(*_USER_OPTIONS).where(*filters))
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
        await _apply_password(self.db, user, new_password)
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
        self,
        page: int,
        size: int,
        *,
        search: str | None = None,
        statut: str = "actif",
        role_code: str | None = None,
        espace_code: str | None = None,
        module_code: str | None = None,
        profil: str = "tous",
        totp: str = "tous",
        connexion: str = "tous",
    ) -> tuple[list[User], int]:
        from app.core.pagination import page_offset

        filters = [User.deleted_at.is_(None)]
        if statut == "actif":
            filters.append(User.is_active.is_(True))
        elif statut == "inactif":
            filters.append(User.is_active.is_(False))
        elif statut != "tous":
            raise ValueError("Statut invalide")
        if role_code and role_code.strip() and role_code != "tous":
            filters.append(User.roles.any(Role.code == role_code.strip()))
        if espace_code and espace_code.strip() and espace_code != "tous":
            filters.append(User.espaces.any(PlateformeEspace.code == espace_code.strip()))
        if module_code and module_code.strip() and module_code != "tous":
            filters.append(User.modules.any(PlateformeModule.code == module_code.strip()))
        if profil == "superuser":
            filters.append(User.is_superuser.is_(True))
        elif profil == "standard":
            filters.append(User.is_superuser.is_(False))
        elif profil != "tous":
            raise ValueError("Profil invalide")
        if totp == "oui":
            filters.append(User.totp_enabled.is_(True))
        elif totp == "non":
            filters.append(User.totp_enabled.is_(False))
        elif totp != "tous":
            raise ValueError("Filtre 2FA invalide")
        if connexion == "jamais":
            filters.append(User.last_login_at.is_(None))
        elif connexion == "connecte":
            filters.append(User.last_login_at.is_not(None))
        elif connexion != "tous":
            raise ValueError("Filtre connexion invalide")
        if search and search.strip():
            term = f"%{search.strip().lower()}%"
            filters.append(
                or_(
                    func.lower(User.full_name).like(term),
                    func.lower(User.email).like(term),
                    func.lower(func.coalesce(User.phone, "")).like(term),
                    User.roles.any(
                        or_(func.lower(Role.code).like(term), func.lower(Role.label).like(term))
                    ),
                    User.espaces.any(
                        or_(
                            func.lower(PlateformeEspace.code).like(term),
                            func.lower(PlateformeEspace.label).like(term),
                        )
                    ),
                    User.modules.any(
                        or_(
                            func.lower(PlateformeModule.code).like(term),
                            func.lower(PlateformeModule.label).like(term),
                        )
                    ),
                )
            )

        count = await self.db.execute(select(func.count()).select_from(User).where(*filters))
        total = int(count.scalar_one())
        result = await self.db.execute(
            select(User)
            .options(*_USER_OPTIONS)
            .where(*filters)
            .order_by(User.full_name.asc())
            .offset(page_offset(page, size))
            .limit(size)
        )
        return list(result.scalars().all()), total
