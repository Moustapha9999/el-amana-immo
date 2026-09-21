"""Accès espaces / modules BEA DIGITAL (grants Login 1)."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import insert, inspect as sa_inspect, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.data.plateforme_catalogue import (
    DEFAULT_ESPACE_CODE,
    DEFAULT_MODULE_CODE,
    FUNCTIONAL_PERMISSIONS,
    PLATEFORME_ESPACES,
    PLATEFORME_MODULES,
    RBAC_ROLES,
    ROLE_PERMISSIONS,
    SEED_LOCKED_ESPACE_CODES,
    SEED_LOCKED_MODULE_CODES,
)
from app.models import Permission, PlateformeEspace, PlateformeModule, Role, User
from app.models.associations import role_permissions_table

logger = logging.getLogger(__name__)


def _text_needs_utf8_repair(value: str | None) -> bool:
    """True si un libellé a perdu ses accents (souvent remplacés par '?')."""
    return bool(value) and "?" in value


def should_insert_missing_seed(*, code: str, locked: frozenset[str], bootstrap: bool) -> bool:
    """Insère une ligne seed absente seulement si système verrouillé ou 1ʳᵉ install."""
    return code in locked or bootstrap


class PlateformeAccessService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def ensure_catalogue(self) -> None:
        try:
            async with self.db.begin_nested():
                await self._sync_catalogue()
        except Exception:
            logger.exception("Synchronisation du catalogue plateforme impossible")

    async def _sync_catalogue(self) -> None:
        # Seed : Comptabilité + Immobilisations toujours présents.
        # Autres espaces/modules du catalogue Python = 1ʳᵉ install seulement.
        # CORE ADMIN (create / update / delete) = source de vérité ensuite ;
        # une suppression ne doit pas être annulée au prochain GET /plateforme/espaces.
        existing = {
            row.code: row
            for row in (await self.db.execute(select(PlateformeEspace))).scalars().all()
        }
        bootstrap = len(existing) == 0
        for item in PLATEFORME_ESPACES:
            row = existing.get(item["code"])
            if row is None:
                if not should_insert_missing_seed(
                    code=item["code"],
                    locked=SEED_LOCKED_ESPACE_CODES,
                    bootstrap=bootstrap,
                ):
                    continue
                row = PlateformeEspace(
                    code=item["code"],
                    label=item["label"],
                    description=item["description"],
                    route=item["route"],
                    statut=item["statut"],
                    sort_order=item["sort_order"],
                    is_active=True,
                )
                self.db.add(row)
                existing[item["code"]] = row
            else:
                # Seeds verrouillés : garder statut / route alignés sur le catalogue produit.
                if item["code"] in SEED_LOCKED_ESPACE_CODES:
                    row.route = item["route"]
                    row.statut = item["statut"]
                    row.sort_order = item["sort_order"]
                if _text_needs_utf8_repair(row.label):
                    row.label = item["label"]
                if _text_needs_utf8_repair(row.description):
                    row.description = item["description"]
        await self.db.flush()

        modules = {
            row.code: row
            for row in (await self.db.execute(select(PlateformeModule))).scalars().all()
        }
        for item in PLATEFORME_MODULES:
            espace = existing.get(item["espace_code"])
            if espace is None:
                continue
            row = modules.get(item["code"])
            if row is None:
                if not should_insert_missing_seed(
                    code=item["code"],
                    locked=SEED_LOCKED_MODULE_CODES,
                    bootstrap=bootstrap,
                ):
                    continue
                self.db.add(
                    PlateformeModule(
                        espace_id=espace.id,
                        code=item["code"],
                        label=item["label"],
                        description=item["description"],
                        entry_path=item["entry_path"],
                        statut=item["statut"],
                        sort_order=item["sort_order"],
                        is_active=True,
                    )
                )
            else:
                if item["code"] in SEED_LOCKED_MODULE_CODES:
                    row.entry_path = item["entry_path"]
                    row.statut = item["statut"]
                    row.sort_order = item["sort_order"]
                    row.espace_id = espace.id
                if _text_needs_utf8_repair(row.label):
                    row.label = item["label"]
                if _text_needs_utf8_repair(row.description):
                    row.description = item["description"]
        await self.db.flush()
        await self._ensure_permissions()

    async def _ensure_permissions(self) -> None:
        existing_perms = {
            row.code: row
            for row in (await self.db.execute(select(Permission))).scalars().all()
        }
        for code, label, module in FUNCTIONAL_PERMISSIONS:
            if code not in existing_perms:
                perm = Permission(code=code, label=label, module=module)
                self.db.add(perm)
                existing_perms[code] = perm
            elif _text_needs_utf8_repair(existing_perms[code].label):
                existing_perms[code].label = label
        await self.db.flush()

        existing_roles = {
            row.code: row
            for row in (await self.db.execute(select(Role))).scalars().all()
        }
        for code, label, description in RBAC_ROLES:
            role = existing_roles.get(code)
            if role is None:
                role = Role(code=code, label=label, description=description)
                self.db.add(role)
                existing_roles[code] = role
            else:
                if _text_needs_utf8_repair(role.label):
                    role.label = label
                if _text_needs_utf8_repair(role.description):
                    role.description = description
        await self.db.flush()

        # Liens rôle→permission additifs pour tous les rôles catalogue (y compris MG).
        existing_links = {
            (role_id, perm_id)
            for role_id, perm_id in (
                await self.db.execute(
                    select(
                        role_permissions_table.c.role_id,
                        role_permissions_table.c.permission_id,
                    )
                )
            ).all()
        }
        new_links: list[dict] = []
        for role_code, perm_codes in ROLE_PERMISSIONS.items():
            role = existing_roles.get(role_code)
            if role is None:
                continue
            for perm_code in perm_codes:
                perm = existing_perms.get(perm_code)
                if perm is None:
                    continue
                key = (role.id, perm.id)
                if key not in existing_links:
                    new_links.append({"role_id": role.id, "permission_id": perm.id})
                    existing_links.add(key)
        if new_links:
            await self.db.execute(insert(role_permissions_table), new_links)
            await self.db.flush()

    async def grant_defaults_if_missing(self, user: User) -> None:
        if user.modules or user.espaces:
            return
        await self.set_user_access(user, [DEFAULT_ESPACE_CODE], [DEFAULT_MODULE_CODE])

    async def grant_defaults_to_users_without_access(self) -> None:
        users = list(
            (
                await self.db.execute(
                    select(User)
                    .options(selectinload(User.espaces), selectinload(User.modules))
                    .where(User.deleted_at.is_(None))
                )
            ).scalars().all()
        )
        for user in users:
            await self.grant_defaults_if_missing(user)

    async def get_espace(self, code: str) -> PlateformeEspace | None:
        result = await self.db.execute(
            select(PlateformeEspace)
            .options(selectinload(PlateformeEspace.modules))
            .where(PlateformeEspace.code == code)
        )
        return result.scalar_one_or_none()

    async def get_module(self, code: str) -> PlateformeModule | None:
        result = await self.db.execute(
            select(PlateformeModule)
            .options(selectinload(PlateformeModule.espace))
            .where(PlateformeModule.code == code)
        )
        return result.scalar_one_or_none()

    async def list_espaces(self) -> list[PlateformeEspace]:
        result = await self.db.execute(
            select(PlateformeEspace)
            .options(selectinload(PlateformeEspace.modules))
            .where(PlateformeEspace.is_active.is_(True))
            .order_by(PlateformeEspace.sort_order.asc(), PlateformeEspace.label.asc())
        )
        return list(result.scalars().all())

    async def user_has_espace(self, user: User, espace_code: str) -> bool:
        if user.is_superuser:
            return True
        codes = {e.code for e in user.espaces}
        if espace_code in codes:
            return True
        # Recharge si la relation n'est pas peuplée
        result = await self.db.execute(
            select(PlateformeEspace.id).where(
                PlateformeEspace.code == espace_code,
                PlateformeEspace.users.any(User.id == user.id),
            )
        )
        return result.scalar_one_or_none() is not None

    async def user_has_module(self, user: User, module_code: str) -> bool:
        if user.is_superuser:
            return True
        module = await self.get_module(module_code)
        if module is None or not module.is_active:
            return False
        result = await self.db.execute(
            select(PlateformeModule.id).where(
                PlateformeModule.code == module_code,
                PlateformeModule.users.any(User.id == user.id),
            )
        )
        if result.scalar_one_or_none() is None:
            return False
        return await self.user_has_espace(user, module.espace.code)

    async def set_user_access(
        self,
        user: User,
        espace_codes: list[str] | None,
        module_codes: list[str] | None,
    ) -> None:
        if espace_codes is None and module_codes is None:
            return
        wanted_espaces = set(espace_codes or [])
        wanted_modules = set(module_codes or [])
        modules = list(
            (
                await self.db.execute(
                    select(PlateformeModule).options(selectinload(PlateformeModule.espace))
                )
            ).scalars().all()
        )
        by_m = {m.code: m for m in modules}
        missing_m = [c for c in wanted_modules if c not in by_m]
        if missing_m:
            raise ValueError(f"Module(s) inconnu(s) : {', '.join(missing_m)}")
        for code in wanted_modules:
            wanted_espaces.add(by_m[code].espace.code)

        espaces = list((await self.db.execute(select(PlateformeEspace))).scalars().all())
        by_e = {e.code: e for e in espaces}
        missing_e = [c for c in wanted_espaces if c not in by_e]
        if missing_e:
            raise ValueError(f"Espace(s) inconnu(s) : {', '.join(missing_e)}")

        if sa_inspect(user).persistent:
            await self.db.refresh(user, attribute_names=["espaces", "modules"])

        user.espaces = [by_e[c] for c in sorted(wanted_espaces)]
        user.modules = [by_m[c] for c in sorted(wanted_modules)]
        await self.db.flush()

    def serialize_espaces_for(self, user: User, espaces: list[PlateformeEspace]) -> list[dict]:
        granted_e = {e.code for e in user.espaces} if not user.is_superuser else None
        granted_m = {m.code for m in user.modules} if not user.is_superuser else None
        payload: list[dict] = []
        for espace in espaces:
            accessible = user.is_superuser or (granted_e is not None and espace.code in granted_e)
            show = espace.statut == "bientot" or accessible
            if not show:
                continue
            modules_out = []
            for mod in sorted(espace.modules, key=lambda m: (m.sort_order, m.label)):
                if not mod.is_active:
                    continue
                m_acc = user.is_superuser or (granted_m is not None and mod.code in granted_m)
                # Bientôt : visible pour tous. Autres statuts : seulement si grant module.
                m_show = mod.statut == "bientot" or m_acc
                if not m_show:
                    continue
                clickable = m_acc and mod.statut == "actif"
                # Restreint (mise à jour, maintenance, …) : carte cliquable → message d’indispo.
                openable = m_acc and mod.statut not in {"inactif", "archive"}
                modules_out.append(
                    {
                        "id": mod.code,
                        "titre": mod.label,
                        "description": mod.description,
                        "route": f"/modules/{mod.code}/acces" if openable else None,
                        "entry_path": mod.entry_path if clickable else None,
                        "statut": mod.statut,
                        "status_message": getattr(mod, "status_message", "") or "",
                        "version": getattr(mod, "version", None),
                        "accessible": clickable,
                    }
                )
            clickable_espace = accessible and espace.statut == "actif" and bool(espace.route)
            payload.append(
                {
                    "id": espace.code,
                    "titre": espace.label,
                    "description": espace.description,
                    "route": espace.route if clickable_espace else None,
                    "statut": espace.statut,
                    "accessible": clickable_espace,
                    "modules": modules_out,
                }
            )
        return payload

    async def serialize_module(self, user: User, module_code: str) -> dict | None:
        module = await self.get_module(module_code)
        if module is None or not module.is_active:
            return None
        allowed = await self.user_has_module(user, module_code)
        from app.services.permission_service import permission_codes_from_user, user_has_permission_codes
        from app.services.platform_ops_service import PlatformOpsService

        have = permission_codes_from_user(user)
        can_bypass = user_has_permission_codes(
            have, "core.admin.maintenance.manage", "core.admin.module_status.manage"
        )
        access = PlatformOpsService.module_access_payload(module, can_bypass=can_bypass)
        clickable = allowed and access["access_allowed"]
        return {
            "id": module.code,
            "titre": module.label,
            "description": module.description,
            "route": f"/modules/{module.code}/acces" if allowed else None,
            "entry_path": module.entry_path if clickable else None,
            "statut": module.statut,
            "status_message": access["status_message"],
            "version": module.version,
            "access_allowed": access["access_allowed"],
            "block_reason": access["block_reason"],
            "maintenance_ends_at": access["maintenance_ends_at"],
            "accessible": clickable,
            "espace_id": module.espace.code,
            "espace_titre": module.espace.label,
            "espace_route": module.espace.route,
        }
