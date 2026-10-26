from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.v1.endpoints.helpers import to_paginated
from app.core.temp_password import generate_temporary_password
from app.data.plateforme_catalogue import DEFAULT_ESPACE_CODE, IMMO_LEGACY_ROLE_CODES
from app.db.session import get_db
from app.models import User
from app.schemas.auth import RoleRead, UserCreate, UserRead, UserUpdate
from app.schemas.common import MessageResponse, PaginatedResponse
from app.services.audit_helpers import record_audit
from app.services.auth_service import AuthService

router = APIRouter(prefix="/users", tags=["users"])

# API historique du module Immobilisations (plus de page dédiée : les comptes se gèrent
# dans CORE ADMIN, /plateforme/admin/users). Périmètre limité aux habilités du module.
MODULE_CODE = "immobilisations"


async def _require_in_module(service: AuthService, user_id: UUID) -> None:
    if await service.get_by_id(user_id, include_inactive=True) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable")
    if not await service.has_module_access(user_id, MODULE_CODE):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cet utilisateur n’a pas accès au module Immobilisations : gérez-le depuis CORE ADMIN.",
        )


def _refuser(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def _verifier_perimetre(
    payload: UserCreate | UserUpdate,
    *,
    modules_actuels: list[str] | None = None,
    espaces_actuels: list[str] | None = None,
) -> None:
    """Cette API ne gère que le module Immobilisations : superuser, rôles et accès
    des autres modules se gèrent exclusivement dans CORE ADMIN."""
    superuser = payload.is_superuser
    if superuser or (isinstance(payload, UserUpdate) and superuser is not None):
        raise _refuser("Le statut superutilisateur se gère depuis CORE ADMIN.")
    if isinstance(payload, UserUpdate) and payload.must_change_password is not None:
        raise _refuser("Le changement de mot de passe obligatoire se gère depuis CORE ADMIN.")
    hors_roles = set(payload.role_codes or []) - IMMO_LEGACY_ROLE_CODES
    if hors_roles:
        raise _refuser(f"Rôle(s) hors module Immobilisations : {', '.join(sorted(hors_roles))}.")
    if payload.module_codes is not None:
        hors = set(payload.module_codes) - {MODULE_CODE} - set(modules_actuels or [])
        if hors:
            raise _refuser(f"Accès module(s) à gérer depuis CORE ADMIN : {', '.join(sorted(hors))}.")
    if payload.espace_codes is not None:
        hors = set(payload.espace_codes) - {DEFAULT_ESPACE_CODE} - set(espaces_actuels or [])
        if hors:
            raise _refuser(f"Accès département(s) à gérer depuis CORE ADMIN : {', '.join(sorted(hors))}.")


def _refuser_cible_superuser(actor: User, target: User | None) -> None:
    if target is not None and target.is_superuser and not actor.is_superuser:
        raise _refuser("Ce compte superutilisateur se gère depuis CORE ADMIN.")


async def _require_users_admin(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Users métier : Login 1 (`plateforme.users.admin`) ou Login 2 (`administrateur`)."""
    from app.services.permission_service import load_user_permission_codes, user_has_permission_codes

    if user.is_superuser:
        return user
    have = await load_user_permission_codes(db, user)
    if user_has_permission_codes(have, "plateforme.users.admin"):
        return user
    if {r.code for r in (user.roles or [])}.intersection({"administrateur"}):
        return user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission refusée")


@router.get("", response_model=PaginatedResponse[UserRead])
async def list_users(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    _: User = Depends(_require_users_admin),
    db: AsyncSession = Depends(get_db),
):
    items, total = await AuthService(db).list_users(page, size, search=search, module_access=MODULE_CODE)
    return to_paginated(items, total, page, size, UserRead.model_validate)


@router.get("/roles", response_model=list[RoleRead])
async def list_roles(
    _: User = Depends(_require_users_admin),
    db: AsyncSession = Depends(get_db),
):
    return await AuthService(db).list_roles()


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    request: Request,
    actor: User = Depends(_require_users_admin),
    db: AsyncSession = Depends(get_db),
):
    """Création sans MDP libre : mot de passe temporaire serveur."""
    _verifier_perimetre(payload)
    data = payload.model_dump()
    data["password"] = generate_temporary_password()
    service = AuthService(db)
    try:
        user = await service.create_user(UserCreate.model_validate(data))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await record_audit(
        db,
        user=actor,
        action="create",
        entity="user",
        entity_id=str(user.id),
        request=request,
        after={
            "email": user.email,
            "module_codes": user.module_codes,
            "temporary_password_issued": True,
        },
    )
    return user


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: UUID,
    _: User = Depends(_require_users_admin),
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    user = await service.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable")
    return user


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: UUID,
    payload: UserUpdate,
    request: Request,
    actor: User = Depends(_require_users_admin),
    db: AsyncSession = Depends(get_db),
):
    if payload.password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La gestion des mots de passe se fait via CORE ADMIN → Sécurité",
        )
    service = AuthService(db)
    await _require_in_module(service, user_id)
    target = await service.get_by_id(user_id, include_inactive=True)
    _refuser_cible_superuser(actor, target)
    _verifier_perimetre(
        payload,
        modules_actuels=target.module_codes if target else None,
        espaces_actuels=target.espace_codes if target else None,
    )
    if payload.role_codes is not None and target is not None:
        autres_roles = {r.code for r in target.roles or []} - IMMO_LEGACY_ROLE_CODES
        payload = payload.model_copy(update={"role_codes": sorted(set(payload.role_codes) | autres_roles)})
    try:
        user = await service.update_user(user_id, payload, preserve_outside_module=MODULE_CODE)
    except ValueError as exc:
        detail = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND
            if detail == "Utilisateur introuvable"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=detail) from exc
    await record_audit(
        db,
        user=actor,
        action="update",
        entity="user",
        entity_id=str(user.id),
        request=request,
        after={"email": user.email, "module_codes": user.module_codes},
    )
    return user


@router.delete("/{user_id}", response_model=MessageResponse)
async def delete_user(
    user_id: UUID,
    request: Request,
    current: User = Depends(_require_users_admin),
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    await _require_in_module(service, user_id)
    target = await service.get_by_id(user_id, include_inactive=True)
    _refuser_cible_superuser(current, target)
    if target is not None and any(code != MODULE_CODE for code in target.module_codes):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cet utilisateur a accès à d’autres modules : sa suppression se fait depuis CORE ADMIN.",
        )
    try:
        await service.soft_delete_user(user_id, actor_id=current.id)
    except ValueError as exc:
        detail = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND
            if detail == "Utilisateur introuvable"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=detail) from exc
    await record_audit(
        db,
        user=current,
        action="delete",
        entity="user",
        entity_id=str(user_id),
        request=request,
    )
    return MessageResponse(message="Utilisateur supprimé")
