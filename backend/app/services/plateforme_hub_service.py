"""Hub personnel Login 1 — Dashboard Global scopé par profil (≠ CORE ADMIN)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import AuditLog, AuthSession, Notification, User
from app.models.plateforme import PlateformeModule
from app.services.core_admin_service import FUSEAU
from app.services.permission_service import permission_codes_from_user, user_has_permission_codes
from app.services.plateforme_access_service import PlateformeAccessService
from app.services.platform_backup_service import upload_root

_TZ = ZoneInfo(FUSEAU)
_JOURS_FR = ("lun", "mar", "mer", "jeu", "ven", "sam", "dim")
_SERIE_ALLOWED = {7, 30, 90}


class PlateformeHubService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.access = PlateformeAccessService(db)

    def resolve_vue(self, user: User) -> str:
        codes = permission_codes_from_user(user)
        if user.is_superuser or user_has_permission_codes(codes, "core.admin.access"):
            return "admin"
        if user.espaces:
            return "responsable"
        return "utilisateur"

    async def summary(self, user: User, *, jours: int = 7) -> dict:
        await self.access.ensure_catalogue()
        vue = self.resolve_vue(user)
        jours = jours if jours in _SERIE_ALLOWED else 7
        now = datetime.now(timezone.utc)

        espaces = await self.access.list_espaces()
        payload = self.access.serialize_espaces_for(user, espaces)
        granted_espace_codes = [e["id"] for e in payload if e.get("accessible")]
        granted_module_codes = [
            m["id"]
            for e in payload
            if e.get("accessible")
            for m in (e.get("modules") or [])
            if m.get("accessible") or m.get("route")
        ]

        depts = [e for e in payload if e.get("accessible") or e.get("statut") == "bientot"]
        depts_ouverts = [e for e in payload if e.get("accessible") and e.get("statut") == "actif"]
        modules: list[dict] = []
        for e in payload:
            if not e.get("accessible"):
                continue
            for m in e.get("modules") or []:
                modules.append(
                    {
                        **m,
                        "espace_id": e["id"],
                        "espace_titre": e["titre"],
                        "espace_route": e.get("route"),
                    }
                )

        unread_perso = await self._count_unread(user_id=user.id)
        sessions_perso = await self._count_sessions(now=now, user_id=user.id)

        all_mods = (
            await self.db.execute(
                select(PlateformeModule).where(PlateformeModule.is_active.is_(True))
            )
        ).scalars().all()
        by_statut: dict[str, int] = {}
        for m in all_mods:
            by_statut[m.statut] = by_statut.get(m.statut, 0) + 1

        plateforme = {
            "ok": by_statut.get("maintenance", 0) == 0 and by_statut.get("bloque", 0) == 0,
            "departements": len(espaces),
            "modules": len(all_mods),
            "modules_actifs": by_statut.get("actif", 0),
            "maintenance": by_statut.get("maintenance", 0) + by_statut.get("mise_a_jour", 0),
            "developpement": by_statut.get("developpement", 0) + by_statut.get("bientot", 0),
            "suspendus": by_statut.get("suspendu", 0) + by_statut.get("bloque", 0),
            "par_statut": by_statut,
        }

        if vue == "admin":
            kpis, sessions_actives = await self._kpis_admin(now=now, plateforme=plateforme)
        elif vue == "responsable":
            kpis, sessions_actives = await self._kpis_responsable(
                now=now,
                granted_espace_codes=granted_espace_codes,
                granted_module_codes=granted_module_codes,
                modules=modules,
                unread=unread_perso,
            )
        else:
            kpis, sessions_actives = self._kpis_utilisateur(
                depts_ouverts=depts_ouverts,
                modules=modules,
                unread=unread_perso,
                sessions=sessions_perso,
            )

        modules_recents = await self._modules_recents(user, modules=modules, limit=6)

        return {
            "vue": vue,
            "user_full_name": user.full_name,
            "departements_accessibles": len(depts_ouverts),
            "departements_visibles": len(depts),
            "modules_accessibles": len(
                [m for m in modules if m.get("accessible") or m.get("route")]
            ),
            "modules_ouverts": len(
                [m for m in modules if m.get("statut") == "actif" and m.get("route")]
            ),
            "notifications_non_lues": unread_perso,
            "sessions_actives": sessions_actives,
            "kpis": kpis,
            "plateforme": plateforme,
            # Santé runtime : réservée aux admins CORE (pas user / responsable).
            "etat_plateforme": await self._etat_plateforme(now=now) if vue == "admin" else None,
            "activite_jours": jours,
            "activite_serie": await self.usage_series(user, jours=jours),
            "mes_modules": modules[:12],
            "modules_recents": modules_recents,
        }

    async def usage_series(self, user: User, *, jours: int = 7) -> list[dict]:
        jours = jours if jours in _SERIE_ALLOWED else 7
        vue = self.resolve_vue(user)
        now_local = datetime.now(_TZ)
        start_local = datetime.combine(
            (now_local.date() - timedelta(days=jours - 1)),
            datetime.min.time(),
            tzinfo=_TZ,
        )
        start_utc = start_local.astimezone(timezone.utc)

        day_expr = func.date(func.timezone(FUSEAU, AuditLog.created_at))
        stmt = (
            select(day_expr.label("jour"), func.count().label("n"))
            .where(AuditLog.created_at >= start_utc)
            .group_by(day_expr)
        )
        stmt = self._scope_audit_stmt(stmt, user=user, vue=vue)
        rows = (await self.db.execute(stmt)).all()
        buckets: dict[date, int] = {}
        for jour, n in rows:
            if jour is None:
                continue
            if isinstance(jour, datetime):
                jour = jour.date()
            buckets[jour] = int(n or 0)

        out: list[dict] = []
        for i in range(jours):
            d = now_local.date() - timedelta(days=jours - 1 - i)
            label = _JOURS_FR[d.weekday()] if jours <= 7 else f"{d.day:02d}/{d.month:02d}"
            out.append({"date": d.isoformat(), "label": label, "count": buckets.get(d, 0)})
        return out

    async def activity(
        self,
        user: User,
        *,
        limit: int = 12,
        offset: int = 0,
    ) -> list[dict]:
        vue = self.resolve_vue(user)
        stmt = (
            select(AuditLog)
            .options(selectinload(AuditLog.user))
            .order_by(AuditLog.created_at.desc())
            .offset(max(offset, 0))
            .limit(limit)
        )
        stmt = self._scope_audit_stmt(stmt, user=user, vue=vue)
        rows = list((await self.db.execute(stmt)).scalars().unique().all())
        out = []
        for row in rows:
            who = row.user.full_name if row.user else None
            out.append(
                {
                    "id": str(row.id),
                    "action": row.action,
                    "entity": row.entity,
                    "entity_id": row.entity_id,
                    "espace_code": row.espace_code,
                    "module_code": row.module_code,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "who": who,
                    "label": self._activity_label(row, include_who=vue == "admin"),
                }
            )
        return out

    def _scope_audit_stmt(self, stmt, *, user: User, vue: str):
        if vue == "admin":
            return stmt
        if vue == "responsable":
            codes = list(user.espace_codes or [])
            if not codes:
                return stmt.where(AuditLog.user_id == user.id)
            return stmt.where(
                or_(
                    AuditLog.espace_code.in_(codes),
                    AuditLog.user_id == user.id,
                )
            )
        return stmt.where(AuditLog.user_id == user.id)

    async def _kpis_admin(self, *, now: datetime, plateforme: dict) -> tuple[list[dict], int]:
        users_total = await self._count(
            select(func.count()).select_from(User).where(User.deleted_at.is_(None))
        )
        sessions = await self._count_sessions(now=now)
        alertes = await self._count(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.archived.is_(False),
                Notification.lu.is_(False),
                Notification.priorite.in_(("attention", "avertissement", "critique")),
            )
        )
        kpis = [
            {
                "key": "departements",
                "label": "Départements",
                "value": plateforme["departements"],
                "hint": "Départements catalogue",
            },
            {
                "key": "modules",
                "label": "Modules",
                "value": plateforme["modules"],
                "hint": "Modules catalogue actifs",
            },
            {
                "key": "utilisateurs",
                "label": "Utilisateurs",
                "value": users_total,
                "hint": "Comptes non supprimés",
            },
            {
                "key": "sessions",
                "label": "Sessions actives",
                "value": sessions,
                "hint": "Utilisateurs actuellement connectés",
            },
            {
                "key": "alertes",
                "label": "Alertes",
                "value": alertes,
                "hint": "Notifications prioritaires non lues",
            },
            {
                "key": "maintenance",
                "label": "Maintenance",
                "value": plateforme["maintenance"],
                "hint": "Modules en maintenance / mise à jour",
            },
        ]
        return kpis, sessions

    async def _kpis_responsable(
        self,
        *,
        now: datetime,
        granted_espace_codes: list[str],
        granted_module_codes: list[str],
        modules: list[dict],
        unread: int,
    ) -> tuple[list[dict], int]:
        modules_actifs = len(
            [m for m in modules if m.get("statut") == "actif" and (m.get("accessible") or m.get("route"))]
        )
        sessions = 0
        if granted_module_codes:
            sessions = await self._count(
                select(func.count())
                .select_from(AuthSession)
                .where(
                    AuthSession.revoked_at.is_(None),
                    AuthSession.expires_at > now,
                    AuthSession.module_code.in_(granted_module_codes),
                )
            )
        alertes = unread
        if granted_espace_codes:
            alertes = await self._count(
                select(func.count())
                .select_from(Notification)
                .where(
                    Notification.archived.is_(False),
                    Notification.lu.is_(False),
                    or_(
                        Notification.espace_code.in_(granted_espace_codes),
                        Notification.module_code.in_(granted_module_codes or ["__none__"]),
                    ),
                )
            )
        kpis = [
            {
                "key": "departements",
                "label": "Départements",
                "value": len(granted_espace_codes),
                "hint": "Vos départements",
            },
            {
                "key": "modules",
                "label": "Modules",
                "value": len(modules),
                "hint": "Modules de vos départements",
            },
            {
                "key": "modules_actifs",
                "label": "Modules actifs",
                "value": modules_actifs,
                "hint": "Modules ouverts dans vos départements",
            },
            {
                "key": "sessions",
                "label": "Sessions actives",
                "value": sessions,
                "hint": "Sessions module de vos départements",
            },
            {
                "key": "alertes",
                "label": "Alertes",
                "value": alertes,
                "hint": "Notifications liées à vos départements",
            },
            {
                "key": "notifications",
                "label": "Notifications",
                "value": unread,
                "hint": "Vos notifications non lues",
            },
        ]
        return kpis, sessions

    @staticmethod
    def _kpis_utilisateur(
        *,
        depts_ouverts: list,
        modules: list[dict],
        unread: int,
        sessions: int,
    ) -> tuple[list[dict], int]:
        kpis = [
            {
                "key": "departements",
                "label": "Départements",
                "value": len(depts_ouverts),
                "hint": "Départements accessibles",
            },
            {
                "key": "modules",
                "label": "Modules",
                "value": len([m for m in modules if m.get("accessible") or m.get("route")]),
                "hint": "Modules auxquels vous avez accès",
            },
            {
                "key": "sessions",
                "label": "Sessions actives",
                "value": sessions,
                "hint": "Vos sessions encore valides",
            },
            {
                "key": "notifications",
                "label": "Notifications",
                "value": unread,
                "hint": "Messages non lus",
            },
        ]
        return kpis, sessions

    async def _etat_plateforme(self, *, now: datetime) -> dict:
        db_ok = True
        try:
            await self.db.execute(text("SELECT 1"))
        except Exception:
            db_ok = False

        auth_ok = True
        try:
            await self._count(
                select(func.count())
                .select_from(AuthSession)
                .where(AuthSession.revoked_at.is_(None), AuthSession.expires_at > now)
            )
        except Exception:
            auth_ok = False

        storage_ok: bool | None
        try:
            storage_ok = upload_root().exists()
        except Exception:
            storage_ok = None

        notif_ok = True
        try:
            await self._count(select(func.count()).select_from(Notification))
        except Exception:
            notif_ok = False

        def _comp(key: str, label: str, ok: bool | None) -> dict:
            if ok is None:
                status = "non_verifie"
                status_label = "Non vérifié"
            elif ok:
                status = "operationnel"
                status_label = "Opérationnel" if key != "notifications" else "Opérationnelles"
                if key == "application":
                    status_label = "Opérationnelle"
                if key == "base":
                    status_label = "Opérationnelle"
                if key == "auth":
                    status_label = "Opérationnelle"
            else:
                status = "degrade"
                status_label = "Dégradé"
            return {
                "key": key,
                "label": label,
                "ok": ok,
                "status": status,
                "status_label": status_label,
            }

        components = [
            _comp("application", "Application", True),
            _comp("base", "Base de données", db_ok),
            _comp("auth", "Authentification", auth_ok),
            _comp("stockage", "Stockage", storage_ok),
            _comp("notifications", "Notifications", notif_ok),
        ]
        overall = all(c["ok"] is not False for c in components)
        return {
            "ok": overall,
            "verifie_at": now.astimezone(_TZ).isoformat(),
            "fuseau": FUSEAU,
            "components": components,
        }

    async def _modules_recents(
        self, user: User, *, modules: list[dict], limit: int = 6
    ) -> list[dict]:
        by_id = {m["id"]: m for m in modules if m.get("id")}
        if not by_id:
            return []
        result = await self.db.execute(
            select(AuditLog.module_code, func.max(AuditLog.created_at).label("last_at"))
            .where(
                AuditLog.user_id == user.id,
                AuditLog.module_code.is_not(None),
                AuditLog.module_code.in_(list(by_id.keys())),
            )
            .group_by(AuditLog.module_code)
            .order_by(func.max(AuditLog.created_at).desc())
            .limit(limit)
        )
        out: list[dict] = []
        for code, _last in result.all():
            mod = by_id.get(code)
            if mod:
                out.append(mod)
        return out

    async def _count_unread(self, *, user_id) -> int:
        return await self._count(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.lu.is_(False),
                Notification.archived.is_(False),
            )
        )

    async def _count_sessions(self, *, now: datetime, user_id=None) -> int:
        stmt = (
            select(func.count())
            .select_from(AuthSession)
            .where(AuthSession.revoked_at.is_(None), AuthSession.expires_at > now)
        )
        if user_id is not None:
            stmt = stmt.where(AuthSession.user_id == user_id)
        return await self._count(stmt)

    async def _count(self, stmt) -> int:
        value = (await self.db.execute(stmt)).scalar()
        return int(value or 0)

    @staticmethod
    def _activity_label(row: AuditLog, *, include_who: bool = False) -> str:
        action = (row.action or "").replace("_", " ")
        entity = row.entity or "élément"
        if row.module_code:
            base = f"{action} · {entity} ({row.module_code})"
        elif row.espace_code:
            base = f"{action} · {entity} ({row.espace_code})"
        else:
            base = f"{action} · {entity}"
        if include_who and row.user:
            return f"{row.user.full_name} — {base}"
        return base
