"""Service Archivage — dossiers année, upload Excel/PDF, scan lecture seule."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError, ValidationError
from app.data.el_amana_referentiel import NATURE_IMMO_CODES_OFFICIELS, TYPES_IMMOBILISATION_EL_AMANA
from app.models import ArchiveDossier, ArchiveFichier, ArchiveLigne, User
from app.services.archive_pdf_parse import parse_bank_pdf
from app.services.bank_immo_import import ParsedBankRow, parse_bank_workbook
from app.storage.local_storage import LocalStorageService

KIND_EXCEL = "excel_banque"
KIND_PDF = "pdf_banque"
EXCEL_EXTS = {".xls", ".xlsx"}
PDF_EXTS = {".pdf"}

NATURE_LABELS: dict[str, str] = {
    t["code"]: str(t.get("famille") or t["code"]) for t in TYPES_IMMOBILISATION_EL_AMANA
}


def nature_label(code: str) -> str:
    return NATURE_LABELS.get(code, code)


def detect_kind(filename: str, content_type: str | None = None) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext in EXCEL_EXTS:
        return KIND_EXCEL
    if ext in PDF_EXTS:
        return KIND_PDF
    mime = (content_type or "").lower()
    if "spreadsheet" in mime or "excel" in mime or mime in {
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }:
        return KIND_EXCEL
    if mime == "application/pdf":
        return KIND_PDF
    raise ValidationError("Formats acceptés : .xls, .xlsx, .pdf")


def validate_nature_code(code: str | None, *, required: bool) -> str | None:
    if code is None or not str(code).strip():
        if required:
            raise ValidationError("nature_code obligatoire (choisir la nature du sous-dossier)")
        return None
    c = str(code).strip()
    if c not in NATURE_IMMO_CODES_OFFICIELS:
        raise ValidationError(
            f"nature_code invalide. Valeurs : {', '.join(NATURE_IMMO_CODES_OFFICIELS)}"
        )
    return c


class ArchiveService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.storage = LocalStorageService()

    async def list_dossiers(self) -> list[ArchiveDossier]:
        result = await self.db.execute(
            select(ArchiveDossier)
            .options(selectinload(ArchiveDossier.fichiers).selectinload(ArchiveFichier.lignes))
            .order_by(ArchiveDossier.annee.desc())
        )
        return list(result.scalars().unique().all())

    async def get_dossier_by_annee(self, annee: int) -> ArchiveDossier:
        result = await self.db.execute(
            select(ArchiveDossier)
            .where(ArchiveDossier.annee == annee)
            .options(selectinload(ArchiveDossier.fichiers).selectinload(ArchiveFichier.lignes))
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise NotFoundError("Dossier archive", str(annee))
        await self._backfill_nature_codes(row)
        return row

    async def _backfill_nature_codes(self, dossier: ArchiveDossier) -> None:
        """Rattache les anciens fichiers sans nature à la catégorie dominante des lignes."""
        from collections import Counter

        dirty = False
        for f in dossier.fichiers or []:
            if f.nature_code or not f.lignes:
                continue
            counts = Counter(l.categorie_code for l in f.lignes if l.categorie_code)
            if not counts:
                continue
            f.nature_code = counts.most_common(1)[0][0]
            dirty = True
        if dirty:
            await self.db.flush()

    async def create_dossier(
        self, *, annee: int, libelle: str | None, user: User | None
    ) -> ArchiveDossier:
        if annee < 1990 or annee > 2100:
            raise ValidationError("Année invalide")
        existing = await self.db.execute(select(ArchiveDossier).where(ArchiveDossier.annee == annee))
        if existing.scalar_one_or_none() is not None:
            raise ValidationError(f"Un dossier archive existe déjà pour {annee}")
        dossier = ArchiveDossier(
            annee=annee,
            libelle=(libelle or "").strip() or f"Dossier {annee}",
            created_by_id=user.id if user else None,
        )
        self.db.add(dossier)
        await self.db.flush()
        await self.db.refresh(dossier)
        return await self.get_dossier_by_annee(annee)

    async def delete_dossier(self, annee: int) -> None:
        """Supprime le dossier année + fichiers stockés + lignes (cascade DB)."""
        dossier = await self.get_dossier_by_annee(annee)
        paths = [
            self.storage.absolute_path(f.stored_path)
            for f in (dossier.fichiers or [])
            if f.stored_path
        ]
        await self.db.delete(dossier)
        await self.db.flush()
        for path in paths:
            if path.exists():
                path.unlink(missing_ok=True)
        # Nettoie le répertoire année s'il est vide
        year_dir = self.storage.root / f"archives/{annee}"
        if year_dir.is_dir() and not any(year_dir.iterdir()):
            year_dir.rmdir()

    async def upload_fichier(
        self,
        *,
        annee: int,
        file: UploadFile,
        nature_code: str | None,
        user: User | None,
    ) -> ArchiveFichier:
        dossier = await self.get_dossier_by_annee(annee)
        filename = file.filename or "fichier"
        kind = detect_kind(filename, file.content_type)
        # Nature obligatoire (1 nature = 1 sous-dossier : AAI 2007, Logiciel 2007…)
        nature = validate_nature_code(nature_code, required=True)

        relative, size = await self.storage.save(file, subdir=f"archives/{annee}")
        fichier = ArchiveFichier(
            dossier_id=dossier.id,
            kind=kind,
            filename=filename,
            stored_path=relative,
            mime_type=file.content_type,
            size_bytes=size,
            nature_code=nature,
            uploaded_by_id=user.id if user else None,
            parse_status="pending",
            lines_count=0,
        )
        self.db.add(fichier)
        await self.db.flush()
        await self._scan_fichier(fichier)
        await self.db.refresh(fichier)
        return await self.get_fichier(fichier.id)

    async def get_fichier(self, fichier_id: UUID) -> ArchiveFichier:
        result = await self.db.execute(
            select(ArchiveFichier)
            .where(ArchiveFichier.id == fichier_id)
            .options(selectinload(ArchiveFichier.lignes), selectinload(ArchiveFichier.dossier))
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise NotFoundError("Fichier archive", str(fichier_id))
        return row

    async def rescan(self, *, annee: int, fichier_id: UUID) -> ArchiveFichier:
        fichier = await self.get_fichier(fichier_id)
        if fichier.dossier.annee != annee:
            raise NotFoundError("Fichier archive", str(fichier_id))
        await self._scan_fichier(fichier)
        return await self.get_fichier(fichier_id)

    async def delete_fichier(self, *, annee: int, fichier_id: UUID) -> None:
        fichier = await self.get_fichier(fichier_id)
        if fichier.dossier.annee != annee:
            raise NotFoundError("Fichier archive", str(fichier_id))
        path = self.storage.absolute_path(fichier.stored_path)
        await self.db.delete(fichier)
        await self.db.flush()
        if path.exists():
            path.unlink(missing_ok=True)

    async def _scan_fichier(self, fichier: ArchiveFichier) -> None:
        path = self.storage.absolute_path(fichier.stored_path)
        if not path.exists():
            fichier.parse_status = "error"
            fichier.parse_error = "Fichier introuvable sur le serveur"
            fichier.lines_count = 0
            return

        await self.db.execute(delete(ArchiveLigne).where(ArchiveLigne.fichier_id == fichier.id))
        await self.db.flush()

        content = path.read_bytes()
        try:
            if fichier.kind == KIND_EXCEL:
                parsed = parse_bank_workbook(content, filename=fichier.filename)
                if fichier.nature_code:
                    for r in parsed:
                        r.categorie_code = fichier.nature_code
                sheets = sorted({r.sheet for r in parsed if r.sheet})
                fichier.sheet_names = sheets or None
            else:
                if not fichier.nature_code:
                    raise ValidationError("nature_code obligatoire pour un PDF")
                parsed = parse_bank_pdf(
                    content, nature_code=fichier.nature_code, filename=fichier.filename
                )
                fichier.sheet_names = sorted({r.sheet for r in parsed if r.sheet}) or None

            for r in parsed:
                self.db.add(_row_to_ligne(fichier, r))
            fichier.lines_count = len(parsed)
            fichier.parse_status = "ok" if parsed else "error"
            fichier.parse_error = None if parsed else "Aucune ligne extraite"
        except ValidationError as exc:
            fichier.parse_status = "error"
            fichier.parse_error = exc.message
            fichier.lines_count = 0
        except Exception as exc:  # noqa: BLE001
            fichier.parse_status = "error"
            fichier.parse_error = str(exc)
            fichier.lines_count = 0
        await self.db.flush()

    async def acquisitions(
        self,
        *,
        annee: int,
        nature_code: str | None = None,
        q: str | None = None,
    ) -> tuple[list[dict], dict]:
        """Lignes du dossier année, y compris REPORT historique (stock d'ouverture)."""
        await self.get_dossier_by_annee(annee)
        # Toutes les lignes scannées du dossier (REPORT + acquisitions),
        # pas de filtre année d'acquisition : le REPORT 2003 doit rester
        # dans l'historique 2007 pour coller au tableau banque.
        stmt = (
            select(ArchiveLigne)
            .join(ArchiveFichier, ArchiveFichier.id == ArchiveLigne.fichier_id)
            .join(ArchiveDossier, ArchiveDossier.id == ArchiveFichier.dossier_id)
            .where(ArchiveDossier.annee == annee)
            .order_by(
                ArchiveLigne.categorie_code,
                ArchiveLigne.is_report.desc(),
                ArchiveLigne.date_acquisition.asc().nulls_last(),
                ArchiveLigne.row_number,
            )
        )
        if nature_code:
            code = validate_nature_code(nature_code, required=True)
            stmt = stmt.where(ArchiveLigne.categorie_code == code)
        if q and q.strip():
            like = f"%{q.strip()}%"
            stmt = stmt.where(ArchiveLigne.designation.ilike(like))

        result = await self.db.execute(stmt)
        lignes = list(result.scalars().all())

        by_nature: dict[str, list[ArchiveLigne]] = defaultdict(list)
        for ligne in lignes:
            by_nature[ligne.categorie_code].append(ligne)

        groupes = []
        grand = _empty_totaux()
        for code in sorted(by_nature.keys(), key=_nature_sort_key):
            items = by_nature[code]
            tot = _totaux(items)
            _add_totaux(grand, tot)
            groupes.append(
                {
                    "nature_code": code,
                    "nature_label": nature_label(code),
                    "lignes": items,
                    "totaux": tot,
                }
            )
        return groupes, grand


def _row_to_ligne(fichier: ArchiveFichier, r: ParsedBankRow) -> ArchiveLigne:
    return ArchiveLigne(
        fichier_id=fichier.id,
        categorie_code=r.categorie_code,
        feuille=r.sheet,
        row_number=r.row_number,
        date_acquisition=r.date_acquisition,
        quantite=r.quantite or 1,
        designation=r.designation or "",
        valeur_brute=r.valeur_brute or Decimal("0"),
        taux=r.taux,
        amt_n1=r.amt_n1 or Decimal("0"),
        dotation=r.dotation or Decimal("0"),
        amt_fin=r.amt_fin or Decimal("0"),
        vnc=r.vnc or Decimal("0"),
        agence_label=r.agence_label,
        is_report=bool(r.is_report),
        source_kind=fichier.kind,
        raw_json={
            "sheet": r.sheet,
            "is_negative": r.is_negative,
            "calc_dotation": r.calc_dotation,
        },
    )


def _empty_totaux() -> dict:
    return {
        "valeur_brute": Decimal("0.00"),
        "amt_n1": Decimal("0.00"),
        "dotation": Decimal("0.00"),
        "amt_fin": Decimal("0.00"),
        "vnc": Decimal("0.00"),
        "nb_lignes": 0,
    }


def _totaux(lignes: list[ArchiveLigne]) -> dict:
    t = _empty_totaux()
    for l in lignes:
        t["valeur_brute"] += l.valeur_brute or Decimal("0")
        t["amt_n1"] += l.amt_n1 or Decimal("0")
        t["dotation"] += l.dotation or Decimal("0")
        t["amt_fin"] += l.amt_fin or Decimal("0")
        t["vnc"] += l.vnc or Decimal("0")
        t["nb_lignes"] += 1
    return t


def _add_totaux(dst: dict, src: dict) -> None:
    for k in ("valeur_brute", "amt_n1", "dotation", "amt_fin", "vnc"):
        dst[k] += src[k]
    dst["nb_lignes"] += src["nb_lignes"]


def _nature_sort_key(code: str) -> tuple[int, str]:
    try:
        return (NATURE_IMMO_CODES_OFFICIELS.index(code), code)
    except ValueError:
        return (999, code)


def dossier_summary(dossier: ArchiveDossier) -> dict:
    fichiers = list(dossier.fichiers or [])
    natures: set[str] = set()
    nb_lignes = 0
    for f in fichiers:
        if f.nature_code:
            natures.add(f.nature_code)
        for l in f.lignes or []:
            natures.add(l.categorie_code)
            nb_lignes += 1
    return {
        "nb_fichiers": len(fichiers),
        "nb_lignes": nb_lignes,
        "natures": sorted(natures, key=_nature_sort_key),
    }
