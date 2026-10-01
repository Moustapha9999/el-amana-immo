"""Tests Document Service — versions, catalogue permissions, reporting helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.data.plateforme_catalogue import FUNCTIONAL_PERMISSIONS, ROLE_PERMISSIONS
from app.schemas.documents import document_out


def test_ged_download_export_in_catalogue():
    codes = {row[0] for row in FUNCTIONAL_PERMISSIONS}
    assert "ged.download" in codes
    assert "ged.export" in codes
    assert "ged.download" in ROLE_PERMISSIONS["archives-mg.admin"]
    assert "ged.export" in ROLE_PERMISSIONS["archives-generales.admin"]


def test_document_out_includes_version_fields():
    row = SimpleNamespace(
        id=uuid4(),
        filename="a.pdf",
        title="A",
        description=None,
        doc_type="FACTURE",
        reference="R1",
        module_code="achats-appro",
        espace_code="moyens-generaux",
        entity="bon_commande",
        entity_id="1",
        date_document=None,
        archived_at=None,
        created_at=None,
        mime_type="application/pdf",
        size_bytes=10,
        version=2,
        parent_document_id=uuid4(),
        version_comment="Correction scan",
        agence_id=None,
        department_id=None,
        fournisseur_id=None,
        uploaded_by_id=None,
        deleted_at=None,
        delete_reason=None,
        ocr_status="done",
        ocr_text="texte",
        ocr_error=None,
        ocr_attempts=1,
        security_level="internal",
    )
    out = document_out(row, include_ocr_text=True)
    assert out.version == 2
    assert out.version_comment == "Correction scan"
    assert out.parent_document_id is not None
    assert out.ocr_text == "texte"


def test_create_version_requires_file():
    import asyncio

    from app.core.exceptions import ValidationError
    from app.services.document_ingest_service import DocumentIngestService

    async def _run():
        from unittest.mock import AsyncMock

        db = MagicMock()
        db.scalar = AsyncMock(return_value=1)
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        svc = DocumentIngestService(db)
        parent = SimpleNamespace(
            id=uuid4(),
            parent_document_id=None,
            espace_code="moyens-generaux",
            module_code="achats-appro",
            entity="bon_commande",
            entity_id="1",
            title="BC",
            description=None,
            doc_type="BC",
            reference="BC-1",
            date_document=None,
            agence_id=None,
            department_id=None,
            fournisseur_id=None,
            security_level="internal",
            filename="bc.pdf",
            mime_type="application/pdf",
        )
        svc.ged.get = AsyncMock(return_value=parent)
        svc._resolve_root = AsyncMock(return_value=parent)
        with pytest.raises(ValidationError, match="Fichier requis"):
            await svc.create_version(parent_id=parent.id, enqueue=False, notify=False)

    asyncio.run(_run())


def test_dashboard_empty_shape():
    from app.services.document_query_service import DocumentQueryService

    empty = DocumentQueryService._empty_dashboard()
    assert empty["total"] == 0
    assert empty["ocr_done"] == 0
    assert empty["par_mois"] == []
    assert empty["activite"] == []


def test_reporting_csv_headers_shape(tmp_path: Path):
    """Smoke : service reporting construit bien un CSV (sans DB)."""
    import asyncio

    from app.services.document_reporting_service import DocumentReportingService

    async def _run():
        db = MagicMock()
        svc = DocumentReportingService(db)
        with patch.object(svc, "query") as query:
            from unittest.mock import AsyncMock

            query.search = AsyncMock(return_value=([], 0, {}))
            user = SimpleNamespace(id=uuid4(), is_superuser=True)
            content, media, filename = await svc.export(user=user, fmt="csv", general=True)
            assert filename.endswith(".csv")
            assert "text/csv" in media
            assert b"R" in content or b"ference" in content or b"Titre" in content

    asyncio.run(_run())
