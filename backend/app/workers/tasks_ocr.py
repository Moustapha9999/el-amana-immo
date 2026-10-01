"""Celery — pipeline OCR asynchrone sur ged_documents."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import text

from app.core.config import get_settings
from app.db.sync_session import sync_session
from app.models.audit import AuditLog, Notification
from app.models.enums import TypeNotification
from app.models.ged import GedDocument
from app.services.ocr_extract import extract_text_from_file
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _absolute_ged_path(stored_path: str) -> Path:
    raw = (stored_path or "").replace("\\", "/").lstrip("/")
    if not raw or ".." in Path(raw).parts:
        raise RuntimeError("Chemin de fichier invalide")
    root = Path(get_settings().ged_dir).resolve()
    candidate = (root / raw).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise RuntimeError("Chemin de fichier hors zone GED") from exc
    return candidate


def _audit_sync(
    session,
    *,
    action: str,
    document_id: str,
    after: dict | None = None,
    espace_code: str | None = None,
    module_code: str | None = None,
) -> None:
    session.add(
        AuditLog(
            user_id=None,
            action=action,
            entity="ged_document",
            entity_id=document_id,
            before_data=None,
            after_data=after,
            ip_address=None,
            espace_code=espace_code,
            module_code=module_code or "documents",
            session_id=None,
        )
    )


def _notify_uploader(
    session,
    *,
    user_id: UUID | None,
    titre: str,
    message: str,
    document_id: str,
    espace_code: str | None,
    module_code: str | None,
    event_type: str,
    priorite: str = "info",
) -> None:
    if user_id is None:
        return
    year = datetime.now(timezone.utc).year
    notif = Notification(
        user_id=user_id,
        type_notification=TypeNotification.SYSTEME,
        titre=titre,
        message=message,
        entity="ged_document",
        entity_id=document_id,
        espace_code=espace_code,
        module_code=module_code,
        lu=False,
        categorie="ged",
        priorite=priorite,
        event_type=event_type,
        emetteur_type="systeme",
        emetteur_label="GED OCR",
        destinataire_type="utilisateur",
        archived=False,
    )
    session.add(notif)
    session.flush()
    if not notif.event_code:
        notif.event_code = f"EVT-{year}-{str(notif.id).replace('-', '')[:8].upper()}"


@celery_app.task(
    name="app.workers.tasks.ocr_document",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    autoretry_for=(OSError, RuntimeError),
    retry_backoff=True,
)
def ocr_document(self, document_id: str) -> dict:
    doc_uuid = UUID(str(document_id))
    with sync_session() as session:
        row = session.get(GedDocument, doc_uuid)
        if row is None or row.deleted_at is not None:
            return {"ok": False, "reason": "not_found"}

        row.ocr_status = "processing"
        row.ocr_attempts = int(row.ocr_attempts or 0) + 1
        row.ocr_error = None
        _audit_sync(
            session,
            action="ocr_processing",
            document_id=str(row.id),
            after={"attempt": row.ocr_attempts},
            espace_code=row.espace_code,
            module_code=row.module_code,
        )
        session.commit()

        try:
            path = _absolute_ged_path(row.stored_path)
            extracted = extract_text_from_file(path)

            row.ocr_text = extracted or None
            row.ocr_status = "done"
            row.ocr_error = None
            row.updated_at = datetime.now(timezone.utc)
            session.flush()
            session.execute(
                text(
                    "UPDATE ged_documents SET ocr_text_search = "
                    "to_tsvector('french', coalesce(ocr_text, '')) "
                    "WHERE id = CAST(:id AS uuid)"
                ),
                {"id": str(row.id)},
            )
            _audit_sync(
                session,
                action="ocr_done",
                document_id=str(row.id),
                after={"chars": len(extracted or "")},
                espace_code=row.espace_code,
                module_code=row.module_code,
            )
            _notify_uploader(
                session,
                user_id=row.uploaded_by_id,
                titre="OCR terminé",
                message=f"L'analyse OCR de «{row.title or row.filename}» est terminée.",
                document_id=str(row.id),
                espace_code=row.espace_code,
                module_code=row.module_code,
                event_type="ocr_done",
            )
            session.commit()
            return {"ok": True, "chars": len(extracted or "")}
        except Exception as exc:
            logger.exception("OCR failed for %s", document_id)
            session.rollback()
            row = session.get(GedDocument, doc_uuid)
            if row is None:
                return {"ok": False, "reason": "not_found"}
            # Retry auto pour erreurs techniques transitoires
            if self.request.retries < self.max_retries and isinstance(
                exc, (OSError, RuntimeError)
            ):
                row.ocr_status = "pending"
                row.ocr_error = str(exc)[:2000]
                _audit_sync(
                    session,
                    action="ocr_retry_auto",
                    document_id=str(row.id),
                    after={"attempt": row.ocr_attempts, "error": row.ocr_error},
                    espace_code=row.espace_code,
                    module_code=row.module_code,
                )
                session.commit()
                raise self.retry(exc=exc)

            row.ocr_status = "failed"
            row.ocr_error = str(exc)[:2000]
            row.updated_at = datetime.now(timezone.utc)
            _audit_sync(
                session,
                action="ocr_failed",
                document_id=str(row.id),
                after={"error": row.ocr_error},
                espace_code=row.espace_code,
                module_code=row.module_code,
            )
            _notify_uploader(
                session,
                user_id=row.uploaded_by_id,
                titre="OCR échoué",
                message=(
                    f"L'analyse OCR de «{row.title or row.filename}» a échoué. "
                    "Vous pouvez relancer le traitement."
                ),
                document_id=str(row.id),
                espace_code=row.espace_code,
                module_code=row.module_code,
                event_type="ocr_failed",
                priorite="avertissement",
            )
            session.commit()
            return {"ok": False, "error": str(exc)}
