"""CORE ADMIN — rôles et permissions (Login 1)."""

from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.data.plateforme_catalogue import (
    CORE_ADMIN_PERMISSION_CODES,
    IMMO_ADMIN_ROLE_CODE,
    SYSTEM_PERMISSION_CODES,
    SYSTEM_ROLE_CODES,
)
from app.models import Permission, Role
from app.models.associations import role_permissions_table, user_roles_table

ROLE_CODE_RE = re.compile(r"^[a-z][a-z0-9_-]{1,48}$")
PERM_CODE_RE = re.compile(r"^[a-z][a-z0-9_-]+(\.[a-z0-9_-]+)+$")
MODULE_RE = re.compile(r"^[a-z][a-z0-9_-]{0,79}$")


def normalize_role_code(raw: str) -> str:
    code = (raw or "").strip().lower()
    if not ROLE_CODE_RE.fullmatch(code):
        raise ValueError(
            "Code de rôle invalide : lettres minuscules, chiffres, tirets et underscores (ex. credit_lecteur)."
        )
    return code


def normalize_permission_code(raw: str) -> str:
    code = (raw or "").strip().lower()
    if code == "*" or "*" in code:
        raise ValueError("Le code * est réservé au superutilisateur")
    if not PERM_CODE_RE.fullmatch(code) or len(code) > 100:
        raise ValueError("Code de permission invalide : {module}.{action} (ex. credit.read).")
    return code


def normalize_module(raw: str | None, *, fallback: str | None = None) -> str:
    value = (raw or "").strip().lower() or (fallback or "")
    if not MODULE_RE.fullmatch(value):
        raise ValueError("Module invalide : lettres minuscules, chiffres, tirets et underscores.")
    return value


def _iso(value) -> str | None:
    return value.isoformat() if value else None


