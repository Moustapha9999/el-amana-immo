from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.api.v1.endpoints.helpers import to_paginated
from app.core.exceptions import AppError, raise_http_from_app
from app.db.session import get_db
from app.models import CategorieImmobilisation, InventaireScan, PieceJointe, User
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
    NextCodeInventaireResponse,
    PieceJointeRead,
    QrCodeResponse,
)
from app.schemas.operations import AjustementRead, SituationComptableRead, TransfertCreate
from app.services.categorie_service import CategorieService
from app.services.immobilisation_service import ImmobilisationService
from app.services.amortissement_service import AmortissementService
from app.services.immobilisation_vnc import compute_situation_comptable
from app.schemas.auth import BankImmoImportResponse, BankImmoPurgeResponse, ImmobilisationImportResponse
from app.services.inventaire_service import InventaireService
from app.services.immobilisation_import import ImmobilisationImportService
from app.services.bank_immo_import import BankImmoImportService
from app.services.audit_helpers import record_audit
from app.services.pieces_comptables_service import PiecesComptablesService, TYPE_LABELS
from app.services.transfert_service import TransfertService
from app.storage.local_storage import LocalStorageService

router = APIRouter(tags=["immobilisations"])


def _piece_to_read(row: PieceJointe) -> PieceJointeRead:
    immo = row.immobilisation
    return PieceJointeRead(
        id=row.id,
        immobilisation_id=row.immobilisation_id,
        filename=row.filename,
        mime_type=row.mime_type,
        size_bytes=row.size_bytes,
        is_photo=row.is_photo,
        type_piece=row.type_piece.value if hasattr(row.type_piece, "value") else str(row.type_piece),
        date_journee=row.date_journee,
        reference=row.reference,
        libelle=row.libelle,
        montant=row.montant,
        created_at=row.created_at,
        code_inventaire=immo.code_inventaire if immo else None,
        designation=immo.designation if immo else None,
    )


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
    _: User = Depends(require_permission("immobilisations.read")),
    db: AsyncSession = Depends(get_db),
):
    from pydantic import ValidationError

    items, total = await BaseRepository(db, CategorieImmobilisation).list(page, size, search, ("famille", "code"))

    # Une catégorie legacy invalide (ex. compte_immobilisation NULL) ne doit pas
    # faire échouer toute la liste Nature IMMO du formulaire.
    mapped: list[CategorieRead] = []
    for row in items:
        try:
            mapped.append(CategorieRead.model_validate(row))
        except ValidationError:
            continue
    return PaginatedResponse(items=mapped, total=total, page=page, size=size)


