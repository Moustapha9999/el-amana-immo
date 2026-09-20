"""Centre de contrôle sécurité — recherche users, dossier, MFA admin, overview."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import AuthSession, SecurityIncident, User
from app.services.auth_service import AuthService
from app.services.core_admin_service import CoreAdminService


class CoreAdminSecurityCenterService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def search_users(self, q: str, *, limit: int = 12) -> list[dict[str, Any]]:
        term = (q or "").strip()
        stmt = (
            select(User)
            .options(
                selectinload(User.espaces),
                selectinload(User.modules),
            )
            .where(User.deleted_at.is_(None))
            .order_by(User.full_name.asc())
            .limit(min(limit, 25))
        )
        if len(term) >= 1:
            pattern = f"%{term.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(User.full_name).like(pattern),
                    func.lower(User.email).like(pattern),
                    func.lower(func.coalesce(User.phone, "")).like(pattern),
                )
            )
        rows = (await self.db.execute(stmt)).scalars().all()
        return [self._user_search_item(u) for u in rows]

    def _user_search_item(self, u: User) -> dict[str, Any]:
        parts = (u.full_name or "").strip().split(None, 1)
        return {
            "id": str(u.id),
            "full_name": u.full_name,
            "prenom": parts[0] if parts else "",
            "nom": parts[1] if len(parts) > 1 else (parts[0] if parts else ""),
            "email": u.email,
            "phone": u.phone,
            "login": u.email,
            "is_active": u.is_active,
            "totp_enabled": bool(u.totp_enabled),
            "espaces": [{"code": e.code, "label": e.label} for e in (u.espaces or [])],
            "modules": [{"code": m.code, "label": m.label} for m in (u.modules or [])],
        }

    async def user_dossier(self, user_id: UUID) -> dict[str, Any] | None:
        user = await AuthService(self.db).get_by_id(user_id, include_inactive=True)
        if user is None or user.deleted_at is not None:
            return None
        now = datetime.now(timezone.utc)
        active_q = await self.db.execute(
            select(func.count())
            .select_from(AuthSession)
            .where(
                AuthSession.user_id == user.id,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
            )
        )
        sessions_actives = int(active_q.scalar_one() or 0)
        item = self._user_search_item(user)
        item.update(
            {
                "is_superuser": user.is_superuser,
                "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
                "sessions_actives": sessions_actives,
                "login1": user.email,
                "login2": user.email,
                "password_shared": True,
                "note_auth": (
                    "Login 1 (plateforme) et Login 2 (module) partagent le même identifiant "
                    "(e-mail) et le même mot de passe hashé. Pas de second secret."
                ),
            }
        )
        return item

    async def update_login(
        self, user_id: UUID, *, new_email: str, actor: User
    ) -> dict[str, Any]:
        email = new_email.strip().lower()
        if not email or "@" not in email:
            raise ValueError("E-mail invalide")
        user = await AuthService(self.db).get_by_id(user_id, include_inactive=True)
        if user is None:
            raise ValueError("Utilisateur introuvable")
        if user.id == actor.id and email != user.email.lower():
            # autorisé mais sensible — laisser passer
            pass
        existing = await AuthService(self.db).find_active_by_email(email)
        if existing is None:
            result = await self.db.execute(
                select(User).where(func.lower(User.email) == email, User.deleted_at.is_(None))
            )
            existing = result.scalar_one_or_none()
        if existing is not None and existing.id != user.id:
            raise ValueError("Cet e-mail est déjà utilisé")
        old = user.email
        from app.schemas.auth import UserUpdate

        await CoreAdminService(self.db).update_user(
            user_id, UserUpdate(email=email), actor=actor
        )
        return {"id": str(user_id), "old_login": old, "new_login": email}

    async def reset_password(
        self, user_id: UUID, *, password: str | None, actor: User
    ) -> dict[str, Any]:
        from app.core.temp_password import generate_temporary_password

        user = await AuthService(self.db).get_by_id(user_id, include_inactive=True)
        if user is None:
            raise ValueError("Utilisateur introuvable")
        pwd = (password or "").strip() or generate_temporary_password()
        await CoreAdminService(self.db).reset_access(user.id, pwd, actor=actor)
        return {
            "id": str(user.id),
            "email": user.email,
            "temporary_password": pwd,
            "message": "Mot de passe réinitialisé (Login 1 et Login 2). Sessions révoquées.",
        }

    async def mfa_disable(self, user_id: UUID) -> dict[str, Any]:
        user = await AuthService(self.db).get_by_id(user_id, include_inactive=True)
        if user is None:
            raise ValueError("Utilisateur introuvable")
        user.totp_enabled = False
        user.totp_secret = None
        await self.db.flush()
        return {"id": str(user.id), "totp_enabled": False}

    async def mfa_reset(self, user_id: UUID) -> dict[str, Any]:
        """Révoque le secret MFA — l’utilisateur devra ré-enrôler."""
        return await self.mfa_disable(user_id)

    async def overview(self) -> dict[str, Any]:
        from app.services.core_admin_ops_service import CoreAdminOpsService

        snap = await CoreAdminOpsService(self.db).security_settings()
        kpis = await CoreAdminService(self.db).users_kpis()
        now = datetime.now(timezone.utc)
        incidents_ouverts = 0
        incidents_critiques = 0
        try:
            r = await self.db.execute(
                select(func.count())
                .select_from(SecurityIncident)
                .where(SecurityIncident.statut.in_(("ouvert", "en_analyse", "en_traitement")))
            )
            incidents_ouverts = int(r.scalar_one() or 0)
            r2 = await self.db.execute(
                select(func.count())
                .select_from(SecurityIncident)
                .where(
                    SecurityIncident.statut.in_(("ouvert", "en_analyse", "en_traitement")),
                    SecurityIncident.niveau.in_(("critique", "eleve", "élevé")),
                )
            )
            incidents_critiques = int(r2.scalar_one() or 0)
        except Exception:
            pass

        last_audit = None
        try:
            from app.models.audit import AuditLog

            row = (
                await self.db.execute(
                    select(AuditLog.created_at).order_by(AuditLog.created_at.desc()).limit(1)
                )
            ).scalar_one_or_none()
            if row:
                last_audit = row.isoformat() if hasattr(row, "isoformat") else str(row)
        except Exception:
            pass

        last_backup = None
        try:
            from app.models.platform_ops import PlatformBackup

            row = (
                await self.db.execute(
                    select(PlatformBackup.created_at)
                    .order_by(PlatformBackup.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if row:
                last_backup = row.isoformat() if hasattr(row, "isoformat") else str(row)
        except Exception:
            pass

        mfa_enabled = int(kpis.get("totp") or 0)
        users_actifs = int(kpis.get("actifs") or 0)
        mfa_pct = round((mfa_enabled / users_actifs) * 100) if users_actifs else 0

        return {
            "snapshot": snap,
            "utilisateurs_total": int(kpis.get("total") or 0),
            "utilisateurs_actifs": users_actifs,
            "sessions_actives": snap.get("sessions_actives", 0),
            "sessions_platform": snap.get("sessions_platform", 0),
            "sessions_module": snap.get("sessions_module", 0),
            "mfa_actives": mfa_enabled,
            "mfa_pct": mfa_pct,
            "comptes_verrouilles": len(snap.get("comptes_verrouilles") or []),
            "alertes": snap.get("alertes_fenetre", 0),
            "incidents_ouverts": incidents_ouverts,
            "incidents_critiques": incidents_critiques,
            "dernier_audit": last_audit,
            "derniere_sauvegarde": last_backup,
            "etat": snap.get("etat") or {},
            "verifie_at": snap.get("verifie_at"),
            "fuseau": snap.get("fuseau") or "Africa/Nouakchott",
        }

    async def list_incidents(
        self,
        *,
        statut: str | None = None,
        niveau: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        try:
            filters = []
            if statut and statut != "tous":
                filters.append(SecurityIncident.statut == statut)
            if niveau and niveau != "tous":
                filters.append(SecurityIncident.niveau == niveau)
            stmt = select(SecurityIncident).order_by(SecurityIncident.created_at.desc()).limit(limit)
            if filters:
                stmt = stmt.where(and_(*filters))
            rows = (await self.db.execute(stmt)).scalars().all()
        except Exception:
            return {"items": [], "total": 0, "available": False}
        return {
            "available": True,
            "total": len(rows),
            "items": [self._incident_dict(r) for r in rows],
        }

    def _incident_dict(self, r: SecurityIncident) -> dict[str, Any]:
        return {
            "id": str(r.id),
            "titre": r.titre,
            "description": r.description,
            "type_incident": getattr(r, "type_incident", None) or "autre",
            "niveau": r.niveau,
            "statut": r.statut,
            "responsable": r.responsable,
            "actions": r.actions,
            "resolution": r.resolution,
            "module_code": getattr(r, "module_code", None),
            "espace_code": getattr(r, "espace_code", None),
            "user_concerne_id": str(r.user_concerne_id)
            if getattr(r, "user_concerne_id", None)
            else None,
            "closed_at": r.closed_at.isoformat() if r.closed_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }

    async def create_incident(self, payload: dict[str, Any], *, actor: User) -> SecurityIncident:
        titre = str(payload.get("titre") or "").strip()
        if not titre:
            raise ValueError("Titre requis")
        niveau = str(payload.get("niveau") or "moyen").strip().lower()[:20]
        statut = str(payload.get("statut") or "ouvert").strip().lower()[:30]
        type_incident = str(payload.get("type_incident") or "autre").strip().lower()[:40]
        user_concerne_id = payload.get("user_concerne_id")
        uid = None
        if user_concerne_id:
            try:
                uid = UUID(str(user_concerne_id))
            except ValueError as exc:
                raise ValueError("user_concerne_id invalide") from exc
        incident = SecurityIncident(
            titre=titre,
            description=str(payload.get("description") or "").strip() or None,
            niveau=niveau,
            statut=statut,
            type_incident=type_incident,
            module_code=str(payload.get("module_code") or "").strip()[:80] or None,
            espace_code=str(payload.get("espace_code") or "").strip()[:80] or None,
            user_concerne_id=uid,
            actions=str(payload.get("actions") or "").strip() or None,
            responsable=str(payload.get("responsable") or actor.email).strip()[:255] or None,
            resolution=str(payload.get("resolution") or "").strip() or None,
            created_by_id=actor.id,
        )
        if statut in ("resolu", "clos", "résolu"):
            incident.closed_at = datetime.now(timezone.utc)
        self.db.add(incident)
        await self.db.flush()
        return incident

    async def update_incident(self, incident_id: UUID, payload: dict[str, Any]) -> SecurityIncident:
        result = await self.db.execute(
            select(SecurityIncident).where(SecurityIncident.id == incident_id)
        )
        incident = result.scalar_one_or_none()
        if incident is None:
            raise ValueError("Incident introuvable")
        for key in (
            "titre",
            "description",
            "niveau",
            "statut",
            "actions",
            "responsable",
            "resolution",
            "type_incident",
            "module_code",
            "espace_code",
        ):
            if key not in payload:
                continue
            val = payload[key]
            if isinstance(val, str):
                val = val.strip()
            if key == "titre":
                if not val:
                    raise ValueError("Titre requis")
                incident.titre = str(val)
            else:
                setattr(incident, key, val or None)
        if "user_concerne_id" in payload:
            raw = payload.get("user_concerne_id")
            incident.user_concerne_id = UUID(str(raw)) if raw else None
        if incident.statut in ("resolu", "clos", "résolu"):
            if not incident.closed_at:
                incident.closed_at = datetime.now(timezone.utc)
        elif incident.statut in ("ouvert", "en_analyse", "en_traitement"):
            incident.closed_at = None
        await self.db.flush()
        return incident

    async def get_incident(self, incident_id: UUID) -> SecurityIncident | None:
        result = await self.db.execute(
            select(SecurityIncident).where(SecurityIncident.id == incident_id)
        )
        return result.scalar_one_or_none()

    async def delete_incident(self, incident_id: UUID) -> dict[str, Any]:
        incident = await self.get_incident(incident_id)
        if incident is None:
            raise ValueError("Incident introuvable")
        meta = self._incident_dict(incident)
        await self.db.delete(incident)
        await self.db.flush()
        return meta
