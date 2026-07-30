"""API Archivage — historique Excel / PDF banque (lecture seule)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.core.exceptions import AppError, NotFoundError, ValidationError, raise_http_from_app
from app.db.session import get_db
from app.models import ArchiveDossier, ArchiveFichier, ArchiveLigne, User
from app.schemas.archive import (
    ArchiveAcquisitionsRead,
    ArchiveClotureRequest,
    ArchiveClotureResponse,
    ArchiveDossierCreate,
    ArchiveDossierDetailRead,
    ArchiveDossierRead,
    ArchiveExerciceSectionRead,
    ArchiveFichierRead,
    ArchiveLigneRead,
    ArchiveNatureGroupeRead,
    ArchiveTotauxRead,
)
from app.schemas.common import MessageResponse
from app.services.archive_service import ArchiveService, dossier_summary
from app.services.audit_helpers import record_audit
from app.services.exercice_cloture_service import ExerciceClotureService
from app.storage.local_storage import LocalStorageService

router = APIRouter(prefix="/archives", tags=["archives"])


def _fichier_to_read(f: ArchiveFichier) -> ArchiveFichierRead:
    return ArchiveFichierRead.model_validate(f)


def _dossier_to_read(d: ArchiveDossier) -> ArchiveDossierRead:
    summary = dossier_summary(d)
    return ArchiveDossierRead(
        id=d.id,
        annee=d.annee,
        libelle=d.libelle,
        created_at=d.created_at,
        nb_fichiers=summary["nb_fichiers"],
        nb_lignes=summary["nb_lignes"],
        natures=summary["natures"],
    )


def _dossier_detail(d: ArchiveDossier) -> ArchiveDossierDetailRead:
    base = _dossier_to_read(d)
    return ArchiveDossierDetailRead(
        **base.model_dump(),
        fichiers=[_fichier_to_read(f) for f in (d.fichiers or [])],
    )


def _ligne_to_read(l: ArchiveLigne) -> ArchiveLigneRead:
    return ArchiveLigneRead.model_validate(l)


def _totaux_read(t: dict) -> ArchiveTotauxRead:
    return ArchiveTotauxRead(**t)


@router.get("/dossiers", response_model=list[ArchiveDossierRead])
async def list_dossiers(
    _: User = Depends(require_roles("administrateur", "comptable", "auditeur")),
    db: AsyncSession = Depends(get_db),
):
    rows = await ArchiveService(db).list_dossiers()
    return [_dossier_to_read(d) for d in rows]


@router.post("/dossiers", response_model=ArchiveDossierDetailRead, status_code=status.HTTP_201_CREATED)
async def create_dossier(
    body: ArchiveDossierCreate,
    request: Request,
    user: User = Depends(require_roles("administrateur", "comptable")),
    db: AsyncSession = Depends(get_db),
):
    try:
        dossier = await ArchiveService(db).create_dossier(
            annee=body.annee, libelle=body.libelle, user=user
        )
        await record_audit(
            db,
            user=user,
            action="create_archive_dossier",
            entity="archive_dossier",
            entity_id=str(dossier.id),
            after={"annee": dossier.annee, "libelle": dossier.libelle},
            request=request,
        )
        return _dossier_detail(dossier)
    except AppError as exc:
        raise_http_from_app(exc)


@router.post("/cloture", response_model=ArchiveClotureResponse, status_code=status.HTTP_201_CREATED)
async def cloturer_exercice(
    body: ArchiveClotureRequest,
    request: Request,
    user: User = Depends(require_roles("administrateur")),
    db: AsyncSession = Depends(get_db),
):
    """Clôture définitive N (archives). L'ouverture N+1 se fait via POST /exercices/ouvrir-suivant."""
    try:
        result = await ExerciceClotureService(db).cloturer(
            annee=body.annee, force=False, user=user
        )
        await record_audit(
            db,
            user=user,
            action="cloture_exercice",
            entity="archive_dossier",
            entity_id=str(result.dossier_id),
            after={
                "annee": result.annee,
                "natures_creees": result.natures_creees,
                "lignes": result.lignes,
                "ouvertures_seed": 0,
                "force": False,
            },
            request=request,
        )
        return ArchiveClotureResponse(
            annee=result.annee,
            natures_creees=result.natures_creees,
            lignes=result.lignes,
            ouvertures_seed=0,
            dossier_id=result.dossier_id,
            message=result.message,
            annee_ouverture=result.annee + 1,
        )
    except AppError as exc:
        raise_http_from_app(exc)


@router.get("/dossiers/{annee}", response_model=ArchiveDossierDetailRead)
async def get_dossier(
    annee: int,
    _: User = Depends(require_roles("administrateur", "comptable", "auditeur")),
    db: AsyncSession = Depends(get_db),
):
    try:
        dossier = await ArchiveService(db).get_dossier_by_annee(annee)
        return _dossier_detail(dossier)
    except AppError as exc:
        raise_http_from_app(exc)


