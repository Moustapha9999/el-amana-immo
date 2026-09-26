"""Exports rapports documentaires (CSV / Excel / PDF)."""

from __future__ import annotations

import csv
import io
from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import User
from app.services.document_query_service import DocumentQueryService
from app.services.reporting_export import build_styled_pdf, build_styled_workbook


class DocumentReportingService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.query = DocumentQueryService(db)

    async def export(
        self,
        *,
        user: User,
        fmt: str = "csv",
        espace_code: str | None = None,
        module_code: str | None = None,
        doc_type: str | None = None,
        ocr_status: str | None = None,
        date_debut: date | None = None,
        date_fin: date | None = None,
        q: str | None = None,
        general: bool = False,
        report_key: str = "documents",
    ) -> tuple[bytes, str, str]:
        rows, _total, _meta = await self.query.search(
            user=user,
            espace_code=espace_code,
            module_code=module_code,
            doc_type=doc_type,
            ocr_status=ocr_status,
            date_debut=date_debut,
            date_fin=date_fin,
            q=q,
            page=1,
            size=200,
            general=general or espace_code is None,
        )
        headers = [
            "Référence",
            "Titre",
            "Fichier",
            "Département",
            "Module",
            "Type",
            "Entité",
            "OCR",
            "Date",
            "Version",
            "Sécurité",
        ]
        data_rows = [
            [
                r.reference or "",
                r.title or "",
                r.filename or "",
                r.espace_code or "",
                r.module_code or "",
                r.doc_type or "",
                f"{r.entity}/{r.entity_id}",
                r.ocr_status or "",
                str(r.date_document or (r.created_at.date() if r.created_at else "")),
                str(r.version or 1),
                r.security_level or "",
            ]
            for r in rows
        ]
        title = {
            "documents": "Registre documentaire",
            "ocr": "État OCR",
            "par_module": "Documents par module",
            "manquants": "Documents à vérifier",
        }.get(report_key, "Rapport documentaire")

        fmt = (fmt or "csv").lower().strip()
        if fmt in ("xlsx", "excel"):
            content = build_styled_workbook(
                sheet_title="Documents",
                report_title=title,
                headers=headers,
                rows=data_rows,
                subtitle=f"{len(data_rows)} ligne(s)",
            )
            return content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "documents.xlsx"
        if fmt == "pdf":
            content = build_styled_pdf(
                report_title=title,
                headers=headers,
                rows=data_rows,
                subtitle=f"{len(data_rows)} ligne(s)",
            )
            return content, "application/pdf", "documents.pdf"

        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=";")
        writer.writerow(headers)
        writer.writerows(data_rows)
        return buf.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8", "documents.csv"
