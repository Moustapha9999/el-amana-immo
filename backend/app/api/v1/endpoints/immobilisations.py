from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.api.v1.endpoints.helpers import to_paginated
from app.core.exceptions import AppError, raise_http_from_app
from app.db.session import get_db
from app.models import CategorieImmobilisation, Immobilisation, InventaireScan, PieceJointe, User
from app.repositories.base import BaseRepository
from app.schemas.common import MessageResponse, PaginatedResponse
from app.schemas.immobilisation import (
    CategorieCreate,
    CategorieRead,
    CategorieUpdate,
    ImmobilisationCreate,
    ImmobilisationRead,
    ImmobilisationUpdate,
    InventaireScanCreate,
    InventaireScanRead,
    PieceJointeRead,
    QrCodeResponse,
)
from app.schemas.operations import AjustementRead, SituationComptableRead, TransfertCreate
from app.services.categorie_service import CategorieService
from app.services.immobilisation_service import ImmobilisationService
from app.services.amortissement_service import AmortissementService
from app.services.immobilisation_vnc import compute_situation_comptable
from app.schemas.auth import ImmobilisationImportResponse
from app.services.inventaire_service import InventaireService
from app.services.immobilisation_import import ImmobilisationImportService
from app.services.audit_helpers import record_audit
from app.storage.local_storage import LocalStorageService

router = APIRouter(tags=["immobilisations"])


def _scan_to_read(row: InventaireScan) -> InventaireScanRead:
    immo = row.immobilisation
    return InventaireScanRead(
        id=row.id,
        immobilisation_id=row.immobilisation_id,
        code_scanne=row.code_scanne,
        valide=row.valide,
        localisation=row.localisation,
        created_at=row.created_at,
        code_inventaire=immo.code_inventaire if immo else None,
        designation=immo.designation if immo else None,
    )


