"""Contrôle d'accès backend : User → espace → module → permission."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.plateforme_catalogue import FUNCTIONAL_PERMISSIONS, permissions_for_role
from app.models import Permission, Role, User
from app.models.associations import role_permissions_table, user_roles_table


def permission_codes_from_user(user: User) -> set[str]:
    """Codes déjà chargés sur user.roles.permissions (plus is_superuser)."""
    if user.is_superuser:
        return {code for code, _label, _module in FUNCTIONAL_PERMISSIONS} | {"*"}
    codes: set[str] = set()
    for role in user.roles or []:
        loaded = role.__dict__.get("permissions", None)
        if loaded is not None:
            for perm in loaded:
                codes.add(perm.code)
        else:
            codes.update(permissions_for_role(role.code))
    return codes


# Espaces transverses : chaque permission y est accordée explicitement, sans racine `{espace}.admin`.
NAMESPACES_SANS_ADMIN_RACINE = frozenset({"core", "plateforme", "ged", "org"})


def admin_root_module(code: str) -> str | None:
    """Module couvert par une permission racine `{module}.admin` (exactement deux segments).

    `immobilisations.admin` → `immobilisations`. Les codes `.admin` plus profonds
    (`core.admin.query.admin`, `mg.request.admin`, `clientele.classif.admin`, …) sont des
    permissions exactes et ne couvrent rien d'autre qu'eux-mêmes.
    """
    parts = code.split(".")
    if len(parts) != 2 or parts[1] != "admin" or not parts[0]:
        return None
    if parts[0] in NAMESPACES_SANS_ADMIN_RACINE:
        return None
    return parts[0]


def user_has_permission_codes(have: set[str], *needed: str) -> bool:
    """True si au moins un code demandé est détenu exactement, ou couvert par une racine `{module}.admin`."""
    if not needed:
        return True
    if "*" in have:
        return True
    if have.intersection(needed):
        return True
    admin_modules = {m for m in (admin_root_module(code) for code in have) if m}
    return any(code.split(".", 1)[0] in admin_modules for code in needed if "." in code)


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
    for perm_code, _role_code in result.all():
        codes.add(perm_code)
    return codes
