"""Tests Document Service — ingest, OCR extract, permissions catalogue."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.data.plateforme_catalogue import FUNCTIONAL_PERMISSIONS, ROLE_PERMISSIONS, SEED_LOCKED_MODULE_CODES
from app.services.ocr_extract import extract_text_from_file


def test_archives_generales_in_catalogue():
    codes = {row[0] for row in FUNCTIONAL_PERMISSIONS}
    assert "archives.general.view" in codes
    assert "archives.general.download" in codes
    assert "archives.general.ocr.retry" in codes
    assert "archives-generales" in SEED_LOCKED_MODULE_CODES
    assert "archives.general.view" in ROLE_PERMISSIONS["archives-generales.lecteur"]
    assert "ged.write" in ROLE_PERMISSIONS["archives-generales.admin"]


def test_extract_text_from_txt(tmp_path: Path):
    f = tmp_path / "note.txt"
    f.write_text("Bon de commande climatisation agence Nouakchott", encoding="utf-8")
    text = extract_text_from_file(f)
    assert "climatisation" in text.lower()


def test_extract_text_missing_file(tmp_path: Path):
    with pytest.raises(RuntimeError, match="introuvable"):
        extract_text_from_file(tmp_path / "absent.pdf")


def test_enqueue_ocr_soft_fail():
    from app.services.document_ingest_service import enqueue_ocr
    from uuid import uuid4

    with patch("app.workers.tasks_ocr.ocr_document") as task:
        task.delay.side_effect = ConnectionError("broker down")
        enqueue_ocr(uuid4())  # ne doit pas lever


def test_document_out_hides_ocr_text_until_done():
    from types import SimpleNamespace
    from uuid import uuid4

    from app.schemas.documents import document_out

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
        version=1,
        agence_id=None,
        department_id=None,
        fournisseur_id=None,
        uploaded_by_id=None,
        ocr_status="pending",
        ocr_text="secret text",
        ocr_error=None,
        ocr_attempts=0,
        security_level="internal",
    )
    out = document_out(row, include_ocr_text=True)
    assert out.ocr_text is None
    row.ocr_status = "done"
    out2 = document_out(row, include_ocr_text=True)
    assert out2.ocr_text == "secret text"


def test_ingest_requires_file():
    import asyncio

    from app.core.exceptions import ValidationError
    from app.services.document_ingest_service import DocumentIngestService

    async def _run():
        svc = DocumentIngestService(MagicMock())
        with pytest.raises(ValidationError):
            await svc.ingest_document(
                espace_code="moyens-generaux",
                module_code="achats-appro",
                entity="manuel",
                entity_id="x",
                enqueue=False,
            )

    asyncio.run(_run())