@router.get("/categories", response_model=PaginatedResponse[CategorieRead])
async def list_categories(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await BaseRepository(db, CategorieImmobilisation).list(page, size, search, ("famille", "code"))
    return to_paginated(items, total, page, size, CategorieRead.model_validate)


@router.post("/categories", response_model=CategorieRead, status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: CategorieCreate,
    request: Request,
    user: User = Depends(require_roles("administrateur")),
    db: AsyncSession = Depends(get_db),
):
    from app.services.categorie_audit import categorie_audit_snapshot

    row = await CategorieService(db).create(payload)
    await record_audit(
        db,
        user=user,
        action="create",
        entity="categorie_immobilisation",
        entity_id=str(row.id),
        request=request,
        after=categorie_audit_snapshot(row),
    )
    return row


@router.get("/categories/{categorie_id}", response_model=CategorieRead)
async def get_category(
    categorie_id: UUID,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(CategorieImmobilisation, categorie_id)
    if row is None or row.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Type d'immobilisation introuvable")
    return row


@router.patch("/categories/{categorie_id}", response_model=CategorieRead)
async def update_category(
    categorie_id: UUID,
    payload: CategorieUpdate,
    request: Request,
    user: User = Depends(require_roles("administrateur")),
    db: AsyncSession = Depends(get_db),
):
    from app.services.categorie_audit import categorie_audit_snapshot

    try:
        existing = await db.get(CategorieImmobilisation, categorie_id)
        if existing is None or existing.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Type d'immobilisation introuvable")
        before = categorie_audit_snapshot(existing)
        row = await CategorieService(db).update(categorie_id, payload)
        await record_audit(
            db,
            user=user,
            action="update",
            entity="categorie_immobilisation",
            entity_id=str(row.id),
            request=request,
            before=before,
            after=categorie_audit_snapshot(row),
        )
        return row
    except AppError as exc:
        raise_http_from_app(exc)


@router.get("/immobilisations", response_model=PaginatedResponse[ImmobilisationRead])
async def list_immobilisations(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ImmobilisationService(db)
    items, total = await service.list(page, size, search)
    return to_paginated(items, total, page, size, ImmobilisationRead.model_validate)


@router.post("/immobilisations", response_model=ImmobilisationRead, status_code=status.HTTP_201_CREATED)
async def create_immobilisation(
    payload: ImmobilisationCreate,
    request: Request,
    user: User = Depends(require_roles("administrateur", "comptable")),
    db: AsyncSession = Depends(get_db),
):
    try:
        item = await ImmobilisationService(db).create(payload)
        await record_audit(
            db,
            user=user,
            action="create",
            entity="immobilisation",
            entity_id=str(item.id),
            request=request,
            after={"code_inventaire": item.code_inventaire, "statut": item.statut.value},
        )
        return item
    except AppError as exc:
        raise_http_from_app(exc)


@router.get("/immobilisations/{item_id}", response_model=ImmobilisationRead)
async def get_immobilisation(item_id: UUID, _: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        return await ImmobilisationService(db).get(item_id)
    except AppError as exc:
        raise_http_from_app(exc)


@router.patch("/immobilisations/{item_id}", response_model=ImmobilisationRead)
async def update_immobilisation(
    item_id: UUID,
    payload: ImmobilisationUpdate,
    request: Request,
    user: User = Depends(require_roles("administrateur", "comptable")),
    db: AsyncSession = Depends(get_db),
):
    try:
        item = await ImmobilisationService(db).update(item_id, payload)
        await record_audit(
            db,
            user=user,
            action="update",
            entity="immobilisation",
            entity_id=str(item.id),
            request=request,
            after={"code_inventaire": item.code_inventaire, "statut": item.statut.value},
        )
        return item
    except AppError as exc:
        raise_http_from_app(exc)


@router.get("/immobilisations/{item_id}/situation-comptable", response_model=SituationComptableRead)
async def get_situation_comptable(item_id: UUID, _: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        immo, cumul, vnc = await compute_situation_comptable(db, item_id)
        return SituationComptableRead(
            immobilisation_id=immo.id,
            valeur_brute=immo.valeur_brute,
            cumul_amortissement=cumul,
            vnc=vnc,
        )
    except AppError as exc:
        raise_http_from_app(exc)


@router.post("/immobilisations/{item_id}/mettre-en-service", response_model=ImmobilisationRead)
async def mettre_en_service_immobilisation(
    item_id: UUID,
    request: Request,
    user: User = Depends(require_roles("administrateur", "comptable")),
    db: AsyncSession = Depends(get_db),
):
    try:
        await AmortissementService(db).mettre_en_service(item_id)
        item = await ImmobilisationService(db).get(item_id)
        await record_audit(
            db,
            user=user,
            action="mettre_en_service",
            entity="immobilisation",
            entity_id=str(item_id),
            request=request,
            after={"statut": item.statut.value},
        )
        return item
    except AppError as exc:
        raise_http_from_app(exc)


@router.post("/immobilisations/{item_id}/transfert", response_model=AjustementRead, status_code=status.HTTP_201_CREATED)
async def transfert_immobilisation(
    item_id: UUID,
    payload: TransfertCreate,
    request: Request,
    user: User = Depends(require_roles("administrateur", "comptable")),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await TransfertService(db).transfer(item_id, payload)
        await record_audit(
            db,
            user=user,
            action="transfert_agence",
            entity="immobilisation",
            entity_id=str(item_id),
            request=request,
            after={"agence_id": str(payload.agence_id)},
        )
        return row
    except AppError as exc:
        raise_http_from_app(exc)


@router.delete("/immobilisations/{item_id}", response_model=MessageResponse)
async def delete_immobilisation(
    item_id: UUID,
    request: Request,
    user: User = Depends(require_roles("administrateur", "comptable")),
    db: AsyncSession = Depends(get_db),
):
    try:
        await ImmobilisationService(db).soft_delete(item_id)
        await record_audit(
            db,
            user=user,
            action="delete",
            entity="immobilisation",
            entity_id=str(item_id),
            request=request,
        )
        return MessageResponse(message="Suppression logique effectuée")
    except AppError as exc:
        raise_http_from_app(exc)


@router.post("/immobilisations/{item_id}/pieces", response_model=PieceJointeRead, status_code=status.HTTP_201_CREATED)
async def upload_piece(
    item_id: UUID,
    file: UploadFile = File(...),
    is_photo: bool = False,
    _: User = Depends(require_roles("administrateur", "comptable")),
    db: AsyncSession = Depends(get_db),
):
    await ImmobilisationService(db).get(item_id)
    storage = LocalStorageService()
    relative, size = await storage.save(file, subdir=f"immobilisations/{item_id}")
    row = PieceJointe(
        immobilisation_id=item_id,
        filename=file.filename or "fichier",
        stored_path=relative,
        mime_type=file.content_type,
        size_bytes=size,
        is_photo=is_photo,
    )
    db.add(row)
    await db.flush()
    return row


@router.post("/immobilisations/import", response_model=ImmobilisationImportResponse)
async def import_immobilisations(
    file: UploadFile = File(...),
    user: User = Depends(require_roles("administrateur", "comptable")),
    db: AsyncSession = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Fichier Excel (.xlsx) requis")
    content = await file.read()
    try:
        created, errors = await ImmobilisationImportService(db).import_from_xlsx(content)
    except AppError as exc:
        raise_http_from_app(exc)
    return ImmobilisationImportResponse(created=created, errors=errors)


@router.post("/inventaire/scans", response_model=InventaireScanRead, status_code=status.HTTP_201_CREATED)
async def create_scan(
    payload: InventaireScanCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await InventaireService(db).create_scan(
        code_scanne=payload.code_scanne,
        localisation=payload.localisation,
        scanned_by_id=user.id,
    )
    await record_audit(
        db,
        user=user,
        action="scan_inventaire",
        entity="inventaire_scan",
        entity_id=str(row.id),
        request=request,
        after={"code_scanne": row.code_scanne, "valide": row.valide},
    )
    if not row.valide:
        from app.models.enums import TypeNotification
        from app.services.notification_service import NotificationService

        await NotificationService(db).notify_staff(
            role_codes={"administrateur", "comptable", "auditeur"},
            type_notification=TypeNotification.INVENTAIRE,
            titre="Scan inventaire invalide",
            message=f"Code scanné inconnu : {row.code_scanne}",
            entity="inventaire_scan",
            entity_id=str(row.id),
        )
    return _scan_to_read(row)


@router.get("/inventaire/scans", response_model=PaginatedResponse[InventaireScanRead])
async def list_scans(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await InventaireService(db).list_scans(page, size)
    return to_paginated(items, total, page, size, _scan_to_read)


@router.get("/immobilisations/{item_id}/qr-code", response_model=QrCodeResponse)
async def get_immobilisation_qr(
    item_id: UUID,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        payload, image_base64 = await InventaireService(db).qr_code_for_immobilisation(item_id)
        return QrCodeResponse(payload=payload, image_base64=image_base64)
    except AppError as exc:
        raise_http_from_app(exc)