@router.post("/categories", response_model=CategorieRead, status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: CategorieCreate,
    request: Request,
    user: User = Depends(require_permission("immobilisations.admin")),
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
    _: User = Depends(require_permission("immobilisations.read")),
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
    user: User = Depends(require_permission("immobilisations.admin")),
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


@router.get("/immobilisations/next-code", response_model=NextCodeInventaireResponse)
async def next_code_inventaire(
    categorie_id: UUID = Query(..., description="Nature IMMO"),
    annee: int = Query(..., ge=2000, le=2100, description="Année du N° (souvent année d'acquisition)"),
    _: User = Depends(require_permission("immobilisations.read")),
    db: AsyncSession = Depends(get_db),
):
    """Prochain N° immobilisation pour une nature : ``AAI-2026-001``, ``Log-2026-001``, …"""
    from app.services.code_inventaire import next_code_for_categorie_id, parse_code_inventaire

    try:
        code = await next_code_for_categorie_id(db, categorie_id, annee)
        parsed = parse_code_inventaire(code)
        prefix = parsed[0] if parsed else ""
        return NextCodeInventaireResponse(code_inventaire=code, prefix=prefix, annee=annee)
    except AppError as exc:
        raise_http_from_app(exc)


@router.get("/immobilisations", response_model=PaginatedResponse[ImmobilisationRead])
async def list_immobilisations(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    amortissable: bool | None = Query(None),
    statuts: str | None = Query(None, description="Statuts séparés par des virgules"),
    famille: str | None = Query(None, description="Filtre sur le type / famille de catégorie"),
    _: User = Depends(require_permission("immobilisations.read")),
    db: AsyncSession = Depends(get_db),
):
    from app.models.enums import StatutImmobilisation

    statut_list: list[StatutImmobilisation] | None = None
    if statuts:
        try:
            statut_list = [
                StatutImmobilisation(s.strip()) for s in statuts.split(",") if s.strip()
            ]
        except ValueError:
            raise HTTPException(status_code=400, detail="Statut invalide dans le paramètre 'statuts'.")

    service = ImmobilisationService(db)
    items, total = await service.list(
        page,
        size,
        search,
        amortissable=amortissable,
        statuts=statut_list,
        famille=famille,
    )
    return to_paginated(items, total, page, size, ImmobilisationRead.model_validate)


@router.post("/immobilisations", response_model=ImmobilisationRead, status_code=status.HTTP_201_CREATED)
async def create_immobilisation(
    payload: ImmobilisationCreate,
    request: Request,
    user: User = Depends(require_permission("immobilisations.create")),
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
async def get_immobilisation(item_id: UUID, _: User = Depends(require_permission("immobilisations.read")), db: AsyncSession = Depends(get_db)):
    try:
        return await ImmobilisationService(db).get(item_id)
    except AppError as exc:
        raise_http_from_app(exc)


@router.patch("/immobilisations/{item_id}", response_model=ImmobilisationRead)
async def update_immobilisation(
    item_id: UUID,
    payload: ImmobilisationUpdate,
    request: Request,
    user: User = Depends(require_permission("immobilisations.update")),
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
async def get_situation_comptable(item_id: UUID, _: User = Depends(require_permission("immobilisations.read")), db: AsyncSession = Depends(get_db)):
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
    user: User = Depends(require_permission("immobilisations.validate")),
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
    user: User = Depends(require_permission("immobilisations.update")),
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
    user: User = Depends(require_permission("immobilisations.delete")),
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
        return MessageResponse(message="Immobilisation supprimée de la base")
    except AppError as exc:
        raise_http_from_app(exc)


@router.post("/immobilisations/{item_id}/pieces", response_model=PieceJointeRead, status_code=status.HTTP_201_CREATED)
async def upload_piece(
    item_id: UUID,
    request: Request,
    file: UploadFile = File(...),
    type_piece: str = Form("facture"),
    date_journee: date | None = Form(None),
    reference: str | None = Form(None),
    libelle: str | None = Form(None),
    montant: str | None = Form(None),
    is_photo: bool = Form(False),
    user: User = Depends(require_permission("immobilisations.update")),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await PiecesComptablesService(db).upload(
            immobilisation_id=item_id,
            file=file,
            type_piece=type_piece,
            date_journee=date_journee,
            reference=reference,
            libelle=libelle,
            montant=montant,
            user=user,
            is_photo=is_photo,
        )
        await record_audit(
            db,
            user=user,
            action="upload_piece_comptable",
            entity="piece_jointe",
            entity_id=str(row.id),
            after={
                "immobilisation_id": str(item_id),
                "type_piece": row.type_piece.value,
                "date_journee": row.date_journee.isoformat(),
                "filename": row.filename,
            },
            request=request,
        )
        row = await PiecesComptablesService(db).get(row.id)
        return _piece_to_read(row)
    except AppError as exc:
        raise_http_from_app(exc)


@router.get("/immobilisations/{item_id}/pieces", response_model=list[PieceJointeRead])
async def list_pieces(
    item_id: UUID,
    _: User = Depends(require_permission("immobilisations.read")),
    db: AsyncSession = Depends(get_db),
):
    try:
        rows = await PiecesComptablesService(db).list_for_immobilisation(item_id)
        return [_piece_to_read(r) for r in rows]
    except AppError as exc:
        raise_http_from_app(exc)


@router.get("/pieces/{piece_id}/download")
async def download_piece(
    piece_id: UUID,
    _: User = Depends(require_permission("immobilisations.read")),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await PiecesComptablesService(db).get(piece_id)
    except AppError as exc:
        raise_http_from_app(exc)
    path = LocalStorageService().absolute_path(row.stored_path)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fichier introuvable sur le serveur")
    return FileResponse(
        path,
        media_type=row.mime_type or "application/octet-stream",
        filename=row.filename,
    )


@router.delete("/pieces/{piece_id}", response_model=MessageResponse)
async def delete_piece(
    piece_id: UUID,
    request: Request,
    user: User = Depends(require_permission("immobilisations.update")),
    db: AsyncSession = Depends(get_db),
):
    try:
        svc = PiecesComptablesService(db)
        row = await svc.get(piece_id)
        await record_audit(
            db,
            user=user,
            action="delete_piece_comptable",
            entity="piece_jointe",
            entity_id=str(piece_id),
            before={"filename": row.filename, "immobilisation_id": str(row.immobilisation_id)},
            request=request,
        )
        await svc.delete(piece_id)
        return MessageResponse(message="Pièce supprimée")
    except AppError as exc:
        raise_http_from_app(exc)


@router.get("/archives/pieces-comptables", response_model=PaginatedResponse[PieceJointeRead])
async def archive_pieces_comptables(
    date_journee: date | None = Query(None),
    type_piece: str | None = Query(None),
    immobilisation_id: UUID | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    _: User = Depends(require_permission("immobilisations.read")),
    db: AsyncSession = Depends(get_db),
):
    try:
        rows, total = await PiecesComptablesService(db).archive(
            date_journee=date_journee,
            type_piece=type_piece,
            immobilisation_id=immobilisation_id,
            search=search,
            page=page,
            size=size,
        )
        return to_paginated(rows, total, page, size, _piece_to_read)
    except AppError as exc:
        raise_http_from_app(exc)


@router.get("/archives/pieces-comptables/types")
async def list_types_pieces(
    _: User = Depends(require_permission("immobilisations.read")),
):
    return [{"value": t.value, "label": TYPE_LABELS[t]} for t in TYPE_LABELS]


@router.post("/immobilisations/import", response_model=ImmobilisationImportResponse)
async def import_immobilisations(
    file: UploadFile = File(...),
    user: User = Depends(require_permission("immobilisations.create")),
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


@router.post("/immobilisations/import-banque", response_model=BankImmoImportResponse)
async def import_immobilisations_banque(
    file: UploadFile = File(...),
    user: User = Depends(require_permission("immobilisations.create")),
    db: AsyncSession = Depends(get_db),
):
    """Import du tableau d'amortissement banque (classeur multi-feuilles IMMO)."""
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fichier Excel banque (.xls / .xlsx) requis",
        )
    content = await file.read()
    try:
        result = await BankImmoImportService(db).import_from_bytes(content, file.filename)
    except AppError as exc:
        raise_http_from_app(exc)
    await record_audit(
        db,
        user=user,
        action="import_banque_immobilisations",
        entity="immobilisation",
        entity_id=None,
        after={
            "filename": file.filename,
            "created": result.created,
            "amortissements_created": result.amortissements_created,
            "errors": len(result.errors),
        },
    )
    return BankImmoImportResponse(
        created=result.created,
        amortissements_created=result.amortissements_created,
        errors=result.errors,
        totaux_par_compte=result.totaux_par_compte,
        reports_created=result.reports_created,
        negatives=result.negatives,
    )


@router.get("/immobilisations/import-banque/count")
async def count_import_banque(
    user: User = Depends(require_permission("immobilisations.read")),
    db: AsyncSession = Depends(get_db),
):
    """Nombre de biens encore présents issus de l'import tableau banque."""
    n = await BankImmoImportService(db).count_import_banque()
    return {"count": n}


@router.post("/immobilisations/import-banque/purge", response_model=BankImmoPurgeResponse)
async def purge_import_banque(
    user: User = Depends(require_permission("immobilisations.admin")),
    db: AsyncSession = Depends(get_db),
):
    """Annule l'import banque : supprime tous les biens marqués import_banque."""
    try:
        deleted = await BankImmoImportService(db).purge_import_banque()
    except AppError as exc:
        raise_http_from_app(exc)
    await record_audit(
        db,
        user=user,
        action="purge_import_banque_immobilisations",
        entity="immobilisation",
        entity_id=None,
        after={"deleted": deleted},
    )
    if deleted == 0:
        msg = "Aucun bien issu de l'import banque à supprimer."
    else:
        msg = f"{deleted} immobilisation(s) de l'import banque supprimée(s)."
    return BankImmoPurgeResponse(deleted=deleted, message=msg)


@router.post("/inventaire/scans", response_model=InventaireScanRead, status_code=status.HTTP_201_CREATED)
async def create_scan(
    payload: InventaireScanCreate,
    request: Request,
    user: User = Depends(require_permission("immobilisations.update")),
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
            espace_code="comptabilite",
            module_code="immobilisations",
        )
    return _scan_to_read(row)


@router.get("/inventaire/scans", response_model=PaginatedResponse[InventaireScanRead])
async def list_scans(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _: User = Depends(require_permission("immobilisations.read")),
    db: AsyncSession = Depends(get_db),
):
    items, total = await InventaireService(db).list_scans(page, size)
    return to_paginated(items, total, page, size, _scan_to_read)


@router.get("/immobilisations/{item_id}/qr-code", response_model=QrCodeResponse)
async def get_immobilisation_qr(
    item_id: UUID,
    _: User = Depends(require_permission("immobilisations.read")),
    db: AsyncSession = Depends(get_db),
):
    try:
        payload, image_base64 = await InventaireService(db).qr_code_for_immobilisation(item_id)
        return QrCodeResponse(payload=payload, image_base64=image_base64)
    except AppError as exc:
        raise_http_from_app(exc)