class CoreAdminRbacService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _count(self, stmt) -> int:
        result = await self.db.execute(stmt)
        return int(result.scalar() or 0)

    async def _role_user_counts(self) -> dict[UUID, int]:
        return {
            role_id: int(n)
            for role_id, n in (
                await self.db.execute(
                    select(user_roles_table.c.role_id, func.count()).group_by(user_roles_table.c.role_id)
                )
            ).all()
        }

    async def _role_perm_counts(self) -> dict[UUID, int]:
        return {
            role_id: int(n)
            for role_id, n in (
                await self.db.execute(
                    select(role_permissions_table.c.role_id, func.count()).group_by(
                        role_permissions_table.c.role_id
                    )
                )
            ).all()
        }

    async def _perm_role_counts(self) -> dict[UUID, int]:
        return {
            perm_id: int(n)
            for perm_id, n in (
                await self.db.execute(
                    select(role_permissions_table.c.permission_id, func.count()).group_by(
                        role_permissions_table.c.permission_id
                    )
                )
            ).all()
        }

    def serialize_role(
        self,
        row: Role,
        *,
        permissions_count: int,
        users_count: int,
        permissions: list[dict] | None = None,
    ) -> dict:
        payload = {
            "id": str(row.id),
            "code": row.code,
            "label": row.label,
            "description": row.description or "",
            "locked": row.code in SYSTEM_ROLE_CODES,
            "permissions_count": permissions_count,
            "users_count": users_count,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
        }
        if permissions is not None:
            payload["permissions"] = permissions
            payload["permission_codes"] = [item["code"] for item in permissions]
        return payload

    def serialize_permission(
        self,
        row: Permission,
        *,
        roles_count: int,
        roles: list[dict] | None = None,
    ) -> dict:
        payload = {
            "id": str(row.id),
            "code": row.code,
            "label": row.label,
            "module": row.module,
            "locked": row.code in SYSTEM_PERMISSION_CODES,
            "roles_count": roles_count,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
        }
        if roles is not None:
            payload["roles"] = roles
        return payload

    def _kind_clause(self, model, kind: str, system_codes: frozenset[str]):
        if kind == "systeme":
            return model.code.in_(system_codes)
        if kind == "custom":
            return model.code.notin_(system_codes)
        return None

    async def roles_kpis(self) -> dict:
        rows = list((await self.db.execute(select(Role.id, Role.code))).all())
        users = await self._role_user_counts()
        total = len(rows)
        systeme = sum(1 for _id, code in rows if code in SYSTEM_ROLE_CODES)
        return {
            "total": total,
            "systeme": systeme,
            "custom": total - systeme,
            "with_users": sum(1 for role_id, _code in rows if users.get(role_id, 0) > 0),
            "unused": 0,
        }

    async def permissions_kpis(self) -> dict:
        rows = list((await self.db.execute(select(Permission.id, Permission.code))).all())
        role_counts = await self._perm_role_counts()
        total = len(rows)
        systeme = sum(1 for _id, code in rows if code in SYSTEM_PERMISSION_CODES)
        unused = sum(1 for perm_id, _code in rows if role_counts.get(perm_id, 0) == 0)
        return {
            "total": total,
            "systeme": systeme,
            "custom": total - systeme,
            "with_users": 0,
            "unused": unused,
        }

    async def list_roles(
        self,
        page: int,
        size: int,
        *,
        search: str | None = None,
        kind: str = "tous",
    ) -> tuple[list[dict], int, dict]:
        stmt = select(Role)
        if search and search.strip():
            term = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(Role.code.ilike(term), Role.label.ilike(term), Role.description.ilike(term))
            )
        clause = self._kind_clause(Role, kind, SYSTEM_ROLE_CODES)
        if clause is not None:
            stmt = stmt.where(clause)
        total = await self._count(select(func.count()).select_from(stmt.subquery()))
        result = await self.db.execute(
            stmt.order_by(Role.label.asc(), Role.code.asc()).offset((page - 1) * size).limit(size)
        )
        rows = list(result.scalars().all())
        perm_counts = await self._role_perm_counts()
        user_counts = await self._role_user_counts()
        items = [
            self.serialize_role(
                row,
                permissions_count=perm_counts.get(row.id, 0),
                users_count=user_counts.get(row.id, 0),
            )
            for row in rows
        ]
        return items, total, await self.roles_kpis()

    async def get_role(self, role_id: UUID) -> Role | None:
        result = await self.db.execute(
            select(Role).options(selectinload(Role.permissions)).where(Role.id == role_id)
        )
        return result.scalar_one_or_none()

    async def role_fiche(self, role_id: UUID) -> dict | None:
        row = await self.get_role(role_id)
        if row is None:
            return None
        users = await self._role_user_counts()
        perms = sorted(row.permissions, key=lambda p: (p.module, p.code))
        return self.serialize_role(
            row,
            permissions_count=len(perms),
            users_count=users.get(row.id, 0),
            permissions=[
                {
                    "id": str(perm.id),
                    "code": perm.code,
                    "label": perm.label,
                    "module": perm.module,
                    "locked": perm.code in SYSTEM_PERMISSION_CODES,
                }
                for perm in perms
            ],
        )

    async def _permissions_by_codes(self, codes: list[str]) -> list[Permission]:
        wanted = []
        seen: set[str] = set()
        for raw in codes:
            code = normalize_permission_code(raw)
            if code in seen:
                continue
            seen.add(code)
            wanted.append(code)
        if not wanted:
            return []
        result = await self.db.execute(select(Permission).where(Permission.code.in_(wanted)))
        found = {row.code: row for row in result.scalars().all()}
        missing = [code for code in wanted if code not in found]
        if missing:
            raise ValueError(f"Permission introuvable : {missing[0]}")
        return [found[code] for code in wanted]

    def _guard_immo_admin_core(self, role: Role, perms: list[Permission]) -> None:
        if role.code != IMMO_ADMIN_ROLE_CODE:
            return
        granted = {perm.code for perm in perms}
        if granted.intersection(CORE_ADMIN_PERMISSION_CODES):
            raise ValueError("Le rôle Immobilisations administrateur n’ouvre pas CORE ADMIN")

    async def create_role(self, payload) -> dict:
        code = normalize_role_code(payload.code)
        existing = await self.db.execute(select(Role.id).where(Role.code == code))
        if existing.scalar_one_or_none() is not None:
            raise ValueError("Ce code de rôle existe déjà")
        perms = await self._permissions_by_codes(payload.permission_codes or [])
        row = Role(
            code=code,
            label=payload.label.strip(),
            description=(payload.description or "").strip() or None,
        )
        self._guard_immo_admin_core(row, perms)
        row.permissions = perms
        self.db.add(row)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            raise ValueError("Ce code de rôle existe déjà") from exc
        return await self.role_fiche(row.id) or self.serialize_role(
            row, permissions_count=len(perms), users_count=0
        )

    async def update_role(self, role_id: UUID, payload) -> dict:
        row = await self.get_role(role_id)
        if row is None:
            raise ValueError("Rôle introuvable")
        data = payload.model_dump(exclude_unset=True)
        if "label" in data and data["label"] is not None:
            row.label = data["label"].strip()
        if "description" in data:
            row.description = (data["description"] or "").strip() or None
        if "permission_codes" in data and data["permission_codes"] is not None:
            perms = await self._permissions_by_codes(data["permission_codes"])
            self._guard_immo_admin_core(row, perms)
            row.permissions = perms
        await self.db.flush()
        return await self.role_fiche(role_id) or self.serialize_role(row, permissions_count=0, users_count=0)

    async def delete_role(self, role_id: UUID) -> None:
        row = await self.get_role(role_id)
        if row is None:
            raise ValueError("Rôle introuvable")
        if row.code in SYSTEM_ROLE_CODES:
            raise ValueError("Impossible de supprimer un rôle système Immobilisations")
        users = await self._role_user_counts()
        if users.get(row.id, 0) > 0:
            raise ValueError("Des utilisateurs ont encore ce rôle")
        await self.db.delete(row)
        await self.db.flush()

    async def role_options(self) -> dict:
        result = await self.db.execute(select(Permission).order_by(Permission.module.asc(), Permission.code.asc()))
        perms = list(result.scalars().all())
        modules = sorted({row.module for row in perms})
        return {
            "permissions": [
                {
                    "id": str(row.id),
                    "code": row.code,
                    "label": row.label,
                    "module": row.module,
                    "locked": row.code in SYSTEM_PERMISSION_CODES,
                }
                for row in perms
            ],
            "modules": modules,
        }

    async def list_permissions(
        self,
        page: int,
        size: int,
        *,
        search: str | None = None,
        kind: str = "tous",
        module: str | None = None,
    ) -> tuple[list[dict], int, dict]:
        stmt = select(Permission)
        if search and search.strip():
            term = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    Permission.code.ilike(term),
                    Permission.label.ilike(term),
                    Permission.module.ilike(term),
                )
            )
        clause = self._kind_clause(Permission, kind, SYSTEM_PERMISSION_CODES)
        if clause is not None:
            stmt = stmt.where(clause)
        if module and module.strip():
            stmt = stmt.where(Permission.module == module.strip().lower())
        total = await self._count(select(func.count()).select_from(stmt.subquery()))
        result = await self.db.execute(
            stmt.order_by(Permission.module.asc(), Permission.code.asc())
            .offset((page - 1) * size)
            .limit(size)
        )
        rows = list(result.scalars().all())
        role_counts = await self._perm_role_counts()
        items = [
            self.serialize_permission(row, roles_count=role_counts.get(row.id, 0)) for row in rows
        ]
        return items, total, await self.permissions_kpis()

    async def get_permission(self, permission_id: UUID) -> Permission | None:
        result = await self.db.execute(select(Permission).where(Permission.id == permission_id))
        return result.scalar_one_or_none()

    async def permission_fiche(self, permission_id: UUID) -> dict | None:
        row = await self.get_permission(permission_id)
        if row is None:
            return None
        result = await self.db.execute(
            select(Role)
            .join(role_permissions_table, role_permissions_table.c.role_id == Role.id)
            .where(role_permissions_table.c.permission_id == row.id)
            .order_by(Role.label.asc())
        )
        roles = list(result.scalars().all())
        return self.serialize_permission(
            row,
            roles_count=len(roles),
            roles=[
                {
                    "id": str(role.id),
                    "code": role.code,
                    "label": role.label,
                    "locked": role.code in SYSTEM_ROLE_CODES,
                }
                for role in roles
            ],
        )

    async def create_permission(self, payload) -> dict:
        code = normalize_permission_code(payload.code)
        existing = await self.db.execute(select(Permission.id).where(Permission.code == code))
        if existing.scalar_one_or_none() is not None:
            raise ValueError("Ce code de permission existe déjà")
        module = normalize_module(payload.module, fallback=code.split(".", 1)[0])
        row = Permission(code=code, label=payload.label.strip(), module=module)
        self.db.add(row)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            raise ValueError("Ce code de permission existe déjà") from exc
        return self.serialize_permission(row, roles_count=0, roles=[])

    async def update_permission(self, permission_id: UUID, payload) -> dict:
        row = await self.get_permission(permission_id)
        if row is None:
            raise ValueError("Permission introuvable")
        data = payload.model_dump(exclude_unset=True)
        if "label" in data and data["label"] is not None:
            row.label = data["label"].strip()
        if "module" in data and data["module"] is not None:
            if row.code in SYSTEM_PERMISSION_CODES:
                raise ValueError("Le module d’une permission système est figé")
            row.module = normalize_module(data["module"])
        await self.db.flush()
        return await self.permission_fiche(permission_id) or self.serialize_permission(row, roles_count=0)

    async def delete_permission(self, permission_id: UUID) -> None:
        row = await self.get_permission(permission_id)
        if row is None:
            raise ValueError("Permission introuvable")
        if row.code in SYSTEM_PERMISSION_CODES:
            raise ValueError("Impossible de supprimer une permission catalogue")
        counts = await self._perm_role_counts()
        if counts.get(row.id, 0) > 0:
            raise ValueError("Retirez d’abord cette permission des rôles qui la portent")
        await self.db.delete(row)
        await self.db.flush()

    async def permission_modules(self) -> list[str]:
        result = await self.db.execute(
            select(Permission.module).distinct().order_by(Permission.module.asc())
        )
        return [row[0] for row in result.all() if row[0]]

    async def get_matrix(self, *, module: str | None = None, search: str | None = None) -> dict:
        roles_result = await self.db.execute(
            select(Role).options(selectinload(Role.permissions)).order_by(Role.label.asc())
        )
        roles = list(roles_result.scalars().unique().all())

        perm_stmt = select(Permission)
        if module and module.strip():
            perm_stmt = perm_stmt.where(Permission.module == module.strip().lower())
        if search and search.strip():
            term = f"%{search.strip()}%"
            perm_stmt = perm_stmt.where(
                or_(
                    Permission.code.ilike(term),
                    Permission.label.ilike(term),
                    Permission.module.ilike(term),
                )
            )
        perms_result = await self.db.execute(
            perm_stmt.order_by(Permission.module.asc(), Permission.code.asc())
        )
        permissions = list(perms_result.scalars().all())
        visible_codes = {row.code for row in permissions}

        grants: dict[str, list[str]] = {}
        grant_count = 0
        for role in roles:
            codes = sorted(perm.code for perm in role.permissions if perm.code in visible_codes)
            grants[str(role.id)] = codes
            grant_count += len(codes)

        modules = sorted({row.module for row in permissions})
        return {
            "roles": [
                {
                    "id": str(role.id),
                    "code": role.code,
                    "label": role.label,
                    "locked": role.code in SYSTEM_ROLE_CODES,
                }
                for role in roles
            ],
            "permissions": [
                {
                    "id": str(row.id),
                    "code": row.code,
                    "label": row.label,
                    "module": row.module,
                    "locked": row.code in SYSTEM_PERMISSION_CODES,
                }
                for row in permissions
            ],
            "grants": grants,
            "modules": modules,
            "kpis": {
                "roles": len(roles),
                "permissions": len(permissions),
                "grants": grant_count,
                "modules": len(modules),
            },
        }

    async def set_matrix_grant(self, role_id: UUID, permission_code: str, granted: bool) -> dict:
        row = await self.get_role(role_id)
        if row is None:
            raise ValueError("Rôle introuvable")
        code = normalize_permission_code(permission_code)
        current = {perm.code for perm in row.permissions}
        if granted:
            current.add(code)
        else:
            current.discard(code)
        perms = await self._permissions_by_codes(sorted(current))
        self._guard_immo_admin_core(row, perms)
        row.permissions = perms
        await self.db.flush()
        return {
            "role_id": str(row.id),
            "permission_code": code,
            "granted": granted and code in {perm.code for perm in perms},
        }
