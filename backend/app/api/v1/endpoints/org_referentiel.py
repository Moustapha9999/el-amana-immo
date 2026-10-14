"""Référentiel organisationnel — API partagée par tous les modules (Login 1 ou Login 2).

Lecture seule : sélecteurs d'entités et d'agences, périmètre de l'utilisateur connecté.
L'administration reste dans CORE ADMIN (``/plateforme/admin/organisation``).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Agence, User
from app.schemas.org import TypeEntite
from app.services import org_referentiel as org

router = APIRouter(prefix="/organisation", tags=["organisation-referentiel"])


@router.get("/entites")
async def entites(
    type_entite: list[TypeEntite] | None = Query(None),
    racine_id: uuid.UUID | None = None,
    inclure_inactives: bool = False,
    q: str | None = Query(None, max_length=120),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    items = await org.lister_entites(db, types=type_entite, actives_seulement=not inclure_inactives,
                                     recherche=q, racine_id=racine_id)
    champs = ("id", "code", "libelle", "sigle", "type_entite", "type_libelle", "parent_id", "actif",
              "a_confirmer", "chemin", "profondeur")
    return {"items": [{k: e[k] for k in champs} for e in items], "types": org.TYPE_LIBELLES}


@router.get("/entites/{entite_id}/sous-arbre")
async def sous_arbre(entite_id: uuid.UUID, _: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)) -> dict:
    return {"ids": sorted(str(i) for i in await org.sous_arbre(db, entite_id))}


@router.get("/agences")
async def agences(_: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    arbre = await org.charger_arbre(db)
    rows = (await db.scalars(select(Agence).where(Agence.deleted_at.is_(None), Agence.is_active.is_(True))
                             .order_by(Agence.code))).all()
    return {"items": [{"id": str(a.id), "code": a.code, "libelle": a.libelle,
                       "org_entite_id": str(a.org_entite_id) if a.org_entite_id else None,
                       "rattachement": arbre.libelle_chemin(a.org_entite_id)} for a in rows]}


@router.get("/mon-perimetre")
async def mon_perimetre(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    perimetre = await org.charger_perimetre(db, user)
    return {**perimetre.to_dict(),
            "affectations": await org.lister_affectations_utilisateur(db, user.id, inclure_closes=False)}
