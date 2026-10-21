"""CORE ADMIN — Studio d'intégration API, fournisseurs d'API externes (Phase 4, Login 1).

Fiches fournisseurs, import OpenAPI par fichier, opérations manuelles. Aucune route n'effectue
d'appel réseau : pas de téléchargement par URL, pas de test de connectivité, pas d'exécution.
"""

import re
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_platform_permission
from app.core.exceptions import AppError
from app.db.session import get_db
from app.models import User
from app.schemas.integration_fournisseurs import (
    AnalyseSpec,
    Environnement,
    FournisseurArchivage,
    FournisseurChangementStatut,
    FournisseurCreation,
    FournisseurFiche,
    FournisseurModification,
    FournisseurPage,
    FournisseurStatut,
    HistoriqueFournisseur,
    Methode,
    OperationArchivage,
    OperationDetail,
    OperationListe,
    OperationManuelle,
    OperationManuelleModification,
    SpecDetail,
    SpecListe,
)
from app.schemas.integration_execution import BilanSuppression
from app.services.integrations import fournisseurs as svc
from app.services.integrations import suppression
from app.services.integrations.openapi_import import TAILLE_MAX
from app.services.permission_service import load_user_permission_codes

router = APIRouter(prefix="/plateforme/admin/integrations/fournisseurs", tags=["core-admin"])

_VIEW = require_platform_permission(svc.P_VIEW)
_MANAGE = require_platform_permission(svc.P_MANAGE)
_STATUT = require_platform_permission(svc.P_MANAGE, svc.P_VALIDATE)

Tri = Literal["nom", "code", "statut", "environnement", "created_at", "updated_at"]
_EMPREINTE = re.compile(r"^[0-9a-f]{64}$")


async def _lire(fichier: UploadFile) -> bytes:
    contenu = await fichier.read(TAILLE_MAX + 1)
    if len(contenu) > TAILLE_MAX:
        raise AppError(f"Fichier de plus de {TAILLE_MAX // (1024 * 1024)} Mo", 413, code="FICHIER_TROP_VOLUMINEUX")
    return contenu


@router.get("", response_model=FournisseurPage)
async def lister_fournisseurs(
    q: str | None = Query(None, max_length=120),
    statut: FournisseurStatut | None = None,
    environnement: Environnement | None = None,
    inclure_archives: bool = False,
    tri: Tri = "updated_at",
    ordre: Literal["asc", "desc"] = "desc",
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=100),
    _: User = Depends(_VIEW),
    db: AsyncSession = Depends(get_db),
):
    return await svc.lister_fournisseurs(
        db, q=q, statut=statut, environnement=environnement, inclure_archives=inclure_archives,
        tri=tri, ordre=ordre, page=page, size=size,
    )


@router.post("", response_model=FournisseurFiche, status_code=201)
async def creer_fournisseur(
    payload: FournisseurCreation,
    request: Request,
    actor: User = Depends(_MANAGE),
    db: AsyncSession = Depends(get_db),
):
    return await svc.creer_fournisseur(db, actor, payload.model_dump(), request)


@router.get("/{fournisseur_id}", response_model=FournisseurFiche)
async def fiche_fournisseur(
    fournisseur_id: uuid.UUID,
    _: User = Depends(_VIEW),
    db: AsyncSession = Depends(get_db),
):
    return await svc.fiche_fournisseur(db, fournisseur_id)


@router.patch("/{fournisseur_id}", response_model=FournisseurFiche)
async def modifier_fournisseur(
    fournisseur_id: uuid.UUID,
    payload: FournisseurModification,
    request: Request,
    actor: User = Depends(_MANAGE),
    db: AsyncSession = Depends(get_db),
):
    fournis = set(payload.model_fields_set) - {"revision"}
    return await svc.modifier_fournisseur(db, actor, fournisseur_id, payload.model_dump(), fournis, request)


@router.post("/{fournisseur_id}/statut", response_model=FournisseurFiche)
async def changer_statut(
    fournisseur_id: uuid.UUID,
    payload: FournisseurChangementStatut,
    request: Request,
    actor: User = Depends(_STATUT),
    db: AsyncSession = Depends(get_db),
):
    have = await load_user_permission_codes(db, actor)
    return await svc.changer_statut(
        db, actor, have, fournisseur_id, payload.revision, payload.statut, payload.motif, request
    )


@router.post("/{fournisseur_id}/archive", response_model=FournisseurFiche)
async def archiver_fournisseur(
    fournisseur_id: uuid.UUID,
    payload: FournisseurArchivage,
    request: Request,
    actor: User = Depends(_MANAGE),
    db: AsyncSession = Depends(get_db),
):
    return await svc.archiver_fournisseur(db, actor, fournisseur_id, payload.revision, payload.motif, request)


@router.get("/{fournisseur_id}/dependances", response_model=BilanSuppression)
async def dependances_fournisseur(fournisseur_id: uuid.UUID, _: User = Depends(_VIEW),
                                  db: AsyncSession = Depends(get_db)):
    return await suppression.dependances_fournisseur(db, fournisseur_id)


@router.delete("/{fournisseur_id}", status_code=204)
async def supprimer_fournisseur(fournisseur_id: uuid.UUID, request: Request, revision: int = Query(..., ge=1),
                                actor: User = Depends(_MANAGE), db: AsyncSession = Depends(get_db)):
    await suppression.supprimer_fournisseur(db, actor, fournisseur_id, revision, request)


