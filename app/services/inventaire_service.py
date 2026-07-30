import base64
import io
from uuid import UUID

import qrcode
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError
from app.models import Immobilisation, InventaireScan


def normalize_scan_code(raw: str) -> str:
    code = raw.strip()
    if not code:
        return code
    upper = code.upper()
    if upper.startswith("IMMO:"):
        return code.split(":", 1)[1].strip()
    return code


async def find_immobilisation_by_scan(db: AsyncSession, code_scanne: str) -> Immobilisation | None:
    normalized = normalize_scan_code(code_scanne)
    clauses = [
        Immobilisation.code_inventaire == normalized,
        Immobilisation.barcode_data == code_scanne.strip(),
        Immobilisation.qr_code_data == code_scanne.strip(),
    ]
    if normalized:
        clauses.append(Immobilisation.code_inventaire == code_scanne.strip())
        clauses.append(Immobilisation.qr_code_data == f"IMMO:{normalized}")
    result = await db.execute(
        select(Immobilisation).where(
            Immobilisation.deleted_at.is_(None),
            or_(*clauses),
        )
    )
    return result.scalar_one_or_none()


def build_qr_png_base64(payload: str) -> str:
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


class InventaireService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_scan(
        self,
        *,
        code_scanne: str,
        localisation: str | None,
        scanned_by_id: UUID,
    ) -> InventaireScan:
        immo = await find_immobilisation_by_scan(self.db, code_scanne)
        row = InventaireScan(
            immobilisation_id=immo.id if immo else None,
            code_scanne=code_scanne.strip(),
            valide=immo is not None,
            localisation=localisation,
            scanned_by_id=scanned_by_id,
        )
        if immo is not None:
            row.immobilisation = immo
        self.db.add(row)
        await self.db.flush()
        return row

    async def list_scans(self, page: int, size: int) -> tuple[list[InventaireScan], int]:
        count = await self.db.execute(select(func.count()).select_from(InventaireScan))
        total = int(count.scalar_one())
        from app.core.pagination import page_offset

        result = await self.db.execute(
            select(InventaireScan)
            .options(selectinload(InventaireScan.immobilisation))
            .order_by(InventaireScan.created_at.desc())
            .offset(page_offset(page, size))
            .limit(size)
        )
        return list(result.scalars().all()), total

    async def qr_code_for_immobilisation(self, item_id: UUID) -> tuple[str, str]:
        immo = await self.db.get(Immobilisation, item_id)
        if immo is None or immo.deleted_at is not None:
            raise NotFoundError("Immobilisation", str(item_id))
        payload = immo.qr_code_data or f"IMMO:{immo.code_inventaire}"
        return payload, build_qr_png_base64(payload)
