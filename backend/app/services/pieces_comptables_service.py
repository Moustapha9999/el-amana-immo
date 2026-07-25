"""Pièces comptables immobilisations — archivage par journée comptable."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError, ValidationError
from app.models import Immobilisation, PieceJointe, User
from app.models.enums import TypePieceComptable
from app.storage.local_storage import LocalStorageService

ALLOWED_MIME_PREFIXES = ("image/", "application/pdf")
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}

TYPE_LABELS = {
    TypePieceComptable.FACTURE: "Facture",
    TypePieceComptable.PV: "PV",
    TypePieceComptable.BON_COMMANDE: "Bon de commande",
    TypePieceComptable.BON_LIVRAISON: "Bon de livraison",
    TypePieceComptable.CONTRAT: "Contrat",
    TypePieceComptable.PROTOCOLE_ACCORD: "Protocole d'accord",
    TypePieceComptable.AUTRE: "Autre",
}


def parse_type_piece(value: str | None) -> TypePieceComptable:
    raw = (value or "facture").strip().lower()
    try:
        return TypePieceComptable(raw)
    except ValueError as exc:
        raise ValidationError(
            f"Type de pièce invalide. Valeurs : {', '.join(t.value for t in TypePieceComptable)}"
        ) from exc


class PiecesComptablesService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.storage = LocalStorageService()

    def _validate_file(self, file: UploadFile) -> None:
        name = (file.filename or "").lower()
        ext = "." + name.rsplit(".", 1)[-1] if "." in name else ""
        mime = (file.content_type or "").lower()
        ok_ext = ext in ALLOWED_EXTENSIONS
        ok_mime = any(mime.startswith(p) for p in ALLOWED_MIME_PREFIXES) if mime else False
        if not ok_ext and not ok_mime:
            raise ValidationError("Formats acceptés : PDF, PNG, JPG, WEBP, TIFF.")

    async def upload(
        self,
        *,
        immobilisation_id: UUID,
        file: UploadFile,
        type_piece: str | None,
        date_journee: date | None,
        reference: str | None,
        libelle: str | None,
        user: User | None,
        is_photo: bool = False,
    ) -> PieceJointe:
        immo = await self.db.get(Immobilisation, immobilisation_id)
        if immo is None or immo.deleted_at is not None:
            raise NotFoundError("Immobilisation", str(immobilisation_id))

        self._validate_file(file)
        tp = parse_type_piece(type_piece)
        journee = date_journee or immo.date_comptabilisation or immo.date_acquisition or date.today()

        relative, size = await self.storage.save(
            file,
            subdir=f"pieces/{journee.isoformat()}/{immobilisation_id}",
        )
        row = PieceJointe(
            immobilisation_id=immobilisation_id,
            filename=file.filename or "piece",
            stored_path=relative,
            mime_type=file.content_type,
            size_bytes=size,
            is_photo=is_photo or (file.content_type or "").startswith("image/"),
            type_piece=tp,
            date_journee=journee,
            reference=(reference or immo.numero_facture or "").strip() or None,
            libelle=(libelle or "").strip() or None,
            uploaded_by_id=user.id if user else None,
        )
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)
        return row

    async def list_for_immobilisation(self, immobilisation_id: UUID) -> list[PieceJointe]:
        immo = await self.db.get(Immobilisation, immobilisation_id)
        if immo is None or immo.deleted_at is not None:
            raise NotFoundError("Immobilisation", str(immobilisation_id))
        result = await self.db.execute(
            select(PieceJointe)
            .where(PieceJointe.immobilisation_id == immobilisation_id)
            .options(selectinload(PieceJointe.immobilisation))
            .order_by(PieceJointe.date_journee.desc(), PieceJointe.created_at.desc())
        )
        return list(result.scalars().all())

    async def get(self, piece_id: UUID) -> PieceJointe:
        result = await self.db.execute(
            select(PieceJointe)
            .where(PieceJointe.id == piece_id)
            .options(selectinload(PieceJointe.immobilisation))
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise NotFoundError("Pièce comptable", str(piece_id))
        return row

    async def delete(self, piece_id: UUID) -> None:
        row = await self.get(piece_id)
        path = self.storage.absolute_path(row.stored_path)
        await self.db.delete(row)
        await self.db.flush()
        if path.exists():
            path.unlink(missing_ok=True)

    async def archive(
        self,
        *,
        date_journee: date | None = None,
        type_piece: str | None = None,
        immobilisation_id: UUID | None = None,
        search: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[PieceJointe], int]:
        stmt = (
            select(PieceJointe)
            .join(Immobilisation, Immobilisation.id == PieceJointe.immobilisation_id)
            .where(Immobilisation.deleted_at.is_(None))
            .options(selectinload(PieceJointe.immobilisation))
        )
        count_stmt = (
            select(func.count())
            .select_from(PieceJointe)
            .join(Immobilisation, Immobilisation.id == PieceJointe.immobilisation_id)
            .where(Immobilisation.deleted_at.is_(None))
        )

        if date_journee is not None:
            stmt = stmt.where(PieceJointe.date_journee == date_journee)
            count_stmt = count_stmt.where(PieceJointe.date_journee == date_journee)
        if type_piece:
            tp = parse_type_piece(type_piece)
            stmt = stmt.where(PieceJointe.type_piece == tp)
            count_stmt = count_stmt.where(PieceJointe.type_piece == tp)
        if immobilisation_id is not None:
            stmt = stmt.where(PieceJointe.immobilisation_id == immobilisation_id)
            count_stmt = count_stmt.where(PieceJointe.immobilisation_id == immobilisation_id)
        if search:
            q = f"%{search.strip()}%"
            filt = (
                PieceJointe.filename.ilike(q)
                | PieceJointe.reference.ilike(q)
                | PieceJointe.libelle.ilike(q)
                | Immobilisation.code_inventaire.ilike(q)
                | Immobilisation.designation.ilike(q)
            )
            stmt = stmt.where(filt)
            count_stmt = count_stmt.where(filt)

        total = int((await self.db.execute(count_stmt)).scalar_one())
        result = await self.db.execute(
            stmt.order_by(PieceJointe.date_journee.desc(), PieceJointe.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return list(result.scalars().all()), total
