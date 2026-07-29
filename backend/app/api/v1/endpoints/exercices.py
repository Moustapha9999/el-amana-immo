"""API — exercices comptables (clôture définitive / ouverture N+1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.core.exceptions import AppError, raise_http_from_app
from app.db.session import get_db
from app.models import User
from app.schemas.exercice import (
    ExerciceClotureRequest,
    ExerciceClotureResponse,
    ExerciceOuvertureResponse,
    PeriodeAmortissementRead,
    ExerciceRead,
    ExerciceSituationRead,
)
from app.services.audit_helpers import record_audit
from app.services.exercice_cloture_service import ExerciceClotureService
from app.services.exercice_ouverture_service import ExerciceOuvertureService
from app.services.periode_amortissement_service import PeriodeAmortissementService

router = APIRouter(prefix="/exercices", tags=["exercices"])


def _exercice_read(exo) -> ExerciceRead:
    return ExerciceRead(
        id=exo.id,
        annee=exo.annee,
        statut=exo.statut.value if hasattr(exo.statut, "value") else str(exo.statut),
        archive_dossier_id=exo.archive_dossier_id,
        cloture_at=exo.cloture_at,
        ouverture_at=exo.ouverture_at,
        total_valeur_brute=exo.total_valeur_brute,
        total_amortissement=exo.total_amortissement,
        total_vnc=exo.total_vnc,
        total_dotation_68=exo.total_dotation_68,
        nb_immobilisations=exo.nb_immobilisations,
        message=exo.message,
    )


@router.get("/situation", response_model=ExerciceSituationRead)
async def get_situation(
    _: User = Depends(require_roles("administrateur", "comptable", "auditeur")),
    db: AsyncSession = Depends(get_db),
):
    data = await ExerciceOuvertureService(db).situation()
    return ExerciceSituationRead(
        dernier_cloture=data["dernier_cloture"],
        exercice_ouvert=data["exercice_ouvert"],
        annee_ouverture_proposee=data["annee_ouverture_proposee"],
        peut_ouvrir=data["peut_ouvrir"],
        exercices=[_exercice_read(e) for e in data["exercices"]],
    )


@router.get("/{annee}/periodes", response_model=list[PeriodeAmortissementRead])
async def get_periodes_amortissement(
    annee: int,
    _: User = Depends(require_roles("administrateur", "comptable", "auditeur")),
    db: AsyncSession = Depends(get_db),
):
    try:
        rows = await PeriodeAmortissementService(db).list_periodes(annee)
        return [
            PeriodeAmortissementRead(
                id=p.id, annee=p.annee, trimestre=p.trimestre, code=p.code,
                date_arrete=p.date_arrete,
                statut=p.statut.value if hasattr(p.statut, "value") else str(p.statut),
                calcule_at=p.calcule_at, valide_at=p.valide_at,
                total_dotation=p.total_dotation, nb_dotations=p.nb_dotations,
            )
            for p in rows
        ]
    except AppError as exc:
        raise_http_from_app(exc)


@router.post("/cloturer", response_model=ExerciceClotureResponse, status_code=status.HTTP_201_CREATED)
async def cloturer_exercice(
    body: ExerciceClotureRequest,
    request: Request,
    user: User = Depends(require_roles("administrateur")),
    db: AsyncSession = Depends(get_db),
):
    """Clôture définitive de l'exercice N (archives immuables, sans ouverture N+1)."""
    try:
        result = await ExerciceClotureService(db).cloturer(
            annee=body.annee, force=False, user=user
        )
        await record_audit(
            db,
            user=user,
            action="cloture_exercice_definitive",
            entity="exercice_comptable",
            entity_id=str(result.annee),
            after={
                "annee": result.annee,
                "natures_creees": result.natures_creees,
                "lignes": result.lignes,
                "dossier_id": str(result.dossier_id),
            },
            request=request,
        )
        return ExerciceClotureResponse(
            annee=result.annee,
            natures_creees=result.natures_creees,
            lignes=result.lignes,
            dossier_id=result.dossier_id,
            message=result.message,
            annee_ouverture_proposee=result.annee + 1,
            total_valeur_brute=result.total_valeur_brute,
            total_amortissement=result.total_amortissement,
            total_vnc=result.total_vnc,
            total_dotation_68=result.total_dotation_68,
            nb_immobilisations=result.nb_immobilisations,
        )
    except AppError as exc:
        raise_http_from_app(exc)


@router.post(
    "/ouvrir-suivant",
    response_model=ExerciceOuvertureResponse,
    status_code=status.HTTP_201_CREATED,
)
async def ouvrir_exercice_suivant(
    request: Request,
    user: User = Depends(require_roles("administrateur")),
    db: AsyncSession = Depends(get_db),
):
    """Ouvre automatiquement N+1 après le dernier exercice clôturé (142/148, 68=0)."""
    try:
        result = await ExerciceOuvertureService(db).ouvrir_suivant(user=user)
        await record_audit(
            db,
            user=user,
            action="ouverture_exercice",
            entity="exercice_comptable",
            entity_id=str(result.annee_ouverture),
            after={
                "annee_source": result.annee_source,
                "annee_ouverture": result.annee_ouverture,
                "ouvertures_seed": result.ouvertures_seed,
            },
            request=request,
        )
        return ExerciceOuvertureResponse(
            annee_source=result.annee_source,
            annee_ouverture=result.annee_ouverture,
            ouvertures_seed=result.ouvertures_seed,
            total_valeur_brute=result.total_valeur_brute,
            total_amortissement=result.total_amortissement,
            total_vnc=result.total_vnc,
            message=result.message,
        )
    except AppError as exc:
        raise_http_from_app(exc)
