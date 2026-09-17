"""Contrôle d'accès backend : User → espace → module → permission."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.plateforme_catalogue import FUNCTIONAL_PERMISSIONS, permissions_for_role
from app.models import Permission, Role, User
from app.models.associations import role_permissions_table, user_roles_table

_IMMO_ADMIN = "immobilisations.admin"
_IMMO_PREFIX = "immobilisations."


def permission_codes_from_user(user: User) -> set[str]:
    """Codes déjà chargés sur user.roles.permissions (plus is_superuser / admin)."""
    if user.is_superuser:
        return {code for code, _label, _module in FUNCTIONAL_PERMISSIONS} | {"*"}
    codes: set[str] = set()
    for role in user.roles or []:
        codes.update(permissions_for_role(role.code))
        loaded = role.__dict__.get("permissions", None)
        if loaded:
            for perm in loaded:
                codes.add(perm.code)
    return codes


def user_has_permission_codes(have: set[str], *needed: str) -> bool:
    if not needed:
        return True
    if "*" in have:
        return True
    if _IMMO_ADMIN in have and all(code.startswith(_IMMO_PREFIX) for code in needed):
        return True
    return bool(have.intersection(needed))


async def load_user_permission_codes(db: AsyncSession, user: User) -> set[str]:
    if user.is_superuser:
        return {code for code, _label, _module in FUNCTIONAL_PERMISSIONS} | {"*"}
    result = await db.execute(
        select(Permission.code, Role.code)
        .select_from(Permission)
        .join(role_permissions_table, role_permissions_table.c.permission_id == Permission.id)
        .join(Role, Role.id == role_permissions_table.c.role_id)
        .join(user_roles_table, user_roles_table.c.role_id == Role.id)
        .where(user_roles_table.c.user_id == user.id)
    )
    codes: set[str] = set()
    role_codes: set[str] = {r.code for r in user.roles or []}
    for perm_code, role_code in result.all():
        codes.add(perm_code)
        role_codes.add(role_code)
    for role_code in role_codes:
        codes.update(permissions_for_role(role_code))
    return codes
