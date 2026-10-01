"""Celery — supervision CORE ADMIN : rétention et alerte sur pic d'erreurs serveur."""

from __future__ import annotations

import logging
import os

from sqlalchemy import text

from app.db.sync_session import sync_session
from app.models.audit import Notification
from app.models.enums import TypeNotification
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

RETENTION_DAYS = int(os.getenv("API_ERRORS_RETENTION_DAYS", "90"))
SPIKE_WINDOW_MIN = int(os.getenv("API_ERRORS_SPIKE_WINDOW_MIN", "15"))
SPIKE_THRESHOLD = int(os.getenv("API_ERRORS_SPIKE_THRESHOLD", "10"))
SPIKE_COOLDOWN_MIN = 60
SPIKE_EVENT = "api_error_spike"


@celery_app.task(name="app.workers.tasks_supervision.purge_api_error_events")
def purge_api_error_events() -> int:
    with sync_session() as session:
        result = session.execute(
            text("DELETE FROM api_error_events WHERE created_at < now() - make_interval(days => :days)"),
            {"days": RETENTION_DAYS},
        )
        session.commit()
        deleted = result.rowcount or 0
    logger.info("api_error_events purgés: %s (rétention %s j)", deleted, RETENTION_DAYS)
    return deleted


def _supervisors(session) -> list:
    rows = session.execute(
        text(
            """
            SELECT DISTINCT u.id FROM users u
            LEFT JOIN user_roles ur ON ur.user_id = u.id
            LEFT JOIN role_permissions rp ON rp.role_id = ur.role_id
            LEFT JOIN permissions p ON p.id = rp.permission_id
            WHERE u.is_active AND (u.is_superuser OR p.code = 'core.admin.audit')
            """
        )
    ).all()
    return [r[0] for r in rows]


@celery_app.task(name="app.workers.tasks_supervision.check_server_error_spike")
def check_server_error_spike() -> int:
    with sync_session() as session:
        count = session.execute(
            text(
                "SELECT count(*) FROM api_error_events "
                "WHERE status_code >= 500 AND created_at >= now() - make_interval(mins => :mins)"
            ),
            {"mins": SPIKE_WINDOW_MIN},
        ).scalar_one()
        if count < SPIKE_THRESHOLD:
            return 0
        recent = session.execute(
            text(
                "SELECT 1 FROM notifications WHERE event_type = :ev "
                "AND created_at >= now() - make_interval(mins => :mins) LIMIT 1"
            ),
            {"ev": SPIKE_EVENT, "mins": SPIKE_COOLDOWN_MIN},
        ).first()
        if recent:
            return 0
        recipients = _supervisors(session)
        for user_id in recipients:
            session.add(
                Notification(
                    user_id=user_id,
                    type_notification=TypeNotification.SYSTEME,
                    titre="Pic d’erreurs serveur",
                    message=(
                        f"{count} erreurs serveur (5xx) en {SPIKE_WINDOW_MIN} minutes. "
                        "Consultez CORE ADMIN › Supervision › Erreurs API."
                    ),
                    entity="api_error_events",
                    entity_id=None,
                    module_code="core",
                    lu=False,
                    categorie="systeme",
                    priorite="haute",
                    event_type=SPIKE_EVENT,
                    emetteur_type="systeme",
                    emetteur_label="Supervision BEA DIGITAL",
                    destinataire_type="utilisateur",
                    archived=False,
                )
            )
        session.commit()
    logger.warning("pic d'erreurs 5xx: %s en %s min, %s superviseur(s) notifié(s)", count, SPIKE_WINDOW_MIN, len(recipients))
    return len(recipients)
