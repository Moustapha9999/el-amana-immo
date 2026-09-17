"""Agrégats CORE ADMIN — compteurs SQL, pas de cache."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.models.audit import AuditLog
from app.models.auth import AuthLoginAttempt, AuthSession, User
from app.models.plateforme import PlateformeEspace, PlateformeModule
from app.schemas.auth import UserCreate, UserRead, UserUpdate
from app.services.auth_service import AuthService
from app.services.auth_session_service import AuthSessionService

NOUAKCHOTT = ZoneInfo("Africa/Nouakchott")
FUSEAU = "Africa/Nouakchott"


def day_bounds_nouakchott(now: datetime | None = None) -> tuple[datetime, datetime]:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    local = moment.astimezone(NOUAKCHOTT)
    start = datetime.combine(local.date(), time.min, tzinfo=NOUAKCHOTT)
    return start, start + timedelta(days=1)


def serialize_activity(log: AuditLog) -> dict:
    user = log.user
    return {
        "id": str(log.id),
        "who": user.full_name if user else "Système",
        "email": user.email if user else None,
        "action": log.action,
        "entity": log.entity,
        "entity_id": log.entity_id,
        "module": log.module_code,
        "espace": log.espace_code,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


def platform_health(*, db_ok: bool, modules_actifs: int) -> dict:
    return {
        "core": {"ok": True, "label": "CORE"},
        "api": {"ok": True, "label": "API"},
        "auth": {"ok": True, "label": "Auth"},
        "db": {"ok": db_ok, "label": "Base de données"},
        "modules": {"ok": modules_actifs > 0, "label": "Modules"},
    }


class CoreAdminService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _count(self, stmt) -> int:
        result = await self.db.execute(stmt)
        value = result.scalar()
        return int(value or 0)

    async def dashboard(self) -> dict:
        now = datetime.now(timezone.utc)
        settings = get_settings()
        start, end = day_bounds_nouakchott(now)
        lockout_from = now - timedelta(minutes=settings.login_lockout_window_minutes)

        users_total = await self._count(
            select(func.count()).select_from(User).where(User.deleted_at.is_(None))
        )
        users_actifs = await self._count(
            select(func.count())
            .select_from(User)
            .where(User.deleted_at.is_(None), User.is_active.is_(True))
        )
        departements = await self._count(
            select(func.count())
            .select_from(PlateformeEspace)
            .where(PlateformeEspace.is_active.is_(True))
        )
        modules = await self._count(
            select(func.count())
            .select_from(PlateformeModule)
            .where(PlateformeModule.is_active.is_(True))
        )
        modules_actifs = await self._count(
            select(func.count())
            .select_from(PlateformeModule)
            .where(PlateformeModule.is_active.is_(True), PlateformeModule.statut == "actif")
        )
        sessions = await self._count(
            select(func.count())
            .select_from(AuthSession)
            .where(AuthSession.revoked_at.is_(None), AuthSession.expires_at > now)
        )
        alertes = await self._count(
            select(func.count())
            .select_from(AuthLoginAttempt)
            .where(
                AuthLoginAttempt.success.is_(False),
                AuthLoginAttempt.created_at >= lockout_from,
            )
        )
        actions = await self._count(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.created_at >= start, AuditLog.created_at < end)
        )

        db_ok = True
        try:
            await self.db.execute(text("SELECT 1"))
        except Exception:
            db_ok = False

        result = await self.db.execute(
            select(AuditLog)
            .options(selectinload(AuditLog.user))
            .order_by(AuditLog.created_at.desc())
            .limit(12)
        )
        logs = result.scalars().all()

        return {
            "kpis": {
                "utilisateurs": users_total,
                "utilisateurs_actifs": users_actifs,
                "departements": departements,
                "modules": modules,
                "modules_actifs": modules_actifs,
                "sessions_actives": sessions,
                "alertes_securite": alertes,
                "actions_aujourd_hui": actions,
            },
            "activite": [serialize_activity(row) for row in logs],
            "etat": platform_health(db_ok=db_ok, modules_actifs=modules_actifs),
            "fuseau": FUSEAU,
        }

    async def users_kpis(self) -> dict:
        base = User.deleted_at.is_(None)
        return {
            "total": await self._count(select(func.count()).select_from(User).where(base)),
            "actifs": await self._count(
                select(func.count()).select_from(User).where(base, User.is_active.is_(True))
            ),
            "inactifs": await self._count(
                select(func.count()).select_from(User).where(base, User.is_active.is_(False))
            ),
            "superusers": await self._count(
                select(func.count()).select_from(User).where(base, User.is_superuser.is_(True))
            ),
            "totp": await self._count(
                select(func.count()).select_from(User).where(base, User.totp_enabled.is_(True))
            ),
            "jamais_connectes": await self._count(
                select(func.count()).select_from(User).where(base, User.last_login_at.is_(None))
            ),
        }

    async def list_users(
        self,
        page: int,
        size: int,
        *,
        search: str | None = None,
        statut: str = "tous",
        role_code: str | None = None,
        espace_code: str | None = None,
        module_code: str | None = None,
        profil: str = "tous",
        totp: str = "tous",
        connexion: str = "tous",
    ) -> tuple[list[User], int]:
        return await AuthService(self.db).list_users(
            page,
            size,
            search=search,
            statut=statut,
            role_code=role_code,
            espace_code=espace_code,
            module_code=module_code,
            profil=profil,
            totp=totp,
            connexion=connexion,
        )

    async def list_roles(self):
        return await AuthService(self.db).list_roles()

    async def get_user(self, user_id: UUID) -> User | None:
        return await AuthService(self.db).get_by_id(user_id, include_inactive=True)

    def _guard_superuser(self, actor: User, *, want_superuser: bool | None) -> None:
        if want_superuser and not actor.is_superuser:
            raise ValueError("Seul un superutilisateur peut attribuer ce statut")

    async def create_user(self, payload: UserCreate, *, actor: User) -> User:
        self._guard_superuser(actor, want_superuser=payload.is_superuser)
        return await AuthService(self.db).create_user(payload)

    async def update_user(self, user_id: UUID, payload: UserUpdate, *, actor: User) -> User:
        self._guard_superuser(actor, want_superuser=payload.is_superuser)
        if payload.is_superuser is False and user_id == actor.id:
            raise ValueError("Impossible de retirer votre propre statut superutilisateur")
        return await AuthService(self.db).update_user(
            user_id, payload, include_inactive=True
        )

    async def set_active(self, user_id: UUID, *, active: bool, actor: User) -> User:
        if user_id == actor.id:
            raise ValueError("Impossible de modifier l'état de votre propre compte")
        user = await self.get_user(user_id)
        if user is None:
            raise ValueError("Utilisateur introuvable")
        return await AuthService(self.db).update_user(
            user_id, UserUpdate(is_active=active), include_inactive=True
        )

    async def reset_access(self, user_id: UUID, password: str, *, actor: User) -> User:
        user = await self.get_user(user_id)
        if user is None:
            raise ValueError("Utilisateur introuvable")
        _ = actor
        return await AuthService(self.db).update_user(
            user_id, UserUpdate(password=password), include_inactive=True
        )

    async def archive_user(self, user_id: UUID, *, actor: User) -> User:
        if user_id == actor.id:
            raise ValueError("Impossible de supprimer votre propre compte")
        user = await self.get_user(user_id)
        if user is None:
            raise ValueError("Utilisateur introuvable")
        user.is_active = False
        user.deleted_at = datetime.now(timezone.utc)
        await AuthSessionService(self.db).revoke_all_for_user(user_id)
        await self.db.flush()
        return user

    async def user_fiche(self, user_id: UUID) -> dict | None:
        user = await self.get_user(user_id)
        if user is None:
            return None
        now = datetime.now(timezone.utc)
        sessions_result = await self.db.execute(
            select(AuthSession)
            .where(AuthSession.user_id == user.id)
            .order_by(AuthSession.created_at.desc())
            .limit(20)
        )
        sessions = []
        for row in sessions_result.scalars().all():
            sessions.append(
                {
                    "id": str(row.id),
                    "kind": row.kind,
                    "module_code": row.module_code,
                    "ip_address": row.ip_address,
                    "user_agent": row.user_agent,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "expires_at": row.expires_at.isoformat() if row.expires_at else None,
                    "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
                    "active": row.revoked_at is None and row.expires_at > now,
                }
            )
        logs_result = await self.db.execute(
            select(AuditLog)
            .options(selectinload(AuditLog.user))
            .where(AuditLog.user_id == user.id)
            .order_by(AuditLog.created_at.desc())
            .limit(20)
        )
        base = UserRead.model_validate(user).model_dump(mode="json")
        base["sessions"] = sessions
        base["activite"] = [serialize_activity(row) for row in logs_result.scalars().all()]
        return base