@router.get("/{fournisseur_id}/historique", response_model=HistoriqueFournisseur)
async def historique(
    fournisseur_id: uuid.UUID,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    _: User = Depends(_VIEW),
    db: AsyncSession = Depends(get_db),
):
    return await svc.historique(db, fournisseur_id, page=page, size=size)


@router.post("/{fournisseur_id}/specs/analyse", response_model=AnalyseSpec)
async def analyser_spec(
    fournisseur_id: uuid.UUID,
    request: Request,
    fichier: UploadFile = File(..., alias="file"),
    actor: User = Depends(_MANAGE),
    db: AsyncSession = Depends(get_db),
):
    contenu = await _lire(fichier)
    return await svc.analyser_spec(db, actor, fournisseur_id, contenu, fichier.filename, request)


@router.post("/{fournisseur_id}/specs", response_model=SpecDetail, status_code=201)
async def importer_spec(
    fournisseur_id: uuid.UUID,
    request: Request,
    fichier: UploadFile = File(..., alias="file"),
    empreinte: str = Form(..., min_length=64, max_length=64),
    version_courante: int | None = Form(None, ge=1),
    accepter_conflits: bool = Form(False),
    actor: User = Depends(_MANAGE),
    db: AsyncSession = Depends(get_db),
):
    if not _EMPREINTE.match(empreinte):
        raise AppError("Empreinte d'analyse invalide", 422, code="EMPREINTE_INVALIDE")
    contenu = await _lire(fichier)
    return await svc.importer_spec(
        db, actor, fournisseur_id, contenu, fichier.filename, empreinte, version_courante, accepter_conflits, request
    )


@router.get("/{fournisseur_id}/specs", response_model=SpecListe)
async def lister_specs(
    fournisseur_id: uuid.UUID,
    _: User = Depends(_VIEW),
    db: AsyncSession = Depends(get_db),
):
    return await svc.lister_specs(db, fournisseur_id)


@router.get("/{fournisseur_id}/specs/{spec_id}", response_model=SpecDetail)
async def spec_detail(
    fournisseur_id: uuid.UUID,
    spec_id: uuid.UUID,
    _: User = Depends(_VIEW),
    db: AsyncSession = Depends(get_db),
):
    return await svc.spec_detail(db, fournisseur_id, spec_id)


@router.get("/{fournisseur_id}/operations", response_model=OperationListe)
async def lister_operations(
    fournisseur_id: uuid.UUID,
    q: str | None = Query(None, max_length=120),
    methode: Methode | None = None,
    origine: Literal["openapi", "manuelle"] | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    _: User = Depends(_VIEW),
    db: AsyncSession = Depends(get_db),
):
    return await svc.lister_operations(db, fournisseur_id, q=q, methode=methode, origine=origine, page=page, size=size)


@router.post("/{fournisseur_id}/operations", response_model=OperationDetail, status_code=201)
async def creer_operation(
    fournisseur_id: uuid.UUID,
    payload: OperationManuelle,
    request: Request,
    actor: User = Depends(_MANAGE),
    db: AsyncSession = Depends(get_db),
):
    return await svc.creer_operation(db, actor, fournisseur_id, payload.model_dump(mode="json"), request)


@router.get("/{fournisseur_id}/operations/{operation_id}", response_model=OperationDetail)
async def operation_detail(
    fournisseur_id: uuid.UUID,
    operation_id: uuid.UUID,
    _: User = Depends(_VIEW),
    db: AsyncSession = Depends(get_db),
):
    return await svc.operation_detail(db, fournisseur_id, operation_id)


@router.patch("/{fournisseur_id}/operations/{operation_id}", response_model=OperationDetail)
async def modifier_operation(
    fournisseur_id: uuid.UUID,
    operation_id: uuid.UUID,
    payload: OperationManuelleModification,
    request: Request,
    actor: User = Depends(_MANAGE),
    db: AsyncSession = Depends(get_db),
):
    return await svc.modifier_operation(
        db, actor, fournisseur_id, operation_id, payload.model_dump(mode="json"), request
    )


@router.post("/{fournisseur_id}/operations/{operation_id}/archive", response_model=OperationDetail)
async def archiver_operation(
    fournisseur_id: uuid.UUID,
    operation_id: uuid.UUID,
    payload: OperationArchivage,
    request: Request,
    actor: User = Depends(_MANAGE),
    db: AsyncSession = Depends(get_db),
):
    return await svc.archiver_operation(db, actor, fournisseur_id, operation_id, payload.revision, request)


@router.get("/{fournisseur_id}/operations/{operation_id}/dependances", response_model=BilanSuppression)
async def dependances_operation(fournisseur_id: uuid.UUID, operation_id: uuid.UUID, _: User = Depends(_VIEW),
                                db: AsyncSession = Depends(get_db)):
    return await suppression.dependances_operation(db, fournisseur_id, operation_id)


@router.delete("/{fournisseur_id}/operations/{operation_id}", status_code=204)
async def supprimer_operation(fournisseur_id: uuid.UUID, operation_id: uuid.UUID, request: Request,
                              revision: int = Query(..., ge=1), actor: User = Depends(_MANAGE),
                              db: AsyncSession = Depends(get_db)):
    await suppression.supprimer_operation(db, actor, fournisseur_id, operation_id, revision, request)