@router.delete("/dossiers/{annee}", response_model=MessageResponse)
async def delete_dossier(
    annee: int,
    request: Request,
    user: User = Depends(require_roles("administrateur", "comptable")),
    db: AsyncSession = Depends(get_db),
):
    try:
        from app.services.exercice_guard import annee_est_cloturee

        if await annee_est_cloturee(db, annee):
            raise ValidationError(
                f"Le dossier {annee} est lié à une clôture définitive et ne peut pas être supprimé."
            )
        await ArchiveService(db).delete_dossier(annee)
        await record_audit(
            db,
            user=user,
            action="delete_archive_dossier",
            entity="archive_dossier",
            entity_id=str(annee),
            after={"annee": annee},
            request=request,
        )
        return MessageResponse(message=f"Dossier {annee} supprimé")
    except AppError as exc:
        raise_http_from_app(exc)


@router.post(
    "/dossiers/{annee}/fichiers",
    response_model=ArchiveFichierRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_fichier(
    annee: int,
    request: Request,
    file: UploadFile = File(...),
    nature_code: str | None = Form(None),
    user: User = Depends(require_roles("administrateur", "comptable")),
    db: AsyncSession = Depends(get_db),
):
    try:
        fichier = await ArchiveService(db).upload_fichier(
            annee=annee, file=file, nature_code=nature_code, user=user
        )
        await record_audit(
            db,
            user=user,
            action="upload_archive_fichier",
            entity="archive_fichier",
            entity_id=str(fichier.id),
            after={
                "annee": annee,
                "filename": fichier.filename,
                "kind": fichier.kind,
                "nature_code": fichier.nature_code,
                "parse_status": fichier.parse_status,
                "lines_count": fichier.lines_count,
            },
            request=request,
        )
        return _fichier_to_read(fichier)
    except AppError as exc:
        raise_http_from_app(exc)


@router.post("/dossiers/{annee}/fichiers/{fichier_id}/rescan", response_model=ArchiveFichierRead)
async def rescan_fichier(
    annee: int,
    fichier_id: UUID,
    request: Request,
    user: User = Depends(require_roles("administrateur", "comptable")),
    db: AsyncSession = Depends(get_db),
):
    try:
        fichier = await ArchiveService(db).rescan(annee=annee, fichier_id=fichier_id)
        await record_audit(
            db,
            user=user,
            action="rescan_archive_fichier",
            entity="archive_fichier",
            entity_id=str(fichier.id),
            after={
                "parse_status": fichier.parse_status,
                "lines_count": fichier.lines_count,
                "parse_error": fichier.parse_error,
            },
            request=request,
        )
        return _fichier_to_read(fichier)
    except AppError as exc:
        raise_http_from_app(exc)


@router.get("/dossiers/{annee}/fichiers/{fichier_id}/download")
async def download_fichier(
    annee: int,
    fichier_id: UUID,
    _: User = Depends(require_roles("administrateur", "comptable", "auditeur")),
    db: AsyncSession = Depends(get_db),
):
    try:
        fichier = await ArchiveService(db).get_fichier(fichier_id)
        if fichier.dossier.annee != annee:
            raise NotFoundError("Fichier archive", str(fichier_id))
    except AppError as exc:
        raise_http_from_app(exc)

    path = LocalStorageService().absolute_path(fichier.stored_path)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fichier introuvable sur le serveur")
    return FileResponse(
        path,
        filename=fichier.filename,
        media_type=fichier.mime_type or "application/octet-stream",
    )


@router.delete("/dossiers/{annee}/fichiers/{fichier_id}", response_model=MessageResponse)
async def delete_fichier(
    annee: int,
    fichier_id: UUID,
    request: Request,
    user: User = Depends(require_roles("administrateur", "comptable")),
    db: AsyncSession = Depends(get_db),
):
    try:
        await ArchiveService(db).delete_fichier(annee=annee, fichier_id=fichier_id)
        await record_audit(
            db,
            user=user,
            action="delete_archive_fichier",
            entity="archive_fichier",
            entity_id=str(fichier_id),
            after={"annee": annee},
            request=request,
        )
        return MessageResponse(message="Fichier archive supprimé")
    except AppError as exc:
        raise_http_from_app(exc)


@router.get("/dossiers/{annee}/acquisitions", response_model=ArchiveAcquisitionsRead)
async def list_acquisitions(
    annee: int,
    nature_code: str | None = Query(None),
    q: str | None = Query(None),
    _: User = Depends(require_roles("administrateur", "comptable", "auditeur")),
    db: AsyncSession = Depends(get_db),
):
    try:
        groupes, totaux = await ArchiveService(db).acquisitions(
            annee=annee, nature_code=nature_code, q=q
        )
        return ArchiveAcquisitionsRead(
            annee=annee,
            groupes=[
                ArchiveNatureGroupeRead(
                    nature_code=g["nature_code"],
                    nature_label=g["nature_label"],
                    lignes=[_ligne_to_read(l) for l in g["lignes"]],
                    sections=[
                        ArchiveExerciceSectionRead(
                            annee=s["annee"],
                            label=s["label"],
                            ouverture=_totaux_read(s["ouverture"]) if s["ouverture"] else None,
                            lignes=[_ligne_to_read(l) for l in s["lignes"]],
                            totaux=_totaux_read(s["totaux"]),
                        )
                        for s in g.get("sections", [])
                    ],
                    totaux=_totaux_read(g["totaux"]),
                )
                for g in groupes
            ],
            totaux=_totaux_read(totaux),
        )
    except AppError as exc:
        raise_http_from_app(exc)
