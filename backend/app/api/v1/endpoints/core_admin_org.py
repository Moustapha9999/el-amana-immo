"""CORE ADMIN — organigramme, postes, affectations, contrôles et correspondances (Login 1)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_platform_permission
from app.db.session import get_db
from app.models import User
from app.schemas.org import (
    AffectationCloture,
    AffectationCreate,
    AffectationPatch,
    AgenceRattachement,
    CorrespondanceApply,
    EntiteCreate,
    EntitePatch,
    EntiteStatut,
    PosteCreate,
    PostePatch,
    TypeEntite,
)
from app.services import org_referentiel as org

router = APIRouter(prefix="/plateforme/admin/organisation", tags=["core-admin-organisation"])

_ORG = require_platform_permission("core.admin.organisation")


@router.get("/entites")
async def lister_entites(
    type_entite: list[TypeEntite] | None = Query(None),
    actives: bool = False,
    q: str | None = Query(None, max_length=120),
    _: User = Depends(_ORG),
    db: AsyncSession = Depends(get_db),
) -> dict:
    items = await org.lister_entites(db, types=type_entite, actives_seulement=actives, recherche=q)
    return {"items": items, "total": len(items), "types": org.TYPE_LIBELLES}


@router.post("/entites", status_code=status.HTTP_201_CREATED)
async def creer_entite(payload: EntiteCreate, request: Request, actor: User = Depends(_ORG),
                       db: AsyncSession = Depends(get_db)) -> dict:
    return await org.creer_entite(db, actor, payload.model_dump(), request)


@router.get("/entites/{entite_id}")
async def fiche_entite(entite_id: uuid.UUID, _: User = Depends(_ORG), db: AsyncSession = Depends(get_db)) -> dict:
    return await org.fiche_entite(db, entite_id)


@router.patch("/entites/{entite_id}")
async def modifier_entite(entite_id: uuid.UUID, payload: EntitePatch, request: Request,
                          actor: User = Depends(_ORG), db: AsyncSession = Depends(get_db)) -> dict:
    return await org.modifier_entite(db, actor, entite_id, payload.model_dump(exclude_unset=True), request)


@router.post("/entites/{entite_id}/desactiver")
async def desactiver_entite(entite_id: uuid.UUID, payload: EntiteStatut, request: Request,
                            actor: User = Depends(_ORG), db: AsyncSession = Depends(get_db)) -> dict:
    return await org.changer_statut_entite(db, actor, entite_id, False, payload.motif, request)


@router.post("/entites/{entite_id}/reactiver")
async def reactiver_entite(entite_id: uuid.UUID, payload: EntiteStatut, request: Request,
                           actor: User = Depends(_ORG), db: AsyncSession = Depends(get_db)) -> dict:
    return await org.changer_statut_entite(db, actor, entite_id, True, payload.motif, request)


@router.post("/entites/{entite_id}/postes", status_code=status.HTTP_201_CREATED)
async def creer_poste(entite_id: uuid.UUID, payload: PosteCreate, request: Request,
                      actor: User = Depends(_ORG), db: AsyncSession = Depends(get_db)) -> dict:
    return await org.creer_poste(db, actor, entite_id, payload.model_dump(), request)


@router.patch("/postes/{poste_id}")
async def modifier_poste(poste_id: uuid.UUID, payload: PostePatch, request: Request,
                         actor: User = Depends(_ORG), db: AsyncSession = Depends(get_db)) -> dict:
    return await org.modifier_poste(db, actor, poste_id, payload.model_dump(exclude_unset=True), request)


@router.get("/affectations")
async def affectations_utilisateur(user_id: uuid.UUID, _: User = Depends(_ORG),
                                   db: AsyncSession = Depends(get_db)) -> dict:
    return {"items": await org.lister_affectations_utilisateur(db, user_id)}


@router.post("/affectations", status_code=status.HTTP_201_CREATED)
async def creer_affectation(payload: AffectationCreate, request: Request, actor: User = Depends(_ORG),
                            db: AsyncSession = Depends(get_db)) -> dict:
    return await org.creer_affectation(db, actor, payload.model_dump(), request)


@router.patch("/affectations/{affectation_id}")
async def modifier_affectation(affectation_id: uuid.UUID, payload: AffectationPatch, request: Request,
                               actor: User = Depends(_ORG), db: AsyncSession = Depends(get_db)) -> dict:
    return await org.modifier_affectation(db, actor, affectation_id, payload.model_dump(exclude_unset=True),
                                          request)


@router.post("/affectations/{affectation_id}/cloturer")
async def cloturer_affectation(affectation_id: uuid.UUID, payload: AffectationCloture, request: Request,
                               actor: User = Depends(_ORG), db: AsyncSession = Depends(get_db)) -> dict:
    return await org.cloturer_affectation(db, actor, affectation_id, payload.date_fin, request)


@router.get("/controles")
async def controles(_: User = Depends(_ORG), db: AsyncSession = Depends(get_db)) -> dict:
    return await org.controles(db)


@router.get("/correspondances")
async def resume_correspondances(_: User = Depends(_ORG), db: AsyncSession = Depends(get_db)) -> dict:
    return {"items": await org.resume_correspondances(db)}


@router.get("/correspondances/{liaison}")
async def correspondances(liaison: str, _: User = Depends(_ORG), db: AsyncSession = Depends(get_db)) -> dict:
    return await org.lister_correspondances(db, liaison)


@router.post("/correspondances")
async def appliquer_correspondance(payload: CorrespondanceApply, request: Request, actor: User = Depends(_ORG),
                                   db: AsyncSession = Depends(get_db)) -> dict:
    return await org.appliquer_correspondance(db, actor, payload.liaison, payload.valeur, payload.entite_id,
                                              memoriser_alias=payload.memoriser_alias, request=request)


@router.get("/agences")
async def agences(_: User = Depends(_ORG), db: AsyncSession = Depends(get_db)) -> dict:
    return {"items": await org.lister_agences(db)}


@router.patch("/agences/{agence_id}")
async def rattacher_agence(agence_id: uuid.UUID, payload: AgenceRattachement, request: Request,
                           actor: User = Depends(_ORG), db: AsyncSession = Depends(get_db)) -> dict:
    return await org.rattacher_agence(db, actor, agence_id, payload.org_entite_id, request)


@router.get("/historique")
async def historique(page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200),
                     entite_id: uuid.UUID | None = None, _: User = Depends(_ORG),
                     db: AsyncSession = Depends(get_db)) -> dict:
    return await org.historique(db, page=page, size=size, entite_id=entite_id)
